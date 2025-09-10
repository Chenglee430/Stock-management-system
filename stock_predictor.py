#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys, json, warnings
from datetime import datetime
import pandas as pd
import numpy as np
import mysql.connector
from sklearn.linear_model import LinearRegression

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore")

DB = dict(host='localhost', user='root', password='', database='stock_db')
MIN_ROWS = 60

def connect_db():
    return mysql.connector.connect(**DB)

def alt_candidates(raw: str):
    s = raw.strip().upper()
    if s.isdigit() and len(s) == 4:
        return [f"{s}.TW", s, f"{s}.TWO"]
    base = s.replace('.', '-')
    alts = [s, base, s.replace('-', '.')]
    if s.endswith('.TW'):
        alts += [s.replace('.TW',''), s.replace('.TW','.TWO')]
    # 去重
    seen=set(); out=[]
    for a in alts:
        if a not in seen:
            seen.add(a); out.append(a)
    return out

def read_history(conn, raw):
    cand = alt_candidates(raw)
    ph = ','.join(['%s'] * len(cand))
    sql = f"SELECT symbol,date,close FROM stock_data WHERE symbol IN ({ph}) ORDER BY date"
    df = pd.read_sql(sql, conn, params=cand)
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
        df = df.dropna(subset=['close'])
    return df

def predict_lr_next_close(df: pd.DataFrame):
    df = df.copy()
    df['ord'] = df['date'].map(lambda d: d.toordinal())
    X = df[['ord']].values
    y = df['close'].values
    mdl = LinearRegression().fit(X, y)
    next_ord = df['ord'].iloc[-1] + 1
    yhat = float(mdl.predict([[next_ord]])[0])
    return round(yhat, 2)

def main():
    if len(sys.argv) < 2:
        print(json.dumps({'error':'No symbol'})); return
    raw = sys.argv[1]

    try:
        conn = connect_db()
        df = read_history(conn, raw)
        if df.empty or len(df) < MIN_ROWS:
            print(json.dumps({'error':'Not enough data'}, ensure_ascii=False)); return

        last_close = float(df['close'].iloc[-1])
        last_date  = df['date'].iloc[-1].strftime('%Y-%m-%d')
        next_close = predict_lr_next_close(df)

        print(json.dumps({
            'success': True,
            'symbol': raw.upper(),
            'method': 'Linear Regression',
            'last_close': round(last_close,2),
            'last_close_date': last_date,
            'next_close_pred': next_close  # 明日預測收盤價（數值）
        }, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({'error': f'An error occurred: {e}'}, ensure_ascii=False))

if __name__ == '__main__':
    main()
