#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
八字命书 HTML 渲染器（v2.3）。

v2.3（2026-10-11，修订人：ABL-李成）：支持「时辰不详」三柱盘——时柱显示为待补占位，
命盘下方列出十二时辰代入后的旺衰稳健性。

v2.2（2026-10-11，修订人：ABL-李成）：每段解读之后渲染「怎么办」（建议 / 注意事项）：
analysis.tips 按字段名挂在对应段落后；大运、流年、关键结构、白话版各条目可带 tip。

v2.1（2026-10-11，修订人：ABL-李成）：新增 analysis.plain 白话版，渲染于报告最前，
不懂命理的读者先看结论，专业推导置后供复核。

输入：paipan.py 的输出 JSON + 键 "analysis"（由解读者撰写）。
输出：单文件 HTML，无外部依赖，可离线打开、可打印。

用法：
  python3 render.py merged.json 命书.html
"""

import json, sys, html, math, datetime

WX = "木火土金水"
WXC = {"木": "#4E9E77", "火": "#D9584A", "土": "#C79A4B", "金": "#B9BEC7", "水": "#5B8FCF"}
WXC_D = {"木": "#2F6B4F", "火": "#A93B2E", "土": "#8E6B29", "金": "#6E747E", "水": "#2F5F96"}

JUDGE = {"大吉": "#2F6B4F", "吉": "#4E8A66", "平": "#8E8A7E", "参半": "#8E6B29",
         "需谨慎": "#B5813A", "不利": "#A93B2E"}


def e(s):
    return html.escape(str(s)) if s is not None else ""


def mi(s):
    """行内标记：**粗体**、【标记】"""
    s = e(s or "")
    out, i = [], 0
    while True:
        a = s.find("**", i)
        if a < 0:
            out.append(s[i:]); break
        b = s.find("**", a + 2)
        if b < 0:
            out.append(s[i:]); break
        out.append(s[i:a]); out.append("<b>" + s[a + 2:b] + "</b>"); i = b + 2
    return "".join(out).replace("【", '<span class="tag">【').replace("】", "】</span>")


def paras(text):
    if not text:
        return ""
    out, buf = [], []
    for b in [x.strip() for x in str(text).split("\n") if x.strip()]:
        if b.startswith("- "):
            buf.append(f"<li>{mi(b[2:])}</li>")
        else:
            if buf:
                out.append("<ul>" + "".join(buf) + "</ul>"); buf = []
            out.append(f"<p>{mi(b)}</p>")
    if buf:
        out.append("<ul>" + "".join(buf) + "</ul>")
    return "".join(out)


def fixbox(tip, label="怎么办"):
    """段落之后的「怎么办」框。tip 可为字符串（支持 - 列表）或字符串列表。"""
    if not tip:
        return ""
    if isinstance(tip, (list, tuple)):
        tip = "\n".join("- " + str(t) for t in tip)
    return f'<div class="fix"><div class="fh">{e(label)}</div>{paras(tip)}</div>'


def fixin(tip):
    """表格行、条目内的单行「怎么办」。"""
    if not tip:
        return ""
    if isinstance(tip, (list, tuple)):
        tip = "；".join(str(t) for t in tip)
    return f'<div class="fixin"><span class="fl">怎么办：</span>{mi(tip)}</div>'


def donut(wxd, size=132):
    """五行环形图（inline SVG，无依赖）"""
    tot = sum(wxd.values()) or 1
    r, sw = size / 2 - 13, 19
    c = 2 * math.pi * r
    segs, off = [], 0.0
    for k in WX:
        frac = wxd[k] / tot
        segs.append(f'<circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="{WXC[k]}" '
                    f'stroke-width="{sw}" stroke-dasharray="{c*frac:.2f} {c:.2f}" '
                    f'stroke-dashoffset="{-off:.2f}" transform="rotate(-90 {size/2} {size/2})">'
                    f'<title>{k} {wxd[k]}</title></circle>')
        off += c * frac
    return (f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" '
            f'role="img" aria-label="五行分布">{"".join(segs)}</svg>')


CSS = r"""
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --ink:#11151B; --ink2:#1A2029; --ink3:#262E39; --rule:#374250;
  --bone:#EFEBE3; --dim:#A49C90; --faint:#767E8A;
  --paper:#F7F5F1; --paper2:#FCFBF9; --text:#22262B; --text2:#5E646C;
  --hair:#DDD8CE; --seal:#B3402F;
}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
body{background:var(--paper);color:var(--text);font-size:16px;line-height:1.85;letter-spacing:.01em;
 font-family:"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans CJK SC",system-ui,sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:0 22px}
h1,h2,h3{font-family:"Songti SC","STSong","Noto Serif CJK SC",SimSun,serif;font-weight:600;letter-spacing:.04em}
.kai{font-family:"Kaiti SC","STKaiti",KaiTi,"AR PL UKai CN","Noto Serif CJK SC",serif}

