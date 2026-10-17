#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""企查查资料包批量提取：docx段落目录+全部表格、xlsx/xls全sheet → 单个文本文件。

输出文件开头附"延伸主体候选速查"：表头命中 分支机构/对外投资/股东 等关键词的表格索引，
供《尽调主体清单》圈定时直接定位（只给指针，不改写数据，仍须回表核对）。

用法: python3 extract_package.py <资料包目录> [-o 输出文件.md]
"""
import argparse
import sys
from pathlib import Path

# 延伸主体候选表头关键词 → 主体类型标签
ENTITY_KEYWORDS = {
    "分支机构": "分公司",
    "分公司": "分公司",
    "对外投资": "子公司/参股",
    "控股企业": "子公司",
    "子公司": "子公司",
    "被投资企业": "子公司/参股",
    "股东信息": "控股股东",
    "股东及出资": "控股股东",
    "股东名称": "控股股东",
    "实际控制人": "控股股东/实控人",
    "受益所有人": "控股股东/实控人",
    "最终受益人": "控股股东/实控人",
}
HEADER_ROWS_TO_CHECK = 2  # 企查查报告常有合并标题行在真正表头之上


def _match_keywords(text: str):
    hits = [k for k in ENTITY_KEYWORDS if k in text]
    return hits


def dump_docx(path: Path):
    import docx
    d = docx.Document(str(path))
    lines = [f"\n######## DOCX: {path.name} ########"]
    lines.append(f"（段落数 {len(d.paragraphs)}，表格数 {len(d.tables)}）")
    lines.append("\n--- 目录/段落（非空，前120条）---")
    n = 0
    for p in d.paragraphs:
        t = p.text.strip()
        if t:
            lines.append(t[:100])
            n += 1
            if n >= 120:
                lines.append("……（段落截断）")
                break
    candidates = []
    for ti, tbl in enumerate(d.tables):
        lines.append(f"\n--- 表{ti}（{len(tbl.rows)}行 × {len(tbl.columns)}列）---")
        header_texts = []
        for ri, r in enumerate(tbl.rows):
            cells = [c.text.strip().replace("\n", "/") for c in r.cells]
            out = []
            for c in cells:  # 相邻去重（合并单元格）
                if not out or out[-1] != c:
                    out.append(c)
            line = " | ".join(out)
            lines.append(line[:600])
            if ri < HEADER_ROWS_TO_CHECK:
                header_texts.append(line)
        hits = _match_keywords(" ".join(header_texts))
        if hits:
            candidates.append({
                "file": path.name, "kind": "DOCX", "loc": f"表{ti}",
                "shape": f"{len(tbl.rows)}行×{len(tbl.columns)}列",
                "hits": hits, "header": " / ".join(header_texts)[:120],
            })
    return "\n".join(lines), candidates


def dump_excel(path: Path):
    import warnings
    warnings.filterwarnings("ignore")
    import pandas as pd
    lines = [f"\n######## EXCEL: {path.name} ########"]
    candidates = []
    try:
        xls = pd.ExcelFile(str(path))
        lines.append(f"Sheets: {xls.sheet_names}")
        for s in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=s, header=None).dropna(how="all")
            lines.append(f"\n--- Sheet [{s}]（{df.shape[0]}行 × {df.shape[1]}列）---")
            header_texts = []
            for ri, (_, row) in enumerate(df.iterrows()):
                vals = [str(v).strip() for v in row if str(v) != "nan" and str(v).strip()]
                if vals:
                    line = " | ".join(vals)
                    lines.append(line[:600])
                    if ri < HEADER_ROWS_TO_CHECK:
                        header_texts.append(line)
            hits = _match_keywords(s + " " + " ".join(header_texts))
            if hits:
                candidates.append({
                    "file": path.name, "kind": "EXCEL", "loc": f"Sheet [{s}]",
                    "shape": f"{df.shape[0]}行×{df.shape[1]}列",
                    "hits": hits, "header": " / ".join(header_texts)[:120],
                })
    except Exception as e:
        lines.append(f"读取失败: {e}")
    return "\n".join(lines), candidates


def render_candidates(cands) -> str:
    lines = ["\n## 延伸主体候选速查（供《尽调主体清单》圈定定位；仅为表头命中指针，数据须回表核对）"]
    if not cands:
        lines.append("（资料包内未命中分支机构/对外投资/股东类表头——请在在线检索阶段用 "
                     "get_branches / get_controlled_companies / get_shareholder_info 补查）")
        return "\n".join(lines)
    for c in cands:
        lines.append(
            f"- {c['kind']} {c['file']} · {c['loc']}（{c['shape']}）· "
            f"命中「{'、'.join(c['hits'])}」· 表头：{c['header']}"
        )
    lines.append("注：登记状态为注销/吊销/撤销的主体不纳入排查，仅入历史沿革；"
                 "参股（≤50%且不控制）仅列示；持股比例逐字引用，禁止相乘自算。")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("directory", help="资料包目录")
    ap.add_argument("-o", "--output", default=None, help="输出文件（默认: 目录名_提取.md）")
    args = ap.parse_args()

    root = Path(args.directory).expanduser().resolve()
    if not root.is_dir():
        sys.exit(f"目录不存在: {root}")

    parts = []
    all_cands = []
    files = sorted(root.rglob("*"))
    for f in files:
        if not f.is_file() or f.name.startswith("~$"):
            continue
        suf = f.suffix.lower()
        try:
            if suf == ".docx":
                text, cands = dump_docx(f)
                parts.append(text)
                all_cands.extend(cands)
            elif suf in (".xlsx", ".xls"):
                text, cands = dump_excel(f)
                parts.append(text)
                all_cands.extend(cands)
            elif suf == ".pdf":
                parts.append(f"\n######## PDF（跳过，如需文字层另行pdftotext）: {f.name}")
        except Exception as e:
            parts.append(f"\n!! 解析失败 {f.name}: {e}")

    header = [f"# 资料包提取：{root.name}\n", render_candidates(all_cands)]
    out = Path(args.output) if args.output else root / f"{root.name}_提取.md"
    out.write_text("\n".join(header + parts), encoding="utf-8")
    print(f"已输出: {out}")
    print(f"共 {len(parts)} 个文件条目，延伸主体候选表 {len(all_cands)} 张，请用 Read 工具分段读取。")


if __name__ == "__main__":
    main()
