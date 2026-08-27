#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""社媒与新闻搜索抓取（微博 / 微信公众号 / 百度资讯 / 小红书）。
微博/百度走 playwright + 系统 Chrome 无头; 微信走 miku_ai 搜索(搜狗微信数据, 异步接口经
专用 venv subprocess 调用; 全文读取按需由日报 agent 另调 wechat-article-for-ai, 见 SKILL.md);
小红书走 opencli CLI(桥接本机 Chrome 已登录会话)。
设计原则: 容错优先——单页失败/反爬拦截不中断, 如实记录到 errors; 解析做启发式初筛,
最终研判由日报 agent 完成(LLM 只做判断, 不负责反爬)。
用法: python3 fetch_social.py [--queries 投诉,处罚] [--platform weibo|weixin|baidu|xhs] [--full]
输出: outbox/social_items.json (candidates + errors)
      outbox/social_raw/{platform}_{short}_{i}.txt (页面原始文本, 供 agent 复核)
依赖: playwright(系统 Chrome, channel="chrome"), ~/.agent-reach/venvs/wechat-md(miku_ai),
      opencli(pipx, 仅小红书通道)。"""
import hashlib
import json
import random
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

BASE = Path(__file__).resolve().parent.parent
OUTBOX = BASE / "outbox"
RAW = OUTBOX / "social_raw"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

PLATFORMS = {
    "weibo": None,  # 特殊: 走 m.weibo.cn JSON API(桌面搜索页无登录态必触发反爬)
    "weixin": None,  # 特殊: 走 miku_ai 搜索(专用 venv subprocess), 已替换搜狗 playwright 通道
    "baidu": lambda q: f"https://www.baidu.com/s?rtt=4&tn=news&word={quote(q)}",
    "xhs": None,    # 特殊: 走 opencli xiaohongshu search(桥接 Chrome 登录会话)
}
# 小红书风控敏感: 每日只跑低频词组(基础名 + 投诉), 每次 sleep 更长
XHS_SUFFIXES_DEFAULT = ["", "投诉"]
# 微信 miku_ai 底层重试较多, 词组同样低频: 基础名 + 投诉 + IPO
WEIXIN_SUFFIXES_DEFAULT = ["", "投诉", "IPO"]
WEIXIN_VENV_PY = str(Path.home() / ".agent-reach" / "venvs" / "wechat-md" / "bin" / "python")
NEG_WORDS_FOR_FILTER = ["诉讼", "仲裁", "处罚", "立案", "调查", "被执行", "失信", "冻结", "查封",
                        "破产", "欠薪", "拖欠", "裁员", "维权", "投诉", "曝光", "举报", "质量",
                        "事故", "违约", "退货", "售后", "骗", "整改", "警示", "中止", "终止"]
UA_MOBILE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")
ANTIBOT_MARKS = ["antispider", "验证码", "安全验证", "异常", "访问验证"]
MAX_CAND_PER_QUERY = 15


def weixin_search_cli(q, top_n=10, timeout=90):
    """miku_ai 微信公众号文章搜索(异步接口, 经专用 venv subprocess 调用)。返回 rows 列表。
    注意: 微信结果 URL 带 timestamp+signature 有时效, 去重指纹须用标题哈希(见调用侧),
    全文读取用 SKILL.md 中的 wechat-article-for-ai 命令现搜现读。"""
    code = (
        "import asyncio, json\n"
        "from miku_ai import get_wexin_article\n"
        "r = asyncio.run(get_wexin_article(%r, top_num=%d))\n"
        "print(json.dumps(r, ensure_ascii=False, default=str))\n"
    ) % (q, top_n)
    r = subprocess.run([WEIXIN_VENV_PY, "-c", code],
                       capture_output=True, text=True, timeout=timeout)
    # stdout 可能混有底层重试日志行, 取最后一行可解析 JSON
    js = None
    for line in reversed((r.stdout or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            js = json.loads(line)
            break
    if js is None:
        raise RuntimeError(f"miku_ai no-json exit {r.returncode}: "
                           f"{(r.stderr or r.stdout).strip()[-160:]}")
    return js


def xhs_search_cli(q, limit=10, timeout=90):
    """opencli xiaohongshu search: 返回 (原始 JSON 数组, 摘要文本)。失败抛异常。"""
    r = subprocess.run(["opencli", "xiaohongshu", "search", q,
                        "--limit", str(limit), "-f", "json"],
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"opencli exit {r.returncode}: {(r.stderr or r.stdout).strip()[:160]}")
    data = json.loads(r.stdout.strip())
    summary_lines = [f"{d.get('published_at', '')} | {d.get('title', '')} | @{d.get('author', '')} "
                     f"| likes={d.get('likes', '')}" for d in data]
    return data, "\n".join(summary_lines)[:12000]


def xhs_make_candidate(row, name):
    """把小红书结果行转候选(仅当标题含主体标识时保留); source_id 由 dedup 按 URL 归一。"""
    title = f"{row.get('title', '').strip()} (@{row.get('author', '').strip()}, 赞{row.get('likes', '')})"
    neg = [w for w in NEG_WORDS_FOR_FILTER if w in row.get("title", "")]
    return {"platform": "xhs", "company": name, "title": title[:200],
            "negative_hint": neg[:4], "source": "xhs",
            "url": row.get("url", ""), "publish_time": row.get("published_at", "")}


def weibo_api_fetch(page, q):
    """m.weibo.cn 搜索 JSON API, 返回 (候选列表, 原始文本)。需先导航至 m.weibo.cn 建立同源。"""
    from urllib.parse import quote as _q
    if "m.weibo.cn" not in page.url:
        page.goto("https://m.weibo.cn/", timeout=25000, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
    url = ("https://m.weibo.cn/api/container/getIndex?containerid=100103type%3D1%26q%3D"
           + _q(q) + "&page_type=searchall")
    text = page.evaluate(
        """async (url) => {
            const r = await fetch(url, {headers: {'X-Requested-With': 'XMLHttpRequest',
                                       'Accept': 'application/json'}});
            return await r.text();
        }""", url)
    import json as _json
    data = _json.loads(text)
    if not data.get("ok"):
        raise RuntimeError(f"weibo api ok=0: {text[:120]}")
    lines = []
    for card in (data.get("data") or {}).get("cards") or []:
        mb = card.get("mblog") or {}
        if mb:
            t = re.sub(r"<[^>]+>", "", mb.get("text", ""))
            lines.append(f"{mb.get('created_at','')} @{(mb.get('user') or {}).get('screen_name','')}: {t}")
    return lines, "\n".join(lines)[:12000]


def load_targets():
    """读取监控主体: 优先命令行 --company 临时主体(一次性专项查询, 不入 targets.yaml),
    否则读 config/targets.yaml。"""
    if "--company" in sys.argv:
        name = sys.argv[sys.argv.index("--company") + 1]
        short = sys.argv[sys.argv.index("--short") + 1] if "--short" in sys.argv else name[:4]
        aliases = ([a.strip() for a in sys.argv[sys.argv.index("--alias") + 1].split(",")]
                   if "--alias" in sys.argv else [])
        return [(name, short, aliases)]
    text = (BASE / "config" / "targets.yaml").read_text(encoding="utf-8")
    try:
        import yaml
        data = yaml.safe_load(text)
        return [(c["name"], c.get("short") or c["name"][:4],
                 c.get("aliases") or []) for c in data.get("companies", [])]
    except Exception:
        pass
    targets, cur = [], None
    for line in text.splitlines():
        m = re.match(r"\s*-?\s*name:\s*(\S+)", line)
        if m:
            cur = {"name": m.group(1), "short": m.group(1)[:4], "aliases": []}
            targets.append(cur)
            continue
        if cur is None:
            continue
        m = re.match(r"\s*short:\s*(\S+)", line)
        if m:
            cur["short"] = m.group(1)
        m = re.match(r"\s*aliases:\s*\[(.*)\]", line)
        if m:
            cur["aliases"] = [a.strip() for a in m.group(1).split(",") if a.strip()]
    return [(t["name"], t["short"], t["aliases"]) for t in targets]


def parse_candidates(platform, text, name, short, aliases):
    """启发式初筛: 返回含公司标识的行, 负面词标记。最终判断交给 agent。"""
    keys = [k for k in ([name, short] + aliases) if k]
    neg_words = ["诉讼", "仲裁", "处罚", "立案", "调查", "被执行", "失信", "冻结", "查封",
                 "破产", "欠薪", "拖欠", "裁员", "维权", "投诉", "曝光", "举报", "质量",
                 "事故", "违约", "退货", "售后", "骗", "整改", "警示", "中止", "终止"]
    seen, cands = set(), []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if len(line) < 10 or len(line) > 220:
            continue
        if not any(k in line for k in keys):
            continue
        sig = line[:80]
        if sig in seen:
            continue
        seen.add(sig)
        neg = [w for w in neg_words if w in line]
        if not neg:
            continue  # 初筛只留负面相关行, 降噪
        cands.append({"platform": platform, "company": name, "title": line[:160],
                      "negative_hint": neg[:4], "source": platform})
        if len(cands) >= MAX_CAND_PER_QUERY:
            break
    return cands


def main():
    extra_queries = []
    if "--queries" in sys.argv:
        extra_queries = [q.strip() for q in sys.argv[sys.argv.index("--queries") + 1].split(",") if q.strip()]
    suffixes = extra_queries or ["", "IPO", "北交所", "投诉", "处罚"]
    targets = load_targets()
    RAW.mkdir(parents=True, exist_ok=True)
    errors, candidates = [], []
    only_platform = sys.argv[sys.argv.index("--platform") + 1] if "--platform" in sys.argv else None
    main_suffixes = suffixes
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(user_agent=UA_MOBILE, viewport={"width": 414, "height": 896},
                                  locale="zh-CN")
        page = ctx.new_page()
        for name, short, aliases in targets:
            xhs_suffixes = extra_queries if extra_queries else XHS_SUFFIXES_DEFAULT
            for suffix in (main_suffixes if only_platform not in ("xhs", "weixin") else []):
                q = f"{short} {suffix}".strip()
                for platform, url_fn in PLATFORMS.items():
                    if platform in ("xhs", "weixin"):
                        continue  # 两者走 CLI 通道, 主循环外统一处理, 避免与 playwright 会话互扰
                    if only_platform and platform != only_platform:
                        continue
                    tag = f"{platform}_{short}_{q.replace(short, '').strip() or 'plain'}"
                    try:
                        if platform == "weibo":
                            lines, body = weibo_api_fetch(page, q)
                            (RAW / f"{tag}.txt").write_text(body, encoding="utf-8")
                            # 微博量小且 IPO 质疑类话术常不含硬负面词, 只按公司名保留,
                            # 负面与否交 agent 研判
                            for ln in lines:
                                ln_c = ln.strip()
                                if len(ln_c) >= 10 and any(k in ln_c for k in [name, short] + aliases):
                                    candidates.append({"platform": platform, "company": name,
                                                       "title": ln_c[:160], "negative_hint": [],
                                                       "source": platform})
                        else:
                            page.goto(url_fn(q), timeout=25000, wait_until="domcontentloaded")
                            page.wait_for_timeout(random.randint(1200, 2500))
                            body = page.inner_text("body")[:12000]
                            if any(m in body for m in ANTIBOT_MARKS) and len(body) < 2000:
                                raise RuntimeError("触发反爬/验证码页面")
                            (RAW / f"{tag}.txt").write_text(body, encoding="utf-8")
                            candidates += parse_candidates(platform, body, name, short, aliases)
                    except Exception as e:
                        errors.append({"platform": platform, "company": short,
                                       "query": q, "error": str(e)[:200]})
                    time.sleep(random.uniform(1.5, 3.0))
            # 小红书通道(opencli CLI, 独立于 playwright; 低频: 每家仅跑 XHS_SUFFIXES)
            if not only_platform or only_platform == "xhs":
                keys = [k for k in ([name, short] + aliases) if k]
                for suffix in xhs_suffixes[:3]:
                    q = f"{short} {suffix}".strip()
                    tag = f"xhs_{short}_{suffix.strip() or 'plain'}"
                    try:
                        rows, body = xhs_search_cli(q)
                        (RAW / f"{tag}.txt").write_text(body, encoding="utf-8")
                        for row in rows:
                            title = row.get("title", "")
                            if any(k in title for k in keys):
                                cand = xhs_make_candidate(row, name)
                                # 基础名查询无负面词也保留(小红书为口碑集中地), 负面判定交研判;
                                # 组合词(投诉等)结果天然相关直接保留
                                candidates.append(cand)
                    except Exception as e:
                        errors.append({"platform": "xhs", "company": short,
                                       "query": q, "error": str(e)[:200]})
                    time.sleep(random.uniform(5.0, 9.0))  # 小红书风控敏感, 放慢节奏
            # 微信公众号通道(miku_ai 搜索; 低频词组; 全文读取按需由日报 agent 调
            # wechat-article-for-ai, 见 SKILL.md。结果 URL 带时效签名, 指纹用标题哈希)
            if not only_platform or only_platform == "weixin":
                keys = [k for k in ([name, short] + aliases) if k]
                wx_suffixes = extra_queries if extra_queries else WEIXIN_SUFFIXES_DEFAULT
                for suffix in wx_suffixes[:3]:
                    q = f"{short} {suffix}".strip()
                    tag = f"weixin_{short}_{suffix.strip() or 'plain'}"
                    try:
                        rows = weixin_search_cli(q)
                        (RAW / f"{tag}.txt").write_text(
                            "\n".join(f"{r.get('date', '')} | {r.get('title', '')} | "
                                      f"{r.get('source', '')} | {str(r.get('snippet', ''))[:80]}"
                                      for r in rows), encoding="utf-8")
                        for row in rows:
                            title = row.get("title", "")
                            if any(k in title for k in keys):
                                sid = "wx-" + hashlib.sha1(title.encode()).hexdigest()[:16]
                                neg = [w for w in NEG_WORDS_FOR_FILTER
                                       if w in title + str(row.get("snippet", ""))]
                                candidates.append({
                                    "platform": "weixin", "company": name, "source_id": sid,
                                    "title": f"{title} ({row.get('source', '')})"[:200],
                                    "negative_hint": neg[:4], "source": "weixin",
                                    "url": row.get("url", ""),
                                    "publish_time": str(row.get("date", ""))[:10]})
                    except Exception as e:
                        errors.append({"platform": "weixin", "company": short,
                                       "query": q, "error": str(e)[:200]})
                    time.sleep(random.uniform(2.0, 4.0))
        browser.close()
    OUTBOX.mkdir(parents=True, exist_ok=True)
    out = OUTBOX / "social_items.json"
    out.write_text(json.dumps(
        {"generated": time.strftime("%Y-%m-%d %H:%M:%S"),
         "queries": [f"{s} {x}".strip() for s in [t[1] for t in targets] for x in suffixes],
         "count": len(candidates), "candidates": candidates, "errors": errors},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK: 抓取完成 candidates={len(candidates)} errors={len(errors)} → {out}")
    for e in errors:
        print(f"  ERR {e['platform']} [{e['company']} {e['query']}]: {e['error'][:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
