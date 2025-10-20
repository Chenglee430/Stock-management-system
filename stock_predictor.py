#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
import os, sys, json
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
os.environ["PYTHONIOENCODING"] = "utf-8"

import sys, json, warnings
from datetime import datetime
import pandas as pd
import numpy as np
import mysql.connector

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore")

try:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import LinearRegression, Ridge
except Exception as e:
    print(json.dumps({'error': f'sklearn_not_available: {e}'}))
    sys.exit(0)

# 依你的環境調整
DB = dict(host='127.0.0.1', user='stockapp', password='920430', database='stock_db')
MIN_ROWS = 60
# 常見台股↔海外對應；沒有 ADR 的留 None（避免亂配）
ADR_MAP = {
    '2330': 'TSM',      # 台積電
    '2303': 'UMC',      # 聯電
    '2317': 'HNHPF',    # 鴻海（OTC）
    '3711': 'ASX',      # 日月光
    '2409': 'AUOTY',    # 友達 ADR
    '2412': 'CHT',      # 中華電
    # 可再擴充
}

def connect_db():
    return mysql.connector.connect(**DB)

def alt_candidates(raw: str):
    s = raw.strip().upper()
    if s.isdigit() and len(s) == 4:
        return [f"{s}.TW", s, f"{s}.TWO"]
    alts = [s, s.replace('.', '-'), s.replace('-', '.')]
    seen=set(); out=[]
    for a in alts:
        if a not in seen:
            seen.add(a); out.append(a)
    return out

def guess_proxy(raw: str):
    s = raw.strip().upper()
    base = s[:-3] if s.endswith('.TW') else s
    return ADR_MAP.get(base)

def read_history(conn, raw):
    cands = alt_candidates(raw)
    ph = ','.join(['%s'] * len(cands))
    sql = f"""SELECT symbol,date,close,volume,open,high,low
              FROM stock_data
              WHERE symbol IN ({ph})
              ORDER BY date"""
    df = pd.read_sql(sql, conn, params=cands)
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
        # 補值：缺開高低時以 close 代，缺量以 0 代（僅用於特徵）
        for col in ['open','high','low','close','volume']:
            if col not in df.columns: df[col] = np.nan
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df['open']  = pd.to_numeric(df['open'],  errors='coerce').fillna(df['close'])
        df['high']  = pd.to_numeric(df['high'],  errors='coerce').fillna(df['close'])
        df['low']   = pd.to_numeric(df['low'],   errors='coerce').fillna(df['close'])
        df['volume']= pd.to_numeric(df['volume'],errors='coerce').fillna(0)
        df = df.dropna(subset=['close'])
        df = df.sort_values('date')
    return df

def make_features(df: pd.DataFrame, prefix='t'):
    df = df.copy().sort_values('date').reset_index(drop=True)
    # 場內特徵
    df['ret1'] = df['close'].pct_change()
    for n in (3,5,10,20):
        df[f'ma{n}'] = df['close'].rolling(n).mean()
        # 簡化 RSI（避免過度複雜的 rolling 乘積 NaN 傳染）
        delta = df['close'].diff()
        up = delta.clip(lower=0).rolling(n).mean()
        down = (-delta.clip(upper=0)).rolling(n).mean()
        rs = up / (down.replace(0, np.nan))
        df[f'rsi{n}'] = 100 - (100 / (1 + rs))
    df['vol_log'] = np.log1p(df['volume'].fillna(0))

    feats = ['close','ret1','vol_log'] + [f'ma{n}' for n in (3,5,10,20)] + [f'rsi{n}' for n in (3,5,10,20)]
    X = df[feats].shift(1)     # 用「前一日」特徵預測當日 close
    y = df['close']
    X.columns = [f'{prefix}_{c}' for c in X.columns]
    out = pd.concat([df[['date']], X, y.rename('target')], axis=1).dropna()
    return out

def robust_ensemble(X_train, y_train, X_pred):
    # 3-model ensemble：RF + LR + Ridge
    rf = RandomForestRegressor(
        n_estimators=320,
        random_state=0,
        max_depth=None,
        min_samples_leaf=2,
        n_jobs=-1
    )
    rf.fit(X_train, y_train)
    yhat_rf = float(rf.predict(X_pred)[0])

    lr = LinearRegression()
    lr.fit(X_train, y_train)
    yhat_lr = float(lr.predict(X_pred)[0])

    rg = Ridge(alpha=1.0, random_state=0)
    rg.fit(X_train, y_train)
    yhat_rg = float(rg.predict(X_pred)[0])

    # 權重：RF 0.5、LR 0.3、Ridge 0.2（可再調）
    yhat = 0.5*yhat_rf + 0.3*yhat_lr + 0.2*yhat_rg
    return round(yhat, 2), {'rf':yhat_rf, 'lr':yhat_lr, 'ridge':yhat_rg}

def main():
    if len(sys.argv) < 2:
        print(json.dumps({'error':'No symbol'})); return
    raw = sys.argv[1]
    proxy = sys.argv[2] if len(sys.argv)>=3 else None
    if not proxy or proxy.strip()=='':
        proxy = guess_proxy(raw)

    try:
        conn = connect_db()
        base = read_history(conn, raw)
        if base.empty or len(base) < MIN_ROWS:
            print(json.dumps({'error':'Not enough data', 'need': MIN_ROWS, 'got': int(len(base)) if not base.empty else 0})); return

        df_base = make_features(base, prefix='t')
        data = df_base.copy()
        proxy_used = None

        if proxy:
            prox = read_history(conn, proxy)
            if not prox.empty and len(prox) >= 40:
                df_p = make_features(prox, prefix='p')
                data = pd.merge(df_base, df_p.drop(columns=['target']), on='date', how='left')
                proxy_used = proxy

        data = data.dropna().reset_index(drop=True)
        if len(data) < 40:
            print(json.dumps({'error':'Not enough aligned data', 'need': 40, 'got': int(len(data))})); return

        X = data.drop(columns=['date','target']).values
        y = data['target'].values
        X_train, y_train = X[:-1], y[:-1]
        X_pred = X[-1:].copy()

        # 防呆：全部常數或變異過低
        if np.std(y_train) < 1e-6:
            last_close = float(base['close'].iloc[-1])
            last_date  = base['date'].iloc[-1].strftime('%Y-%m-%d')
            print(json.dumps({
                'success': True,
                'symbol': raw.upper(),
                'method': 'fallback_last_close',
                'last_close': round(last_close,2),
                'last_close_date': last_date,
                'next_close_pred': round(last_close,2),
                'proxy_used': None
            }, ensure_ascii=False)); return

        yhat, parts = robust_ensemble(X_train, y_train, X_pred)

        last_close = float(base['close'].iloc[-1])
        last_date  = base['date'].iloc[-1].strftime('%Y-%m-%d')

        print(json.dumps({
            'success': True,
            'symbol': raw.upper(),
            'method': 'RF+LR+Ridge ensemble',
            'last_close': round(last_close,2),
            'last_close_date': last_date,
            'next_close_pred': yhat,
            'proxy_used': proxy_used,
            'components': {k: round(v,2) for k,v in parts.items()}
        }, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({'error': f'An error occurred: {e}'}, ensure_ascii=False))

if __name__ == '__main__':
    main()
