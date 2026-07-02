/*
 * CNIPA evidence PDF automation template.
 *
 * Context:
 * - Run from a Codex Chrome browser-client / Node REPL session after selecting
 *   a logged-in CNIPA list tab as `tab`.
 * - Provide `fs` and `path` from Node imports if writing files directly:
 *     var fs = await import("node:fs/promises");
 *     var path = await import("node:path");
 *
 * This template deliberately contains no credentials. It uses the current
 * logged-in CNIPA page at runtime and never writes tokens/cookies to disk.
 */

const CNIPA_EVIDENCE_DEFAULTS = {
  listUrl: "https://cpquery.cponline.cnipa.gov.cn/chinesepatent/index",
  sections: ["申请信息", "费用信息", "发文信息", "专利权质押", "实施许可备案"],
  headerTemplate:
    '<div style="font-size:8px; width:100%; padding:0 10mm; color:#555; display:flex; justify-content:space-between;"><span class="date"></span><span class="title" style="max-width:65%; overflow:hidden; white-space:nowrap; text-overflow:ellipsis;"></span></div>',
  footerTemplate:
    '<div style="font-size:8px; width:100%; padding:0 10mm; color:#555; display:flex; justify-content:space-between;"><span class="url" style="max-width:82%; overflow:hidden; white-space:nowrap; text-overflow:ellipsis;"></span><span><span class="pageNumber"></span>/<span class="totalPages"></span></span></div>',
  printOptions: {
    landscape: false,
    printBackground: true,
    displayHeaderFooter: true,
    preferCSSPageSize: false,
    paperWidth: 8.27,
    paperHeight: 11.69,
    marginTop: 0.55,
    marginBottom: 0.55,
    marginLeft: 0.35,
    marginRight: 0.35,
  },
};

