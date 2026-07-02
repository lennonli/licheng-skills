import fs from "node:fs";
import path from "node:path";

const DEFAULT_CHROME_PLUGIN_ROOT =
  "/Users/licheng/.codex/plugins/cache/openai-bundled/chrome/26.623.81905";

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function jsString(value) {
  return JSON.stringify(String(value));
}

function sanitizePathPart(value) {
  return String(value).replace(/[\\/:*?"<>|]/g, "_").trim();
}

function parseCnDate(value) {
  const match = String(value || "").match(/(\d{4})年(\d{1,2})月(\d{1,2})日/);
  if (!match) {
    return value || "";
  }
  return `${match[1]}-${match[2].padStart(2, "0")}-${match[3].padStart(2, "0")}`;
}

async function ensureChrome(pluginRoot = DEFAULT_CHROME_PLUGIN_ROOT) {
  if (globalThis.agent?.browsers == null) {
    const { setupBrowserRuntime } = await import(
      `${pluginRoot}/scripts/browser-client.mjs`
    );
    await setupBrowserRuntime({ globals: globalThis });
  }
  globalThis.browser = await globalThis.agent.browsers.get("extension");
  await globalThis.browser.nameSession("🔎 商标底稿下载");
  return globalThis.browser;
}

async function getCdp(tab, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    const url = await tab.url().catch(() => "");
    if (!/^https?:\/\//.test(url || "")) {
      lastError = new Error("当前标签页尚未进入 HTTP(S) 页面，不能调用 Chrome CDP");
      await sleep(500);
      continue;
    }
    try {
      const cdp = await tab.capabilities.get("cdp");
      await cdp.send("Page.enable", {}, { timeoutMs: 30000 }).catch(() => {});
      return cdp;
    } catch (error) {
      lastError = error;
      if (!String(error?.message || error).includes("paused document response")) {
        throw error;
      }
      await sleep(800);
    }
  }
  throw lastError || new Error("无法取得 Chrome CDP 能力");
}

async function waitForHttpPage(tab, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const url = await tab.url().catch(() => "");
    if (/^https?:\/\//.test(url || "")) {
      return url;
    }
    await sleep(500);
  }
  throw new Error("标签页未能进入 HTTP(S) 页面");
}

async function sendCdp(cdp, method, params = {}, options = {}, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      return await cdp.send(method, params, options);
    } catch (error) {
      lastError = error;
      if (!String(error?.message || error).includes("paused document response")) {
        throw error;
      }
      await sleep(800);
    }
  }
  throw lastError || new Error(`Chrome CDP 调用超时：${method}`);
}

async function cdpJson(cdp, expression, timeoutMs = 30000) {
  const result = await sendCdp(
    cdp,
    "Runtime.evaluate",
    { expression, awaitPromise: true, returnByValue: true },
    { timeoutMs },
    timeoutMs,
  );
  const value = result.result?.value;
  return typeof value === "string" ? JSON.parse(value) : value;
}

async function claimCurrentListTab(browser, applicantName) {
  const openTabs = await browser.user.openTabs();
  const candidates = openTabs.filter(
    (tab) =>
      (tab.title || "").includes("商标检索结果") &&
      (tab.url || "").includes("wcjs.sbj.cnipa.gov.cn/list"),
  );

  for (const candidate of candidates) {
    const tab = await browser.user.claimTab(candidate);
    const cdp = await getCdp(tab);
    const state = await cdpJson(
      cdp,
      `JSON.stringify({
        title: document.title,
        url: location.href,
        text: document.body.innerText.slice(0, 4000),
        params: sessionStorage.getItem("params"),
        rows: Array.from(document.querySelectorAll("table tr")).slice(1).map(tr => {
          const cells = Array.from(tr.querySelectorAll("td")).map(td => td.innerText.trim());
          const img = tr.querySelector("img");
          return {
            sn: cells[0],
            regNum: cells[1],
            intCls: cells[2],
            appDate: cells[3],
            appNameCn: cells[5],
            smallImgUrl: img ? img.src : ""
          };
        }).filter(row => row.regNum && row.intCls)
      })`,
    );
    if (!applicantName || state.text.includes(applicantName)) {
      const params = JSON.parse(state.params || "{}");
      if (!params.dataList?.length) {
        params.qw = params.qw || 3;
        params.dataList = state.rows.map((row) => ({
          regNum: row.regNum,
          intCls: Number(row.intCls) || row.intCls,
          appDate: parseCnDate(row.appDate),
          appNameCn: row.appNameCn,
          smallImgUrl: row.smallImgUrl,
          imgUrl: row.smallImgUrl
            ? row.smallImgUrl.replace("/thumbnail/", "/image/")
            : "",
          similarity: null,
        }));
      }
      return { tab, cdp, params };
    }
  }

  throw new Error(
    `未找到当前 Chrome 中的 CNIPA 商标检索结果页${
      applicantName ? `：${applicantName}` : ""
    }`,
  );
}