.masthead{background:var(--ink);color:var(--bone);padding:44px 0 4px}
.masthead h1{font-size:31px;line-height:1.3}
.masthead .sub{color:var(--dim);font-size:14.5px;margin-top:11px;line-height:1.95}
.masthead .sub b{color:var(--bone);font-weight:500}

.nav{position:sticky;top:0;z-index:20;background:rgba(17,21,27,.96);
 border-top:1px solid var(--rule);border-bottom:1px solid var(--rule)}
.nav ul{display:flex;gap:2px;list-style:none;overflow-x:auto;scrollbar-width:none}
.nav ul::-webkit-scrollbar{display:none}
.nav a{display:block;padding:11px 13px;color:var(--dim);text-decoration:none;font-size:13.5px;white-space:nowrap}
.nav a:hover{color:var(--bone);background:var(--ink2)}

.plate{background:var(--ink);padding:24px 0 40px}
.pillars{display:grid;grid-template-columns:repeat(4,1fr);gap:13px}
.col{background:var(--ink2);border:1px solid var(--rule);border-radius:3px;padding:15px 9px 13px;text-align:center}
.col.dm{background:var(--ink3);border-color:var(--seal)}
.col .pos{color:var(--dim);font-size:12.5px;letter-spacing:.35em;padding-left:.35em}
.col .god{color:var(--dim);font-size:13.5px;margin-top:8px;min-height:20px}
.col .god.self{color:var(--seal);font-weight:600}
.gz{font-size:52px;line-height:1.14;margin:3px 0 1px;font-weight:500}
.col .hid{border-top:1px solid var(--rule);margin-top:11px;padding-top:8px;color:var(--dim);font-size:12.5px;line-height:1.75}
.col .hid i{font-style:normal;font-size:14px}
.col .ny{color:var(--faint);font-size:11.5px;margin-top:7px}

