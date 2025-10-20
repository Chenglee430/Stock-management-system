#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, json, warnings
from datetime import datetime, timedelta, timezone
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore")

def normalize(sym: str) -> str:
    s = (sym or "").strip().upper()
    if not s: return s
    if s.isdigit() and len(s)==4 and not s.endswith(".TW") and not s.endswith(".TWO"):
        s = s + ".TW"
    return s

def safe_get_fast(info, keys):
    for k in keys:
        v = info.get(k)
        if v is not None:
            return v
    return None

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error":"need_symbol"})); return
    raw = sys.argv[1]
    sym = normalize(raw)

    try:
        tk = yf.Ticker(sym)

        # 先用 fast_info（比 info 穩定、速度快）
        fi = getattr(tk, "fast_info", {}) or {}
        last = safe_get_fast(fi, ["lastPrice","regularMarketPrice","last_price"])
        prev = safe_get_fast(fi, ["previousClose","regularMarketPreviousClose"])
        opn  = safe_get_fast(fi, ["open","regularMarketOpen"])
        high = safe_get_fast(fi, ["dayHigh","regularMarketDayHigh"])
        low  = safe_get_fast(fi, ["dayLow","regularMarketDayLow"])
        vol  = safe_get_fast(fi, ["lastVolume","volume","regularMarketVolume"])

        # 如果 fast_info 拿不到，就用 history 補
        h = tk.history(period="5d", interval="1d", auto_adjust=False)  # 5天用來保底 prev
        h = h.reset_index().rename(columns={
            "Date":"date","Open":"open","High":"high","Low":"low",
            "Close":"close","Adj Close":"adj","Volume":"volume"
        })
        if not last and not h.empty:
            # 以最新一根 close 當 last（休市時也可）
            last = float(h.iloc[-1]["close"])
        if not prev and len(h) >= 2:
            prev = float(h.iloc[-2]["close"])
        if not opn and not h.empty:
            opn = float(h.iloc[-1]["open"])
        if not high and not h.empty:
            high = float(h.iloc[-1]["high"])
        if not low and not h.empty:
            low = float(h.iloc[-1]["low"])
        if not vol and not h.empty:
            vol = int(h.iloc[-1]["volume"]) if pd.notna(h.iloc[-1]["volume"]) else None

        # 給前端畫K線：最近 ~200 根（避免太大）
        hfull = tk.history(period="1y", interval="1d", auto_adjust=False)
        ohlc = []
        if not hfull.empty:
            hf = hfull.reset_index().rename(columns={
                "Date":"date","Open":"open","High":"high","Low":"low",
                "Close":"close","Adj Close":"adj","Volume":"volume"
            })
            # 用調整後收盤覆蓋 close（若有）
            if "adj" in hf.columns:
                hf["close"] = hf["adj"].where(hf["adj"].notna(), hf["close"])
            for _, r in hf.tail(220).iterrows():
                ohlc.append({
                    "date": r["date"].strftime("%Y-%m-%d") if isinstance(r["date"], (pd.Timestamp, datetime)) else str(r["date"]),
                    "open": float(r["open"]) if pd.notna(r["open"]) else None,
                    "high": float(r["high"]) if pd.notna(r["high"]) else None,
                    "low":  float(r["low"])  if pd.notna(r["low"])  else None,
                    "close":float(r["close"])if pd.notna(r["close"])else None,
                    "volume": int(r["volume"]) if pd.notna(r["volume"]) else None
                })

        # 組裝
        changePct = None
        if last is not None and prev is not None and prev != 0:
            changePct = round((float(last) - float(prev)) / float(prev) * 100, 2)

        out = {
            "symbol": sym,
            "last": float(last) if last is not None else None,
            "prevClose": float(prev) if prev is not None else None,
            "open": float(opn) if opn is not None else None,
            "high": float(high) if high is not None else None,
            "low":  float(low) if low is not None else None,
            "volume": int(vol) if vol is not None else None,
            "changePct": changePct,
            "ohlc": ohlc
        }
        print(json.dumps(out, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error":"quote_exception","msg":str(e)}, ensure_ascii=False))

if __name__ == "__main__":
    main()
