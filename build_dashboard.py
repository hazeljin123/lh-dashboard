# -*- coding: utf-8 -*-
"""
生猪期货季节性看板构建脚本 v4
数据: data/LH*.json (fetch_data.py 产出)
输出: dashboard.html (单文件, 内嵌 ECharts 与数据)

内容:
  ① 单合约绝对价格季节性 (1/3/5/7/9/11月合约, 各届叠加)
  ② 临近月价差 (相差2个日历月)   ③ 隔1合约价差 (相差4个月)
  ④ 隔3合约价差 (相差8个月)       ⑤ 隔4合约价差 (相差10个月)
  ⑥ 市场总览: 在市合约期限结构 + 全市场持仓/成交量日度加总季节性
每张季节性图支持 公历/农历 横轴切换。
价差定义: 近月合约收盘价 - 远月合约收盘价 (正 = 近月升水)
"""
import json, math, bisect
from pathlib import Path
from datetime import date, timedelta

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT = ROOT / "dashboard.html"
ECHARTS = Path(__file__).resolve().parent / "echarts.min.js"
MONTHS = [1, 3, 5, 7, 9, 11]

# ==================== 农历转换 (内嵌自 lunardate 0.2.2, GPLv2, 覆盖1900-2099) ====================
_YEAR_INFOS = [
    0x04bd8,
    0x04ae0, 0x0a570, 0x054d5, 0x0d260, 0x0d950, 0x16554, 0x056a0, 0x09ad0, 0x055d2, 0x04ae0,
    0x0a5b6, 0x0a4d0, 0x0d250, 0x1d255, 0x0b540, 0x0d6a0, 0x0ada2, 0x095b0, 0x14977, 0x04970,
    0x0a4b0, 0x0b4b5, 0x06a50, 0x06d40, 0x1ab54, 0x02b60, 0x09570, 0x052f2, 0x04970, 0x06566,
    0x0d4a0, 0x0ea50, 0x06e95, 0x05ad0, 0x02b60, 0x186e3, 0x092e0, 0x1c8d7, 0x0c950, 0x0d4a0,
    0x1d8a6, 0x0b550, 0x056a0, 0x1a5b4, 0x025d0, 0x092d0, 0x0d2b2, 0x0a950, 0x0b557, 0x06ca0,
    0x0b550, 0x15355, 0x04da0, 0x0a5d0, 0x14573, 0x052b0, 0x0a9a8, 0x0e950, 0x06aa0, 0x0aea6,
    0x0ab50, 0x04b60, 0x0aae4, 0x0a570, 0x05260, 0x0f263, 0x0d950, 0x05b57, 0x056a0, 0x096d0,
    0x04dd5, 0x04ad0, 0x0a4d0, 0x0d4d4, 0x0d250, 0x0d558, 0x0b540, 0x0b5a0, 0x195a6, 0x095b0,
    0x049b0, 0x0a974, 0x0a4b0, 0x0b27a, 0x06a50, 0x06d40, 0x0af46, 0x0ab60, 0x09570, 0x04af5,
    0x04970, 0x064b0, 0x074a3, 0x0ea50, 0x06b58, 0x05ac0, 0x0ab60, 0x096d5, 0x092e0, 0x0c960,
    0x0d954, 0x0d4a0, 0x0da50, 0x07552, 0x056a0, 0x0abb7, 0x025d0, 0x092d0, 0x0cab5, 0x0a950,
    0x0b4a0, 0x0baa4, 0x0ad50, 0x055d9, 0x04ba0, 0x0a5b0, 0x15176, 0x052b0, 0x0a930, 0x07954,
    0x06aa0, 0x0ad50, 0x05b52, 0x04b60, 0x0a6e6, 0x0a4e0, 0x0d260, 0x0ea65, 0x0d530, 0x05aa0,
    0x076a3, 0x096d0, 0x04afb, 0x04ad0, 0x0a4d0, 0x1d0b6, 0x0d250, 0x0d520, 0x0dd45, 0x0b5a0,
    0x056d0, 0x055b2, 0x049b0, 0x0a577, 0x0a4b0, 0x0aa50, 0x1b255, 0x06d20, 0x0ada0, 0x14b63,
    0x09370, 0x049f8, 0x04970, 0x064b0, 0x168a6, 0x0ea50, 0x06aa0, 0x1a6c4, 0x0aae0, 0x092e0,
    0x0d2e3, 0x0c960, 0x0d557, 0x0d4a0, 0x0da50, 0x05d55, 0x056a0, 0x0a6d0, 0x055d4, 0x052d0,
    0x0a9b8, 0x0a950, 0x0b4a0, 0x0b6a6, 0x0ad50, 0x055a0, 0x0aba4, 0x0a5b0, 0x052b0, 0x0b273,
    0x06930, 0x07337, 0x06aa0, 0x0ad50, 0x14b55, 0x04b60, 0x0a570, 0x054e4, 0x0d160, 0x0e968,
    0x0d520, 0x0daa0, 0x16aa6, 0x056d0, 0x04ae0, 0x0a9d4, 0x0a2d0, 0x0d150, 0x0f252,
]
_L_START = date(1900, 1, 31)

def _year_days(yi):
    leap = yi % 16 != 0
    n = 29 * 12 + (29 if leap else 0)
    v = yi >> 4
    for _ in range(12 + (1 if leap else 0)):
        if v & 1: n += 1
        v >>= 1
    return n

