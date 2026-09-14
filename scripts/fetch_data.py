# -*- coding: utf-8 -*-
"""生猪期货(LH)日线数据抓取 —— 数据源:新浪财经(与大商所行情同源)"""
import json, re, time, sys
from pathlib import Path
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Referer": "https://finance.sina.com.cn/"}
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

def fetch_symbol(sym, retries=3):
    url = (f"https://stock2.finance.sina.com.cn/futures/api/jsonp.php/"
           f"var%20t=/InnerFuturesNewService.getDailyKLine?symbol={sym}")
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                text = r.read().decode("utf-8", "ignore")
            m = text.split("=(")[1].rsplit(");", 1)[0]
            data = json.loads(m)
            return data
        except Exception as e:
            if i == retries - 1:
                print(f"  [FAIL] {sym}: {e}")
                return None
            time.sleep(2)

def main():
    # 生猪期货 2021-01-08 上市,合约月份为 1,3,5,7,9,11
    # 枚举 2109..2711 所有奇数月合约
    symbols = []
    for yy in range(21, 28):
        for mm in (1, 3, 5, 7, 9, 11):
            symbols.append(f"LH{yy}{mm:02d}")
    results = {}
    for sym in symbols:
        d = fetch_symbol(sym)
        if d and len(d) > 0:
            # 只保留有成交/报价的记录: d=日期 o/h/l/c/v/p(持仓)/s(结算)
            rows = [{"date": x["d"], "open": float(x["o"]), "high": float(x["h"]),
                     "low": float(x["l"]), "close": float(x["c"]),
                     "settle": float(x["s"]), "vol": int(float(x["v"])),
                     "oi": int(float(x["p"]))} for x in d]
            results[sym] = rows
            (DATA_DIR / f"{sym}.json").write_text(
                json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            print(f"  [OK] {sym}: {len(rows):4d} 条  {rows[0]['date']} ~ {rows[-1]['date']}")
        else:
            print(f"  [--] {sym}: 无数据(未上市或未挂牌)")
        time.sleep(0.4)
    print(f"\n共获取 {len(results)} 个合约")
    # 汇总清单
    meta = {s: {"start": v[0]["date"], "end": v[-1]["date"], "n": len(v)}
            for s, v in results.items()}
    (DATA_DIR / "_index.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

if __name__ == "__main__":
    main()