async function claimWorkingDetailTab(browser, fallbackTab) {
  const openTabs = await browser.user.openTabs();
  const candidate = openTabs.find(
    (tab) =>
      (tab.title || "").includes("商标详细内容") &&
      (tab.url || "").includes("wcjs.sbj.cnipa.gov.cn/detail"),
  );
  if (candidate) {
    return browser.user.claimTab(candidate);
  }
  return fallbackTab;
}

async function openDetailByResultClick(browser, listTab, regNum) {
  const beforeTabs = await browser.user.openTabs();
  const beforeIds = new Set(beforeTabs.map((tab) => tab.id));
  const link = listTab.playwright.getByText(String(regNum), { exact: true });
  const count = await link.count();
  if (count !== 1) {
    throw new Error(`结果页未找到唯一申请号链接：${regNum}，匹配数：${count}`);
  }

  await link.click({ timeoutMs: 10000 });
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    const afterTabs = await browser.user.openTabs();
    const detailInfo = afterTabs.find(
      (tab) =>
        !beforeIds.has(tab.id) &&
        (tab.title || "").includes("商标详细内容") &&
        (tab.url || "").includes("wcjs.sbj.cnipa.gov.cn/detail"),
    );
    if (detailInfo) {
      return browser.user.claimTab(detailInfo);
    }
    await sleep(1000);
  }
  throw new Error(`点击申请号后未打开详情页：${regNum}`);
}

async function waitForDetail(tab, regNum, applicantName) {
  const deadline = Date.now() + 60000;
  while (Date.now() < deadline) {
    try {
      const cdp = await getCdp(tab, 60000);
      const state = await cdpJson(
        cdp,
        `JSON.stringify({
          title: document.title,
          url: location.href,
          text: document.body.innerText.slice(0, 6000)
        })`,
        60000,
      );
      if (
        state.text.includes(String(regNum)) &&
        (!applicantName || state.text.includes(applicantName))
      ) {
        return state;
      }
    } catch (error) {
      if (!String(error?.message || error).includes("paused document response")) {
        throw error;
      }
    }
    await sleep(1000);
  }
  throw new Error(`详情页加载超时：${regNum}`);
}

async function printPdf(tab, filePath) {
  const cdp = await getCdp(tab);
  const pdf = await sendCdp(
    cdp,
    "Page.printToPDF",
    {
      printBackground: true,
      displayHeaderFooter: true,
      preferCSSPageSize: true,
      marginTop: 0.65,
      marginBottom: 0.65,
      marginLeft: 0.3,
      marginRight: 0.3,
    },
    { timeoutMs: 30000 },
    30000,
  );
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, Buffer.from(pdf.data, "base64"));
  return fs.statSync(filePath).size;
}

async function openDetailInWorkingTab(tab, params, item) {
  const cdp = await getCdp(tab);
  const index = params.dataList.findIndex(
    (entry) => String(entry.regNum) === String(item.regNum),
  );
  const detailParams = {
    intCls: item.intCls,
    regNum: item.regNum,
    _index: Math.max(index, 0),
    _qw: params.qw || params.qw_ || 3,
    dataList: params.dataList,
  };
  const paramsJson = JSON.stringify(detailParams);
  await sendCdp(
    cdp,
    "Runtime.evaluate",
    {
      expression: `
        sessionStorage.setItem("params", ${jsString(paramsJson)});
        location.href = "/detail";
      `,
      returnByValue: true,
    },
    { timeoutMs: 30000 },
    60000,
  );
  await sleep(5000);
}