_YEAR_DAYS = [_year_days(x) for x in _YEAR_INFOS]

def lunar_of(dt):
    """公历date -> (农历月1-12, 农历日1-30, 是否闰月)"""
    off = (dt - _L_START).days
    idx = 0
    while off >= _YEAR_DAYS[idx]:
        off -= _YEAR_DAYS[idx]; idx += 1
    yi = _YEAR_INFOS[idx]
    lm = yi % 16
    months = list(range(1, 13))
    if lm: months.insert(lm, lm)
    for i, mm in enumerate(months):
        is_leap = bool(lm and i == lm)
        days = (((yi >> 16) & 1) + 29) if is_leap else (((yi >> (16 - mm)) & 1) + 29)
        if off < days:
            return mm, off + 1, is_leap
        off -= days
    return 12, 30, False

_LX_CACHE = {}

def lunar_x(ds):
    """公历日期串 -> 农历横轴坐标 [0,12)
    正常月m日d: (m-1)+(d-1)*0.03  占[m-1, m-0.13]
    闰m月日d:   (m-1)+0.9+(d-1)*0.002 压缩在该月末尾窄条, 不与相邻月重叠
    正月=0, 腊月≈11.9; 同一农历月日各年精确对齐"""
    v = _LX_CACHE.get(ds)
    if v is None:
        m, dd, leap = lunar_of(d(ds))
        v = round((m - 1) + (0.9 if leap else 0) + (dd - 1) * (0.002 if leap else 0.03), 4)
        _LX_CACHE[ds] = v
    return v

def lunar_series(pairs):
    """[(date_str, val)] -> 线性农历坐标 (pts, xmap)
    x = 农历月-日(0~12) + 12*该届已跨春节次数, 各届起点 offset=0
    曲线 x 单调递增, 跨春节后进入「次年」区间(与公历次年处理一致), 不再有首尾拉线"""
    pts, prev, off = [], None, 0
    xmap = {}
    for ds, val in pairs:
        lx = lunar_x(ds)
        if prev is not None and prev - lx > 6:   # 跨春节
            off += 12
        x = round(lx + off, 4)
        pts.append([x, val])
        xmap[ds] = x
        prev = lx
    return pts, xmap

def deliv_lx(xmap, dates, dd):
    """该届近月交割月首日的线性农历x (取>=dd的首个交易日, 无则取末日)"""
    i = bisect.bisect_left(dates, dd)
    if i >= len(dates): i = len(dates) - 1
    return xmap[dates[i]]

def lunar_axis_lin(series, metas):
    """组级线性农历轴: (min, max, dmin, dmax, delivXL)
    delivXL = 各届交割月首日线性农历x的均值(农历日期各年浮动, 取均值)"""
    lxs = [p[0] for s in series for p in s["ptsL"]]
    amin, amax = min(lxs), max(lxs)
    dxs = [deliv_lx(xm, dts, dd) for (xm, dts, dd) in metas]
    deliv = round(sum(dxs) / len(dxs), 2) if dxs else None
    return (math.floor(amin), math.ceil(amax + 0.05),
            round(amin, 3), round(amax, 3), deliv)

def d(s): return date.fromisoformat(s)

def load():
    c = {}
    for f in sorted(DATA_DIR.glob("LH*.json")):
        sym = f.stem
        y, m = 2000 + int(sym[2:4]), int(sym[4:6])
        rows = json.loads(f.read_text(encoding="utf-8"))
        c[(y, m)] = {"sym": sym, "rows": rows}
    return c

def xabs(ds):
    """绝对公历月浮点数: 2024年5月中旬 ≈ 2024*12+4.5"""
    t = d(ds)
    return t.year * 12 + (t.month - 1) + (t.day - 1) / 30.44

def group_axis(xs, deliv_x, anchor):
    """组级公历坐标: xs=组内全部点x; deliv_x=近月交割月x; anchor=起始月索引(0=1月)"""
    xmin, xmax = min(xs), max(xs)
    return {"min": round(xmin, 2), "max": round(xmax, 2),
            "min2": math.floor(xmin), "max2": math.ceil(max(xmax, deliv_x) + 0.05),
            "delivX": deliv_x, "anchor": anchor}

def mean_curve(series_list, xmin, xmax, step=0.25, tol=0.16, key="pts"):
    """各届曲线在统一 x 网格上求均值 (>=2届才输出); 自动跳过null断点"""
    cleaned = []
    for s in series_list:
        cleaned.append([p for p in s[key] if p is not None])
    out = []
    g = math.ceil((xmin + 1e-9) / step) * step
    while g <= xmax + 1e-9:
        vals = []
        for pts in cleaned:
            i = bisect.bisect_left([p[0] for p in pts], g) if pts else 0
            best = None
            for j in (i - 1, i):
                if 0 <= j < len(pts):
                    dx = abs(pts[j][0] - g)
                    if dx <= tol and (best is None or dx < best[0]):
                        best = (dx, pts[j][1])
            if best: vals.append(best[1])
        if len(vals) >= 2:
            out.append([round(g, 3), round(sum(vals) / len(vals), 1)])
        g += step
    return out

