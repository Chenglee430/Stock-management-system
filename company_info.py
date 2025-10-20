#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, json, warnings
import mysql.connector
import yfinance as yf

warnings.filterwarnings("ignore")

DB = dict(host='127.0.0.1', user='stockapp', password='920430', database='stock_db')

def connect_db():
    try:
        return mysql.connector.connect(**DB)
    except Exception as e:
        return None

def safe_json(data):
    """確保回傳為合法JSON"""
    try:
        return json.dumps(data, ensure_ascii=False)
    except Exception:
        return json.dumps({'error': 'json_encode_failed'}, ensure_ascii=False)

def get_info_from_yf(sym: str):
    try:
        t = yf.Ticker(sym)
        info = t.info or {}
        if not info:
            return {}
        return {
            'symbol': sym,
            'company_name': info.get('longName') or info.get('shortName'),
            'industry': info.get('industry'),
            'sector': info.get('sector'),
            'market': 'TW' if sym.endswith('.TW') else 'US',
            'market_cap': info.get('marketCap'),
            'pe': info.get('trailingPE') or info.get('forwardPE'),
            'dividend_yield': info.get('dividendYield'),
            'dividend_per_share': info.get('lastDividendValue'),
        }
    except Exception as e:
        return {'error': str(e)}

def db_fallback(conn, symbol):
    if not conn: return {}
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT symbol, company_name, industry, sector, market_cap, pe 
            FROM stock_data 
            WHERE symbol=%s ORDER BY date DESC LIMIT 1
        """, (symbol,))
        row = cur.fetchone()
        cur.close()
        return row or {}
    except Exception:
        return {}

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(safe_json({'error': 'no_symbol'})); sys.exit(0)

    sym = sys.argv[1].strip().upper()
    info = get_info_from_yf(sym)

    if not info.get('company_name'):
        conn = connect_db()
        fb = db_fallback(conn, sym)
        if conn: conn.close()
        info.update({k:v for k,v in fb.items() if v and not info.get(k)})

    if not info:
        info = {'error': 'no_data'}

    print(safe_json(info))

