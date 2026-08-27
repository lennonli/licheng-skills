#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将 summaries/ 日报与 raw/ 附件同步至 Google Drive(本机 Google Drive 桌面版目录)。
同步根目录从 config/system.json 的 drive_root 读取(支持 ~ 展开); 未配置则报错提示。
"""
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def get_drive_root():
    cfg = BASE / "config" / "system.json"
    if not cfg.exists():
        print(f"ERROR: 缺少 {cfg}。请复制 config/system.example.json 为 system.json 并填入 drive_root"
              f"(本机 Google Drive 桌面版同步目录, 支持 ~ 展开)。")
        sys.exit(1)
    root = json.loads(cfg.read_text(encoding="utf-8")).get("drive_root", "")
    if not root:
        print("ERROR: system.json 缺少 drive_root 字段")
        sys.exit(1)
    return Path(root).expanduser()


def main():
    GD_ROOT = get_drive_root()
    if not GD_ROOT.parent.exists():
        print(f"ERROR: 未找到 Google Drive 目录 {GD_ROOT.parent}，请确认 Google Drive 桌面版已登录运行")
        return 1
    for sub in ("日报", "PDF"):
        (GD_ROOT / sub).mkdir(parents=True, exist_ok=True)
    for src, dst in ((BASE / "summaries", GD_ROOT / "日报"), (BASE / "raw", GD_ROOT / "PDF")):
        # raw 用 --ignore-existing: Drive 文件提供器对已存在文件做内容比对会超时挂起
        extra = ["--ignore-existing"] if "raw" in str(src) else []
        r = subprocess.run(["rsync", "-a"] + extra + [str(src) + "/", str(dst) + "/"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"ERROR: rsync {src} -> {dst} 失败: {r.stderr.strip()}")
            return 1
        n = sum(1 for f in dst.rglob("*") if f.is_file())
        print(f"synced {src.name} -> Drive/{dst.name} (Drive侧现有 {n} 个文件)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