def build():
    contracts = load()
    all_end = max(r["rows"][-1]["date"] for r in contracts.values())
    last_global = d(all_end)

    def is_live(y, m):
        return date(y, m, 1) + timedelta(days=35) > last_global

    DATA = {"updated": all_end, "months": MONTHS}

    # ---------- 1) 单合约绝对价格 ----------
    price = {}
    for m in MONTHS:
        key = f"{m:02d}"
        series, metas = [], []
        for (y, mm), c in sorted(contracts.items()):
            if mm != m: continue
            live = is_live(y, mm)
            base = y * 12 + (mm - 1) - 12
            pairs = [(r["date"], r["close"]) for r in c["rows"]]
            dates = [ds0 for ds0, _ in pairs]
            ptsL, xmap = lunar_series(pairs)
            series.append({
                "name": c["sym"], "year": y, "live": live,
                "deliv": f"{y}-{mm:02d}",
                "start": c["rows"][0]["date"], "end": c["rows"][-1]["date"],
                "dates": dates,
                "pts": [[round(xabs(ds0) - base, 3), v] for ds0, v in pairs],
                "ptsL": ptsL})
            metas.append((xmap, dates, f"{y}-{mm:02d}-01"))
        if not series: continue
        xs = [p[0] for s in series for p in s["pts"]]
        axG = group_axis(xs, 12, m - 1)
        lv = [s for s in series if s["live"]] or series[-1:]
        s0 = lv[0]
        lmin, lmax, dminL, dmaxL, delivXL = lunar_axis_lin(series, metas)
        lastp = s0["pts"][-1][1]; prevp = s0["pts"][-2][1] if len(s0["pts"]) > 1 else None
        price[key] = {
            "series": series,
            "mean": mean_curve(series, axG["min"], axG["max"]),
            "meanL": mean_curve(series, dminL, dmaxL, key="ptsL"),
            "axG": {"min": axG["min2"], "max": axG["max2"], "delivX": axG["delivX"], "anchor": axG["anchor"]},
            "axL": {"min": lmin, "max": lmax, "delivXL": delivXL},
            "latest": {"name": s0["name"], "val": lastp,
                       "date": s0["dates"][-1],
                       "chg": round(lastp - prevp, 1) if prevp is not None else None,
                       "live": s0["live"]}}
    DATA["price"] = price

    # ---------- 2~5) 四类价差: 临近月(2) / 隔1(4) / 隔3(8) / 隔4(10) ----------
    for gkey, gap, label in (("spread1", 2, "临近月"), ("spread2", 4, "隔1合约"),
                             ("spread3", 8, "隔3合约"), ("spread4", 10, "隔4合约")):
        grp = {}
        for m in MONTHS:
            m2v = m + gap
            y_off, m2 = (1, m2v - 12) if m2v > 12 else (0, m2v)
            key = f"{m:02d}-{m2:02d}"
            series, metas = [], []
            for (y, mm), c in sorted(contracts.items()):
                if mm != m: continue
                far = contracts.get((y + y_off, m2))
                if not far: continue
                fmap = {r["date"]: r["close"] for r in far["rows"]}
                base = y * 12 + (m - 1) + gap - 12
                pairs = [(r["date"], round(r["close"] - fmap[r["date"]], 1))
                         for r in c["rows"] if r["date"] in fmap]
                if len(pairs) < 5: continue
                dates = [ds0 for ds0, _ in pairs]
                ptsL, xmap = lunar_series(pairs)
                live = is_live(y, m)
                series.append({
                    "name": f"{c['sym']}-{far['sym'][2:]}", "year": y, "live": live,
                    "deliv": f"{y}-{m:02d}",
                    "start": pairs[0][0], "end": pairs[-1][0],
                    "dates": dates,
                    "pts": [[round(xabs(ds0) - base, 3), v] for ds0, v in pairs],
                    "ptsL": ptsL})
                metas.append((xmap, dates, f"{y}-{m:02d}-01"))
            if not series: continue
            xs = [p[0] for s in series for p in s["pts"]]
            axG = group_axis(xs, 12 - gap, (m - 1 + gap) % 12)
            lv = [s for s in series if s["live"]] or series[-1:]
            s0 = lv[0]
            lmin, lmax, dminL, dmaxL, delivXL = lunar_axis_lin(series, metas)
            lastp = s0["pts"][-1][1]; prevp = s0["pts"][-2][1] if len(s0["pts"]) > 1 else None
            grp[key] = {
                "series": series,
                "mean": mean_curve(series, axG["min"], axG["max"]),
                "meanL": mean_curve(series, dminL, dmaxL, key="ptsL"),
                "axG": {"min": axG["min2"], "max": axG["max2"], "delivX": axG["delivX"], "anchor": axG["anchor"]},
                "axL": {"min": lmin, "max": lmax, "delivXL": delivXL},
                "near": f"{m:02d}", "far": f"{m2:02d}",
                "latest": {"name": s0["name"], "val": lastp,
                           "date": s0["dates"][-1],
                           "chg": round(lastp - prevp, 1) if prevp is not None else None,
                           "live": s0["live"]}}
        DATA[gkey] = grp

    # ---------- 6) 市场总览: 在市合约 + 全市场日度加总 ----------
    live_contracts = []
    for (y, m), c in sorted(contracts.items()):
        if not is_live(y, m): continue
        rows = c["rows"]
        lc, pc = rows[-1]["close"], (rows[-2]["close"] if len(rows) > 1 else None)
        live_contracts.append({
            "sym": c["sym"], "close": lc, "settle": rows[-1]["settle"],
            "chg": round(lc - pc, 1) if pc is not None else None,
            "vol": rows[-1]["vol"], "oi": rows[-1]["oi"],
            "deliv": f"{y}-{m:02d}", "start": rows[0]["date"],
            "end": rows[-1]["date"]})
    main = max(live_contracts, key=lambda r: r["oi"])

    daily = {}
    for (y, m), c in contracts.items():
        for r in c["rows"]:
            e = daily.setdefault(r["date"], [0, 0])
            e[0] += r["oi"]; e[1] += r["vol"]
    market = {"term": live_contracts, "mainSym": main["sym"]}
    for fkey, idx in (("oi", 0), ("vol", 1)):
        years = {}
        for ds0, e in sorted(daily.items()):
            years.setdefault(int(ds0[:4]), []).append((ds0, e[idx]))
        cur = max(years)
        series = []
        for yy, pairs in sorted(years.items()):
            ptsL, _ = lunar_series(pairs)
            series.append({
                "name": f"{yy}年", "year": yy, "live": yy == cur,
                "pts": [[round(xabs(ds0) - yy * 12, 3), v] for ds0, v in pairs],
                "ptsL": ptsL,
                "dates": [ds0 for ds0, _ in pairs]})
        lxs = [p[0] for s in series for p in s["ptsL"]]
        aminL, amaxL = min(lxs), max(lxs)
        market[fkey] = {
            "series": series,
            "mean": mean_curve(series, 0, 11.9),
            "meanL": mean_curve(series, round(aminL, 3), round(amaxL, 3), key="ptsL"),
            "axG": {"min": 0, "max": 11.99, "delivX": None, "anchor": 1},
            "axL": {"min": math.floor(aminL), "max": math.ceil(amaxL + 0.05), "delivXL": None}}
    DATA["market"] = market
    return DATA

