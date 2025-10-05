#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys, json, warnings
import yfinance as yf
from datetime import datetime, timezone

warnings.filterwarnings("ignore")

def norm(sym: str) -> str:
    s = (sym or '').strip().upper()
    if not s: return s
    if s.isdigit() and len(s) == 4:  # 台股
        return s + ".TW"
    return s.replace('.', '-')       # 美股 BRK.B -> BRK-B

def safe_float(x):
    try:
        return float(x)
    except Exception:
        return None

def to_iso(ts):
    # yfinance fast_info 的時間可能是 unix 秒數或 pandas Timestamp
    if ts is None: return None
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        # pandas/np datetime
        return str(ts)
    except Exception:
        return str(ts)

if __name__=='__main__':
    if len(sys.argv) < 2:
        print(json.dumps({'error':'no_symbol'})); sys.exit(0)

    sym = norm(sys.argv[1])

    out = {
        'symbol': sym, 'price': None, 'volume': None, 'asof': None,
        'last_close': None, 'pct_change': None,
        'open': None, 'high': None, 'low': None
    }

    try:
        t = yf.Ticker(sym)

        # -------- 1) 先嘗試 fast_info（最快） --------
        fi = getattr(t, 'fast_info', None) or {}
        price  = fi.get('last_price') or fi.get('lastPrice')
        volume = fi.get('last_volume') or fi.get('volume')
        ctime  = fi.get('last_timestamp') or fi.get('regular_market_time')

        out['price']  = safe_float(price)
        out['volume'] = int(volume) if volume is not None else None
        out['asof']   = to_iso(ctime)

        # -------- 2) 以最近 2 根日K 做完整補齊：昨收 + (當日)開/高/低/量 --------
        hist = t.history(period='2d', interval='1d', auto_adjust=False)
        if hist is not None and not hist.empty:
            # 取最後一根（可能是今天尚未收盤的日K）
            last = hist.iloc[-1]
            # 前一根 → 作為昨收
            if len(hist) >= 2:
                prev = hist.iloc[-2]
                out['last_close'] = safe_float(prev.get('Close'))

            # 若即時價缺，拿最後一根的 Close（若為今日盤中則是盤中 close）
            if out['price'] is None:
                out['price'] = safe_float(last.get('Close'))

            # 補齊開高低量
            o = safe_float(last.get('Open'))
            h = safe_float(last.get('High'))
            l = safe_float(last.get('Low'))
            v = last.get('Volume')
            out['open']  = o if o is not None else out['open']
            out['high']  = h if h is not None else out['high']
            out['low']   = l if l is not None else out['low']
            if out['volume'] is None and v is not None:
                try: out['volume'] = int(v)
                except: pass

            # 若 fast_info 沒給時間，用最後一根 K 線時間
            if out['asof'] is None:
                try:
                    idx = hist.index[-1]
                    out['asof'] = str(idx.to_pydatetime().astimezone(timezone.utc).isoformat())
                except Exception:
                    out['asof'] = str(hist.index[-1])

            # 計算 % 變動
            if out['pct_change'] is None and out['price'] is not None and out['last_close']:
                try:
                    prev = float(out['last_close'])
                    if prev != 0:
                        out['pct_change'] = (float(out['price']) - prev) / prev * 100.0
                except Exception:
                    pass

        print(json.dumps(out, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({'error': str(e)}))
