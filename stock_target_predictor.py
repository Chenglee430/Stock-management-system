#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-

# -*- coding: utf-8 -*-
import os, sys, json
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
os.environ["PYTHONIOENCODING"] = "utf-8"


# 建議：若你的摘要會輸出特殊符號（例如 ≤ ≥ ★ …），請改成 ASCII：
# text = text.replace("≤", "<=").replace("≥", ">=").replace("★", "*")

import sys, json, warnings, math
from datetime import datetime
import pandas as pd, numpy as np
import mysql.connector
import yfinance as yf

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore")

# === 環境參數（依你的 MySQL 調整） ===
DB = dict(host='127.0.0.1', user='stockapp', password='920430', database='stock_db')
MIN_ROWS = 60                # 最少歷史筆數
DEFAULT_HORIZON = 40         # 目標價看幾個交易日（約2個月）
TECH_WEIGHT = 0.7            # 綜合權重：技術 70%
VAL_WEIGHT  = 0.3            # 綜合權重：估值 30%

# 常見台股→海外對應（如有 ADR 可增加）
ADR_MAP = {'2330':'TSM','2303':'UMC','2412':'CHT','3711':'ASX'}

def connect_db():
    return mysql.connector.connect(**DB)

def alt_candidates(raw: str):
    s = (raw or '').strip().upper()
    if not s: return []
    if s.isdigit() and len(s)==4:
        return [f"{s}.TW", s, f"{s}.TWO"]
    return [s, s.replace('.', '-'), s.replace('-', '.')]

def read_history(conn, raw):
    cands = alt_candidates(raw)
    if not cands: return pd.DataFrame()
    ph = ','.join(['%s'] * len(cands))
    sql = f"""SELECT symbol,date,open,high,low,close,volume
              FROM stock_data
              WHERE symbol IN ({ph})
              ORDER BY date"""
    df = pd.read_sql(sql, conn, params=cands)
    if df.empty: return df
    df['date'] = pd.to_datetime(df['date'])
    # 補值：避免 NaN 傳染
    for col in ['open','high','low','close']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0)
    for c in ['open','high','low']:
        df[c] = df[c].fillna(df['close'])
    df = df.dropna(subset=['close']).sort_values('date').reset_index(drop=True)
    return df

# === 技術特徵（與你現有 stock_predictor 的設計一致、略化以穩定） ===
def make_features(df: pd.DataFrame, prefix='t'):
    df = df.copy().sort_values('date').reset_index(drop=True)
    df['ret1'] = df['close'].pct_change()
    for n in (3,5,10,20):
        df[f'ma{n}'] = df['close'].rolling(n).mean()
        delta = df['close'].diff()
        up = delta.clip(lower=0).rolling(n).mean()
        down = (-delta.clip(upper=0)).rolling(n).mean()
        rs = up / (down.replace(0, np.nan))
        df[f'rsi{n}'] = 100 - (100/(1+rs))
    df['vol_log'] = np.log1p(df['volume'].fillna(0))
    feats = ['close','ret1','vol_log'] + [f'ma{n}' for n in (3,5,10,20)] + [f'rsi{n}' for n in (3,5,10,20)]
    X = df[feats].shift(1)   # 用 t-1 預測 t
    out = pd.concat([df[['date']], X], axis=1)
    out.columns = ['date'] + [f'{prefix}_{c}' for c in X.columns]
    return out.dropna()

# === 產生「未來N日最高價」的 Label（技術面目標價） ===
def future_high_label(df: pd.DataFrame, horizon=20):
    # 建 rolling 窗：未來 N 日的 high 最大值
    # 做法：shift(-i) 的 high 取 row-wise 最大
    highs = []
    for i in range(1, horizon+1):
        highs.append(df['high'].shift(-i))
    arr = np.vstack([h.values for h in highs]).T  # shape: [len, horizon]
    fut_high = np.nanmax(arr, axis=1)
    return pd.Series(fut_high, index=df.index, name='future_high')

# ===  Ensemble === 
def ensemble_predict(X_train, y_train, X_pred):
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import LinearRegression, Ridge

    rf = RandomForestRegressor(n_estimators=320, random_state=0, n_jobs=-1, min_samples_leaf=2)
    rf.fit(X_train, y_train)
    rf_hat = float(rf.predict(X_pred)[0])
    lr = LinearRegression()
    lr.fit(X_train, y_train)
    lr_hat = float(lr.predict(X_pred)[0])

    rg = Ridge(alpha=1.0, random_state=0)
    rg.fit(X_train, y_train)
    rg_hat = float(rg.predict(X_pred)[0])

    yhat = 0.5*rf_hat + 0.3*lr_hat + 0.2*rg_hat
    return round(yhat,2), {'rf':round(rf_hat,2),'lr':round(lr_hat,2),'ridge':round(rg_hat,2)}