# ================= HTML 模板 =================
TPL = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>生猪期货价格季节性看板 · DCE LH</title>
<style>
:root{
  --bg:#f4f6f8; --card:#ffffff; --ink:#1c2733; --muted:#6b7a89;
  --line:#e4e9ef; --accent:#14538c; --up:#c0392b; --down:#1e8449;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  font-size:14px;line-height:1.55}
.wrap{max-width:1380px;margin:0 auto;padding:0 20px 48px}
header{background:linear-gradient(135deg,#0d2b45 0%,#14538c 78%);color:#fff;
  padding:26px 0 22px;margin-bottom:18px}
header .wrap{padding-bottom:0}
.h-title{font-size:24px;font-weight:700;letter-spacing:.5px}
.h-title small{font-weight:400;opacity:.75;font-size:13px;margin-left:12px}
.h-sub{margin-top:6px;font-size:13px;opacity:.85}
.h-sub b{color:#ffd166}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 6px;position:sticky;top:0;
  background:var(--bg);padding:10px 0;z-index:50}
.tab{border:1px solid var(--line);background:var(--card);border-radius:999px;
  padding:7px 16px;cursor:pointer;font-size:13.5px;color:var(--muted);user-select:none;
  transition:all .15s;font-weight:500}
.tab:hover{border-color:#b9c6d3}
.tab.on{background:var(--accent);border-color:var(--accent);color:#fff;box-shadow:0 2px 8px rgba(20,83,140,.3)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(560px,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:14px 16px 8px;box-shadow:0 1px 3px rgba(28,39,51,.05)}
.chhead{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
.ch-t{font-size:15px;font-weight:700}
.ch-t .unit{font-weight:400;margin-left:10px;white-space:nowrap}
.ch-t .tag{font-size:11px;color:#fff;background:var(--accent);border-radius:4px;
  padding:1.5px 7px;margin-left:8px;font-weight:500;vertical-align:2px}
.axtg{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden;
  flex:none;margin:2px 0 2px 6px;background:#fff}
.axtg span{padding:3px 11px;font-size:11.5px;cursor:pointer;color:var(--muted);
  user-select:none;line-height:1.5;transition:all .12s}
.axtg span+span{border-left:1px solid var(--line)}
.axtg span:hover{color:var(--accent)}
.axtg span.on{background:var(--accent);color:#fff}
.chart{height:375px;width:100%}
.up{color:var(--up)}.down{color:var(--down)}
@media (max-width:640px){.grid{grid-template-columns:1fr}.chart{height:320px}}
</style>
</head>
<body>
<header>
  <div class="wrap">
    <div class="h-title">生猪期货价格季节性看板<small>Live Hog Futures · DCE · LH</small></div>
    <div class="h-sub">大连商品交易所生猪期货各月合约 <b>日线收盘价</b>（元/吨）· 数据截至 <b id="hDate"></b> · 每日 <b>15:05</b> 自动更新 · 每张季节性图支持 <b>公历 / 农历</b> 横轴切换</div>
  </div>
</header>
<div class="wrap">
  <div class="tabs" id="tabs"></div>
  <div id="panePrice"></div>
  <div id="paneS1" hidden></div>
  <div id="paneS2" hidden></div>
  <div id="paneS3" hidden></div>
  <div id="paneS4" hidden></div>
  <div id="paneMarket" hidden></div>
</div>
<script>__ECHARTS__</script>
<script>const DATA = __DATA__;</script>
<script>
"use strict";
const fmtN = v => v == null ? '–' : Number(v).toLocaleString('zh-CN', {maximumFractionDigits: 1});
const fmtD = s => s ? s.slice(5).replace('-', '/') : '';
const LIVE_RED = '#d81e2c';
const YEAR_COLORS = {2021:'#9aa5b1',2022:'#4e79a7',2023:'#59a14f',2024:'#f28e2b',2025:'#76b7b2',2026:'#af7aa1',2027:'#8d6e63'};
const CHARTS = {}, REG = {}, INITED = {}, MODE = {};
const monthCN = { '01':'1月','03':'3月','05':'5月','07':'7月','09':'9月','11':'11月' };
const LUNAR_MONTHS = ['正月','二月','三月','四月','五月','六月','七月','八月','九月','十月','冬月','腊月'];

document.getElementById('hDate').textContent = DATA.updated;

/* ---------- 公历/农历 标签与文本 ---------- */
const gLabelMaker = anchor => v => {
  const mm = anchor + Math.floor(v + 1e-6);
  return (mm >= 12 ? '次' : '') + ((mm % 12) + 1) + '月';
};
/* 线性农历坐标: 0~12 当年, 12~24 次年(跨春节 +12), 闰月压缩在各月末尾窄条 */
const lunarLabel = v => {
  const r = Math.round(v);
  if (Math.abs(v - r) > 1e-6 || r < 0 || r >= 24) return '';
  const offN = Math.floor(r / 12);
  return (offN > 0 ? '次' : '') + (LUNAR_MONTHS[r % 12] || '');
};
const lunarStr = x => {
  const xv = Math.max(0, x);
  const offN = Math.floor(xv / 12);
  const base = Math.floor(xv) % 12;
  const off = xv - Math.floor(xv);
  let leap = false, dd;
  if (off >= 0.885) { leap = true; dd = Math.round((off - 0.9) / 0.002) + 1; }
  else dd = Math.round(off / 0.03) + 1;
  dd = Math.max(1, Math.min(30, dd));
  return (offN > 0 ? '次年' : '') + (leap ? '闰' : '') + LUNAR_MONTHS[base] + dd + '日';
};

/* ---------- Tabs ---------- */
const TAB_DEFS = [
  {id:'price', name:'① 单合约价格季节性', pane:'panePrice', intro:
    `<b>各月份合约历届价格叠加</b>：每个子图展示同月份合约（如 LH2401 / LH2501 / LH2601 …）自上市至摘牌的收盘价走势，各届按月-日对齐；
     <span style="color:#d81e2c;font-weight:700">红色粗线为当前在市一届</span>，黑色虚线为历届均值。右上角可切换公历/农历横轴。`},
  {id:'spread1', label:'临近月', name:'② 临近月价差季节性', pane:'paneS1', intro:
    `<b>临近月价差</b>（相邻两个合约，相差 2 个日历月，如 LH2601-2603）。用于观察月差在一年内的季节性规律（备货旺季/淡季的月差强弱）。`},
  {id:'spread2', label:'隔1', name:'③ 隔1合约价差季节性', pane:'paneS2', intro:
    `<b>隔 1 个合约价差</b>（中间隔 1 个合约，相差 4 个日历月，如 LH2601-2605）。覆盖「1 个季度 + 1 个月」的价差结构，反映中期的供需预期差。`},
  {id:'spread3', label:'隔3', name:'④ 隔3合约价差季节性', pane:'paneS3', intro:
    `<b>隔 3 个合约价差</b>（中间隔 3 个合约，相差 8 个日历月，如 LH2601-2609）。因生猪单合约存续约 12 个月，该类价差的可交易窗口约 4 个月（远月上市 → 近月摘牌）。`},
  {id:'spread4', label:'隔4', name:'⑤ 隔4合约价差季节性', pane:'paneS4', intro:
    `<b>隔 4 个合约价差</b>（中间隔 4 个合约，相差 10 个日历月，如 LH2601-2611）。因生猪单合约存续约 12 个月，该类价差的可交易窗口仅约 2 个月，曲线较短属正常。`},
  {id:'market', name:'⑥ 市场总览', pane:'paneMarket', intro:
    `<b>市场总览</b>：在市合约期限结构折线（横轴按交割月由近到远，红色大圆点为主力合约）；全市场持仓量与成交量的日度加总季节性（每个交易日所有在市合约的持仓/成交合计，按年叠加）。`},
];

function buildTabs(){
  const el = document.getElementById('tabs');
  TAB_DEFS.forEach((t, i) => {
    const b = document.createElement('div');
    b.className = 'tab' + (i === 0 ? ' on' : '');
    b.textContent = t.name;
    b.onclick = () => {
      document.querySelectorAll('.tab').forEach(x => x.classList.remove('on'));
      b.classList.add('on');
      TAB_DEFS.forEach(tt => document.getElementById(tt.pane).hidden = (tt.id !== t.id));
      if (t.id === 'market') renderMarket();
      else ensureCharts(t.id);
      window.scrollTo({top:0});
    };
    el.appendChild(b);
  });
}
buildTabs();

/* ---------- 图例行数估算: 排不下自动换行(plain legend), grid.top 按行数预留 ---------- */
const LEGEND_FS = 9;
function estLegendRows(names, width){
  const maxW = Math.max(160, width - 56);
  let rows = 1, w = 0;
  names.forEach(nm => {
    let tw = 0;
    for (const ch of nm) tw += ch.charCodeAt(0) > 255 ? LEGEND_FS : LEGEND_FS * 0.6;
    const iw = 10 + 5 + tw + 6;   /* icon + icon-text间距 + 文本 + itemGap */
    if (w > 0 && w + iw > maxW){ rows++; w = iw; }
    else w += iw;
  });
  return rows;
}
function legendTop(names, width){ return 34 + (estLegendRows(names, width) - 1) * 16; }
/* 隐藏(0宽)pane 中的图表跳过, 避免被错误压缩/校准 */
function resizeVisibleCharts(){
  Object.values(CHARTS).forEach(c => {
    const dom = c.getDom();
    if (dom && dom.clientWidth) c.resize();
  });
}
function recalibGrid(){
  Object.entries(CHARTS).forEach(([cid, c]) => {
    const dom = c.getDom();
    if (!dom || !dom.clientWidth || !REG[cid] || !REG[cid].g) return;
    const names = ['历届均值'].concat(REG[cid].g.series.map(s => s.name));
    c.setOption({grid: {top: legendTop(names, dom.clientWidth)}});
  });
}

/* ---------- 季节性图通用挂载 ---------- */
function mountSeason(cid, g, cfg){
  const markG = cfg.markG || [], markL = cfg.markL || [];
  REG[cid] = {
    g, gLabel: cfg.gLabel, markG, markL,
    meta: [{isMean:true}].concat(g.series.map(s => ({dates: s.dates, live: s.live})))
  };
  MODE[cid] = false;
  const series = [{
    name: '历届均值', type: 'line', data: g.mean, showSymbol: false,
    lineStyle: {width: 2.6, type: 'dashed', color: '#222831', opacity: .9},
    itemStyle: {color: '#222831'}, z: 5, emphasis: {disabled: true}
  }];
  if (markG.length) series[0].markLine = {
    symbol: 'none', silent: true,
    lineStyle: {color: '#c0392b', type: 'dashed', width: 1.2},
    label: {formatter: '交割月', color: '#c0392b', fontSize: 10, position: 'insideEndTop'},
    data: markG
  };
  g.series.forEach(s => {
    const col = s.live ? LIVE_RED : (YEAR_COLORS[s.year] || '#888');
    series.push({
      name: s.name, type: 'line',
      data: s.pts, showSymbol: false, smooth: false,
      lineStyle: {width: s.live ? 3.2 : 1.5, color: col, opacity: s.live ? 1 : .85},
      itemStyle: {color: col},
      emphasis: {focus: 'series', lineStyle: {width: 3.6}},
      endLabel: {show: !!s.live, formatter: s.name, color: col, fontSize: 10, distance: 6},
      z: s.live ? 6 : 3
    });
  });
  const ax = g.axG;
  const el = document.getElementById(cid);
  const lgNames = ['历届均值'].concat(g.series.map(s => s.name));
  const opt = {
    animation: false,
    grid: {left: 72, right: 62, top: legendTop(lgNames, el ? el.clientWidth : 600), bottom: 46},
    legend: {top: 2, left: 4, itemWidth: 10, itemHeight: 6,
      textStyle: {fontSize: LEGEND_FS, color: '#4b5a68'}, itemGap: 6},
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(255,255,255,.97)', borderColor: '#dbe3ea',
      textStyle: {color: '#1c2733', fontSize: 12},
      extraCssText: 'box-shadow:0 4px 14px rgba(20,40,70,.14);border-radius:8px;padding:8px 12px;max-width:420px;white-space:normal;',
      axisPointer: {type: 'line', lineStyle: {color: '#9fb3c6', type: 'dashed'}},
      formatter: makeTip(cid)
    },
    xAxis: {
      type: 'value', min: ax.min, max: ax.max, interval: 1,
      name: '公历日期', nameLocation: 'middle', nameGap: 30,
      nameTextStyle: {color: '#6b7a89', fontSize: 10},
      axisLabel: {formatter: cfg.gLabel, color: '#6b7a89', fontSize: 10},
      splitLine: {lineStyle: {color: '#edf1f5'}}
    },
    yAxis: {
      type: 'value', scale: true,
      axisLabel: {formatter: v => fmtN(v), color: '#6b7a89', fontSize: 11},
      splitLine: {lineStyle: {color: '#edf1f5'}}
    },
    dataZoom: [{type: 'inside', filterMode: 'weakFilter'}],
    toolbox: {right: 6, top: -4, itemSize: 12,
      feature: {saveAsImage: {name: 'LH_' + cid, pixelRatio: 2, title: '保存图片'}}},
    series: series
  };
  const c = echarts.init(document.getElementById(cid));
  c.setOption(opt);
  CHARTS[cid] = c;
  bindToggle(cid);
}

/* ---------- 公历/农历 切换 ---------- */
function switchMode(cid, lunar){
  const ch = CHARTS[cid], rec = REG[cid], g = rec.g;
  if (!ch || MODE[cid] === lunar) return;
  MODE[cid] = lunar;
  const ax = lunar ? g.axL : g.axG;
  const labeler = lunar ? lunarLabel : rec.gLabel;
  const ser = [{ data: lunar ? g.meanL : g.mean }];
  if (rec.markG.length || rec.markL.length)
    ser[0].markLine = { data: lunar ? rec.markL : rec.markG };
  g.series.forEach(s => ser.push({ data: lunar ? s.ptsL : s.pts }));
  ch.setOption({
    xAxis: { min: ax.min, max: ax.max,
      name: lunar ? '农历日期' : '公历日期',
      axisLabel: { formatter: labeler } },
    series: ser
  });
  ch.dispatchAction({ type: 'dataZoom', start: 0, end: 100 });
}
function bindToggle(cid){
  const el = document.getElementById('tg-' + cid);
  if (!el) return;
  const bg = el.children[0], bl = el.children[1];
  const set = lunar => {
    bg.classList.toggle('on', !lunar);
    bl.classList.toggle('on', lunar);
    switchMode(cid, lunar);
  };
  bg.onclick = () => set(false);
  bl.onclick = () => set(true);
}

/* ---------- Tooltip ---------- */
function makeTip(cid){
  return function(params){
    const items = params.filter(p => Array.isArray(p.value) && p.value[1] != null);
    if (!items.length) return '';
    const rec = REG[cid], lunar = MODE[cid];
    const x0 = items[0].value[0];
    let head;
    if (lunar){
      head = `农历 <b style="color:#14538c">${lunarStr(x0)}</b> <span style="font-weight:400;color:#8494a4;font-size:11px">（历届对齐）</span>`;
    } else {
      const anchor = rec.g.axG.anchor;
      const totalMo = anchor + Math.floor(x0 + 1e-6);
      const mo = totalMo % 12 + 1;
      const dy = Math.max(1, Math.min(28, Math.round((x0 - Math.floor(x0 + 1e-6)) * 30.44) + 1));
      head = `公历 <b style="color:#14538c">${totalMo >= 12 ? '次年' : ''}${mo}月${dy}日</b> <span style="font-weight:400;color:#8494a4;font-size:11px">（历届对齐）</span>`;
    }
    let html = `<div style="font-weight:700;margin-bottom:4px">${head}</div>`;
    html += '<table style="border-collapse:collapse;font-size:12px">';
    items.forEach(p => {
      const meta = rec.meta[p.seriesIndex];
      const isMean = meta && meta.isMean;
      const dt = (!isMean && meta) ? (meta.dates[p.dataIndex] || null) : null;
      const col = p.color;
      const liveTag = (!isMean && meta && meta.live) ? ' <span style="color:#d81e2c;font-size:11px">●在市</span>' : '';
      html += `<tr>
        <td style="padding:1px 8px 1px 0"><span style="display:inline-block;width:9px;height:9px;border-radius:2px;background:${col};margin-right:6px;vertical-align:-1px"></span>${p.seriesName}${liveTag}</td>
        <td style="padding:1px 10px;color:#8494a4;font-variant-numeric:tabular-nums">${dt ? fmtD(dt) : (isMean ? '均值' : '–')}</td>
        <td style="padding:1px 0;text-align:right;font-weight:600;font-variant-numeric:tabular-nums;color:${isMean ? '#222831' : col}">${fmtN(p.value[1])}</td></tr>`;
    });
    html += '</table>';
    return html;
  };
}

/* ---------- 季节性 Tab 渲染 ---------- */
function ensureCharts(tabId){
  if (INITED[tabId]) { resizeVisibleCharts(); recalibGrid(); return; }
  INITED[tabId] = true;
  const def = TAB_DEFS.find(t => t.id === tabId);
  const pane = document.getElementById(def.pane);
  const grp = DATA[tabId];
  const isPrice = tabId === 'price';
  const order = Object.keys(grp).sort();

  let html = `<div class="grid">`;
  order.forEach(key => {
    const g = grp[key];
    let title;
    if (isPrice){
      title = `${monthCN[key]}合约 · 收盘价`;
    } else {
      const [a,b] = [g.near, g.far];
      title = `${key} 价差（近月${monthCN[a]} − 远月${monthCN[b]}）`;
    }
    html += `<div class="card">
      <div class="chhead">
        <div><div class="ch-t">${title}<span class="unit" style="font-size:10px;color:#9aa7b3">单位：元/吨</span></div></div>
        <span class="axtg" id="tg-ch-${tabId}-${key}"><span class="on">公历</span><span>农历</span></span>
      </div>
      <div class="chart" id="ch-${tabId}-${key}"></div></div>`;
  });
  html += `</div>`;
  pane.innerHTML = html;

  order.forEach(key => {
    const g = grp[key];
    const cid = `ch-${tabId}-${key}`;
    const y0 = !isPrice;
    const mk = (dx) => [{xAxis: dx}].concat(y0 ? [{yAxis: 0, lineStyle: {color:'#b8c4cf', width: 1}, label: {show:false}}] : []);
    mountSeason(cid, g, {
      gLabel: gLabelMaker(g.axG.anchor),
      markG: g.axG.delivX != null ? mk(g.axG.delivX) : [],
      markL: g.axL.delivXL != null ? mk(g.axL.delivXL) : []
    });
  });
}

/* ---------- 市场总览 ---------- */
function renderMarket(){
  if (INITED.market) { resizeVisibleCharts(); recalibGrid(); return; }
  INITED.market = true;
  const M = DATA.market;
  const pane = document.getElementById('paneMarket');
  const seasonCard = (cid, title, unit) => `<div class="card">
    <div class="chhead">
      <div><div class="ch-t">${title}<span class="unit" style="font-size:10px;color:#9aa7b3">单位：${unit}</span></div></div>
      <span class="axtg" id="tg-${cid}"><span class="on">公历</span><span>农历</span></span>
    </div>
    <div class="chart" id="${cid}"></div></div>`;
  pane.innerHTML = `<div class="grid">
    <div class="card" style="grid-column:1/-1">
      <div class="chhead">
        <div><div class="ch-t">在市合约期限结构 · 最新收盘价<span class="unit" style="font-size:12px;color:#6b7a89">单位：元/吨</span></div></div>
      </div>
      <div class="chart" id="ch-term" style="height:350px"></div></div>
    ${seasonCard('ch-mkt-oi', '全市场持仓量 · 日度加总季节性', '手')}
    ${seasonCard('ch-mkt-vol', '全市场成交量 · 日度加总季节性', '手')}
  </div>`;
  renderTerm();
  mountSeason('ch-mkt-oi', M.oi, {gLabel: gLabelMaker(1)});
  mountSeason('ch-mkt-vol', M.vol, {gLabel: gLabelMaker(1)});
}

function renderTerm(){
  const M = DATA.market;
  const c = echarts.init(document.getElementById('ch-term'));
  c.setOption({
    animation: false,
    grid: {left: 74, right: 30, top: 30, bottom: 50},
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(255,255,255,.97)', borderColor: '#dbe3ea',
      textStyle: {color: '#1c2733', fontSize: 12},
      extraCssText: 'box-shadow:0 4px 14px rgba(20,40,70,.14);border-radius:8px;padding:8px 12px;',
      formatter: p => {
        const r = M.term[p.dataIndex];
        if (!r) return '';
        const chgHtml = r.chg == null ? '–' :
          `<span style="color:${r.chg>=0?'#c0392b':'#1e8449'};font-weight:700">${r.chg>=0?'▲ +':'▼ '}${fmtN(r.chg)}</span>`;
        const row = (k, v) => `<tr><td style="padding:1px 10px 1px 0;color:#8494a4">${k}</td><td style="text-align:right;font-variant-numeric:tabular-nums">${v}</td></tr>`;
        return `<div style="font-weight:700;margin-bottom:4px">${r.sym}${r.sym===M.mainSym?' <span style="color:#d81e2c;font-size:11px">●主力</span>':''}</div>
          <table style="border-collapse:collapse;font-size:12px">
          ${row('收盘价', fmtN(r.close) + ' 元/吨')}
          ${row('结算价', fmtN(r.settle))}
          ${row('涨跌', chgHtml)}
          ${row('成交量', fmtN(r.vol) + ' 手')}
          ${row('持仓量', fmtN(r.oi) + ' 手')}
          ${row('交割月', r.deliv)}
          ${row('上市日', r.start)}
          </table>`;
      }
    },
    xAxis: {type: 'category', data: M.term.map(r => r.sym),
      name: '合约（交割月由近到远）', nameLocation: 'middle', nameGap: 30,
      nameTextStyle: {color: '#6b7a89', fontSize: 11},
      axisLabel: {color: '#4b5a68', fontSize: 11.5, interval: 0},
      axisTick: {alignWithLabel: true}},
    yAxis: {type: 'value', scale: true,
      axisLabel: {formatter: v => fmtN(v), color: '#6b7a89', fontSize: 11},
      splitLine: {lineStyle: {color: '#edf1f5'}}},
    series: [{
      type: 'line',
      data: M.term.map(r => ({
        value: r.close,
        symbol: 'circle',
        symbolSize: r.sym === M.mainSym ? 14 : 9,
        itemStyle: {
          color: r.sym === M.mainSym ? '#d81e2c' : '#4e79a7',
          borderColor: '#ffffff', borderWidth: 1.5},
        label: {show: true, position: 'top', fontSize: 10.5,
          color: r.sym === M.mainSym ? '#d81e2c' : '#4b5a68',
          fontWeight: r.sym === M.mainSym ? 700 : 400,
          formatter: p => fmtN(p.value)}
      })),
      lineStyle: {width: 2.5, color: '#4e79a7'},
      emphasis: {focus: 'series', lineStyle: {width: 3.5}}
    }]
  });
  CHARTS['ch-term'] = c;
}

/* 窗口尺寸变化: 可见图表立即 resize, 防抖后按稳定宽度重新校准图例预留行数 */
let _rzT = null;
window.addEventListener('resize', () => {
  resizeVisibleCharts();
  clearTimeout(_rzT);
  _rzT = setTimeout(recalibGrid, 150);
});
ensureCharts('price');
</script>
</body>
</html>
"""

def main():
    data = build()
    html = (TPL
            .replace("__ECHARTS__", ECHARTS.read_text(encoding="utf-8"))
            .replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":"))))
    OUT.write_text(html, encoding="utf-8")
    def summ(grp, name):
        out = [f"{name}:"]
        for k, v in grp.items():
            liv = [s["name"] + ("*" if s["live"] else "") for s in v["series"]]
            out.append(f"  {k}: {len(v['series'])}届 mean{len(v['mean'])}/meanL{len(v['meanL'])} axL[{v['axL']['min']},{v['axL']['max']}] -> {', '.join(liv)}")
        print("\n".join(out))
    summ(data["price"], "单合约价格")
    for g, n in (("spread1", "临近月"), ("spread2", "隔1"), ("spread3", "隔3"), ("spread4", "隔4")):
        summ(data[g], n)
    m = data["market"]
    print(f"\n市场总览: term={len(m['term'])}个在市 主力={m['mainSym']}")
    for f in ("oi", "vol"):
        ys = [s["name"] + ("*" if s["live"] else "") for s in m[f]["series"]]
        npts = sum(len(s["pts"]) for s in m[f]["series"])
        print(f"  {f}: {len(ys)}年 {npts}点 mean{len(m[f]['mean'])}/meanL{len(m[f]['meanL'])} axL[{m[f]['axL']['min']},{m[f]['axL']['max']}] -> {', '.join(ys)}")
    print(f"\n输出: {OUT}  ({OUT.stat().st_size/1e6:.2f} MB)")

if __name__ == "__main__":
    main()
