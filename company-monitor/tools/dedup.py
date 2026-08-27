#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""增量去重状态库管理（SQLite）。
用法:
  python3 dedup.py init-check            # 确认库就绪, 输出 Baseline/增量 模式提示
  python3 dedup.py feed --file X.json    # 读条目数组, 指纹比对, 输出 outbox/new_items.json
  python3 dedup.py stats                 # 各公司入库条数统计
指纹 = sha1(company + event_type + source_id); 舆情类无稳定 source_id 时由调用方传规范化 URL。
同指纹但 title 实质不同 → status=变化; 否则不输出仅更新 last_seen。"""
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "state" / "monitor.db"
OUTBOX = BASE / "outbox"

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY,
  fingerprint TEXT UNIQUE NOT NULL,
  company TEXT, source TEXT, event_type TEXT, source_id TEXT,
  title TEXT, url TEXT, publish_time TEXT,
  severity TEXT, evidence TEXT,
  first_seen TEXT, last_seen TEXT, last_title TEXT
);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def norm_url(u):
    if not u:
        return ""
    try:
        p = urlsplit(u.strip())
        return urlunsplit((p.scheme, p.netloc, p.path, "", ""))
    except Exception:
        return u.strip()


def fingerprint(company, event_type, source_id):
    if not source_id:
        source_id = "no-id-" + hashlib.sha1((company + event_type).encode()).hexdigest()[:12]
    return hashlib.sha1(f"{company}|{event_type}|{source_id}".encode()).hexdigest()


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def init_check():
    conn = connect()
    n = conn.execute("SELECT COUNT(*) c FROM items").fetchone()["c"]
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('last_init', ?)", (datetime.now().isoformat(timespec="seconds"),))
    conn.commit()
    if n == 0:
        print(f"MODE:BASELINE db={DB} 条目=0, 今日应做全量基线扫描")
    else:
        print(f"MODE:INCREMENT db={DB} 已有条目={n}, 今日只报增量")


def feed(path):
    OUTBOX.mkdir(parents=True, exist_ok=True)
    items = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(items, dict):
        items = items.get("items", [])
    now = datetime.now().isoformat(timespec="seconds")
    conn = connect()
    out_new = []
    for it in items:
        company = it.get("company", "")
        event_type = it.get("event_type", "舆情")
        sid = it.get("source_id") or norm_url(it.get("url", ""))
        fp = fingerprint(company, event_type, sid)
        row = conn.execute("SELECT * FROM items WHERE fingerprint=?", (fp,)).fetchone()
        title = (it.get("title") or "").strip()
        if row is None:
            conn.execute(
                "INSERT INTO items(fingerprint,company,source,event_type,source_id,title,url,publish_time,severity,evidence,first_seen,last_seen,last_title)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (fp, company, it.get("source", ""), event_type, sid, title,
                 it.get("url", ""), it.get("publish_time", ""), it.get("severity", ""),
                 it.get("evidence", ""), now, now, title))
            rec = dict(it)
            rec.update({"status": "新增", "first_seen": now})
            out_new.append(rec)
        else:
            changed = title and row["last_title"] and title != row["last_title"]
            conn.execute("UPDATE items SET last_seen=?, last_title=?, url=?, severity=COALESCE(NULLIF(?,''),severity) WHERE fingerprint=?",
                         (now, title or row["last_title"], it.get("url") or row["url"], it.get("severity", ""), fp))
            if changed:
                rec = dict(it)
                rec.update({"status": "变化", "first_seen": row["first_seen"],
                            "previous_title": row["last_title"]})
                out_new.append(rec)
    conn.commit()
    out = OUTBOX / "new_items.json"
    out.write_text(json.dumps({"generated": now, "count": len(out_new), "items": out_new},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK: 入库比对完成, 新增/变化 {len(out_new)} 条 → {out}")
    return 0


def scan_snapshot(path):
    """保存 risk_scan 维度计数快照到 state/last_scan.json, 供次日增量比对。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    conn = connect()
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('last_scan', ?)",
                 (json.dumps(data, ensure_ascii=False),))
    conn.commit()
    (BASE / "state" / "last_scan.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("OK: scan 快照已保存 -> state/last_scan.json")


def stats():
    conn = connect()
    for r in conn.execute("SELECT company, event_type, COUNT(*) n FROM items GROUP BY company, event_type ORDER BY company, n DESC"):
        print(f"{r['company']:40s} {r['event_type']:10s} {r['n']}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    cmd = sys.argv[1]
    if cmd == "init-check":
        init_check()
    elif cmd == "feed":
        feed(sys.argv[sys.argv.index("--file") + 1])
    elif cmd == "scan-snapshot":
        scan_snapshot(sys.argv[sys.argv.index("--file") + 1])
    elif cmd == "stats":
        stats()
    else:
        print(__doc__)
        sys.exit(2)