async function openProcessTab(tab) {
  const flowTab = tab.playwright.getByText("商标流程", { exact: true });
  const count = await flowTab.count();
  if (count < 1) {
    throw new Error("详情页未找到“商标流程”入口");
  }
  await flowTab.first().click({ timeoutMs: 10000 });
  await sleep(4000);
}

async function inspectProcessPage(tab) {
  const cdp = await getCdp(tab);
  return cdpJson(
    cdp,
    `JSON.stringify({
      text: document.body.innerText.slice(0, 6000),
      rows: Array.from(document.querySelectorAll("table tr"))
        .map(tr => Array.from(tr.querySelectorAll("td, th")).map(td => td.innerText.trim()))
    })`,
  );
}

export async function exportCnipaTrademarkPdfs(options = {}) {
  const {
    applicantName,
    trademarkNumbers,
    limit,
    outputRoot,
    pluginRoot = DEFAULT_CHROME_PLUGIN_ROOT,
    saveProcessEvenIfEmpty = true,
  } = options;

  const browser = await ensureChrome(pluginRoot);
  const { tab: listTab, params } = await claimCurrentListTab(
    browser,
    applicantName,
  );

  if (!params?.dataList?.length) {
    throw new Error("当前结果页 sessionStorage.params.dataList 为空");
  }

  const selected = params.dataList.filter((item) => {
    if (trademarkNumbers?.length) {
      return trademarkNumbers.map(String).includes(String(item.regNum));
    }
    return true;
  });
  const marks = selected.slice(0, trademarkNumbers?.length ? selected.length : limit || 2);
  if (!marks.length) {
    throw new Error("未在当前结果页找到目标商标号");
  }

  const root =
    outputRoot ||
    path.join("/Users/licheng/Downloads", sanitizePathPart(applicantName || "CNIPA商标底稿"));

  const results = [];
  for (const item of marks) {
    const regNum = String(item.regNum);
    const markDir = path.join(root, `商标-${sanitizePathPart(regNum)}`);
    fs.mkdirSync(markDir, { recursive: true });

    const detailTab = await openDetailByResultClick(browser, listTab, regNum);
    await waitForHttpPage(detailTab);
    const detailState = await waitForDetail(detailTab, regNum, applicantName);
    const detailFile = path.join(markDir, "商标详细内容-1.pdf");
    const detailBytes = await printPdf(detailTab, detailFile);

    await openProcessTab(detailTab);
    const processState = await inspectProcessPage(detailTab);
    const hasProcessHeader =
      processState.text.includes("业务名称") &&
      processState.text.includes("环节名称");
    const dataRows = processState.rows
      .filter((row) => row.length >= 5)
      .slice(1)
      .filter((row) => row.join("\t").includes(regNum));
    const hasForbidden =
      processState.text.includes("403") || processState.text.includes("Forbidden");
    const processFile = path.join(markDir, "商标详细内容-2.pdf");
    let processBytes = 0;
    let processWarning = "";

    if (hasProcessHeader && (dataRows.length || saveProcessEvenIfEmpty)) {
      processBytes = await printPdf(detailTab, processFile);
      if (!dataRows.length) {
        processWarning = "流程页仅显示表头，未取得流程行";
      }
    } else if (hasForbidden) {
      processWarning = "流程接口被官网风控拦截，未导出流程 PDF";
    } else {
      processWarning = "未识别到流程页有效内容，未导出流程 PDF";
    }

    results.push({
      regNum,
      intCls: item.intCls,
      detailFile,
      detailBytes,
      processFile: processBytes ? processFile : null,
      processBytes,
      processWarning,
      detailVerified:
        detailState.text.includes(regNum) &&
        (!applicantName || detailState.text.includes(applicantName)),
      processRows: dataRows.length,
    });

    await detailTab.close().catch(() => {});
  }

  await browser.tabs.finalize({
    keep: [{ tab: listTab, status: "handoff" }],
  });

  return { outputRoot: root, results };
}
