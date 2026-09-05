#!/usr/bin/env python3
"""IPO问询案例库本地统一检索——与 legal-knowledge MCP 检索同源等价。

数据源：GitHub 主仓 lennonli/ipo-inquiry-kb（monorepo，按年度子目录）。
知识库根目录解析顺序：环境变量 IPO_KB_ROOT → 常见克隆位置 → 默认 ~/ipo-inquiry-kb。
**首次运行时若本机没有知识库，会自动 git clone 到默认位置**（无需手动克隆）。

用法：
  kb_search.py list                                   # 列出各知识库及案例数（首次运行自动克隆知识库）
  kb_search.py search "关键词1 关键词2" [过滤参数]      # 统一检索（元数据+正文加权排序）
  kb_search.py meta   --tag 股权代持 --board 北交所    # 仅元数据筛选
  kb_search.py full   "关键词1 关键词2" [--kb ipo2023] # 仅正文全文（多关键词同文命中）
  kb_search.py read   ipo2023 cases/xxx.md             # 读案例原文
  kb_search.py update                                  # git pull 同步知识库最新内容

过滤参数（search/meta 共用）：--tag --board --lawyer --code --company --year --limit
"""
import argparse, json, os, subprocess, sys

KB_REPO_URL = "https://github.com/lennonli/ipo-inquiry-kb.git"


def _resolve_kb_root():
    """知识库根目录解析顺序：环境变量 IPO_KB_ROOT → 常见克隆位置 → 默认克隆目标。"""
    env = os.environ.get("IPO_KB_ROOT")
    if env:
        return os.path.expanduser(env)
    for cand in (
        "~/Documents/Macbook-pro项目/19-IPO问询案例知识库",
        "~/ipo-inquiry-kb",
    ):
        p = os.path.expanduser(cand)
        if os.path.isdir(os.path.join(p, "2026")):
            return p
    return os.path.expanduser("~/ipo-inquiry-kb")


KB_ROOT = _resolve_kb_root()
REPOS = {
    "ipo":     "2026",
    "ipo2023": "2023",
    "ipo2024": "2024",
    "ipo2025": "2025",
}


def kb_ready():
    return os.path.isdir(os.path.join(KB_ROOT, "2026"))


def ensure_kb():
    """首次运行自动克隆知识库；目录异常时给出明确指引。"""
    if kb_ready():
        return
    if os.path.isdir(KB_ROOT) and os.listdir(KB_ROOT):
        print(f"[初始化失败] {KB_ROOT} 已存在但不是有效的知识库目录（缺少 2026/ 子目录）。")
        print("  请清理该目录，或设置环境变量 IPO_KB_ROOT 指向知识库根目录后重试。")
        sys.exit(2)
    print(f"[首次运行] 本机尚未安装知识库，正在自动克隆到 {KB_ROOT} ……")
    print("  （仓库约百余 MB，视网络需数分钟，请耐心等待）")
    os.makedirs(KB_ROOT, exist_ok=True)
    r = subprocess.run(["git", "clone", KB_REPO_URL, KB_ROOT])
    if r.returncode != 0 or not kb_ready():
        print("[初始化失败] 自动克隆未完成。请检查：git 是否安装、能否访问 github.com。")
        print(f"  也可手动执行：git clone {KB_REPO_URL} {KB_ROOT}")
        sys.exit(2)
    print("[初始化完成] 知识库已就位，后续运行直接可用；定期运行 update 子命令同步更新。")


