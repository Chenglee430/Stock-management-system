#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, json, warnings
from datetime import date, timedelta
import pandas as pd
import yfinance as yf
import mysql.connector

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore")

DB = dict(host='127.0.0.1', user='stockapp', password='920430', database='stock_db')
MIN_ROWS = 60

def tomorrow_str():
    return (date.today() + timedelta(days=1)).isoformat()  # yfinance end 不含該日

def alt_candidates(raw: str):
    s = raw.strip().upper()
    if s.isdigit() and len(s)==4:
        return [f"{s}.TW", s, f"{s}.TWO"]
    out = [s, s.replace('.', '-'), s.replace('-', '.')]
    if s.endswith('.TW'):
        out += [s.replace('.TW',''), s.replace('.TW','.TWO')]
    seen=set(); r=[]
    for x in out:
        if x not in seen:
            seen.add(x); r.append(x)
    return r

def dl(sym, start=None, end=None):
    try:
        if start and end:
            return yf.download(sym, start=start, end=end, auto_adjust=False,
                               progress=False, threads=False, interval='1d')
        return yf.Ticker(sym).history(period="10y", interval="1d", auto_adjust=False)
    except Exception:
        return pd.DataFrame()

def connect_db():
    return mysql.connector.connect(**DB)

def write_db(conn, symbol_out: str, df: pd.DataFrame, name='N/A', ind='N/A'):
    df = df.reset_index().rename(columns={
        'Date':'date','Open':'open','High':'high','Low':'low',
        'Close':'close','Adj Close':'adj','Volume':'volume'
    })
    # 盡量用調整後收盤
    if 'adj' in df.columns:
        df['close'] = df['adj'].where(df['adj'].notna(), df['close'])

    df['symbol'] = symbol_out
    df['company_name'] = name
    df['industry'] = ind
    # 欄位順序符合資料表
    cols = ['symbol','company_name','industry','date','open','high','low','close','volume']
    df = df[cols]
    # None 轉換
    df = df.where(pd.notnull(df), None)

    sql = (
        "INSERT INTO stock_data (symbol,company_name,industry,date,open,high,low,close,volume) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON DUPLICATE KEY UPDATE "
        " company_name=VALUES(company_name),"
        " industry=VALUES(industry),"
        " open=VALUES(open), high=VALUES(high), low=VALUES(low),"
        " close=VALUES(close), volume=VALUES(volume)"
    )
    cur = conn.cursor()
    cur.executemany(sql, [tuple(r) for r in df.itertuples(index=False, name=None)])
    conn.commit(); cur.close()

def main():
    if len(sys.argv)<2:
        print(json.dumps({'error':'Usage: python backfill_one.py <symbol>'})); return
    raw = sys.argv[1]
    tried=[]
    try:
        conn = connect_db()
        end = tomorrow_str()
        for sym in alt_candidates(raw):
            for mode in ['3y','7y','10y']:
                if mode=='3y':
                    start = (date.today().replace(year=date.today().year-3)).isoformat()
                    df = dl(sym, start, end)
                elif mode=='7y':
                    start = (date.today().replace(year=max(1970, date.today().year-7))).isoformat()
                    df = dl(sym, start, end)
                else:
                    df = dl(sym, None, None)
                tried.append((sym, mode, 0 if df is None else len(df)))
                if df is not None and not df.empty and len(df)>=MIN_ROWS:
                    name, ind = 'N/A','N/A'
                    try:
                        info=yf.Ticker(sym).info or {}
                        name=info.get('longName') or info.get('shortName') or name
                        ind=info.get('industry') or ind
                    except Exception:
                        pass
                    target=sym
                    head=sym.split('.')[0]
                    if head.isdigit() and len(head)==4:
                        target=head+'.TW'
                    write_db(conn, target, df, name, ind)
                    print(json.dumps({'success':True,'written_symbol':target,'rows':int(len(df)),'from':sym,'mode':mode}, ensure_ascii=False))
                    return
        print(json.dumps({'error':'backfill_failed','tried':tried}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({'error':str(e)}, ensure_ascii=False))

if __name__=='__main__':
    main()
