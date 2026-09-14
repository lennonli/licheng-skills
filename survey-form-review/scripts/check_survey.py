#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
董监高/自然人股东/核心技术人员调查表 —— 本地解析与规则校验
用法:
  python3 check_survey.py <docx文件或目录> \
      --issuer "示例科技股份有限公司" \
      --period-start 2024-01-01 --period-end 2026-08-31 \
      [--stale-dates "2026年6月30日,2026年1—6月"] \
      [-o /tmp/项目-调查表复核-YYYYMMDD.json]

输出: JSON（结构化提取 + findings问题清单 + mcp_todo待MCP核查清单）。
本脚本只做确定性规则校验（R1-R10）；MCP公开信息比对、底稿勾稽由模型按SKILL.md流程执行。
"""
import argparse
import datetime as dt
import json
import os
import re
import zipfile

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table

# ---------- 通用提取 ----------

def p_text(p_el):
    return "".join(t.text or "" for t in p_el.findall(".//" + qn("w:t")))


def row_cells(tr):
    """一行内的tc元素列表（findall天然去重，gridSpan合并格只出现一次）"""
    el = tr._tr if hasattr(tr, "_tr") else tr
    return el.findall(qn("w:tc"))


def tc_text(tc):
    return "\n".join(p_text(p) for p in tc.findall(".//" + qn("w:p"))).strip()


def cell_flat(tc):
    return tc_text(tc).replace("\n", " ")


def table_rows(table):
    return [[cell_flat(tc) for tc in row_cells(tr)] for tr in table.rows]


# ---------- 日期解析 ----------

DATE_TOKEN = re.compile(r"(\d{4})\s*[-/.年]\s*(\d{1,2})(?!\d)(?:\s*[-/.月]\s*(\d{1,2})\s*日?(?!\d))?")


def date_tokens(text):
    """提取文本中所有年月token（顺序），兼容 2006/03-2009/07、2015-11-10、2023.08、2011年11月"""
    toks = []
    for m in DATE_TOKEN.finditer(text or ""):
        toks.append((int(m.group(1)), int(m.group(2))))
    return toks


def parse_range(text):
    """起止时间 → ((y,m), (y,m)|None表示至今, precise:bool)
    token法：首token=起、末token=止、含“至今”则止=None；
    不精确=只有年份/无法解析；不完整=有起无止且非至今"""
    t = (text or "").strip()
    if not t or t in ("/", "无"):
        return None, None, False
    now = "至今" in t
    toks = date_tokens(t)
    if not toks:
        if re.search(r"\d{4}", t):
            return None, None, False  # 只有年份
        return None, None, False
    start = toks[0]
    end = None if now else (toks[-1] if len(toks) > 1 else None)
    precise = len(toks) >= 2 or now
    return start, end, precise


def gap_months(a, b):
    return (b[0] - a[0]) * 12 + (b[1] - a[1])


def ym_add(ym, k):
    y, m = ym
    m += k
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return (y, m)


def fmt_ym(ym):
    return f"{ym[0]}年{ym[1]}月" if ym else "?"


# ---------- 身份证 ----------

def idcard_issues(idno, birth_ym, gender):
    out = []
    idno = idno.strip()
    if not re.fullmatch(r"\d{17}[\dXx]", idno):
        return [f"身份证号码格式非18位（“{idno[:4]}…{idno[-2:]}”）"]
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check = "10X98765432"[sum(int(c) * w for c, w in zip(idno[:17], weights)) % 11]
    if check != idno[-1].upper():
        out.append("身份证号码校验位不符，须与证件原件核对")
    try:
        bd = dt.datetime.strptime(idno[6:14], "%Y%m%d").date()
        if birth_ym and (bd.year, bd.month) != tuple(int(x) for x in birth_ym):
            out.append(f"身份证出生年月({bd.year}年{bd.month}月)与表格“出生年月”不一致")
        g = "男" if int(idno[16]) % 2 else "女"
        if gender and g != gender:
            out.append(f"身份证性别位({g})与表格“性别”不一致")
    except ValueError:
        out.append("身份证出生日期段非有效日期")
    return out


# ---------- 表格分类 ----------

def classify(rows):
    j = " ".join(" ".join(r) for r in rows[:4])
    if "姓名" in j and ("出生年月" in j or "身份证号码" in j) and "亲属关系" not in j:
        return "basic"
    if "起止时间" in j and "学校" in j:
        return "edu"
    if "单位名称" in j and "职位" in j and "持股比例" not in j:
        return "work"
    if "单位名称" in j and "持股比例" in j and "任职情况" in j:
        return "external"
    if "亲属关系" in j and "身份证号码" in j:
        return "relatives"
    if "调查内容" in j and "调查结果" in j:
        return "other"
    return "unknown"


# ---------- 解析 ----------

BASIC_LABELS = {"姓名": "姓名", "性别": "性别", "出生年月": "出生年月", "国籍": "国籍",
                "学历": "学历", "现在公司任职": "position_now", "身份证号码": "身份证号码"}


def parse_basic(rows):
    """基本情况大表分段解析：键值对 / 教育及培训 / 直接或间接持股"""
    person, edu, shares = {}, [], []
    mode = "kv"
    for cells in rows:
        j = "".join(cells)
        if "教育及培训" in j:
            mode = "edu"
            continue
        if "直接或者间接持有" in j or "入股时间" in j and "持股主体" in j:
            mode = "share"
            continue
        if "起止时间" in j and "学校" in j:
            continue
        if mode == "kv":
            for i, c in enumerate(cells):
                label = re.sub(r"\s|（.*?）|\(.*?\)", "", c)
                if label in BASIC_LABELS and i + 1 < len(cells):
                    person[BASIC_LABELS[label]] = cells[i + 1].strip()
        elif mode == "edu":
            if not is_blank_row(cells):
                edu.append({"range": cells[0].strip(), "school": cells[1].strip() if len(cells) > 1 else "",
                            "major": cells[2].strip() if len(cells) > 2 else "",
                            "degree": cells[3].strip() if len(cells) > 3 else ""})
        elif mode == "share":
            if not is_blank_row(cells) and "持股主体" not in j:
                shares.append({"time": cells[0].strip(),
                               "holder": cells[1].strip() if len(cells) > 1 else "",
                               "amount": cells[2].strip() if len(cells) > 2 else "",
                               "pct": cells[3].strip() if len(cells) > 3 else "",
                               "pledge": cells[4].strip() if len(cells) > 4 else ""})
    m = re.search(r"(\d{4})\s*[-/.年]\s*(\d{1,2})", person.get("出生年月", ""))
    person["_birth_ym"] = (m.group(1), m.group(2)) if m else None
    return person, edu, shares


def is_control(v):
    """“是”“共同控制”“实际控制”均视为控制；“否”“/”空不视为控制"""
    v = (v or "").strip()
    return v.startswith("是") or ("控制" in v and "不" not in v and "否" not in v)


def norm_company(name):
    """公司名归一：去括号备注（强制注销/已注销等）、空格、全半角括号"""
    n = re.sub(r"[（(][^）)]*[）)]", "", name or "")
    return re.sub(r"[\s　]", "", n)


DECEASED = ("已故", "去世", "过世", "已逝", "已去世", "已过世", "故")


def is_blank_row(cells):
    """模板行：全部为空、'/'、'无'、'-'"""
    return all(c.strip() in ("", "/", "无", "-", "—") for c in cells)


def parse_rows_after_header(rows, header_pred, ncols):
    """表头行之后的数据行 → list[dict by index]"""
    out, seen_hdr = [], False
    for cells in rows:
        j = " ".join(cells)
        if not seen_hdr and header_pred(j):
            seen_hdr = True
            continue
        if seen_hdr and any(c.strip() for c in cells):
            padded = cells + [""] * max(0, ncols - len(cells))
            out.append(padded[:ncols])
    return out


def parse_doc(path, issuer):
    doc = Document(path)
    result = {"file": path, "issuer": issuer, "person": {}, "education": [], "work": [],
              "shareholding": [], "external": [], "relatives": [], "relatives_sub": [],
              "other_qa": [], "paragraphs": [], "signature": {}, "notes_range": None}
    section, sub_title = "", ""
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            txt = p_text(child).strip()
            if not txt:
                continue
            result["paragraphs"].append(txt)
            if re.match(r"^[一二三四五六七八九十]+、.{2,20}调查", txt):
                section, sub_title = txt[:14], ""
                continue
            if re.match(r"^\d+、.{2,15}情况调查", txt):
                sub_title = txt[:22]
                continue
            if "填表人签名" in txt or "填表人签字" in txt:
                result["signature"]["signer"] = re.sub(r"[_\s]", "", txt.replace("填表人签名：", ""))
            m = re.search(r"(\d{4})[\s_]*年[\s_]*(\d{1,2})[\s_]*月[\s_]*(\d{1,2})[\s_]*日", txt)
            if m and len(txt) < 30 and "报告期" not in txt:
                result["signature"]["date"] = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            m3 = re.search(r"即\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*至\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", txt)
            if m3:
                result["notes_range"] = (
                    f"{m3.group(1)}-{int(m3.group(2)):02d}-{int(m3.group(3)):02d}",
                    f"{m3.group(4)}-{int(m3.group(5)):02d}-{int(m3.group(6)):02d}")
        elif child.tag == qn("w:tbl"):
            rows = table_rows(Table(child, doc))
            if not rows:
                continue
            ttype = classify(rows)
            if ttype == "basic":
                result["person"], result["education"], result["shareholding"] = parse_basic(rows)
            elif ttype == "edu":
                _, result["education"], _ = parse_basic(rows)
            elif ttype == "work":
                result["work"] = [
                    {"range": r[0], "company": r[1], "title": r[2]}
                    for r in parse_rows_after_header(rows, lambda j: "起止时间" in j and "单位名称" in j, 3)
                    if not is_blank_row(r)]
            elif ttype == "external":
                data = [r for r in parse_rows_after_header(
                    rows, lambda j: "单位名称" in j and "持股比例" in j, 10) if r[1].strip()]
                if section.startswith("四") or sub_title:
                    # 近亲属子表（1配偶/2子女/3父母/4兄弟姐妹/5配偶的兄弟姐妹/6子女配偶的父母）
                    for r in data:
                        if all(c.strip() in ("/", "无", "") for c in r):
                            continue
                        result["relatives_sub"].append(
                            {"title": sub_title or "近亲属任职投资子表", "relation": r[0],
                             "company": r[1], "share": r[3], "position": r[4],
                             "range": r[5], "control": r[6]})
                else:
                    for r in data:
                        if r[1].strip() in ("/", "无"):
                            continue
                        result["external"].append(
                            {"company": r[1], "reg_capital": r[2], "share": r[3], "position": r[4],
                             "range": r[5], "control": r[6], "salary": r[7],
                             "business": r[8], "trade": r[9]})
            elif ttype == "relatives":
                last_rel = ""
                for r in parse_rows_after_header(rows, lambda j: "亲属关系" in j, 4):
                    rel = r[0].strip() or last_rel  # 合并单元格续行继承称谓
                    last_rel = rel
                    result["relatives"].append(
                        {"relation": rel, "name": r[1], "idno": r[2], "contact": r[3],
                         "_inherited": not r[0].strip()})
            elif ttype == "other":
                for r in parse_rows_after_header(rows, lambda j: "调查内容" in j and "调查结果" in j, 3):
                    result["other_qa"].append({"question": r[1], "answer": r[2]})
    return result


# ---------- 规则校验 ----------

LOW_EDU = ("高中", "初中", "小学", "中学")


def build_findings(d, args):
    F = []

    def add(rule, sev, loc, msg, sug=""):
        F.append({"rule": rule, "severity": sev, "location": loc,
                  "message": msg, "suggestion": sug})

    person, name = d["person"], (d["person"].get("姓名") or os.path.basename(d["file"]))

    # R1 报告期
    defs = [p for p in d["paragraphs"] if "报告期是指" in p]
    if not defs:
        add("R1报告期", "高", "填写须知", "未找到“报告期是指…”定义句", "按项目申报口径补充")
    else:
        m = re.search(r"报告期是指\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*至\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", defs[0])
        m_now = re.search(r"报告期是指\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*至今", defs[0])
        if not m and m_now:
            add("R1报告期", "中", "填写须知第8条",
                f"报告期定义句采用“{m_now.group(1)}年{m_now.group(2)}月{m_now.group(3)}日至今”式，"
                f"与项目口径截止日{args.period_end}的固定式不同", "全部调查表统一为同一表述（固定截止日或至今，二选一）")
            m = None
        elif not m:
            add("R1报告期", "中", "填写须知", f"报告期定义句日期无法解析：{defs[0][:50]}", "人工核对")
        if m and (f"{m.group(4)}-{int(m.group(5)):02d}-{int(m.group(6)):02d}" != args.period_end
                  or f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" != args.period_start):
            add("R1报告期", "高", "填写须知第8条",
                f"报告期为{m.group(1)}年{m.group(2)}月{m.group(3)}日至{m.group(4)}年{m.group(5)}月{m.group(6)}日，"
                f"与项目口径{args.period_start}~{args.period_end}不符", "统一为项目申报口径")
    if len(defs) > 1:
        add("R1报告期", "中", "填写须知", f"“报告期是指”出现{len(defs)}次，存在重复定义", "删除重复句")
    all_text = "\n".join(d["paragraphs"])
    for stale in args.stale_dates:
        if stale and stale in all_text:
            add("R1报告期", "高", "全文", f"旧日期残留“{stale}”", "更新为现行报告期")
    if d["notes_range"]:
        exp = ym_add(tuple(int(x) for x in args.period_start.split("-")[:2]), -12)
        got = tuple(int(x) for x in d["notes_range"][0].split("-")[:2])
        if got != exp or d["notes_range"][1] != args.period_end:
            add("R1报告期", "中", "三/四部分调查范围说明",
                f"调查范围“即{d['notes_range'][0]}至{d['notes_range'][1]}”与报告期前十二个月至期末"
                f"（{exp[0]}-{exp[1]:02d}~{args.period_end}）不一致", "同步更新说明句")

    # R2 关键字段留空
    for k, label in [("姓名", "姓名"), ("身份证号码", "身份证号码"), ("学历", "学历"), ("出生年月", "出生年月")]:
        v = person.get(k, "")
        if not v:
            add("R2留空", "高", "一、基本情况", f"“{label}”未填写", "必填项，补齐")
        elif v in ("/", "无", "略", "-"):
            add("R2留空", "高", "一、基本情况", f"“{label}”填为“{v}”，不合常理", "补填真实信息")
    if person.get("position_now") == "":
        add("R2留空", "中", "一、基本情况", "“现在公司任职”留空", "非本公司任职填“/”")

    # R3 身份证
    idno = person.get("身份证号码", "")
    if idno:
        for msg in idcard_issues(idno, person.get("_birth_ym"), person.get("性别")):
            add("R3身份证", "高", "一、基本情况", msg, "与证件原件核对后更正")

    # R4 教育及培训
    edu = [e for e in d["education"] if e["range"] not in ("/", "无")]
    declared_none_edu = any(e["range"] in ("/", "无") for e in d["education"])
    declared = person.get("学历", "")
    if not edu:
        if declared and any(t in declared for t in LOW_EDU):
            add("R4教育", "低", "一、教育及培训", "教育及培训未填（学历为高中及以下，可能确无大中专经历）",
                "与填表人确认后保持“无”")
        else:
            add("R4教育", "中", "一、教育及培训", "未填写任何教育记录", "从大中专以上起填")
    for i, e in enumerate(edu, 1):
        deg = e["degree"] or ""
        if any(t in deg for t in LOW_EDU):
            same_as_declared = any(t in deg and t in (person.get("学历") or "") for t in LOW_EDU)
            add("R4教育", "低" if same_as_declared else "中", f"教育第{i}行",
                f"学历“{deg}”低于大中专（须知要求从大中专起填）" + ("，但系本人最高学历" if same_as_declared else ""),
                "项目组统一口径：最高学历为高中及以下者可保留该行或填“/”")
        if not e["school"]:
            add("R4教育", "中", f"教育第{i}行", "学校（机构）留空", "补填或删行")
        s, t, precise = parse_range(e["range"])
        if s is None:
            add("R4教育", "中", f"教育第{i}行", f"起止时间“{e['range']}”未含年月", "按“×年×月—×年×月”补全")
        elif not precise:
            add("R4教育", "中", f"教育第{i}行", f"起止时间“{e['range']}”缺结束时间", "补全止于×年×月")
    declared = person.get("学历", "")
    if declared and edu and not declared_none_edu:
        tok = next((t for t in ["博士", "硕士研究生", "硕士", "本科", "大专", "专科", "中专", "高中"] if t in declared), None)
        if tok and not any(tok in (e["degree"] or "") for e in edu):
            add("R4教育", "中", "学历↔教育经历",
                f"基本情况“学历:{declared}”在教育经历中无对应记录", "两处口径统一")

    # R5 工作经历
    work = d["work"]
    if not work:
        add("R5工作经历", "高", "二、工作经历", "未填写任何工作经历", "自首次就业起连续填写至至今")
    for i, w in enumerate(work, 1):
        if not w["company"]:
            add("R5工作经历", "中", f"工作第{i}行", "单位名称留空", "补填")
        s, e, precise = parse_range(w["range"])
        if s is None:
            add("R5工作经历", "中", f"工作第{i}行（{w['company'][:12]}）",
                f"起止时间“{w['range']}”未含年月", "按“×年×月—×年×月/至今”补全")
        elif not precise:
            add("R5工作经历", "中", f"工作第{i}行（{w['company'][:12]}）",
                f"起止时间“{w['range']}”缺结束时间（非至今）", "补全或改“至今”")
        if i == len(work) and w["range"] and "至今" not in w["range"]:
            _, e_last, _ = parse_range(w["range"])
            pe = tuple(int(x) for x in args.period_end.split("-")[:2])
            tail = f"，{fmt_ym(e_last)}至报告期末{pe[0]}年{pe[1]}月无记录（{gap_months(e_last, pe)}个月）" if e_last and gap_months(e_last, pe) > 3 else ""
            add("R5工作经历", "中", f"工作第{i}行（{w['company'][:12]}）",
                f"末段经历未填至“至今”{tail}", "现职填“至今”；已离职/退休/待业须补填至今状态")
        c = w["company"]
        if c and len(re.sub(r"[\s（）()]", "", c)) < 4 and c not in ("/", "无"):
            add("R5工作经历", "低", f"工作第{i}行", f"单位名称“{c}”疑似简称", "改用工商登记全称（待MCP核查）")
    # 综合：教育+工作合并覆盖，找既未读书也未工作的空档（工作内部断档天然涵盖于此）
    ivs = []
    for seg in edu:
        s0, e0, _ = parse_range(seg["range"])
        if s0 and (e0 or "至今" in seg["range"]):
            ivs.append((s0, e0, seg.get("school", "")[:12] or "教育段"))
    for seg in work:
        s0, e0, _ = parse_range(seg["range"])
        if s0 and (e0 or "至今" in seg["range"]):
            ivs.append((s0, e0, seg.get("company", "")[:12] or "工作段"))
    if ivs:
        ivs.sort()
        merged = [list(ivs[0])]
        for s0, e0, lab in ivs[1:]:
            if merged[-1][1] is None:
                break
            if s0 <= ym_add(merged[-1][1], 1):
                if e0 is None or merged[-1][1] is None or e0 > merged[-1][1]:
                    merged[-1][1] = e0
            else:
                merged.append([s0, e0, lab])
        for a, b in zip(merged, merged[1:]):
            if a[1] is not None and gap_months(a[1], b[0]) > 3:
                add("R5工作经历", "中", "综合时间线",
                    f"{fmt_ym(a[1])}（{a[2]}）至{fmt_ym(b[0])}（{b[2]}）期间教育与工作均无记录，"
                    f"空档{gap_months(a[1], b[0])}个月",
                    "待业填“待业”、退休填“退休”、就读补教育经历")

    # R6 对外任职投资
    ext = d["external"]
    for i, x in enumerate(ext, 1):
        if is_control(x["control"]) and not x["range"]:
            add("R6对外任职投资", "中", f"三、第{i}项（{x['company'][:14]}）",
                "填“是”控制但未填任职/持股起止期间", "补填起止时间")
    for i, x in enumerate(ext, 1):
        if x["company"] and all(not (x[k] or "").strip() or x[k].strip() == "/" for k in ("share", "position", "control", "range")):
            k_, exact_ = (None, False)
            for k in (getattr(args, "known_entities", []) or []):
                if norm_company(k) == norm_company(x["company"]):
                    k_, exact_ = k, True
            add("R6对外任职投资", "高" if not exact_ else "中", f"三、第{i}项（{x['company'][:14]}）",
                "仅填单位名称，持股比例/任职/是否控制/起止期间均留空" + ("（系已知关联主体）" if exact_ else ""),
                "补齐各栏，无则填“/”；MCP核查其真实持股任职" if not exact_ else "若为发行人子公司，按须知不属“其他单位”，应删除该行或注明任职")
    if not ext:
        add("R6对外任职投资", "中", "三、对外任职投资",
            "本人申报无对外任职投资", "列为MCP重点交叉核查对象，防漏报")

    # R7 近亲属
    rels = d["relatives"]
    for r in rels:
        if r["relation"] and not r["name"] and r["relation"] not in ("/", "无"):
            add("R7近亲属", "中", "四、近亲属表", f"“{r['relation']}”行留空", "无该类亲属填“无”，有则补填")
    for r in rels:
        if r["name"] and r["name"] not in ("无", "/"):
            idv = (r["idno"] or "").replace(" ", "")
            if idv and idv not in ("无", "/") and not any(k in idv for k in DECEASED) and not re.fullmatch(r"\d{17}[\dXx]", idv):
                hint = "疑似填成手机号" if re.fullmatch(r"1\d{10}", idv) else "非18位"
                add("R7近亲属", "中", f"四、（{r['relation']}/{r['name']}）", f"身份证号码格式异常（{len(idv)}位，{hint}）", "核对证件后更正")
            if not r["idno"]:
                add("R7近亲属", "中", f"四、（{r['relation']}/{r['name']}）", "身份证号码留空", "补填")
            if not r["contact"]:
                add("R7近亲属", "低", f"四、（{r['relation']}/{r['name']}）", "联系方式留空", "补填")
    if rels and not any(r["name"] and r["name"] not in ("无", "/") for r in rels):
        add("R7近亲属", "中", "四、近亲属表", "近亲属全部留空", "逐类填写，无则填“无”")
    if not rels:
        add("R7近亲属", "中", "四、近亲属表", "未找到近亲属明细表", "确认表结构完整")
    for sub in d["relatives_sub"]:
        if is_control(sub["control"]):
            add("R7近亲属", "中", f"四、{sub['title']}（{sub['company'][:14]}）",
                "近亲属控制企业——须进一步核查该公司控制的下一级公司是否已填报",
                "按调查表说明穿透一级，MCP查其对外投资比对")

    # R11 入股情况（基本情况表内“直接或者间接持有公司股权情况”子表）
    for i, s in enumerate(d.get("shareholding", []), 1):
        if not date_tokens(s["time"]):
            add("R11入股情况", "中", f"一、持股第{i}行", f"入股时间“{s['time']}”未精确到月", "补全年月")
        for k, lab in [("holder", "持股主体名称"), ("amount", "出资额/持股数量"), ("pct", "持股比例")]:
            if not s[k]:
                add("R11入股情况", "中", f"一、持股第{i}行", f"“{lab}”留空", "补填")
        if not s["pledge"]:
            add("R11入股情况", "低", f"一、持股第{i}行", "“抵押冻结情况”留空", "无则填“无”")
    if d["shareholding"]:
        pass  # 与底稿勾稽由模型/用户提供底稿后进行，见SKILL.md
    else:
        person_name = person.get("姓名", "")
        add("R11入股情况", "低", "一、持股情况", "未填持股子表（或模板无此项）",
            "自然人股东/平台穿透自然人必须填写入股情况")

    # R12 名称与口径一致性（持股主体白名单、持股子表↔三表时间）
    known = getattr(args, "known_entities", []) or []
    def match_known(name):
        n = norm_company(name)
        for k in known:
            kn = norm_company(k)
            if n == kn:
                return k, True
            if len(n) >= 4 and len(kn) >= 4 and n[:4] == kn[:4]:
                return k, False
        return None, False
    for i, s in enumerate(d.get("shareholding", []), 1):
        k, exact = match_known(s["holder"])
        if k and not exact:
            add("R12一致性", "中", f"一、持股第{i}行", f"持股主体“{s['holder']}”与登记全称“{k}”不一致", f"改为“{k}”")
        for x in d["external"]:
            if norm_company(x["company"])[:4] == norm_company(s["holder"])[:4] and s["holder"] not in ("直接持股", ""):
                st, _, _ = parse_range(x["range"])
                ht = date_tokens(s["time"])
                if st and ht and st != ht[0]:
                    add("R12一致性", "低", f"一、持股第{i}行↔三、{x['company'][:10]}",
                        f"入股时间{s['time']}与三表起始{x['range'][:12]}不一致", "统一为入伙/入股工商登记时间")
    for i, x in enumerate(d["external"], 1):
        k, exact = match_known(x["company"])
        if k and not exact:
            add("R12一致性", "中", f"三、第{i}项", f"单位名称“{x['company']}”与登记全称“{k}”不一致", f"改为“{k}”")

    # R8 勾选题
    for i, qa in enumerate(d["other_qa"], 1):
        ans = qa["answer"]
        if not ans:
            add("R8勾选题", "高", f"五、第{i}项", f"“{qa['question'][:24]}”留空", "必答，勾选并说明")
        elif "☑" not in ans and "√" not in ans:
            add("R8勾选题", "高", f"五、第{i}项", f"“{qa['question'][:24]}”未勾选", "勾选是/否")
        if "至今" not in qa["question"] and re.search(r"\d{4}年\d{1,2}月\d{1,2}日至\d{4}年\d{1,2}月\d{1,2}日", qa["question"]):
            add("R8勾选题", "低", f"五、第{i}项", "题干含旧式起止日期表述", "核对是否为“至今”口径")

    # R9 签署
    sig = d["signature"]
    if not sig.get("signer"):
        add("R9签署", "高", "签署页", "填表人未签名", "打印后亲笔签署")
    if not sig.get("date"):
        add("R9签署", "中", "签署页", "签署日期未填写", "补填")
    return F


def comments_info(path):
    try:
        z = zipfile.ZipFile(path)
        if "word/comments.xml" not in z.namelist():
            return []
        cx = z.read("word/comments.xml").decode("utf-8")
        return [{"author": m.group(1),
                 "text": "".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", m.group(2)))[:60]}
                for m in re.finditer(r'<w:comment [^>]*w:author="([^"]*)"[^>]*>(.*?)</w:comment>', cx, re.S)]
    except Exception:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--issuer", default="", help="发行人全称（MCP人员核查锚定用）")
    ap.add_argument("--period-start", required=True, dest="period_start")
    ap.add_argument("--period-end", required=True, dest="period_end")
    ap.add_argument("--stale-dates", default="", help="逗号分隔旧日期串，如 '2026年6月30日,2026年1—6月'")
    ap.add_argument("--known-entities", default="", dest="known_entities",
                    help="逗号分隔的已知主体全称（发行人、持股平台、子公司），用于名称一致性比对")
    ap.add_argument("-o", "--output", default=None)
    args = ap.parse_args()
    args.stale_dates = [x.strip() for x in args.stale_dates.split(",") if x.strip()]
    args.known_entities = [x.strip() for x in args.known_entities.split(",") if x.strip()]

    files = []
    if os.path.isdir(args.target):
        for root, _, fs in os.walk(args.target):
            files += [os.path.join(root, f) for f in sorted(fs)
                      if f.endswith(".docx") and not f.startswith((".~", "~$"))]
    else:
        files = [args.target]

    all_out = []
    for f in sorted(files):
        try:
            d = parse_doc(f, args.issuer)
            d["findings"] = build_findings(d, args)
            d["comments"] = comments_info(f)
            if d["comments"]:
                c0 = d["comments"][0]
                d["findings"].append({
                    "rule": "R10批注", "severity": "低", "location": "全文",
                    "message": f"存在{len(d['comments'])}条未处理批注（首条：{c0['author']}：{c0['text']}）",
                    "suggestion": "逐条落实批注意见"})
            companies = [w["company"] for w in d["work"] if w["company"] and w["company"] not in ("/", "无")]
            companies += [x["company"] for x in d["external"]]
            companies += [s["company"] for s in d["relatives_sub"]]
            d["mcp_todo"] = {
                "person": d["person"].get("姓名", ""),
                "shareholding": d.get("shareholding", []),
                "fullname_check": sorted({c for c in companies if c}),
                "controlled_next_level": [x["company"] for x in d["external"] if is_control(x["control"])]
                                          + [s["company"] for s in d["relatives_sub"] if is_control(s["control"])]}
            all_out.append(d)
        except Exception as ex:
            all_out.append({"file": f, "error": f"{type(ex).__name__}: {ex}"})

    out_path = args.output or f"/tmp/调查表复核-{dt.date.today():%Y%m%d}.json"
    # 同名多版本检测：同一人多份文件并存时逐份提示，避免复核作废版本
    by_name = {}
    for d in all_out:
        n = d.get("person", {}).get("姓名")
        if n:
            by_name.setdefault(n, []).append(d)
    for n, ds in by_name.items():
        if len(ds) > 1:
            names = "、".join(os.path.basename(x["file"]) for x in ds)
            for x in ds:
                x["findings"].insert(0, {
                    "rule": "R0版本", "severity": "高", "location": "文件",
                    "message": f"同名“{n}”存在{len(ds)}份文件并存：{names}",
                    "suggestion": "与用户确认基准版本后仅复核该版"})
    # 跨表交叉核对：A表近亲属子表所述“某亲属N的企业”与N本人表三表比对
    docs_by_name = {n: ds[0] for n, ds in by_name.items() if len(ds) == 1}
    for d in all_out:
        if "error" in d:
            continue
        a_name = d.get("person", {}).get("姓名", "")
        for sub in d.get("relatives_sub", []):
            n = re.sub(r"(配偶|父亲|母亲|兄弟姐妹|兄弟|姐妹|子女|及其|的|之|：|:|\d+\.?|[（(].*?[）)]|\s)", "", sub.get("relation") or "")
            if not n or n not in docs_by_name or n == a_name:
                continue
            b = docs_by_name[n]
            b_companies = {norm_company(x["company"]): x for x in b.get("external", [])}
            key = norm_company(sub["company"])
            if "调查表" in sub["company"] and "见" in sub["company"]:
                d["findings"].append({
                    "rule": "R7近亲属", "severity": "中", "location": f"四、{sub['title'][:10]}",
                    "message": f"以“{sub['company']}”代替填写", "suggestion": "每份调查表须自行完整填写，不得引用他人表格"})
                continue
            if key not in b_companies:
                d["findings"].append({
                    "rule": "R13跨表", "severity": "高", "location": f"四、{sub['title'][:10]}（{sub['company'][:16]}）",
                    "message": f"本表称{n}在该企业任职/持股，但{n}本人调查表三表未填报该企业",
                    "suggestion": f"与{a_name}、{n}双方核对：填错公司名或{n}漏报"})
            else:
                x = b_companies[key]
                sa, _, _ = parse_range(sub.get("range", ""))
                sb, _, _ = parse_range(x.get("range", ""))
                if sa and sb and sa != sb:
                    d["findings"].append({
                        "rule": "R13跨表", "severity": "中", "location": f"四、{sub['title'][:10]}（{sub['company'][:16]}）",
                        "message": f"本表填{n}起始{fmt_ym(sa)}，{n}本人表填{fmt_ym(sb)}",
                        "suggestion": "以工商登记时间统一"})
    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(all_out, fp, ensure_ascii=False, indent=1)

    for d in all_out:
        name = d.get("person", {}).get("姓名") or os.path.basename(d.get("file", "?"))
        if "error" in d:
            print(f"✗ {name}: {d['error']}")
            continue
        f_ = d["findings"]
        hi = sum(1 for x in f_ if x["severity"] == "高")
        mid = sum(1 for x in f_ if x["severity"] == "中")
        print(f"◆ {name}：问题{len(f_)}条（高{hi}/中{mid}/低{len(f_)-hi-mid}） 未处理批注{len(d.get('comments', []))}条")
        for x in f_:
            if x["severity"] in ("高", "中"):
                print(f"   [{x['severity']}|{x['rule']}] {x['location']}: {x['message']}")
    print(f"\nJSON已落盘: {out_path}")


if __name__ == "__main__":
    main()
