#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Markdown 日报转 PDF（pandoc gfm→HTML + 系统 Chrome 无头打印，中文渲染最佳）。
用法: python3 md2pdf.py <日报.md> [输出.pdf]  — 默认输出同名 .pdf"""
import subprocess
import sys
import tempfile
from pathlib import Path

CSS = """
<style>
@page { size: A4; margin: 16mm 14mm; }
body { font-family: "PingFang SC", "Songti SC", "STSong", serif;
       font-size: 10.5pt; line-height: 1.65; color: #1a1a1a; margin: 0; }
h1 { font-size: 16pt; text-align: center; border-bottom: 2px solid #333;
     padding-bottom: 8px; margin: 0 0 14px; }
h2 { font-size: 13pt; border-left: 4px solid #2b5797; padding-left: 8px;
     margin: 18px 0 8px; color: #2b5797; }
h3 { font-size: 11.5pt; margin: 14px 0 6px; color: #222; }
h4 { font-size: 10.5pt; margin: 12px 0 4px; }
p { margin: 6px 0; }
blockquote { margin: 8px 0; padding: 6px 10px; background: #f5f7fa;
             border-left: 3px solid #b8c4d8; color: #444; }
table { border-collapse: collapse; width: 100%; margin: 8px 0;
        font-size: 8.5pt; table-layout: fixed; }
th, td { border: 0.5pt solid #999; padding: 4px 5px; word-break: break-word;
         vertical-align: top; }
th { background: #eef2f8; font-weight: 600; }
a { color: #2b5797; text-decoration: none; word-break: break-all; }
ul, ol { margin: 6px 0; padding-left: 22px; }
li { margin: 3px 0; }
hr { border: none; border-top: 0.75pt solid #ccc; margin: 14px 0; }
strong { font-weight: 600; }
code { font-family: "Menlo", monospace; font-size: 9pt; }
</style>
"""


def main():
    if len(sys.argv) < 2:
        print("用法: md2pdf.py <日报.md> [输出.pdf]")
        return 2
    src = Path(sys.argv[1]).resolve()
    if not src.exists():
        print(f"ERROR: 找不到 {src}")
        return 1
    dst = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else src.with_suffix(".pdf")

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tf:
        tf.write(CSS)
        css_file = tf.name

    r = subprocess.run(
        ["pandoc", "-f", "gfm", "-t", "html5", "-s",
         "-V", "pagetitle=digest", "-H", css_file,
         "-o", str(dst.with_suffix(".html")), str(src)],
        capture_output=True, text=True)
    if r.returncode != 0:
        print(f"ERROR: pandoc 转换失败: {r.stderr.strip()}")
        return 1

    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    r = subprocess.run(
        [chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
         f"--print-to-pdf={dst}", dst.with_suffix(".html").as_uri()],
        capture_output=True, text=True, timeout=120)
    Path(css_file).unlink(missing_ok=True)
    dst.with_suffix(".html").unlink(missing_ok=True)
    if r.returncode != 0 or not dst.exists() or dst.stat().st_size < 1000:
        print(f"ERROR: Chrome 打印失败: {r.stderr.strip()[:300]}")
        return 1
    print(f"OK: {dst} ({dst.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
