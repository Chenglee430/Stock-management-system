#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, json, warnings
from datetime import date, timedelta
import pandas as pd
import yfinance as yf
import mysql.connector

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore")

DB = dict(host='localhost', user='root', password='', database='stock_db')
MIN_ROWS = 60

def today_str():
    return date.today().isoformat()

def tomorrow_str():
    return (date.today() + timedelta(days=1)).isoformat()  # yfinance end 不含該日，故取明天

def alt_candidates(raw: str):
    s = raw.strip().upper()
    if s.isdigit() and len(s)==4:
        return [f"{s}.TW", s, f"{s}.TWO"]
    base = s
    out = [base, base.replace('.', '-'), base.replace('-', '.')]
    if base.endswith('.TW'):
        out += [base.replace('.TW',''), base.replace('.TW','.TWO')]
    seen=set(); L=[]
    for x in out:
        if x not in seen:
            seen.add(x); L.append(x)
    return L

def yd(symbol, start=None, end=None):
    try:
        if start and end:
            return yf.download(symbol, start=start, end=end, auto_adjust=False,
                               progress=False, threads=False, interval='1d')
        return yf.Ticker(symbol).history(period="10y", interval="1d", auto_adjust=False)
    except Exception:
        return pd.DataFrame()

def connect_db():
    return mysql.connector.connect(**DB)

def write_db(conn, sym_out: str, df: pd.DataFrame, name='N/A', ind='N/A'):
    df = df.reset_index().rename(columns={'Date':'date','Close':'close','Adj Close':'adj'})
    if 'adj' in df.columns:
        df['close'] = df['adj'].where(df['adj'].notna(), df['close'])
    df['symbol'] = sym_out
    df['company_name'] = name
    df['industry'] = ind
    df = df[['symbol','company_name','industry','date','close']]
    df['open']=None; df['high']=None; df['low']=None; df['volume']=None
    df = df[['symbol','company_name','industry','date','open','high','low','close','volume']]
    df = df.where(pd.notnull(df), None)

    sql=("INSERT INTO stock_data (symbol,company_name,industry,date,open,high,low,close,volume) "
         "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
         "ON DUPLICATE KEY UPDATE company_name=VALUES(company_name),industry=VALUES(industry),close=VALUES(close),open=VALUES(open),high=VALUES(high),low=VALUES(low),volume=VALUES(volume)")
    cur=conn.cursor()
    cur.executemany(sql, [tuple(r) for r in df.itertuples(index=False, name=None)])
    conn.commit(); cur.close()

def main():
    if len(sys.argv)<2:
        print(json.dumps({'error':'Usage: python backfill_one.py <symbol>'})); return
    raw = sys.argv[1]
    tried=[]
    try:
        conn = connect_db()
        end = tomorrow_str()  # 讓今日資料可被包含
        # 試 3y、7y、10y
        for sym in alt_candidates(raw):
            for mode in ['range3y','range7y','period10y']:
                if mode=='range3y':
                    start = (date.today().replace(year=date.today().year-3)).isoformat()
                    df = yd(sym, start, end)
                elif mode=='range7y':
                    start = (date.today().replace(year=max(1970, date.today().year-7))).isoformat()
                    df = yd(sym, start, end)
                else:
                    df = yd(sym,None,None)
                tried.append((sym, mode, 0 if df is None else len(df)))
                if df is not None and not df.empty and len(df)>=MIN_ROWS:
                    # 取得公司/產業
                    name, ind = 'N/A','N/A'
                    try:
                        info=yf.Ticker(sym).info or {}
                        name=info.get('longName') or info.get('shortName') or name
                        ind=info.get('industry') or ind
                    except Exception:
                        pass
                    target = sym
                    head = sym.split('.')[0]
                    if head.isdigit() and len(head)==4:
                        target = head+'.TW'
                    write_db(conn, target, df, name, ind)
                    print(json.dumps({'success':True,'written_symbol':target,'rows':int(len(df)),'from':sym,'mode':mode}, ensure_ascii=False))
                    return
        print(json.dumps({'error':'backfill_failed','tried':tried}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({'error':str(e)}, ensure_ascii=False))

if __name__=='__main__':
    main()
