#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
八字排盘引擎 —— 输出结构化 JSON，供解读与 HTML 渲染使用。

设计原则：凡可计算者一律计算，绝不凭记忆。
  - 日柱：儒略日独立推算（锚点 1949-10-01 甲子日），不依赖任何外部库
  - 节气/农历：lunar-python（自动安装）；缺失时用内置 Meeus 太阳视黄经算法兜底
  - 真太阳时：经度时差 + 均时差（Meeus 公式）

用法：
  python3 paipan.py --date 2000-01-01 --time 00:30 --place 北京 --gender male
  python3 paipan.py --lunar 2000-11-20 --time 20:00 --lon 115.4 --gender female
  python3 paipan.py --date 2019-01-03 --time 00:02 --place 深圳 --gender male --json out.json

v2.3（2026-10-11，修订人：ABL-李成）：新增「时辰不详」三柱模式：--time unknown。
时柱留空，旺衰、刑冲合害、神煞、评分均按三柱计算；自动扫描出生当天 0:00–23:59，
若交节或子时换日使三柱在当天内变化，逐段列出并写入 warnings。
"""

import argparse, json, math, sys, subprocess

# ---------------------------------------------------------------- 基础常数

GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = "子丑寅卯辰巳午未申酉戌亥"
GAN_YY = [1, -1] * 5                      # 阳干=1 阴干=-1
GAN_WX = "木木火火土土金金水水"
ZHI_WX = "水土木木土火火土金金土水"
ZHI_HOUR = ["23-01", "01-03", "03-05", "05-07", "07-09", "09-11",
            "11-13", "13-15", "15-17", "17-19", "19-21", "21-23"]

# 地支藏干（本气、中气、余气），权重用于旺衰评分
HIDDEN = {
    "子": [("癸", 1.0)],
    "丑": [("己", 0.6), ("癸", 0.25), ("辛", 0.15)],
    "寅": [("甲", 0.6), ("丙", 0.25), ("戊", 0.15)],
    "卯": [("乙", 1.0)],
    "辰": [("戊", 0.6), ("乙", 0.25), ("癸", 0.15)],
    "巳": [("丙", 0.6), ("庚", 0.25), ("戊", 0.15)],
    "午": [("丁", 0.7), ("己", 0.3)],
    "未": [("己", 0.6), ("丁", 0.25), ("乙", 0.15)],
    "申": [("庚", 0.6), ("壬", 0.25), ("戊", 0.15)],
    "酉": [("辛", 1.0)],
    "戌": [("戊", 0.6), ("辛", 0.25), ("丁", 0.15)],
    "亥": [("壬", 0.7), ("甲", 0.3)],
}

WX_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
WX_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

# 十神：以日主为我，(对方五行关系, 阴阳同异) -> 名称
def ten_god(day_gan, other_gan):
    di, oi = GAN.index(day_gan), GAN.index(other_gan)
    dw, ow = GAN_WX[di], GAN_WX[oi]
    same = GAN_YY[di] == GAN_YY[oi]
    if dw == ow:
        return "比肩" if same else "劫财"
    if WX_SHENG[dw] == ow:
        return "食神" if same else "伤官"
    if WX_KE[dw] == ow:
        return "偏财" if same else "正财"
    if WX_KE[ow] == dw:
        return "七杀" if same else "正官"
    return "偏印" if same else "正印"

SHISHEN_GROUP = {
    "比肩": "比劫", "劫财": "比劫", "食神": "食伤", "伤官": "食伤",
    "正财": "财", "偏财": "财", "正官": "官杀", "七杀": "官杀",
    "正印": "印", "偏印": "印",
}

NAYIN = ["海中金","炉中火","大林木","路旁土","剑锋金","山头火","涧下水","城头土","白蜡金","杨柳木",
         "泉中水","屋上土","霹雳火","松柏木","长流水","砂石金","山下火","平地木","壁上土","金箔金",
         "覆灯火","天河水","大驿土","钗钏金","桑柘木","大溪水","沙中土","天上火","石榴木","大海水"]

# ---------------------------------------------------------------- 儒略日 / 日柱

def jdn(y, m, d):
    a = (14 - m) // 12
    yy, mm = y + 4800 - a, m + 12 * a - 3
    return d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045

_ANCHOR = jdn(1949, 10, 1)   # 1949-10-01 为甲子日（公认锚点）

def day_ganzhi(y, m, d):
    n = (jdn(y, m, d) - _ANCHOR) % 60
    return GAN[n % 10] + ZHI[n % 12]

# ---------------------------------------------------------------- 真太阳时

def equation_of_time(y, m, d, hour=12.0):
    """均时差（分钟），Meeus 近似。返回 视太阳时 - 平太阳时。"""
    jd = jdn(y, m, d) - 0.5 + hour / 24.0
    T = (jd - 2451545.0) / 36525.0
    L0 = (280.46646 + 36000.76983 * T + 0.0003032 * T * T) % 360
    M = math.radians((357.52911 + 35999.05029 * T - 0.0001537 * T * T) % 360)
    e = 0.016708634 - 0.000042037 * T - 0.0000001267 * T * T
    eps = 23.439291 - 0.0130042 * T
    y_ = math.tan(math.radians(eps / 2)) ** 2
    L0r = math.radians(L0)
    E = (y_ * math.sin(2 * L0r) - 2 * e * math.sin(M)
         + 4 * e * y_ * math.sin(M) * math.cos(2 * L0r)
         - 0.5 * y_ * y_ * math.sin(4 * L0r) - 1.25 * e * e * math.sin(2 * M))
    return math.degrees(E) * 4.0

# 常用出生地经度表（东经，度）。未收录者用 --lon 直接给经度。
CITY_LON = {
    "北京":116.41,"上海":121.47,"天津":117.20,"重庆":106.55,"广州":113.26,"深圳":114.06,
    "珠海":113.55,"东莞":113.75,"佛山":113.12,"中山":113.39,"惠州":114.42,"汕头":116.68,
    "杭州":120.15,"宁波":121.55,"温州":120.70,"南京":118.80,"苏州":120.62,"无锡":120.30,
    "常州":119.95,"徐州":117.18,"合肥":117.28,"福州":119.30,"厦门":118.09,"泉州":118.59,
    "南昌":115.89,"宜春":114.42,"赣州":114.93,"九江":115.99,
    "吉安":114.99,"上饶":117.97,"抚州":116.36,"萍乡":113.85,"新余":114.93,"鹰潭":117.07,
    "景德镇":117.18,"济南":117.00,"青岛":120.38,"烟台":121.39,"潍坊":119.10,"郑州":113.62,
    "洛阳":112.45,"武汉":114.31,"长沙":112.94,"衡阳":112.57,"株洲":113.13,"常德":111.69,
    "成都":104.07,"绵阳":104.68,"贵阳":106.71,"昆明":102.83,"西安":108.94,"太原":112.55,
    "石家庄":114.51,"沈阳":123.43,"大连":121.62,"长春":125.32,"哈尔滨":126.53,"呼和浩特":111.75,
    "银川":106.23,"西宁":101.78,"兰州":103.82,"乌鲁木齐":87.62,"喀什":75.99,"拉萨":91.11,
    "南宁":108.37,"桂林":110.29,"柳州":109.42,"海口":110.20,"三亚":109.51,"香港":114.17,
    "澳门":113.55,"台北":121.52,"高雄":120.30,
}

def resolve_lon(place=None, lon=None):
    if lon is not None:
        return float(lon), f"手动指定经度 {lon}°E"
    if place:
        for k, v in CITY_LON.items():
            if k in place:
                return v, f"{k}（东经{v}°）"
    return 120.0, "未识别出生地，按东经120°（北京时间基准）处理，未作真太阳时校正"

# ---------------------------------------------------------------- 历法（节气/农历）

def ensure_lunar_lib():
    """历法库加载顺序：随包 vendor/ → 环境已装 → pip 安装（最后手段）。

    vendor/ 已内置 lunar-python（纯 Python，约 1.1MB），因此本技能默认
    完全离线运行：不需要联网、不需要 pip、不触发沙箱审批。
    """
    import os
    vendor = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vendor")
    if os.path.isdir(os.path.join(vendor, "lunar_python")) and vendor not in sys.path:
        sys.path.insert(0, vendor)
    try:
        import lunar_python  # noqa
        return True
    except ImportError:
        pass
    for mirror in ("https://pypi.tuna.tsinghua.edu.cn/simple", None):
        cmd = [sys.executable, "-m", "pip", "install", "lunar-python",
               "--break-system-packages", "-q"]
        if mirror:
            cmd += ["-i", mirror]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=180)
            import lunar_python  # noqa
            return True
        except Exception:
            continue
    return False


HAS_LUNAR = ensure_lunar_lib()

JIE12 = ["立春","惊蛰","清明","立夏","芒种","小暑","立秋","白露","寒露","立冬","大雪","小寒"]
JIE_MONTH_ZHI = ["寅","卯","辰","巳","午","未","申","酉","戌","亥","子","丑"]

def solar_longitude(jd):
    """太阳视黄经（度），Meeus 简算，误差约 0.01°。仅在无 lunar-python 时兜底。"""
    T = (jd - 2451545.0) / 36525.0
    L0 = 280.46646 + 36000.76983 * T + 0.0003032 * T * T
    M = math.radians(357.52911 + 35999.05029 * T - 0.0001537 * T * T)
    C = ((1.914602 - 0.004817 * T - 0.000014 * T * T) * math.sin(M)
         + (0.019993 - 0.000101 * T) * math.sin(2 * M) + 0.000289 * math.sin(3 * M))
    om = math.radians(125.04 - 1934.136 * T)
    return (L0 + C - 0.00569 - 0.00478 * math.sin(om)) % 360

@__import__("functools").lru_cache(maxsize=None)
def jieqi_table(year):
    """返回 {节名: (y,m,d,hour_float)}，覆盖该年 12 节 + 前后邻接。"""
    if HAS_LUNAR:
        from lunar_python import Solar
        out = {}
        for probe in (Solar.fromYmdHms(year, 6, 1, 12, 0, 0), Solar.fromYmdHms(year, 12, 1, 12, 0, 0)):
            for name, s in probe.getLunar().getJieQiTable().items():
                if name in JIE12:
                    out.setdefault((s.getYear(), name), (s.getYear(), s.getMonth(), s.getDay(),
                                                         s.getHour() + s.getMinute()/60 + s.getSecond()/3600))
        return {k[1]: v for k, v in out.items() if k[0] == year} or _jieqi_fallback(year)
    return _jieqi_fallback(year)

def _jieqi_fallback(year):
    out = {}
    for i, name in enumerate(JIE12):
        target = (315 + i * 30) % 360
        lo = jdn(year, 1, 1) - 0.5 + i * 30.0
        for _ in range(60):
            diff = (solar_longitude(lo) - target + 180) % 360 - 180
            lo -= diff / 0.9856
            if abs(diff) < 1e-6:
                break
        z = lo + 8 / 24.0 + 0.5          # 转北京时
        Z = int(z); F = z - Z
        a = Z + 32044; b = (4*a+3)//146097; c = a - 146097*b//4
        dd = (4*c+3)//1461; e = c - 1461*dd//4; mm = (5*e+2)//153
        day = e - (153*mm+2)//5 + 1; month = mm + 3 - 12*(mm//10); yr = 100*b + dd - 4800 + mm//10
        out[name] = (yr, month, day, F * 24)
    return out

def lunar_to_solar(ly, lm, ld, leap=False):
    if not HAS_LUNAR:
        raise RuntimeError("农历转换需要 lunar-python，请先安装：pip install lunar-python")
    from lunar_python import Lunar
    s = Lunar.fromYmdHms(ly, -lm if leap else lm, ld, 12, 0, 0).getSolar()
    return s.getYear(), s.getMonth(), s.getDay()

def solar_to_lunar_str(y, m, d):
    if not HAS_LUNAR:
        return ""
    from lunar_python import Solar
    l = Solar.fromYmdHms(y, m, d, 12, 0, 0).getLunar()
    return f"{l.getYearInChinese()}年{l.getMonthInChinese()}月{l.getDayInChinese()}"

# ---------------------------------------------------------------- 四柱

def to_float_hour(h, mi):
    return h + mi / 60.0

def _cmp(a, b):
    return (a > b) - (a < b)

def four_pillars(y, m, d, hour, late_zi_new_day=True):
    """按真太阳时的 (y,m,d,hour) 定四柱。hour 为 0-24 浮点。"""
    tbl_prev, tbl, tbl_next = jieqi_table(y - 1), jieqi_table(y), jieqi_table(y + 1)
    now = (y, m, d, hour)

    # —— 年柱：以立春为界
    lc = tbl["立春"]
    year_for_gz = y if _cmp(now, lc) >= 0 else y - 1
    yi = (year_for_gz - 1984) % 60
    year_gz = GAN[yi % 10] + ZHI[yi % 12]

    # —— 月柱：以 12 节为界
    seq = []
    for name, base in ((n, tbl_prev) for n in JIE12):
        seq.append((base[name], name, y - 1))
    for name in JIE12:
        seq.append((tbl[name], name, y))
    for name in JIE12:
        seq.append((tbl_next[name], name, y + 1))
    seq.sort()
    cur = None
    for t, name, yy in seq:
        if _cmp(now, t) >= 0:
            cur = (t, name, yy)
        else:
            break
    jie_name = cur[1]
    month_zhi = JIE_MONTH_ZHI[JIE12.index(jie_name)]
    # 五虎遁：甲己之年丙作首
    ygi = GAN.index(year_gz[0])
    first = [2, 4, 6, 8, 0][ygi % 5]                  # 正月(寅)天干序号
    month_gan = GAN[(first + (ZHI.index(month_zhi) - 2) % 12) % 10]
    month_gz = month_gan + month_zhi

    # —— 日柱：儒略日；晚子时（23:00-24:00）按主流换日法归次日
    dy, dm, dd = y, m, d
    if hour >= 23 and late_zi_new_day:
        import datetime
        nd = datetime.date(y, m, d) + datetime.timedelta(days=1)
        dy, dm, dd = nd.year, nd.month, nd.day
    day_gz = day_ganzhi(dy, dm, dd)

    # —— 时柱：五鼠遁
    hz = ZHI[int(((hour + 1) % 24) // 2)]
    dgi = GAN.index(day_gz[0])
    hour_gan = GAN[((dgi % 5) * 2 + ZHI.index(hz)) % 10]
    hour_gz = hour_gan + hz

    return {"year": year_gz, "month": month_gz, "day": day_gz, "hour": hour_gz,
            "jie": jie_name, "jie_time": cur[0], "next_jie": seq[seq.index(cur) + 1] if cur else None,
            "prev_jie_time": cur[0], "used_date": (dy, dm, dd)}

# ---------------------------------------------------------------- 可用柱

def plist(p):
    """可用的柱 [(位, 干支)]；时辰不详时不含时柱。"""
    out = [("年", p["year"]), ("月", p["month"]), ("日", p["day"])]
    if p.get("hour"):
        out.append(("时", p["hour"]))
    return out

# ---------------------------------------------------------------- 旺衰评分

def strength(pillars):
    """返回 (帮我分, 耗我分, 判语, 明细)。月令权重最大。"""
    dg = pillars["day"][0]
    dwx = GAN_WX[GAN.index(dg)]
    helper = {dwx, [k for k, v in WX_SHENG.items() if v == dwx][0]}   # 同我 + 生我
    support = drain = 0.0
    detail = []
    weights = {"year_g":0.8,"month_g":1.0,"hour_g":0.8,
               "year_z":1.0,"month_z":2.6,"day_z":1.6,"hour_z":1.0}
    for key, gz in [(k, pillars[k]) for k in ("year", "month", "day", "hour") if pillars.get(k)]:
        if key != "day":
            w = weights[key + "_g"]; wx = GAN_WX[GAN.index(gz[0])]
            (support if wx in helper else drain).__class__
            if wx in helper: support += w
            else: drain += w
            detail.append((f"{key}干 {gz[0]}({wx})", round(w, 2), "帮" if wx in helper else "耗"))
        w = weights[key + "_z"]
        for hg, ratio in HIDDEN[gz[1]]:
            wx = GAN_WX[GAN.index(hg)]
            s = w * ratio
            if wx in helper: support += s
            else: drain += s
            detail.append((f"{key}支 {gz[1]}藏{hg}({wx})", round(s, 2), "帮" if wx in helper else "耗"))
    ratio = support / (support + drain)
    if ratio >= 0.62: verdict = "身极旺"
    elif ratio >= 0.52: verdict = "身旺"
    elif ratio >= 0.45: verdict = "中和"
    elif ratio >= 0.34: verdict = "身弱"
    else: verdict = "身极弱"
    return round(support, 2), round(drain, 2), verdict, detail

# ---------------------------------------------------------------- 结构：刑冲合害

LIUHE = {("子","丑"),("寅","亥"),("卯","戌"),("辰","酉"),("巳","申"),("午","未")}
LIUCHONG = {("子","午"),("丑","未"),("寅","申"),("卯","酉"),("辰","戌"),("巳","亥")}
LIUHAI = {("子","未"),("丑","午"),("寅","巳"),("卯","辰"),("申","亥"),("酉","戌")}
SANHE = {("申","子","辰"):"水",("亥","卯","未"):"木",("寅","午","戌"):"火",("巳","酉","丑"):"金"}
SANHUI = {("寅","卯","辰"):"木",("巳","午","未"):"火",("申","酉","戌"):"金",("亥","子","丑"):"水"}
XING = [(("寅","巳","申"),"无恩之刑"),(("丑","戌","未"),"恃势之刑"),(("子","卯"),"无礼之刑")]
SELF_XING = {"辰","午","酉","亥"}

def branch_relations(zhis):
    names = ["年","月","日","时"][:len(zhis)]
    out = []
    pairs = [(i, j) for i in range(len(zhis)) for j in range(i + 1, len(zhis))]
    for i, j in pairs:
        a, b = zhis[i], zhis[j]
        key = tuple(sorted((a, b), key=lambda x: ZHI.index(x)))
        for s, label in ((LIUCHONG,"相冲"),(LIUHE,"六合"),(LIUHAI,"相害")):
            if key in s or (key[1], key[0]) in s:
                out.append({"type": label, "detail": f"{names[i]}{a} {label} {names[j]}{b}",
                            "pos": [names[i], names[j]]})
        if a == b and a in SELF_XING:
            out.append({"type": "自刑", "detail": f"{names[i]}{a} 自刑 {names[j]}{b}", "pos": [names[i], names[j]]})
        elif a == b:
            out.append({"type": "伏吟", "detail": f"{names[i]}{a} 伏吟 {names[j]}{b}", "pos": [names[i], names[j]]})
    s = set(zhis)
    for combo, wx in SANHUI.items():
        if set(combo) <= s:
            out.append({"type": "三会", "detail": f"{''.join(combo)} 三会{wx}局（力最强）", "wx": wx})
    for combo, wx in SANHE.items():
        if set(combo) <= s:
            out.append({"type": "三合", "detail": f"{''.join(combo)} 三合{wx}局", "wx": wx})
        else:
            inter = set(combo) & s
            if len(inter) == 2 and combo[1] in inter:      # 半合须带旺神（中神）
                out.append({"type": "半合", "detail": f"{''.join(sorted(inter, key=lambda x: combo.index(x)))} 半合{wx}局", "wx": wx})
    for combo, label in XING:
        if set(combo) <= s:
            out.append({"type": "三刑", "detail": f"{''.join(combo)} 三刑（{label}）"})
        elif len(set(combo) & s) == 2 and len(combo) == 3:
            out.append({"type": "半刑", "detail": f"{''.join(sorted(set(combo) & s, key=lambda x: combo.index(x)))} 相刑（{label}，缺一不全）"})
    # 天干五合
    return out

TIANGAN_HE = {("甲","己"):"土",("乙","庚"):"金",("丙","辛"):"水",("丁","壬"):"木",("戊","癸"):"火"}

def stem_relations(gans):
    names = ["年","月","日","时"][:len(gans)]
    out = []
    for i in range(len(gans)):
        for j in range(i + 1, len(gans)):
            a, b = gans[i], gans[j]
            for (x, y), wx in TIANGAN_HE.items():
                if {a, b} == {x, y}:
                    adj = "（紧贴）" if j - i == 1 else "（遥合）"
                    out.append({"type": "天干五合", "detail": f"{names[i]}{a} 合 {names[j]}{b}，合化{wx}{adj}", "wx": wx})
    return out

# ---------------------------------------------------------------- 神煞

TIANYI = {"甲":"丑未","乙":"子申","丙":"亥酉","丁":"亥酉","戊":"丑未",
          "己":"子申","庚":"丑未","辛":"寅午","壬":"卯巳","癸":"卯巳"}
LU = dict(zip(GAN, "寅卯巳午巳午申酉亥子"))
YANGREN = {"甲":"卯","丙":"午","戊":"午","庚":"酉","壬":"子",
           "乙":"寅","丁":"巳","己":"巳","辛":"申","癸":"亥"}
JINYU = dict(zip(GAN, "辰巳未申未申戌亥丑寅"))
WENCHANG = dict(zip(GAN, "巳午申酉申酉亥子寅卯"))
SANHE_GROUP = {"申子辰":("子","辰","寅","酉"), "亥卯未":("卯","未","巳","子"),
               "寅午戌":("午","戌","申","卯"), "巳酉丑":("酉","丑","亥","午")}
# 每组 -> (将星, 华盖, 驿马, 桃花)

XUN_KONG = {}
for _i in range(60):
    _g, _z = _i % 10, _i % 12
    _kong = ((_z - _g) % 12 + 10) % 12
    XUN_KONG[GAN[_g] + ZHI[_z]] = ZHI[_kong] + ZHI[(_kong + 1) % 12]

KUIGANG = {"庚辰", "庚戌", "壬辰", "戊戌"}

def shensha(p):
    dg, dz = p["day"][0], p["day"][1]
    yz = p["year"][1]
    names = [n for n, _ in plist(p)]
    zhis = [gz[1] for _, gz in plist(p)]
    out = []
    def add(name, targets, desc):
        hit = [f"{names[i]}支{z}" for i, z in enumerate(zhis) if z in targets]
        if hit:
            out.append({"name": name, "at": "、".join(hit), "desc": desc})
    add("天乙贵人", TIANYI[dg], "第一吉星。主人缘好、遇难有人扶、逢凶化吉")
    add("禄神", LU[dg], "主自力得财、衣食有靠、有实权实利")
    add("羊刃", YANGREN.get(dg, ""), "主性刚、有魄力、争强好胜；身旺则易过刚")
    add("金舆", JINYU[dg], "主得配偶或家庭之实助、有安稳之资")
    add("文昌", WENCHANG[dg], "主聪慧好学、利考试文书")
    for grp, (jiang, huagai, yima, taohua) in SANHE_GROUP.items():
        if yz in grp or dz in grp:
            add("将星", jiang, "主有主见、不甘居人下、有主导欲")
            add("华盖", huagai, "主清高好独处、近文史哲与传统学问、心思深")
            add("驿马", yima, "主奔波变动、迁徙外出、不宜久守一地")
            add("桃花", taohua, "主人缘好、有魅力、异性缘佳")
            break
    kong = XUN_KONG[p["day"]]
    hit = [f"{names[i]}支{z}" for i, z in enumerate(zhis) if z in kong and i != 2]
    out.append({"name": "空亡", "at": "、".join(hit) if hit else f"空{kong}（原局不见，不落空）",
                "desc": "落空之宫位主有名无实、得而复失；逢冲逢合则解"})
    if p["day"] in KUIGANG:
        out.append({"name": "魁罡", "at": f"日柱{p['day']}",
                    "desc": "主聪明果断、有权威领导力；性刚好胜，喜身旺，忌财官显露"})
    return out

# ---------------------------------------------------------------- 调候（穷通宝鉴速查）

TIAOHOU = {
 "甲":{"寅":"丙、癸","卯":"庚、丙、丁、戊、己","辰":"庚、丁、壬","巳":"癸、丁、庚","午":"癸、丁、庚",
       "未":"癸、丁、庚","申":"庚、丁、壬","酉":"庚、丁、丙","戌":"庚、甲、丁、壬、癸","亥":"庚、丁、丙、戊",
       "子":"丁、庚、丙","丑":"丁、庚、丙"},
 "乙":{"寅":"丙、癸","卯":"丙、癸","辰":"癸、丙、戊","巳":"癸","午":"癸、丙","未":"癸、丙",
       "申":"丙、癸、己","酉":"癸、丙、丁","戌":"癸、辛","亥":"丙、戊","子":"丙","丑":"丙"},
 "丙":{"寅":"壬、庚","卯":"壬、己","辰":"壬、甲","巳":"壬、庚、癸","午":"壬、庚","未":"壬、庚",
       "申":"壬、戊","酉":"壬、癸","戌":"甲、壬","亥":"甲、戊、庚、壬","子":"壬、戊、己","丑":"壬、甲"},
 "丁":{"寅":"甲、庚","卯":"庚、甲","辰":"甲、庚","巳":"甲、庚","午":"壬、庚、癸","未":"甲、壬、庚",
       "申":"甲、庚、丙、戊","酉":"甲、庚、丙、戊","戌":"甲、庚、戊","亥":"甲、庚","子":"甲、庚","丑":"甲、庚"},
 "戊":{"寅":"丙、甲、癸","卯":"丙、甲、癸","辰":"甲、丙、癸","巳":"甲、丙、癸","午":"壬、甲、丙","未":"癸、丙、甲",
       "申":"丙、癸、甲","酉":"丙、癸","戌":"甲、丙、癸","亥":"甲、丙","子":"丙、甲","丑":"丙、甲"},
 "己":{"寅":"丙、庚、甲","卯":"甲、癸、丙","辰":"丙、癸、甲","巳":"癸、丙","午":"癸、丙","未":"癸、丙",
       "申":"丙、癸","酉":"丙、癸","戌":"甲、丙、癸","亥":"丙、甲、戊","子":"丙、甲、戊","丑":"丙、甲、戊"},
 "庚":{"寅":"戊、甲、壬、丙、丁","卯":"丁、甲、庚、丙","辰":"甲、丁、壬、癸","巳":"壬、戊、丙、丁","午":"壬、癸",
       "未":"丁、甲","申":"丁、甲","酉":"丁、甲、丙","戌":"甲、壬","亥":"丁、丙","子":"丁、甲、丙","丑":"丙、丁、甲"},
 "辛":{"寅":"己、壬、庚","卯":"壬、甲","辰":"壬、甲","巳":"壬、甲、癸","午":"壬、己、癸","未":"壬、庚、甲",
       "申":"壬、甲、戊","酉":"壬、甲","戌":"壬、甲","亥":"壬、丙","子":"丙、戊、壬、甲","丑":"丙、壬、戊、己"},
 "壬":{"寅":"庚、丙、戊","卯":"戊、辛、庚","辰":"甲、庚","巳":"壬、辛、庚、癸","午":"癸、庚、辛","未":"辛、甲",
       "申":"戊、丁","酉":"甲、庚","戌":"甲、丙","亥":"戊、庚、丙","子":"戊、丙","丑":"丙、丁、甲"},
 "癸":{"寅":"辛、丙","卯":"庚、辛","辰":"丙、辛、甲","巳":"辛","午":"庚、壬、癸","未":"庚、辛、壬、癸",
       "申":"丁","酉":"辛、丙","戌":"辛、甲、壬、癸","亥":"庚、辛、戊、丁","子":"丙、辛","丑":"丙、丁"},
}

# ---------------------------------------------------------------- 大运

def dayun(p, gender, birth, true_hour, n=8):
    """gender: 'male'/'female'。返回起运与 n 步大运。"""
    y, m, d = birth
    yg = GAN.index(p["year"][0])
    yang_year = yg % 2 == 0
    forward = (yang_year and gender == "male") or ((not yang_year) and gender == "female")

    tbl_p, tbl, tbl_n = jieqi_table(y - 1), jieqi_table(y), jieqi_table(y + 1)
    all_j = sorted([(v, k) for t in (tbl_p, tbl, tbl_n) for k, v in t.items()])
    now = (y, m, d, true_hour)
    prev_t = next_t = None
    for t, name in all_j:
        if _cmp(now, t) >= 0: prev_t = t
        elif next_t is None: next_t = t
    def to_jd(t): return jdn(t[0], t[1], t[2]) + t[3] / 24.0
    now_jd = jdn(y, m, d) + true_hour / 24.0
    days = (to_jd(next_t) - now_jd) if forward else (now_jd - to_jd(prev_t))
    total_days = days / 3.0 * 365.2422          # 三日折一年
    start_years = total_days / 365.2422
    yrs = int(start_years); mos = int((start_years - yrs) * 12); dys = int((((start_years - yrs) * 12) - mos) * 30)

    idx = GAN.index(p["month"][0]) * 0 + 0
    mg, mz = GAN.index(p["month"][0]), ZHI.index(p["month"][1])
    steps = []
    for i in range(1, n + 1):
        k = i if forward else -i
        gz = GAN[(mg + k) % 10] + ZHI[(mz + k) % 12]
        sy = y + yrs + (1 if mos or dys else 0) + (i - 1) * 10
        steps.append({"gz": gz, "start_year": sy, "end_year": sy + 9,
                      "start_age": yrs + (i - 1) * 10, "xu_age": yrs + (i - 1) * 10 + 1})
    return {"forward": forward, "start": f"{yrs}岁{mos}个月{dys}天",
            "start_years_float": round(start_years, 3), "steps": steps}

# ---------------------------------------------------------------- 十二长生

CHANGSHENG = ["长生","沐浴","冠带","临官","帝旺","衰","病","死","墓","绝","胎","养"]
CS_START = dict(zip(GAN, "亥午寅酉寅酉巳子申卯"))   # 各天干长生所在地支

def twelve_stage(gan, zhi):
    start = ZHI.index(CS_START[gan])
    step = 1 if GAN_YY[GAN.index(gan)] == 1 else -1     # 阳顺阴逆
    return CHANGSHENG[((ZHI.index(zhi) - start) * step) % 12]

# ---------------------------------------------------------------- 喜忌评分

def default_yongji(pillars, verdict):
    """由旺衰自动推导默认喜忌；Claude 可用 --yong/--ji 覆盖。"""
    dwx = GAN_WX[GAN.index(pillars["day"][0])]
    sheng_me = [k for k, v in WX_SHENG.items() if v == dwx][0]   # 生我
    wo_sheng = WX_SHENG[dwx]                                      # 我生
    wo_ke = WX_KE[dwx]                                            # 我克
    ke_wo = [k for k, v in WX_KE.items() if v == dwx][0]          # 克我
    if verdict in ("身旺", "身极旺"):
        return [wo_sheng, wo_ke, ke_wo], [sheng_me, dwx]
    if verdict in ("身弱", "身极弱"):
        return [sheng_me, dwx], [wo_sheng, wo_ke, ke_wo]
    return [wo_sheng, wo_ke], [sheng_me]

def _rel_of(a, b):
    key = tuple(sorted((a, b), key=lambda x: ZHI.index(x)))
    if key in LIUCHONG: return "冲"
    if key in LIUHE:    return "合"
    if key in LIUHAI:   return "害"
    if a == b:          return "自刑" if a in SELF_XING else "伏吟"
    for combo, _ in XING:
        if a in combo and b in combo and a != b and len(combo) == 3: return "刑"
        if len(combo) == 2 and {a, b} == set(combo): return "刑"
    return ""

def score_gz(gz, yong, ji, pillars, dayun_gz=None):
    """给任一干支（流年/流月/流日）打分并列出与原局的关系。"""
    gan, zhi = gz[0], gz[1]
    s = 0.0
    wx = GAN_WX[GAN.index(gan)]
    s += 2.0 if wx in yong else (-2.0 if wx in ji else 0.0)
    for hg, w in HIDDEN[zhi]:
        w2 = GAN_WX[GAN.index(hg)]
        s += 2.4 * w * (1 if w2 in yong else (-1 if w2 in ji else 0))
    rels = []
    names = [n for n, _ in plist(pillars)]
    zhis = [gz[1] for _, gz in plist(pillars)]
    for i, z in enumerate(zhis):
        r = _rel_of(zhi, z)
        if not r:
            continue
        rels.append(f"{r}{names[i]}支{z}")
        base = {"冲": -1.4, "刑": -0.9, "害": -0.7, "自刑": -0.9, "伏吟": -0.6, "合": 0.4}[r]
        if i == 2:                       # 日支为自身与配偶宫，加重
            base *= 1.5
        s += base
    if dayun_gz:
        r = _rel_of(zhi, dayun_gz[1])
        if r in ("冲", "刑"):
            # 天克地冲大运，主动荡
            gk = WX_KE.get(GAN_WX[GAN.index(gan)]) == GAN_WX[GAN.index(dayun_gz[0])]
            rels.append(("天克地冲大运" if (r == "冲" and gk) else f"{r}大运") + dayun_gz)
            s += -1.8 if (r == "冲" and gk) else -1.0
    if s >= 3.0:   j = "大吉"
    elif s >= 1.2: j = "吉"
    elif s >= -1.2: j = "平"
    elif s >= -3.0: j = "需谨慎"
    else:           j = "不利"
    return round(s, 2), j, rels

def liunian(pillars, yong, ji, dy, start_year, n=12):
    out = []
    for y in range(start_year, start_year + n):
        idx = (y - 1984) % 60
        gz = GAN[idx % 10] + ZHI[idx % 12]
        cur = next((s for s in dy["steps"] if s["start_year"] <= y <= s["end_year"]), None)
        sc, j, rels = score_gz(gz, yong, ji, pillars, cur["gz"] if cur else None)
        dg = pillars["day"][0]
        out.append({"year": y, "gz": gz,
                    "gan_god": ten_god(dg, gz[0]),
                    "zhi_god": ten_god(dg, HIDDEN[gz[1]][0][0]),
                    "stage": twelve_stage(dg, gz[1]),
                    "dayun": cur["gz"] if cur else "", "score": sc, "judge": j,
                    "relations": rels})
    return out

def liuyue(pillars, yong, ji, dy, year):
    """按节气分月，返回 12 个月的流月。"""
    tbl, tbl_n = jieqi_table(year), jieqi_table(year + 1)
    idx = (year - 1984) % 60
    ygan = GAN[idx % 10]
    first = [2, 4, 6, 8, 0][GAN.index(ygan) % 5]
    cur = next((s for s in dy["steps"] if s["start_year"] <= year <= s["end_year"]), None)
    dg = pillars["day"][0]
    out = []
    for i, jie in enumerate(JIE12):
        mz = JIE_MONTH_ZHI[i]
        mg = GAN[(first + (ZHI.index(mz) - 2) % 12) % 10]
        gz = mg + mz
        # 干支年 Y 的十二节：立春~大雪在 Y 年内，丑月之首「小寒」落在 Y+1 年 1 月
        t = tbl_n["小寒"] if jie == "小寒" else tbl[jie]
        sc, j, rels = score_gz(gz, yong, ji, pillars, cur["gz"] if cur else None)
        out.append({"jie": jie, "gz": gz, "zhi": mz,
                    "start": f"{t[1]:02d}-{t[2]:02d} {int(t[3]):02d}:{int((t[3]%1)*60):02d}",
                    "gan_god": ten_god(dg, mg), "score": sc, "judge": j, "relations": rels})
    return {"year": year, "year_gz": GAN[idx % 10] + ZHI[idx % 12], "months": out}

DAY_TIPS = {
    "冲日支": "冲身宫——忌重大决断、签约、远行；宜静守、处理已定之事",
    "自刑日支": "自刑——易钻牛角尖、反复纠结；忌情绪化决定，宜把事写下来再判断",
    "刑日支": "刑身宫——易有摩擦与是非；说话留余地，忌争辩",
    "害日支": "害身宫——暗损，事情未必摊开却在消耗；留意被动承诺",
    "伏吟日支": "伏吟——旧事重提、同类问题再现；宜复盘，忌新开局面",
    "合日支": "合身宫——易得配合与机缘；适合谈事、见人、推进合作",
    "冲年支": "与长辈、家族相关之事易起波澜，沟通宜缓",
    "刑年支": "与长辈或原生家庭易有摩擦，避免翻旧账",
    "冲月支": "工作与本职环境变动，宜稳；不宜主动求变",
    "刑月支": "同事、上级之间易生嫌隙，事务按流程走",
    "冲时支": "子女、晚辈、晚间安排易有变，注意作息",
    "刑时支": "子女或晚辈之事需多留心，晚间勿过劳",
}

def liuri(pillars, yong, ji, dy, start, days=30):
    """start = (y,m,d)"""
    import datetime
    d0 = datetime.date(*start)
    dg = pillars["day"][0]
    names = [n for n, _ in plist(pillars)]
    zhis = [gz[1] for _, gz in plist(pillars)]
    out = []
    for k in range(days):
        d = d0 + datetime.timedelta(days=k)
        gz = day_ganzhi(d.year, d.month, d.day)
        cur = next((s for s in dy["steps"] if s["start_year"] <= d.year <= s["end_year"]), None)
        sc, j, rels = score_gz(gz, yong, ji, pillars, cur["gz"] if cur else None)
        tips = []
        for i, z in enumerate(zhis):
            r = _rel_of(gz[1], z)
            key = f"{r}{names[i]}支"
            if key in DAY_TIPS:
                tips.append(DAY_TIPS[key])
        if j == "大吉" and not any("宜" in t for t in tips):
            tips.insert(0, "全日五行俱合喜用——宜办要事：签约、面谈、提案、出行")
        if not tips:
            wx = GAN_WX[GAN.index(gz[0])]
            if wx in yong:
                tips.append("日干为喜——宜推进、表达、谈事、拜访")
            elif wx in ji:
                tips.append("日干为忌——宜守成，忌大额支出与临时起意")
            else:
                tips.append("平顺之日，按既定安排行事")
        out.append({"date": d.isoformat(), "md": f"{d.month}/{d.day}",
                    "weekday": "一二三四五六日"[d.weekday()], "gz": gz,
                    "gan_god": ten_god(dg, gz[0]), "stage": twelve_stage(dg, gz[1]),
                    "score": sc, "judge": j, "relations": rels, "tips": tips})
    return out

# ---------------------------------------------------------------- 其他解析

WX_NUM = {"木": "3、8", "火": "2、7", "土": "5、0", "金": "4、9", "水": "1、6"}
WX_DIR = {"木": "东", "火": "南", "土": "中部、西南", "金": "西", "水": "北"}
WX_COLOR_CN = {"木": "青、绿", "火": "红、橙、紫", "土": "黄、褐、米",
               "金": "白、银、灰", "水": "黑、深蓝"}
SHENGXIAO = "鼠牛虎兔龙蛇马羊猴鸡狗猪"

def extras(p, yong, ji, y, m, d, hh=12, mi=0):
    dg = p["day"][0]
    # 胎元：月干进一、月支进三
    ty = GAN[(GAN.index(p["month"][0]) + 1) % 10] + ZHI[(ZHI.index(p["month"][1]) + 3) % 12]
    mg = sg = ""
    if HAS_LUNAR:
        try:
            from lunar_python import Solar
            if p.get("hour"):                       # 命宫、身宫须用出生时辰
                ec = Solar.fromYmdHms(y, m, d, hh, mi, 0).getLunar().getEightChar()
                mg, sg = ec.getMingGong(), ec.getShenGong()
        except Exception:
            pass
    stages = [{"pos": lab, "zhi": gz[1], "stage": twelve_stage(dg, gz[1])} for lab, gz in plist(p)]
    return {
        "taiyuan": ty, "minggong": mg, "shengong": sg,
        "shengxiao": SHENGXIAO[ZHI.index(p["year"][1])],
        "stages": stages,
        "lucky": {
            "numbers": "、".join(WX_NUM[w] for w in yong),
            "directions": "、".join(WX_DIR[w] for w in yong),
            "colors": "、".join(WX_COLOR_CN[w] for w in yong),
            "avoid_directions": "、".join(WX_DIR[w] for w in ji),
            "avoid_colors": "、".join(WX_COLOR_CN[w] for w in ji),
        },
    }

# ---------------------------------------------------------------- 组装

def build(args):
    # --- 日期
    leap = False
    if args.lunar:
        parts = args.lunar.replace("/", "-").split("-")
        ly, lm, ld = int(parts[0]), int(parts[1]), int(parts[2])
        if args.leap: leap = True
        y, m, d = lunar_to_solar(ly, lm, ld, leap)
        src = f"农历{ly}年{'闰' if leap else ''}{lm}月{ld}日 → 公历{y}-{m:02d}-{d:02d}"
    else:
        y, m, d = [int(x) for x in args.date.replace("/", "-").split("-")]
        src = f"公历{y}-{m:02d}-{d:02d}"
    time_known = args.time.strip().lower() not in ("unknown", "未知", "none", "?", "不详")
    if time_known:
        hh, mm_ = [int(x) for x in args.time.split(":")]
    else:
        hh, mm_ = 12, 0                         # 时辰不详：以当日正午定三柱，再逐段扫描全天
    clock = to_float_hour(hh, mm_)

    # --- 真太阳时
    lon, lon_note = resolve_lon(args.place, args.lon)
    lon_min = (lon - 120.0) * 4.0
    eot = equation_of_time(y, m, d, clock)
    delta = lon_min + eot                       # 分钟
    tsy, tsm, tsd, tsh = y, m, d, clock + delta / 60.0
    import datetime
    if tsh < 0:
        nd = datetime.date(y, m, d) - datetime.timedelta(days=1); tsy, tsm, tsd, tsh = nd.year, nd.month, nd.day, tsh + 24
    elif tsh >= 24:
        nd = datetime.date(y, m, d) + datetime.timedelta(days=1); tsy, tsm, tsd, tsh = nd.year, nd.month, nd.day, tsh - 24

    p = four_pillars(tsy, tsm, tsd, tsh)
    pb = four_pillars(tsy, tsm, tsd, tsh, late_zi_new_day=False)

    # —— 时辰不详：扫描当天钟表 0:00–23:59，看三柱是否在当天内变化（交节、子时换日）
    segments = []
    if not time_known:
        def _ts(c):
            dl = lon_min + equation_of_time(y, m, d, c)
            ty, tm, td, th = y, m, d, c + dl / 60.0
            if th < 0:
                nd = datetime.date(y, m, d) - datetime.timedelta(days=1); ty, tm, td, th = nd.year, nd.month, nd.day, th + 24
            elif th >= 24:
                nd = datetime.date(y, m, d) + datetime.timedelta(days=1); ty, tm, td, th = nd.year, nd.month, nd.day, th - 24
            return ty, tm, td, th
        for mins in range(0, 1440):
            q = four_pillars(*_ts(mins / 60.0))
            key = (q["year"], q["month"], q["day"])
            lab = f"{mins // 60:02d}:{mins % 60:02d}"
            if segments and segments[-1]["key"] == key:
                segments[-1]["to"] = lab
            else:
                segments.append({"key": key, "from": lab, "to": lab})
        for sg_ in segments:
            sg_["year"], sg_["month"], sg_["day"] = sg_.pop("key")
            sg_["main"] = (sg_["year"], sg_["month"], sg_["day"]) == (p["year"], p["month"], p["day"])
        p["hour"] = None
        pb = p

    gans = [gz[0] for _, gz in plist(p)]
    zhis = [gz[1] for _, gz in plist(p)]
    dg = p["day"][0]

    cols = []
    for i, (label, gz) in enumerate((n + "柱", gz) for n, gz in plist(p)):
        idx60 = (GAN.index(gz[0]) - ZHI.index(gz[1])) % 2
        n60 = None
        for k in range(60):
            if GAN[k % 10] + ZHI[k % 12] == gz: n60 = k; break
        cols.append({
            "label": label, "gz": gz, "gan": gz[0], "zhi": gz[1],
            "gan_wx": GAN_WX[GAN.index(gz[0])], "zhi_wx": ZHI_WX[ZHI.index(gz[1])],
            "gan_god": "日主" if i == 2 else ten_god(dg, gz[0]),
            "zhi_hidden": [{"gan": hg, "god": ten_god(dg, hg), "wx": GAN_WX[GAN.index(hg)],
                            "weight": w} for hg, w in HIDDEN[gz[1]]],
            "nayin": NAYIN[n60 // 2], "hour_range": ZHI_HOUR[ZHI.index(gz[1])] if i == 3 else "",
        })

    # 五行统计（含藏干加权）
    wx_count = {k: 0.0 for k in "木火土金水"}
    for _, gz in plist(p):
        wx_count[GAN_WX[GAN.index(gz[0])]] += 1.0
        for hg, w in HIDDEN[gz[1]]:
            wx_count[GAN_WX[GAN.index(hg)]] += w
    wx_count = {k: round(v, 2) for k, v in wx_count.items()}

    # 十神统计
    god_count = {}
    for n, gz in plist(p):
        if n == "日":
            continue
        god_count[ten_god(dg, gz[0])] = god_count.get(ten_god(dg, gz[0]), 0) + 1
    for _, gz in plist(p):
        for hg, w in HIDDEN[gz[1]]:
            g = ten_god(dg, hg)
            god_count[g] = god_count.get(g, 0) + 1

    sup, dr, verdict, detail = strength(p)

    # —— 时辰不详：把 12 个可能的时柱逐一代入，看旺衰判语是否稳定
    hour_scan = []
    if not time_known:
        dgi = GAN.index(p["day"][0])
        for k, hz in enumerate(ZHI):
            hgz = GAN[((dgi % 5) * 2 + k) % 10] + hz
            q = dict(p); q["hour"] = hgz
            s_, d_, v_, _ = strength(q)
            hour_scan.append({"hour": hgz, "range": ZHI_HOUR[k], "ratio": round(s_ / (s_ + d_), 3), "verdict": v_})

    # 临界提示
    warnings = []
    jt = p["jie_time"]
    gap_h = abs((jdn(tsy,tsm,tsd)+tsh/24.0) - (jdn(jt[0],jt[1],jt[2])+jt[3]/24.0)) * 24
    if not time_known:
        warnings.append("★ 时辰不详：本盘只排年、月、日三柱，时柱空缺。子女、晚年、命宫身宫，以及与时柱相关的"
                        "神煞、刑冲合害一律不下结论；旺衰与喜用按三柱评定——若三柱接近临界，补上时柱后结论可能改变。"
                        "起运岁数按当日正午估算，误差在两个月以内。")
        for sg_ in segments:
            if sg_["main"]:
                continue
            diff = "、".join(n for n, k in (("年柱", "year"), ("月柱", "month"), ("日柱", "day")) if sg_[k] != p[k])
            why = "子时换日" if diff == "日柱" else "交节"
            warnings.append(f"★ 若出生在钟表 {sg_['from']}–{sg_['to']}（北京时间），因{why}，三柱为 "
                            f"{sg_['year']} {sg_['month']} {sg_['day']}（{diff}不同）。本盘按当天其余时段的 "
                            f"{p['year']} {p['month']} {p['day']} 排，请先确认出生是否落在这一时段。")
    elif gap_h < 12:
        warnings.append(f"★ 出生时刻距【{p['jie']}】交节仅 {gap_h:.1f} 小时，月柱处于临界。"
                        f"若出生时间记录有出入，月柱可能变动，须核对出生证明。")
    if time_known and (23 <= tsh or tsh < 1):
        if p["day"] != pb["day"]:
            warnings.append(f"★ 真太阳时落在子时（{tsh:.2f}时）且跨日界。主流「子时换日」得 {p['day']}日{p['hour']}时；"
                            f"少数派「夜子时不换日」得 {pb['day']}日{pb['hour']}时。本盘采用主流算法，"
                            f"两者日主不同，结论差异极大，建议核对。")
    if time_known and abs(delta) > 45:
        warnings.append(f"★ 真太阳时校正达 {delta:.0f} 分钟，时柱受影响明显，务必确认出生地与时间。")
    if not HAS_LUNAR:
        warnings.append("⚠ 未能安装 lunar-python，节气采用内置近似算法（误差约±15分钟），临界个案请人工复核。")

    dy = dayun(p, args.gender, (tsy, tsm, tsd), tsh, n=args.dayun_steps)

    # —— 喜忌：命令行优先，否则由旺衰自动推导
    yong = [x.strip() for x in args.yong.split(",") if x.strip()] if args.yong else None
    ji = [x.strip() for x in args.ji.split(",") if x.strip()] if args.ji else None
    auto_y, auto_j = default_yongji(p, verdict)
    yong, ji = yong or auto_y, ji or auto_j

    import datetime as _dt
    today = _dt.date.today()
    ln = liunian(p, yong, ji, dy, args.liunian_from or today.year, args.liunian)
    ly = liuyue(p, yong, ji, dy, args.liuyue_year or today.year)
    if args.liuri_from:
        _s = tuple(int(x) for x in args.liuri_from.split("-"))
    else:
        _s = (today.year, today.month, today.day)
    lr = liuri(p, yong, ji, dy, _s, args.liuri)
    ex = extras(p, yong, ji, tsy, tsm, tsd, int(tsh), int((tsh % 1) * 60))   # 命宫、身宫按真太阳时定时辰

    return {
        "time_known": time_known,
        "three_pillar_segments": segments,
        "hour_scan": hour_scan,
        "input": {"source": src, "clock_time": f"{hh:02d}:{mm_:02d}" if time_known else "时辰不详", "gender": args.gender,
                  "gender_cn": "男" if args.gender == "male" else "女",
                  "place": args.place or "", "lon_note": lon_note,
                  "lunar_str": solar_to_lunar_str(y, m, d)},
        "true_solar": {"lon_correction_min": round(lon_min, 1), "eot_min": round(eot, 1),
                       "total_min": round(delta, 1),
                       "time": f"{tsy}-{tsm:02d}-{tsd:02d} {int(tsh):02d}:{int((tsh%1)*60):02d}" if time_known else "时辰不详",
                       "hour_zhi": p["hour"][1] if p.get("hour") else None},
        "pillars": {"year": p["year"], "month": p["month"], "day": p["day"], "hour": p["hour"],
                    "day_master": dg, "day_master_wx": GAN_WX[GAN.index(dg)],
                    "month_ling": p["month"][1], "jie": p["jie"],
                    "jie_time": f"{jt[0]}-{jt[1]:02d}-{jt[2]:02d} {int(jt[3]):02d}:{int((jt[3]%1)*60):02d}"},
        "columns": cols,
        "wuxing": wx_count,
        "shishen_count": god_count,
        "strength": {"support": sup, "drain": dr, "ratio": round(sup/(sup+dr), 3),
                     "verdict": verdict, "detail": detail},
        "branch_relations": branch_relations(zhis),
        "stem_relations": stem_relations(gans),
        "shensha": shensha(p),
        "tiaohou": TIAOHOU.get(dg, {}).get(p["month"][1], ""),
        "dayun": dy,
        "yongji": {"yong": yong, "ji": ji,
                   "source": "命令行指定" if (args.yong or args.ji) else "由旺衰自动推导（建议由解读者复核后用 --yong/--ji 覆盖）"},
        "liunian": ln,
        "liuyue": ly,
        "liuri": lr,
        "extras": ex,
        "warnings": warnings,
        "alt_plate": {"day": pb["day"], "hour": pb["hour"]} if (time_known and p["day"] != pb["day"]) else None,
    }

def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--date", help="公历 YYYY-MM-DD")
    g.add_argument("--lunar", help="农历 YYYY-MM-DD")
    ap.add_argument("--leap", action="store_true", help="农历闰月")
    ap.add_argument("--time", required=True,
                    help="出生钟表时间 HH:MM（北京时间）；完全不知时辰时传 unknown，只排年月日三柱")
    ap.add_argument("--place", default="", help="出生地（城市名）")
    ap.add_argument("--lon", type=float, default=None, help="出生地东经度数，优先于 --place")
    ap.add_argument("--gender", required=True, choices=["male", "female"])
    ap.add_argument("--dayun-steps", type=int, default=8)
    ap.add_argument("--yong", default="", help="喜用五行，逗号分隔，如 木,火。不传则由旺衰自动推导")
    ap.add_argument("--ji", default="", help="忌神五行，逗号分隔，如 金,水")
    ap.add_argument("--liunian", type=int, default=12, help="流年推算年数，默认12")
    ap.add_argument("--liunian-from", type=int, default=0, help="流年起始年份，默认今年")
    ap.add_argument("--liuyue-year", type=int, default=0, help="流月所在年份，默认今年")
    ap.add_argument("--liuri", type=int, default=30, help="流日天数，默认30")
    ap.add_argument("--liuri-from", default="", help="流日起始 YYYY-MM-DD，默认今天")
    ap.add_argument("--json", default="", help="输出 JSON 文件路径")
    a = ap.parse_args()
    data = build(a)
    out = json.dumps(data, ensure_ascii=False, indent=2)
    if a.json:
        open(a.json, "w", encoding="utf-8").write(out)
        print(f"已写入 {a.json}")
    print(out if not a.json else "")

if __name__ == "__main__":
    main()
