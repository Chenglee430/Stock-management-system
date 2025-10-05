#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys, json, warnings
import mysql.connector
import yfinance as yf

warnings.filterwarnings("ignore")

# 依你環境調整
DB = dict(host='localhost', user='root', password='', database='stock_db')

def connect_db():
    try:
        return mysql.connector.connect(**DB)
    except Exception:
        return None

def norm(sym: str) -> str:
    s = (sym or '').strip().upper()
    if not s:
        return s
    # 台股數字代碼 → .TW
    if s.isdigit() and len(s) == 4:
        return s + ".TW"
    # 美股 . → -（BRK.B → BRK-B）
    return s.replace('.', '-')

def alt_candidates(sym: str):
    """
    嘗試多種寫法：2330、2330.TW、2330.TWO、美股 . / - 互換
    """
    s = (sym or '').strip().upper()
    out = []
    if s.isdigit() and len(s) == 4:
        out += [s + ".TW", s, s + ".TWO"]
    else:
        out += [s, s.replace('.', '-'), s.replace('-', '.')]
    # 去重
    seen = set(); arr = []
    for x in out:
        if x and x not in seen:
            seen.add(x); arr.append(x)
    return arr

def get_info_from_yf(sym: str) -> dict:
    try:
        t = yf.Ticker(sym)
        info = t.info or {}
        return {
            'symbol': sym,
            'company_name': info.get('longName') or info.get('shortName'),
            'industry': info.get('industry'),
            'sector': info.get('sector'),
            'market': 'TW' if sym.endswith('.TW') else 'US',
            'market_cap': info.get('marketCap'),
            'pe': info.get('trailingPE') or info.get('forwardPE'),
            'dividend_yield': info.get('dividendYield', None),
            'dividend_per_share': info.get('lastDividendValue', None),
        }
    except Exception:
        return {}

def db_fallback(conn, cands):
    """
    從本地 DB 的 stock_data 撈最新一筆該代碼的公司名/產業
    """
    if not conn: return {}
    try:
        sql = (
            "SELECT symbol, company_name, industry "
            "FROM stock_data "
            "WHERE symbol IN ({}) "
            "AND company_name IS NOT NULL AND company_name <> '' AND company_name <> 'N/A' "
            "AND industry IS NOT NULL AND industry <> '' AND industry <> 'N/A' "
            "ORDER BY date DESC LIMIT 1"
        ).format(','.join(['%s'] * len(cands)))
        cur = conn.cursor()
        cur.execute(sql, cands)
        row = cur.fetchone()
        cur.close()
        if row:
            return {'symbol': row[0], 'company_name': row[1], 'industry': row[2]}
    except Exception:
        pass
    return {}

def merge_info(primary: dict, fallback: dict) -> dict:
    out = dict(primary) if primary else {}
    for k, v in (fallback or {}).items():
        if out.get(k) in (None, '', 'N/A') and v not in (None, '', 'N/A'):
            out[k] = v
    # 基本欄位確保存在
    for k in ['symbol','company_name','industry','sector','market','market_cap','pe','dividend_yield','dividend_per_share']:
        out.setdefault(k, None)
    # 空白統一為 None
    for k in list(out.keys()):
        if isinstance(out[k], str) and (out[k].strip() == '' or out[k].strip().upper() == 'N/A'):
            out[k] = None
    return out

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({'error':'no_symbol'})); sys.exit(0)

    raw = sys.argv[1]
    sym = norm(raw)
    cands = alt_candidates(sym)

    # 1) 先試 yfinance
    primary = {}
    for s in cands:
        primary = get_info_from_yf(s)
        # 有抓到公司名或產業就認定成功
        if primary.get('company_name') or primary.get('industry'):
            break

    # 2) DB 後備
    conn = connect_db()
    fb = db_fallback(conn, cands) if cands else {}
    if conn: 
        try: conn.close()
        except: pass

    # 3) 合併輸出
    final = merge_info(primary, fb)
    # 若 symbol 仍為空，用第一個候選
    if not final.get('symbol') and cands:
        final['symbol'] = cands[0]

    print(json.dumps(final, ensure_ascii=False))