.meters{display:grid;grid-template-columns:auto 1fr 1fr;gap:24px;margin-top:26px;align-items:center}
.meters h4{color:var(--dim);font-size:12px;font-weight:400;margin-bottom:9px;letter-spacing:.2em}
.wxlist{display:flex;flex-wrap:wrap;gap:5px 14px;color:var(--bone);font-size:13px;margin-top:9px}
.wxlist i{font-style:normal;display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px}
.scale{position:relative;height:25px;border:1px solid var(--rule);border-radius:2px;
 background:linear-gradient(90deg,#3D5A78,#4E6B7E,#5F6B5F,#8A6B44,#A34B39)}
.scale .mk{position:absolute;top:-5px;bottom:-5px;width:3px;background:var(--bone);box-shadow:0 0 0 1px var(--ink)}
.slbl{display:flex;justify-content:space-between;color:var(--faint);font-size:11px;margin-top:6px}
.verdict{color:var(--bone);font-size:14.5px;margin-top:9px}
.verdict b{color:var(--seal);font-size:19px;font-family:"Songti SC",serif}
.yj{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.pill{font-size:12.5px;padding:3px 10px;border-radius:99px;border:1px solid}
.pill.y{color:#8FCCA8;border-color:#3A5F4C;background:#182620}
.pill.j{color:#E07A69;border-color:#5F3A34;background:#261A18}

.alert{background:#2A1D19;border-left:3px solid var(--seal);color:#E8D9CF;padding:14px 18px;
 margin-top:24px;font-size:14.5px;line-height:1.85;border-radius:2px}
.alert p+p{margin-top:8px}
.alert .hd{color:var(--seal);font-weight:600;font-size:13.5px;margin-bottom:6px}

main{padding:44px 0 20px}
section{margin-bottom:46px;scroll-margin-top:56px}
section>h2{font-size:22px;padding-bottom:10px;border-bottom:2px solid var(--ink);margin-bottom:20px;
 display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
section>h2 em{font-style:normal;font-size:13px;color:var(--text2);font-weight:400;
 font-family:"PingFang SC",sans-serif;letter-spacing:.02em}
h3{font-size:16.5px;margin:24px 0 10px}
p{margin:10px 0}
ul{margin:10px 0;list-style:none}
ul li{position:relative;padding-left:17px;margin:7px 0}
ul li::before{content:"";position:absolute;left:2px;top:.72em;width:5px;height:5px;background:var(--seal);border-radius:50%}
.tag{color:var(--seal);font-weight:600}
b{font-weight:600;color:#0E1218}

table{width:100%;border-collapse:collapse;margin:14px 0;font-size:14.5px}
th,td{padding:9px 12px;border-bottom:1px solid var(--hair);text-align:left;vertical-align:top}
thead th{background:#EDE9E1;font-weight:600;border-bottom:1.5px solid #B9B2A4;white-space:nowrap}
tbody tr:hover{background:#F1EEE8}
td.num{text-align:right;white-space:nowrap}
td.c{text-align:center;white-space:nowrap}

.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(248px,1fr));gap:12px;margin-top:12px}
.card{border:1px solid var(--hair);border-left:3px solid var(--ink);padding:12px 15px;background:var(--paper2)}
.card .t{font-weight:600;font-size:14.5px}
.card .d{color:var(--text2);font-size:13.5px;margin-top:4px;line-height:1.75}

.dy{display:grid;grid-template-columns:repeat(auto-fit,minmax(102px,1fr));gap:8px;margin:16px 0 6px}
.dy .step{border:1px solid var(--hair);border-top:4px solid #9AA0A8;padding:11px 8px;text-align:center;background:var(--paper2)}
.dy .step .g{font-size:27px;line-height:1.2}
.dy .step .a{font-size:12px;color:var(--text2);margin-top:5px}
.dy .step .y{font-size:11.5px;color:#8B9098}
.dy .step .j{font-size:12px;margin-top:6px;font-weight:600}
.dy .step.now{background:#FFF8E8;box-shadow:inset 0 0 0 1px #D9B15E}
.dy .step.now .a::after{content:" · 当下";color:#9A7524}

.ln{display:grid;grid-template-columns:repeat(auto-fit,minmax(86px,1fr));gap:7px;margin:14px 0}
.ln .y{border:1px solid var(--hair);background:var(--paper2);padding:9px 6px;text-align:center}
.ln .y .yr{font-size:12.5px;color:var(--text2)}
.ln .y .g{font-size:23px;line-height:1.25;margin:2px 0}
.ln .y .s{font-size:11.5px;font-weight:600}
.ln .y .bar{height:3px;margin-top:6px;border-radius:2px;background:#E4DFD4;overflow:hidden}
.ln .y .bar i{display:block;height:100%}
.ln .y.now{box-shadow:inset 0 0 0 2px #D9B15E;background:#FFF8E8}

.ly{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;margin:14px 0}
.ly .m{border:1px solid var(--hair);background:var(--paper2);padding:11px 12px;border-left:3px solid #9AA0A8}
.ly .m .hd{display:flex;justify-content:space-between;align-items:baseline}
.ly .m .jq{font-size:12.5px;color:var(--text2)}
.ly .m .g{font-size:21px}
.ly .m .dt{font-size:11.5px;color:#8B9098;margin-top:2px}
.ly .m .j{font-size:12px;font-weight:600;margin-top:4px}
.ly .m .r{font-size:11.5px;color:var(--text2);margin-top:3px;line-height:1.6}

.cal{display:grid;grid-template-columns:repeat(7,1fr);gap:5px;margin:14px 0}
.cal .h{text-align:center;font-size:12px;color:var(--text2);padding-bottom:2px}
.cal .d{aspect-ratio:1/1;border-radius:3px;display:flex;flex-direction:column;align-items:center;
 justify-content:center;color:#fff;font-size:11.5px;line-height:1.35;padding:2px}
.cal .d .dd{font-weight:600;font-size:12.5px}
.cal .d .gg{opacity:.92;font-size:11px}
.cal .d.empty{background:none}
.legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12.5px;color:var(--text2);margin-top:8px}
.legend i{display:inline-block;width:11px;height:11px;border-radius:2px;margin-right:5px;vertical-align:-1px}
.daylist .row{display:grid;grid-template-columns:96px 58px 62px 1fr;gap:10px;padding:8px 0;
 border-bottom:1px solid var(--hair);font-size:14px;align-items:baseline}
.daylist .row .dt{color:var(--text2);font-size:13px}
.daylist .row .g{font-size:17px}
.daylist .row .j{font-weight:600;font-size:13px}

.summary{background:var(--ink);color:var(--bone);padding:26px 28px;border-radius:2px}
.summary h2{color:var(--bone);border-color:var(--rule);font-size:20px}
.summary b{color:#fff}
.summary .tag{color:#E4A08F}
.summary ul li::before{background:#E4A08F}
footer{border-top:1px solid var(--hair);margin-top:10px;padding:22px 0 64px;color:var(--text2);font-size:13px;line-height:1.9}

.nav ul li{padding-left:0;margin:0}
.nav ul li::before{display:none}   /* 修正：导航项误继承正文列表圆点 */
/* 时辰不详 */
.col.unk{border-style:dashed;opacity:.72}
.col.unk .gz{color:var(--faint)}
.hscan{margin-top:20px;background:var(--ink2);border:1px solid var(--rule);border-radius:3px;padding:14px 16px}
.hscan .hd{color:var(--bone);font-size:14px;font-weight:600;letter-spacing:.06em}
.hscan .sub{color:var(--dim);font-size:12.5px;margin:4px 0 10px;line-height:1.7}
.hscan .g{display:grid;grid-template-columns:repeat(6,1fr);gap:6px}
.hscan .c{border:1px solid var(--rule);border-radius:2px;padding:6px 2px;text-align:center}
.hscan .c .z{font-size:16px;color:var(--bone)}
.hscan .c .r{font-size:11px;color:var(--faint)}
.hscan .c .v{font-size:12px;margin-top:2px}
@media (max-width:760px){.hscan .g{grid-template-columns:repeat(4,1fr)}}
/* 怎么办（每段解读之后的建议与注意事项） */
.fix{margin:14px 0 8px;padding:11px 16px 9px;background:#F2F6F3;border:1px solid #D5E3D9;border-left:4px solid #2F6B4F;border-radius:2px}
.fix .fh{font-size:13px;font-weight:600;color:#2F6B4F;letter-spacing:.12em}
.fix p,.fix li{font-size:15px;margin:6px 0}
.fix ul{margin:4px 0}
.fix ul li::before{background:#2F6B4F}
.fixin{margin-top:7px;padding:6px 10px;background:#F2F6F3;border-left:3px solid #2F6B4F;font-size:13.5px;line-height:1.75}
.fixin .fl{color:#2F6B4F;font-weight:600}
.sitem{margin:16px 0}
.sitem>p{margin:0}
/* 白话版（置顶） */
.plain{background:var(--paper2);border-bottom:1px solid var(--hair);padding:30px 0 28px;scroll-margin-top:56px}
.plain .in{max-width:760px}
.plain .k{display:inline-block;font-size:12.5px;letter-spacing:.14em;color:var(--seal);border:1px solid var(--seal);padding:2px 10px;border-radius:2px}
.plain .hl{font-size:23px;line-height:1.6;margin:14px 0 4px;color:var(--ink)}
.plain h3{font-size:17px;margin:24px 0 6px;padding-left:10px;border-left:3px solid var(--seal)}
.plain p,.plain li{font-size:16.5px;line-height:1.9}
.plain .ft{color:var(--text2);font-size:13.5px;margin-top:24px;padding-top:12px;border-top:1px dashed var(--hair)}
@media (max-width:760px){
 .pillars{grid-template-columns:repeat(2,1fr)}
 .meters{grid-template-columns:1fr}
 .gz{font-size:44px}.masthead h1{font-size:24px}
 .daylist .row{grid-template-columns:84px 52px 56px;row-gap:2px}
 .daylist .row>span:last-child{grid-column:1/-1;color:var(--text2);font-size:13px}
}
@media print{
 .plain{page-break-after:always;background:#fff}
 .fix,.fixin{background:#fff}
 body{font-size:12px}
 .nav{display:none}
 .masthead,.plate{background:#fff!important;color:#000!important}
 .masthead h1,.masthead .sub b{color:#000!important}.masthead .sub{color:#444!important}
 .col{background:#fff!important;border:1px solid #999!important}
 .col .god,.col .hid,.col .ny,.meters h4,.verdict,.wxlist{color:#333!important}
 .summary{background:#fff!important;color:#000!important;border:1px solid #999}
 .summary h2,.summary b{color:#000!important}
 .cal .d{color:#000!important;border:1px solid #bbb}
 section{break-inside:avoid}
}
"""


def render(d, out):
    a = d.get("analysis", {})
    inp, ts, p = d["input"], d["true_solar"], d["pillars"]
    H = []; A = H.append
    today = datetime.date.today()

    A(f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
      f'<meta name="viewport" content="width=device-width,initial-scale=1">'
      f'<title>八字命书 · {e("".join(x for x in (p["year"], p["month"], p["day"], p.get("hour")) if x))}</title>'
      f'<style>{CSS}</style></head><body>')

    title = a.get("title") or f'{e(inp["gender_cn"])}命 · {e(p["day_master"])}{e(p["day_master_wx"])}日主'
    A('<header class="masthead"><div class="wrap">')
    A(f'<h1>{mi(title)}</h1><div class="sub">')
    A(f'{e(inp["source"])}　{e(inp["clock_time"])}（{e(inp["gender_cn"])}）'
      + (f'　{e(inp["place"])}' if inp.get("place") else ""))
    if inp.get("lunar_str"):
        sx = (d.get("extras") or {}).get("shengxiao", "")
        A(f'<br>农历：{e(inp["lunar_str"])}' + (f'　生肖：{e(sx)}' if sx else ""))
    if d.get("time_known", True):
        A(f'<br>真太阳时：<b>{e(ts["time"])}</b>　（{e(inp["lon_note"])}；'
          f'经度时差 {ts["lon_correction_min"]:+.1f} 分，均时差 {ts["eot_min"]:+.1f} 分，'
          f'合计 <b>{ts["total_min"]:+.1f} 分</b>）')
    else:
        A(f'<br>时辰：<b>不详</b>　（只排年、月、日三柱；按{e(inp["lon_note"])}的真太阳时判定当天日界）')
    A(f'<br>月令：{e(p["month_ling"])}月（{e(p["jie"])}交节于 {e(p["jie_time"])}）')
    A('</div></div>')

    navs = [("plate", "命盘"), ("geju", "格局"), ("yong", "喜用"), ("jiegou", "结构"),
            ("shensha", "神煞"), ("dayun", "大运"), ("liunian", "流年"), ("liuyue", "流月"),
            ("liuri", "流日"), ("extra", "其他解析"), ("char", "性情"), ("liuqin", "六亲"),
            ("health", "健康"), ("career", "方位行业"), ("sum", "总结")]
    if a.get("plain"):
        navs = [("plain", "白话版")] + navs
    A('<nav class="nav"><div class="wrap"><ul>'
      + "".join(f'<li><a href="#{k}">{v}</a></li>' for k, v in navs) + '</ul></div></nav></header>')

    # 白话版（置顶）：给不懂命理的读者，先看结论
    pl = a.get("plain")
    if pl:
        A('<div class="plain" id="plain"><div class="wrap"><div class="in">'
          '<span class="k">白话版 · 先看这里</span>')
        if isinstance(pl, str):
            A(paras(pl))
        else:
            if pl.get("headline"):
                A(f'<h2 class="hl">{mi(pl["headline"])}</h2>')
            A(paras(pl.get("intro")))
            for sct in pl.get("sections", []):
                A(f'<h3>{mi(sct.get("h", ""))}</h3>{paras(sct.get("text"))}{fixbox(sct.get("tip"), "怎么做")}')
            if pl.get("closing"):
                A(f'<h3>一句话</h3>{paras(pl["closing"])}')
        A('<p class="ft">以下为专业排盘与推导。白话版的每一条结论都出自后文，'
          '想知道「为什么这么说」或日后复核，可往下看。</p></div></div></div>')

    # 命盘
    A('<div class="plate" id="plate"><div class="wrap"><div class="pillars">')
    for c in d["columns"]:
        dm = c["label"] == "日柱"
        A(f'<div class="col{" dm" if dm else ""}"><div class="pos">{e(c["label"])}</div>'
          f'<div class="god{" self" if dm else ""}">{e(c["gan_god"])}</div>'
          f'<div class="gz kai" style="color:{WXC[c["gan_wx"]]}">{e(c["gan"])}</div>'
          f'<div class="gz kai" style="color:{WXC[c["zhi_wx"]]};font-size:44px">{e(c["zhi"])}</div><div class="hid">')
        for h in c["zhi_hidden"]:
            A(f'<div><i class="kai" style="color:{WXC[h["wx"]]}">{e(h["gan"])}</i> {e(h["god"])}</div>')
        A(f'</div><div class="ny">{e(c["nayin"])}'
          + (f' · {e(c["hour_range"])}时' if c.get("hour_range") else "") + '</div></div>')
    if not d.get("time_known", True):
        A('<div class="col unk"><div class="pos">时柱</div><div class="god">—</div>'
          '<div class="gz kai">？</div><div class="gz kai" style="font-size:44px">？</div>'
          '<div class="hid"><div>时辰不详</div><div>子女 · 晚年待补</div></div><div class="ny">补上出生时间后重排</div></div>')
    A('</div>')

    wx, st, yj = d["wuxing"], d["strength"], d.get("yongji", {})
    A('<div class="meters">')
    A(f'<div><h4>五行分布</h4>{donut(wx)}</div>')
    A('<div><h4>加权计数（含藏干）</h4><div class="wxlist">'
      + "".join(f'<span><i style="background:{WXC[k]}"></i>{k} {wx[k]}</span>' for k in WX) + '</div>')
    if yj:
        A('<div class="yj">'
          + "".join(f'<span class="pill y">喜 {e(x)}</span>' for x in yj.get("yong", []))
          + "".join(f'<span class="pill j">忌 {e(x)}</span>' for x in yj.get("ji", [])) + '</div>')
    A('</div>')
    A(f'<div><h4>旺衰量度</h4><div class="scale">'
      f'<div class="mk" style="left:calc({min(max(st["ratio"],.05),.95)*100:.1f}% - 1.5px)"></div></div>'
      f'<div class="slbl"><span>极弱</span><span>弱</span><span>中和</span><span>旺</span><span>极旺</span></div>'
      f'<div class="verdict"><b>{e(st["verdict"])}</b>　帮 {st["support"]} ／ 耗 {st["drain"]}</div></div>')
    A('</div>')

    if d.get("warnings"):
        A('<div class="alert"><div class="hd">定盘提示 · 请先确认</div>'
          + "".join(f'<p>{mi(w)}</p>' for w in d["warnings"]) + '</div>')
    hs = d.get("hour_scan") or []
    if hs:
        vc = {}
        for x in hs:
            vc[x["verdict"]] = vc.get(x["verdict"], 0) + 1
        summ = "、".join(f"{k} {v} 个" for k, v in sorted(vc.items(), key=lambda kv: -kv[1]))
        col = {"身极旺": "#E4A08F", "身旺": "#D9B77A", "中和": "#9FC7A8", "身弱": "#8DB3D9", "身极弱": "#A79BD6"}
        A('<div class="hscan"><div class="hd">十二时辰代入 · 旺衰是否稳定</div>'
          f'<div class="sub">把 12 个可能的时柱逐一代入重算旺衰：{e(summ)}。'
          '判语越集中，三柱结论越可靠；分散时，补上时辰前不宜下重话。</div><div class="g">')
        for x in hs:
            A(f'<div class="c"><div class="z kai">{e(x["hour"])}</div><div class="r">{e(x["range"])}点</div>'
              f'<div class="v" style="color:{col.get(x["verdict"], "#ccc")}">{e(x["verdict"])}</div></div>')
        A('</div></div>')
    A('</div></div><main class="wrap">')

    tips = a.get("tips") or {}

    def T(key):
        """解读正文 + 其后的「怎么办」。字段可为字符串，或 {"text":…, "tip":…}。"""
        v = a.get(key)
        if isinstance(v, dict):
            return paras(v.get("text")) + fixbox(v.get("tip") or tips.get(key))
        return paras(v) + fixbox(tips.get(key))

    def sec(sid, title, sub, body):
        if body:
            A(f'<section id="{sid}"><h2>{e(title)}' + (f'<em>{e(sub)}</em>' if sub else "") + f'</h2>{body}</section>')

    b = T("day_master") + T("strength_reason")
    if a.get("geju"):
        b += f'<h3>格局</h3>{T("geju")}'
    if a.get("congge"):
        b += f'<h3>从格辨析</h3>{T("congge")}'
    sec("geju", "日主与格局", "旺衰依据、格局定性", b)

    y = a.get("yongshen", {})
    if y:
        b = '<table><thead><tr><th>五行</th><th>十神</th><th>作用</th><th>评级</th></tr></thead><tbody>'
        for r in y.get("rows", []):
            b += (f'<tr><td style="color:{WXC_D.get(r.get("wx",""),"#222")};font-weight:600">{e(r.get("wx"))}</td>'
                  f'<td>{e(r.get("god"))}</td><td>{mi(r.get("why"))}</td><td><b>{e(r.get("level"))}</b></td></tr>')
        b += '</tbody></table>' + paras(y.get("note"))
        if d.get("tiaohou"):
            b += (f'<div class="card"><div class="t">调候参考（穷通宝鉴）</div><div class="d">'
                  f'{e(p["day_master"])}日生于{e(p["month_ling"])}月，古法调候用神为 <b>{e(d["tiaohou"])}</b>。'
                  f'{mi(y.get("tiaohou_note",""))}</div></div>')
        b += fixbox(y.get("tip") or tips.get("yongshen"))
        sec("yong", "喜用神与忌神", "扶抑与调候", b)

    rel = d.get("branch_relations", []) + d.get("stem_relations", [])
    if rel or a.get("structures"):
        b = ('<div class="grid2">' + "".join(
            f'<div class="card"><div class="t">{e(r["type"])}</div><div class="d">{e(r["detail"])}</div></div>'
            for r in rel) + '</div>') if rel else ""
        st_ = a.get("structures")
        if isinstance(st_, list):          # [{"k":"丁壬合","text":"…","tip":"…"}]
            for it in st_:
                b += (f'<div class="sitem"><p><b>{mi(it.get("k",""))}</b>　{mi(it.get("text",""))}</p>'
                      f'{fixin(it.get("tip"))}</div>')
            b += fixbox(tips.get("structures"))
        else:
            b += T("structures")
        sec("jiegou", "关键结构", "刑冲合害与其含义", b)

    if d.get("shensha"):
        b = ('<table><thead><tr><th>神煞</th><th>所临</th><th>含义</th></tr></thead><tbody>' + "".join(
            f'<tr><td><b>{e(s["name"])}</b></td><td>{e(s["at"])}</td><td>{e(s["desc"])}</td></tr>'
            for s in d["shensha"]) + '</tbody></table>' + T("shensha_note"))
        sec("shensha", "神煞", "参考性质，不作独立断语", b)

    # 大运
    dy = d["dayun"]; notes = {s.get("gz"): s for s in a.get("dayun", [])}
    b = (f'<p>{e(inp["gender_cn"])}命，大运<b>{"顺" if dy["forward"] else "逆"}排</b>，'
         f'起运 <b>{e(dy["start"])}</b>。</p><div class="dy">')
    for s in dy["steps"]:
        n = notes.get(s["gz"], {}); j = n.get("judge", ""); col = JUDGE.get(j, "#9AA0A8")
        now = "now" if s["start_year"] <= today.year <= s["end_year"] else ""
        b += (f'<div class="step {now}" style="border-top-color:{col}"><div class="g kai">{e(s["gz"])}</div>'
              f'<div class="a">{s["xu_age"]}岁起</div><div class="y">{s["start_year"]}–{s["end_year"]}</div>'
              f'<div class="j" style="color:{col}">{e(j)}</div></div>')
    b += '</div>'
    if a.get("dayun"):
        b += '<table><thead><tr><th>大运</th><th>年份</th><th>判</th><th>说明</th></tr></thead><tbody>'
        for s in dy["steps"]:
            n = notes.get(s["gz"], {}); col = JUDGE.get(n.get("judge", ""), "#5E646C")
            b += (f'<tr><td><b class="kai" style="font-size:18px">{e(s["gz"])}</b></td>'
                  f'<td class="num">{s["start_year"]}–{s["end_year"]}</td>'
                  f'<td class="c" style="color:{col};font-weight:600">{e(n.get("judge"))}</td>'
                  f'<td>{mi(n.get("text",""))}{fixin(n.get("tip"))}</td></tr>')
        b += '</tbody></table>'
    b += T("dayun_summary")
    sec("dayun", "大运", "十年一步，运补命之不足", b)

    # 流年
    ln = d.get("liunian", [])
    if ln:
        lnn = {x.get("year"): x for x in a.get("liunian", [])}
        mx = max(abs(x["score"]) for x in ln) or 1
        b = '<div class="ln">'
        for x in ln:
            col = JUDGE.get(x["judge"], "#9AA0A8")
            now = "now" if x["year"] == today.year else ""
            b += (f'<div class="y {now}" title="{e("、".join(x["relations"]))}">'
                  f'<div class="yr">{x["year"]}</div><div class="g kai">{e(x["gz"])}</div>'
                  f'<div class="s" style="color:{col}">{e(x["judge"])}</div>'
                  f'<div class="bar"><i style="width:{abs(x["score"])/mx*100:.0f}%;background:{col}"></i></div></div>')
        b += ('</div><table><thead><tr><th>年份</th><th>流年</th><th>十神</th><th>十二长生</th>'
              '<th>所在大运</th><th>判</th><th>与原局关系 / 说明</th></tr></thead><tbody>')
        for x in ln:
            col = JUDGE.get(x["judge"], "#5E646C")
            note = lnn.get(x["year"], {}).get("text", ""); ntip = lnn.get(x["year"], {}).get("tip")
            b += (f'<tr><td class="num">{x["year"]}</td>'
                  f'<td><b class="kai" style="font-size:17px">{e(x["gz"])}</b></td>'
                  f'<td class="c">{e(x["gan_god"])}／{e(x["zhi_god"])}</td>'
                  f'<td class="c">{e(x["stage"])}</td><td class="c kai">{e(x["dayun"])}</td>'
                  f'<td class="c" style="color:{col};font-weight:600">{e(x["judge"])}</td>'
                  f'<td>{e("、".join(x["relations"]) or "—")}{("　" + mi(note)) if note else ""}{fixin(ntip)}</td></tr>')
        b += '</tbody></table>' + T("liunian_note")
        sec("liunian", "流年运势", "一年一运，叠加于大运之上", b)

    # 流月
    ly = d.get("liuyue")
    if ly:
        b = f'<p>{ly["year"]} 年（<b class="kai">{e(ly["year_gz"])}</b>年）十二月建，按节气分月。</p><div class="ly">'
        for m in ly["months"]:
            col = JUDGE.get(m["judge"], "#9AA0A8")
            b += (f'<div class="m" style="border-left-color:{col}"><div class="hd">'
                  f'<span class="jq">{e(m["jie"])}</span><span class="g kai">{e(m["gz"])}</span></div>'
                  f'<div class="dt">{e(m["start"])} 交节</div>'
                  f'<div class="j" style="color:{col}">{e(m["judge"])}'
                  f'　<span style="color:#8B9098;font-weight:400">{e(m["gan_god"])}</span></div>'
                  + (f'<div class="r">{e("、".join(m["relations"]))}</div>' if m["relations"] else "") + '</div>')
        b += '</div>' + T("liuyue_note")
        sec("liuyue", "流月运势", f'{ly["year"]} 年逐月，以节为界而非以初一', b)

    # 流日
    lr = d.get("liuri", [])
    if lr:
        first = datetime.date.fromisoformat(lr[0]["date"])
        b = '<div class="cal">' + "".join(f'<div class="h">{c}</div>' for c in "一二三四五六日")
        b += '<div class="d empty"></div>' * (first.weekday() % 7)
        for x in lr:
            col = JUDGE.get(x["judge"], "#9AA0A8")
            b += (f'<div class="d" style="background:{col}" '
                  f'title="{e(x["date"])} {e(x["gz"])}（{e(x["judge"])}）：{e("；".join(x["tips"]))}">'
                  f'<span class="dd">{e(x["md"])}</span><span class="gg kai">{e(x["gz"])}</span></div>')
        b += '</div><div class="legend">' + "".join(
            f'<span><i style="background:{c}"></i>{k}</span>' for k, c in JUDGE.items() if k != "参半")
        b += '</div><p style="color:#5E646C;font-size:13.5px">鼠标悬停可看当日干支与提示。</p>'
        best = sorted(lr, key=lambda x: -x["score"])[:3]
        worst = sorted(lr, key=lambda x: x["score"])[:3]
        b += '<h3>值得留意的日子</h3><div class="daylist">'
        for x in best + worst:
            col = JUDGE.get(x["judge"], "#5E646C")
            b += (f'<div class="row"><span class="dt">{e(x["date"][5:])}（周{e(x["weekday"])}）</span>'
                  f'<span class="g kai">{e(x["gz"])}</span>'
                  f'<span class="j" style="color:{col}">{e(x["judge"])}</span>'
                  f'<span>{e("；".join(x["tips"]))}</span></div>')
        b += '</div>' + T("liuri_note")
        sec("liuri", "每日注意事项", f'{lr[0]["date"]} 起 {len(lr)} 天', b)

    # 其他解析
    ex = d.get("extras")
    if ex:
        b = '<div class="grid2">'
        _mg = ex.get("minggong") or ("需出生时辰" if not d.get("time_known", True) else "")
        _sg = ex.get("shengong") or ("需出生时辰" if not d.get("time_known", True) else "")
        for t, v in (("胎元", ex.get("taiyuan")), ("命宫", _mg),
                     ("身宫", _sg), ("生肖", ex.get("shengxiao"))):
            if v:
                b += (f'<div class="card"><div class="t">{t}</div>'
                      f'<div class="d kai" style="font-size:19px;color:var(--text)">{e(v)}</div></div>')
        b += '</div>'
        if ex.get("stages"):
            b += ('<h3>日主十二长生</h3><table><thead><tr><th>柱位</th><th>地支</th><th>状态</th></tr></thead><tbody>'
                  + "".join(f'<tr><td>{e(s["pos"])}柱</td>'
                            f'<td class="c kai" style="font-size:17px">{e(s["zhi"])}</td>'
                            f'<td><b>{e(s["stage"])}</b></td></tr>' for s in ex["stages"]) + '</tbody></table>')
        lk = ex.get("lucky", {})
        if lk:
            b += ('<h3>取用参考</h3><table><tbody>'
                  f'<tr><th>宜方位</th><td>{e(lk.get("directions"))}</td>'
                  f'<th>忌方位</th><td>{e(lk.get("avoid_directions"))}</td></tr>'
                  f'<tr><th>宜色</th><td>{e(lk.get("colors"))}</td>'
                  f'<th>忌色</th><td>{e(lk.get("avoid_colors"))}</td></tr>'
                  f'<tr><th>喜用数</th><td colspan="3">{e(lk.get("numbers"))}</td></tr></tbody></table>'
                  '<p style="color:#5E646C;font-size:13.5px">方位、颜色、数字一类属辅助性参考，'
                  '权重远低于后天努力与具体选择。</p>')
        b += T("extras_note")
        sec("extra", "其他解析", "胎元、命宫、十二长生与取用参考", b)

    sec("char", "性情与才性", "长处与需留意处", T("character"))
    sec("liuqin", "六亲与感情", "父母、手足、配偶、子女", T("liuqin"))
    sec("health", "健康提示", "薄弱环节与日常方向", T("health"))
    sec("career", "方位、行业与用色", "顺用神而行", T("career"))
    if a.get("advice"):
        sec("advice", "当下阶段建议", "针对现行大运与流年", paras(a["advice"]))

    if a.get("summary"):
        A('<section class="summary" id="sum"><h2>一页总结</h2>' + paras(a["summary"]) + '</section>')

    A('<footer>')
    if a.get("todo"):
        A('<p><b>待核实事项</b></p>' + paras(a["todo"]))
    A('<p>命理属中国传统文化范畴，非可实证核验的结论，本文仅供参考，不构成医疗、法律、财务或任何专业建议。'
      '流年、流月、流日的吉凶评分由五行喜忌与刑冲合害机械计算得出，只反映倾向、不构成对具体事件的预测。'
      '人生走向取决于具体选择与行动。</p>')
    if d.get("yongji"):
        A(f'<p>评分所用喜忌：喜 {e("、".join(d["yongji"]["yong"]))}，忌 {e("、".join(d["yongji"]["ji"]))}'
          f'（{e(d["yongji"]["source"])}）。</p>')
    A(f'<p>排盘依据：日柱以儒略日独立推算（锚点 1949-10-01 甲子日）；节气与农历采用天文历算；'
      f'真太阳时按出生地经度与均时差校正。'
      + (f'四柱：{e(p["year"])} {e(p["month"])} {e(p["day"])} {e(p["hour"])}。</p>' if p.get("hour")
         else f'三柱：{e(p["year"])} {e(p["month"])} {e(p["day"])}（时辰不详，时柱待补）。</p>'))
    A('</footer></main></body></html>')

    open(out, "w", encoding="utf-8").write("".join(H))
    return out


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python3 render.py merged.json out.html"); sys.exit(1)
    print("已生成:", render(json.load(open(sys.argv[1], encoding="utf-8")), sys.argv[2]))