def load_index(kb):
    path = os.path.join(KB_ROOT, REPOS[kb], "scripts", "index.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def all_kbs():
    return list(REPOS)


def match_meta(entry, args):
    if args.tag and args.tag not in (entry.get("tags") or []):
        return False
    for field in ("board", "lawyer", "code"):
        val = getattr(args, field, None)
        if val and val not in (entry.get(field) or ""):
            return False
    if args.company and args.company not in (entry.get("company") or "") + (entry.get("short") or ""):
        return False
    if args.year and not (entry.get("listing_date") or "").startswith(args.year):
        return False
    return True


def read_case(kb, relpath):
    path = os.path.join(KB_ROOT, REPOS[kb], relpath)
    if not os.path.isfile(path):
        print(f"[未找到] {kb}/{relpath}")
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def snippets(text, keywords, width=110, max_snip=3):
    out, seen = [], set()
    for line in text.splitlines():
        low = line.lower()
        if any(k.lower() in low for k in keywords):
            core = line.strip()
            for k in keywords:
                i = core.lower().find(k.lower())
                if i >= 0:
                    s = max(0, i - 40)
                    frag = core[s:s + width]
                    if frag not in seen:
                        seen.add(frag)
                        out.append("    …" + frag + ("…" if s + width < len(core) else ""))
                    break
        if len(out) >= max_snip:
            break
    return out


def body_hit(path, keywords):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def cmd_list(_):
    for kb, d in REPOS.items():
        n = len(load_index(kb))
        print(f"{kb:8s} {d}  ({n}份)")


def cmd_search(args):
    keywords = args.query.split()
    results = []
    for kb in all_kbs():
        if args.kb and kb != args.kb:
            continue
        for e in load_index(kb):
            if not match_meta(e, args):
                continue
            score, snips = 0, []
            tag_hit = args.query in " ".join(e.get("tags") or []) or any(k in (e.get("tags") or []) for k in keywords)
            who_hit = any(k in (e.get("company") or "") or k == e.get("code") or k in (e.get("short") or "") for k in keywords)
            if tag_hit:
                score += 2
            if who_hit:
                score += 2
            text = body_hit(os.path.join(KB_ROOT, REPOS[kb], "cases", e["file"]), keywords)
            hits = sum(1 for k in keywords if k.lower() in text.lower())
            if hits:
                score += hits
                snips = snippets(text, keywords)
            if score:
                results.append((score, kb, e, snips))
    results.sort(key=lambda x: -x[0])
    for score, kb, e, snips in results[: args.limit]:
        print(f"[{kb}] {e['file']}  {e.get('short') or e.get('company')}（{e.get('code','')}·{e.get('board','')}·上市 {e.get('listing_date') or '未上市'}）相关度{score}")
        for s in snips:
            print(s)
    print(f"—— 共命中 {len(results)} 份，显示前 {min(args.limit, len(results))} 份 ——")


def cmd_meta(args):
    count = 0
    for kb in all_kbs():
        if args.kb and kb != args.kb:
            continue
        for e in load_index(kb):
            if match_meta(e, args):
                count += 1
                if count <= args.limit:
                    tags = ",".join(e.get("tags") or [])
                    print(f"[{kb}] {e['file']}  {e.get('short') or e.get('company')}（{e.get('code','')}·{e.get('board','')}·上市 {e.get('listing_date') or '未上市'}·{e.get('lawyer') or '律所未载'}）标签: {tags}")
    print(f"—— 共命中 {count} 份 ——")


def cmd_full(args):
    keywords = args.query.split()
    count = 0
    for kb in all_kbs():
        if args.kb and kb != args.kb:
            continue
        d = os.path.join(KB_ROOT, REPOS[kb], "cases")
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".md"):
                continue
            text = body_hit(os.path.join(d, fn), keywords)
            if all(k.lower() in text.lower() for k in keywords):
                count += 1
                if count <= args.limit:
                    e = next((x for x in load_index(kb) if x["file"] == fn), {})
                    print(f"[{kb}] cases/{fn}  {e.get('short') or e.get('company') or ''}（{e.get('board','')}）")
                    for s in snippets(text, keywords):
                        print(s)
    print(f"—— 共命中 {count} 份（全部关键词须同文命中）——")


def cmd_read(args):
    text = read_case(args.kb, args.path)
    if text is not None:
        print(text)


def cmd_update(_):
    r = subprocess.run(["git", "-C", KB_ROOT, "pull", "--ff-only"], capture_output=True, text=True)
    line = (r.stdout or r.stderr).strip().splitlines()
    print(f"知识库: {line[-1] if line else ('OK' if r.returncode == 0 else '失败')}")


def main():
    ap = argparse.ArgumentParser(description="IPO问询案例库本地检索（首次运行自动克隆知识库）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list").set_defaults(fn=cmd_list)

    def common(p):
        p.add_argument("--kb", choices=all_kbs(), help="限定单个知识库")
        p.add_argument("--tag"); p.add_argument("--board"); p.add_argument("--lawyer")
        p.add_argument("--code"); p.add_argument("--company"); p.add_argument("--year")
        p.add_argument("--limit", type=int, default=15)

    p = sub.add_parser("search"); p.add_argument("query"); common(p)
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("meta"); common(p)
    p.set_defaults(fn=cmd_meta)

    p = sub.add_parser("full"); p.add_argument("query"); p.add_argument("--kb"); p.add_argument("--limit", type=int, default=15)
    p.set_defaults(fn=cmd_full)

    p = sub.add_parser("read"); p.add_argument("kb", choices=all_kbs()); p.add_argument("path")
    p.set_defaults(fn=cmd_read)

    sub.add_parser("update").set_defaults(fn=cmd_update)

    args = ap.parse_args()
    ensure_kb()
    args.fn(args)


if __name__ == "__main__":
    main()