# === 估值面目標價（PE × EPS），以 trailing/forward 擇一可用值 ===
def valuation_target(symbol_norm: str):
    try:
        t = yf.Ticker(symbol_norm)
        info = t.info or {}
        eps = info.get('trailingEps') or info.get('forwardEps')
        pe  = info.get('trailingPE')  or info.get('forwardPE')
        if eps is None or pe is None: return None, {'eps':eps,'pe':pe}
        target = float(eps) * float(pe)
        return round(target,2), {'eps':eps, 'pe':pe}
    except Exception:
        return None, {'eps':None, 'pe':None}

def norm_symbol(s: str):
    s = (s or '').strip().upper()
    if s.isdigit() and len(s)==4: return s + '.TW'
    if s.endswith('.TW') or s.endswith('.TWO'): # 檢查台股
        return s
    return s.replace('.', '-')

def main():
    if len(sys.argv) < 2:
        print(json.dumps({'error':'No symbol provided'})); return
    raw = sys.argv[1]
    horizon = int(sys.argv[2]) if len(sys.argv)>=3 and str(sys.argv[2]).isdigit() else DEFAULT_HORIZON

    sym_norm = norm_symbol(raw)
    try:
        conn = connect_db()
        df = read_history(conn, raw)
        if df.empty or len(df) < MIN_ROWS:
            print(json.dumps({'error':'Not enough data','need':MIN_ROWS,'got':int(len(df)) if not df.empty else 0}, ensure_ascii=False)); return

        # 構建特徵 + 技術面 Label
        feats = make_features(df, prefix='t')                 # t-1 特徵
        label = future_high_label(df, horizon=horizon)        # 未來N日最高價
        data = pd.merge(df[['date','close']], feats, on='date', how='inner')
        data = pd.concat([data, label], axis=1).dropna().reset_index(drop=True)

        if len(data) < 40:
            print(json.dumps({'error':'Not enough aligned data','need':40,'got':int(len(data))}, ensure_ascii=False)); return

        # 訓練/預測
        X = data.drop(columns=['date','close','future_high']).values
        y = data['future_high'].values
        X_train, y_train = X[:-1], y[:-1]
        X_pred = X[-1:].copy()

        # 若 y 幾乎無變異，回退：目標價=最近收盤價
        if np.std(y_train) < 1e-6:
            last_close = float(df['close'].iloc[-1])
            last_date  = df['date'].iloc[-1].strftime('%Y-%m-%d')
            print(json.dumps({
                'success': True,
                'symbol': raw.upper(),
                'method': 'fallback_last_close_as_target',
                'last_close': round(last_close,2),
                'last_close_date': last_date,
                'horizon_days': horizon,
                'tech_target': round(last_close,2),
                'val_target': None,
                'suggested_target': round(last_close,2),
                'components': {}
            }, ensure_ascii=False)); return

        tech_hat, parts = ensemble_predict(X_train, y_train, X_pred)

        last_close = float(df['close'].iloc[-1])
        last_date  = df['date'].iloc[-1].strftime('%Y-%m-%d')

        # 估值面（可能拿不到，就給 None）
        val_hat, val_parts = valuation_target(sym_norm)

        # 綜合建議
        if val_hat is None:
            suggested = tech_hat
        else:
            suggested = TECH_WEIGHT*tech_hat + VAL_WEIGHT*val_hat
        out = {
            'success': True,
            'symbol': raw.upper(),
            'method': 'TargetPrice = max_high_next_%dd (tech)  +  valuation mix' % horizon,
            'last_close': round(last_close,2),
            'last_close_date': last_date,
            'horizon_days': horizon,
            'tech_target': tech_hat,
            'val_target': val_hat,
            'suggested_target': round(suggested,2),
            'components': {'tech_rf_lr_ridge': parts, 'valuation_inputs': val_parts}
        }
        print(json.dumps(out, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({'error': f'An error occurred: {e}'}, ensure_ascii=False))

if __name__ == '__main__':
    main()
