#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""官方/权威公告通道（见微 MCP 额度受限时的降级通道, 亦可日常直接使用）。
子命令:
  announcements --days 4     东财新三板公告接口(轻量 JSON API, 零浏览器), 按代码取近 N 天公告
  neeq-web --days 4          股转系统官网 www.neeq.com.cn 信息披露(playwright, 东财异常时降级)
  bse-status                 北交所官网审核公示页抓取(尽力而为, 失败容错)
输出: outbox/official_items.json
依赖: playwright(系统 Chrome); announcements 子命令仅用标准库。"""
import json
import re
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

BASE = Path(__file__).resolve().parent.parent
OUTBOX = BASE / "outbox"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")


def load_targets():
    text = (BASE / "config" / "targets.yaml").read_text(encoding="utf-8")
    try:
        import yaml
        data = yaml.safe_load(text)
        return [(c["name"], c.get("short") or c["name"][:4], c.get("neeq_code", ""))
                for c in data.get("companies", [])]
    except Exception:
        pass
    targets, cur = [], None
    for line in text.splitlines():
        m = re.match(r"\s*-?\s*name:\s*(\S+)", line)
        if m:
            cur = {"name": m.group(1), "short": m.group(1)[:4], "code": ""}
            targets.append(cur)
            continue
        if cur is None:
            continue
        m = re.match(r"\s*short:\s*(\S+)", line)
        if m:
            cur["short"] = m.group(1)
        m = re.match(r'\s*neeq_code:\s*"?(\d+)"?', line)
        if m:
            cur["code"] = m.group(1)
    return [(t["name"], t["short"], t["code"]) for t in targets]


def fetch_json(url):
    req = Request(url, headers={"User-Agent": UA, "Referer": "https://xinsanban.eastmoney.com/"})
    with urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def cmd_announcements(days):
    items, errors = [], []
    for name, short, code in load_targets():
        if not code:
            errors.append({"channel": "eastmoney", "company": short, "error": "无新三板代码"})
            continue
        try:
            url = ("https://np-anotice-stock.eastmoney.com/api/security/ann"
                   f"?sr=-1&page_size=50&page_index=1&ann_list=A&client_source=web"
                   f"&stock_list={code}&f_node=0&s_node=0")
            data = fetch_json(url)
            for a in (data.get("data") or {}).get("list") or []:
                d = (a.get("notice_date") or "")[:10]
                if d and d >= time.strftime("%Y-%m-%d", time.localtime(time.time() - days * 86400)):
                    items.append({
                        "company": name, "source": "eastmoney-neeq", "event_type": "公告",
                        "source_id": f"{code}-{a.get('art_code', '')}",
                        "title": a.get("title", ""),
                        "url": f"https://xinsanban.eastmoney.com/Article/NoticeContent?id={a.get('art_code', '')}",
                        "publish_time": d})
        except Exception as e:
            errors.append({"channel": "eastmoney", "company": short, "error": str(e)[:200]})
        time.sleep(1)
    _write(items, errors, "eastmoney")
    return 0


def cmd_neeq_web(days):
    """股转官网信息披露降级通道: 抓挂牌公司公告检索页。"""
    from playwright.sync_api import sync_playwright
    items, errors = [], []
    cutoff = time.strftime("%Y-%m-%d", time.localtime(time.time() - days * 86400))
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(user_agent=UA, locale="zh-CN")
        page = ctx.new_page()
        for name, short, code in load_targets():
            if not code:
                continue
            try:
                page.goto(f"https://www.neeq.com.cn/disclosure/info.html?code={code}&companyName={short}",
                          timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)
                body = page.inner_text("body")[:15000]
                (OUTBOX / "social_raw").mkdir(parents=True, exist_ok=True)
                (OUTBOX / "social_raw" / f"neeq_{short}.txt").write_text(body, encoding="utf-8")
                for line in body.splitlines():
                    line = line.strip()
                    m = re.match(r"(\d{4}-\d{2}-\d{2})", line)
                    if m and m.group(1) >= cutoff and len(line) > 14:
                        items.append({"company": name, "source": "neeq-web", "event_type": "公告",
                                      "source_id": f"neeqweb-{code}-{m.group(1)}-{line[11:40]}",
                                      "title": line[11:150], "url": "", "publish_time": m.group(1)})
            except Exception as e:
                errors.append({"channel": "neeq-web", "company": short, "error": str(e)[:200]})
        browser.close()
    _write(items, errors, "neeq-web")
    return 0


def cmd_bse_status():
    """北交所官网审核公示(尽力而为; 失败时 agent 降级为见微/人工链接核验)。"""
    from playwright.sync_api import sync_playwright
    items, errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(user_agent=UA, locale="zh-CN")
        page = ctx.new_page()
        try:
            page.goto("https://www.bse.cn/audit_process.html", timeout=30000,
                      wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            body = page.inner_text("body")[:15000]
            (OUTBOX / "social_raw").mkdir(parents=True, exist_ok=True)
            (OUTBOX / "social_raw" / "bse_status.txt").write_text(body, encoding="utf-8")
            for name, short, _ in load_targets():
                hits = [ln.strip() for ln in body.splitlines() if short in ln or name in ln]
                if hits:
                    items.append({"company": name, "source": "bse-web", "event_type": "审核动态",
                                  "source_id": f"bse-{short}", "title": " / ".join(hits[:5])[:300],
                                  "url": "https://www.bse.cn/audit_process.html",
                                  "publish_time": time.strftime("%Y-%m-%d")})
        except Exception as e:
            errors.append({"channel": "bse-web", "error": str(e)[:200]})
        browser.close()
    _write(items, errors, "bse-web")
    return 0


def _write(items, errors, channel):
    OUTBOX.mkdir(parents=True, exist_ok=True)
    out = OUTBOX / "official_items.json"
    out.write_text(json.dumps(
        {"generated": time.strftime("%Y-%m-%d %H:%M:%S"), "channel": channel,
         "count": len(items), "items": items, "errors": errors},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK[{channel}]: items={len(items)} errors={len(errors)} → {out}")
    for e in errors:
        print(f"  ERR {e.get('channel')}: {str(e.get('error'))[:100]}")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "announcements":
        days = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 4
        sys.exit(cmd_announcements(days))
    elif sys.argv[1] == "neeq-web":
        days = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 4
        sys.exit(cmd_neeq_web(days))
    elif sys.argv[1] == "bse-status":
        sys.exit(cmd_bse_status())
    else:
        print(__doc__)
        sys.exit(2)