function cnipaSafeName(name) {
  return String(name).replace(/[\\/:*?"<>|]/g, "_").slice(0, 120);
}

async function cnipaWaitUntilBodyIncludes(tab, text, timeoutMs = 15000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const has = await tab.playwright.evaluate(
      (needle) => document.body.innerText.includes(needle),
      text
    );
    if (has) return true;
    await tab.playwright.waitForTimeout(300);
  }
  return false;
}

async function cnipaSearchApplicant(tab, keyword, listUrl = CNIPA_EVIDENCE_DEFAULTS.listUrl) {
  await tab.goto(listUrl);
  await tab.playwright
    .waitForLoadState({ state: "domcontentloaded", timeoutMs: 10000 })
    .catch(() => {});
  await tab.playwright.waitForTimeout(800);

  const reset = tab.playwright.getByRole("button", { name: "重置", exact: true });
  if ((await reset.count()) === 1) {
    await reset.click({ timeoutMs: 5000 });
    await tab.playwright.waitForTimeout(500);
  }

  const applicantInputs = tab.playwright
    .locator('input[placeholder="请输入"]')
    .filter({ visible: true });
  if ((await applicantInputs.count()) < 2) throw new Error("未找到申请人输入框");
  await applicantInputs.nth(1).fill(keyword, { timeoutMs: 5000 });

  const queryButton = tab.playwright.getByRole("button", { name: "查询", exact: true });
  await queryButton.click({ timeoutMs: 5000 });
  await tab.playwright
    .waitForLoadState({ state: "networkidle", timeoutMs: 15000 })
    .catch(() => {});
  await tab.playwright.waitForTimeout(1200);
}

async function cnipaCaptureDetailHref(tab, applicantKeyword, patentNo) {
  await cnipaSearchApplicant(tab, applicantKeyword);
  if (!(await cnipaWaitUntilBodyIncludes(tab, patentNo))) {
    throw new Error(`检索结果未出现专利号：${patentNo}`);
  }

  const cdp = await tab.capabilities.get("cdp");
  const res = await cdp.send(
    "Runtime.evaluate",
    {
      expression: `(() => {
        const patentNo = ${JSON.stringify(patentNo)};
        const vmEl = Array.from(document.querySelectorAll('*')).find(el =>
          el.__vue__ && typeof el.__vue__.routerPush === 'function' && Array.isArray(el.__vue__.dataList)
        );
        if (!vmEl) return { ok: false, reason: 'vm not found' };
        const vm = vmEl.__vue__;
        const rec = vm.dataList.find(r => r.zhuanlisqh === patentNo);
        if (!rec) return { ok: false, reason: 'record not found', count: vm.dataList.length };
        const oldOpen = window.open;
        let captured = null;
        window.open = (href, target) => { captured = { href, target }; return null; };
        try { vm.routerPush(rec); } finally { window.open = oldOpen; }
        return { ok: true, href: captured && captured.href, rec: { zhuanlisqh: rec.zhuanlisqh, zhuanlimc: rec.zhuanlimc, shenqingrxm: rec.shenqingrxm } };
      })()`,
      returnByValue: true,
    },
    { timeoutMs: 10000 }
  );

  if (!res.result.value.ok || !res.result.value.href) {
    throw new Error(`无法捕获详情页 URL：${JSON.stringify(res.result.value)}`);
  }
  return new URL(res.result.value.href, "https://cpquery.cponline.cnipa.gov.cn").href;
}

async function cnipaClickSection(tab, section) {
  const cdp = await tab.capabilities.get("cdp");
  const result = await cdp.send(
    "Runtime.evaluate",
    {
      expression: `(() => {
        const section = ${JSON.stringify(section)};
        const candidates = Array.from(document.querySelectorAll('[role="treeitem"], .q-tree__node, .q-tree__node-header, div, span'))
          .filter(el => (el.innerText || el.textContent || '').trim().includes(section));
        const el = candidates.find(el => el.getAttribute('role') === 'treeitem' && (el.innerText || '').includes(section)) || candidates[0];
        if (!el) return false;
        el.scrollIntoView({ block: 'center' });
        el.click();
        return true;
      })()`,
      awaitPromise: true,
      returnByValue: true,
    },
    { timeoutMs: 10000 }
  );
  await tab.playwright
    .waitForLoadState({ state: "networkidle", timeoutMs: 10000 })
    .catch(() => {});
  await tab.playwright.waitForTimeout(700);
  return Boolean(result.result.value);
}

async function cnipaCleanForPrint(tab) {
  const cdp = await tab.capabilities.get("cdp");
  await tab.cua.keypress({ keys: ["ESC"] }).catch(() => {});
  await cdp.send(
    "Runtime.evaluate",
    {
      expression: `(() => {
        window.getSelection()?.removeAllRanges();
        document.activeElement?.blur?.();
        const style = document.getElementById('codex-print-clean-style') || document.createElement('style');
        style.id = 'codex-print-clean-style';
        style.textContent = '@media print {.q-page-sticky,.q-drawer__opener,.q-drawer,.q-drawer__backdrop,.q-notifications__list{display:none!important}}';
        document.head.appendChild(style);
        return true;
      })()`,
      returnByValue: true,
    },
    { timeoutMs: 5000 }
  );
  return cdp;
}

async function cnipaPrintCurrentPanel(tab, outputPath, fs) {
  const cdp = await cnipaCleanForPrint(tab);
  const pdf = await cdp.send(
    "Page.printToPDF",
    {
      ...CNIPA_EVIDENCE_DEFAULTS.printOptions,
      headerTemplate: CNIPA_EVIDENCE_DEFAULTS.headerTemplate,
      footerTemplate: CNIPA_EVIDENCE_DEFAULTS.footerTemplate,
    },
    { timeoutMs: 30000 }
  );
  await fs.writeFile(outputPath, Buffer.from(pdf.data, "base64"));
  return (await fs.stat(outputPath)).size;
}

async function cnipaExportPatentEvidence(tab, fs, path, options) {
  const {
    companyName,
    applicantKeyword,
    patent,
    outputRoot,
    sections = CNIPA_EVIDENCE_DEFAULTS.sections,
  } = options;

  const caseDir = path.join(outputRoot, `${cnipaSafeName(companyName)}-${patent.applicationNo}`);
  await fs.mkdir(caseDir, { recursive: true });

  const detailUrl = await cnipaCaptureDetailHref(tab, applicantKeyword, patent.applicationNo);
  await tab.goto(detailUrl);
  await tab.playwright
    .waitForLoadState({ state: "domcontentloaded", timeoutMs: 15000 })
    .catch(() => {});
  await tab.playwright
    .waitForLoadState({ state: "networkidle", timeoutMs: 15000 })
    .catch(() => {});
  await tab.playwright.waitForTimeout(1600);

  const verified = await tab.playwright.evaluate(
    (no) => document.body.innerText.includes("国内案件信息详情") && document.body.innerText.includes(no),
    patent.applicationNo
  );
  if (!verified) throw new Error(`详情页校验失败：${patent.applicationNo}`);

  const sectionLogs = [];
  for (const section of sections) {
    const clicked = await cnipaClickSection(tab, section);
    const outputPath = path.join(caseDir, `中国及多国专利审查信息查询-${section}.pdf`);
    const bytes = await cnipaPrintCurrentPanel(tab, outputPath, fs);
    sectionLogs.push({ section, clicked, pdf: outputPath, bytes, url: await tab.url() });
  }

  return { patent, caseDir, detailUrl, sections: sectionLogs };
}
