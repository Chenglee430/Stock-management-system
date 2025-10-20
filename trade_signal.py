#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
import os, sys, json
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
os.environ["PYTHONIOENCODING"] = "utf-8"

import sys, json, warnings
import pandas as pd, numpy as np
import mysql.connector

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore")

DB = dict(host='127.0.0.1', user='stockapp', password='920430', database='stock_db')
MIN_ROWS = 80     # 至少 80 根K棒
HORIZON_DAYS = 5  # 建議有效期（近日）

def connect_db(): return mysql.connector.connect(**DB)

def alt_candidates(raw: str):
    s = (raw or '').strip().upper()
    if not s: return []
    if s.isdigit() and len(s)==4:  # 台股代碼
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
    for c in ['open','high','low','close']: df[c] = pd.to_numeric(df[c], errors='coerce')
    df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0)
    for c in ['open','high','low']: df[c] = df[c].fillna(df['close'])
    df = df.dropna(subset=['close']).sort_values('date').reset_index(drop=True)
    return df

# ==== 指標 ====
def SMA(a, n):
    return pd.Series(a).rolling(n).mean().values

def EMA(a, n):
    a = pd.Series(a)
    k = 2/(n+1)
    out = []
    prev = None
    for v in a:
        if pd.isna(v): out.append(np.nan); continue
        prev = v if prev is None else v*k + prev*(1-k)
        out.append(prev)
    return np.array(out)

def RSI(close, n=14):
    c = pd.Series(close)
    delta = c.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ma_up = up.ewm(alpha=1/n, adjust=False).mean()
    ma_down = down.ewm(alpha=1/n, adjust=False).mean()
    rs = ma_up / (ma_down.replace(0, np.nan))
    rsi = 100 - (100/(1+rs))
    return rsi.values

def MACD(close, a=12, b=26, s=9):
    ema_a = EMA(close, a)
    ema_b = EMA(close, b)
    macd = ema_a - ema_b
    signal = EMA(macd, s)
    hist = macd - signal
    return macd, signal, hist

def ATR(high, low, close, n=14):
    h = pd.Series(high); l = pd.Series(low); c = pd.Series(close)
    prev_close = c.shift(1)
    tr = pd.concat([(h-l).abs(), (h-prev_close).abs(), (l-prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean().values

# ==== 規則打分 ====
def rule_score(df):
    close = df['close'].values
    high  = df['high'].values
    low   = df['low'].values
    vol   = df['volume'].values

    ma10 = SMA(close,10); ma20 = SMA(close,20); ma60 = SMA(close,60)
    rsi14 = RSI(close,14)
    macd, sig, hist = MACD(close,12,26,9)
    atr14 = ATR(high,low,close,14)
    vma20 = SMA(vol,20)

    i = len(df)-1  # 最新一根
    if i < 60: return None

    last_close = float(close[i])
    last_high  = float(high[i])
    last_low   = float(low[i])
    last_date  = str(df['date'].iloc[i].date())

    s = 50  # 初始中性 50
    reasons = []
    tags = []  # 用來描述 setup

    # 趨勢濾網
    slope20 = (ma20[i] - ma20[i-5]) if (i>=5 and not np.isnan(ma20[i-5])) else 0
    if last_close > ma20[i] > ma60[i] and slope20 > 0:
        s += 20; reasons.append("趨勢：價>MA20>MA60，MA20上彎")
        tags.append("多頭")
    elif last_close < ma20[i] < ma60[i] and slope20 < 0:
        s -= 20; reasons.append("趨勢：價<MA20<MA60，MA20下彎")
        tags.append("空頭")

    # 突破/壓力
    if i >= 20:
        hh20 = float(np.nanmax(high[i-19:i+1]))
        if last_close > hh20 * 0.999:   # 允許極小誤差
            s += 25; reasons.append(f"突破：收盤接近/創 20日高 ({hh20:.2f})")
            tags.append("突破")
        else:
            # 觀察是否靠近壓力
            dist = (hh20 - last_close) / last_close
            if 0 < dist < 0.02:
                s += 5; reasons.append("逼近 20日高，若放量突破可追")
                tags.append("待突破")

    # 量能
    if not np.isnan(vma20[i]) and vma20[i] > 0:
        vr = vol[i] / vma20[i]
        if vr >= 1.5:
            s += 10; reasons.append(f"量能放大：{vr:.2f}× 近20均量")
        elif vr <= 0.5:
            s -= 5; reasons.append(f"量能偏弱：{vr:.2f}× 近20均量")

    # 動能
    if not (np.isnan(macd[i]) or np.isnan(sig[i])):
        if macd[i] > sig[i]:
            s += 8; reasons.append("MACD 多頭交叉上方")
        else:
            s -= 8; reasons.append("MACD 空頭交叉下方")
        # 柱體變化
        if i>=3 and all(not np.isnan(x) for x in hist[i-3:i+1]):
            if hist[i] > hist[i-1] > hist[i-2]:
                s += 5; reasons.append("動能增強（MACD 柱體連續放大）")
            elif hist[i] < hist[i-1] < hist[i-2]:
                s -= 5; reasons.append("動能轉弱（MACD 柱體連續縮小）")

    # RSI 區間
    if not np.isnan(rsi14[i]):
        if 45 <= rsi14[i] <= 70:
            s += 5; reasons.append(f"RSI {rsi14[i]:.0f}：多頭區")
        elif rsi14[i] > 75:
            s -= 10; reasons.append(f"RSI {rsi14[i]:.0f}：過熱")
        elif rsi14[i] < 30:
            s += 6; reasons.append(f"RSI {rsi14[i]:.0f}：超賣反彈潛力")

    # 回測買點（多頭趨勢且靠近 MA10/20）
    if last_close > ma60[i] and slope20 > 0:
        if abs(last_close - ma10[i]) / last_close < 0.01 or abs(last_close - ma20[i]) / last_close < 0.015:
            s += 12; reasons.append("回測均線附近（MA10/20）")
            tags.append("回測")

    # 止損/目標（用 ATR）
    atr = float(atr14[i]) if not np.isnan(atr14[i]) else max(1.0, last_close*0.01)
    # 優先根據 setup 決定 entry
    entry = None
    setup = "觀察"
    if "突破" in tags and i>=20:
        hh20 = float(np.nanmax(high[i-19:i+1]))
        entry = round(max(last_high, hh20) + atr*0.1, 2)
        setup = "突破追價"
    elif "回測" in tags:
        entry = round((ma10[i] if abs(last_close-ma10[i])<abs(last_close-ma20[i]) else ma20[i]), 2)
        setup = "回測承接"
    else:
        entry = round(last_close, 2)
        setup = "區間操作"

    stop  = round(entry - 1.5*atr, 2)
    tp1   = round(entry + 1.0*atr, 2)
    tp2   = round(entry + 2.0*atr, 2)

    # 信心分數與偏向
    conf = max(0, min(100, s))
    bias = "偏多" if conf >= 60 else ("偏空" if conf <= 40 else "觀望")

    # 一句話（給使用者）
    if bias == "偏多":
        sentence = f"短線偏多：{setup}，進場 {entry}，停損 {stop}，目標 {tp1}/{tp2}（信心 {conf:.0f}）。"
    elif bias == "偏空":
        sentence = f"短線偏空：反彈觀望，若跌破 {stop} 續弱；站回 {entry} 再觀察（信心 {conf:.0f}）。"
    else:
        sentence = f"短線觀望：等待放量突破或回測均線轉強（信心 {conf:.0f}）。"

    out = {
        "success": True,
        "symbol": str(df['symbol'].iloc[i]),
        "asof_date": last_date,
        "last_close": round(last_close,2),
        "bias": bias,
        "confidence": round(conf,1),
        "setup": setup,
        "entry": entry,
        "stop": stop,
        "tp1": tp1,
        "tp2": tp2,
        "timeframe_days": HORIZON_DAYS,
        "volume_avg20": float(vma20[i]) if not np.isnan(vma20[i]) else None,
        "atr14": round(atr,2),
        "reasons": reasons[-6:],   # 取重點
        "summary": sentence
    }
    return out

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error":"No symbol provided"})); return
    sym = sys.argv[1]
    try:
        conn = connect_db()
        df = read_history(conn, sym)
        if df.empty or len(df) < MIN_ROWS:
            print(json.dumps({"error":"Not enough data","need":MIN_ROWS,"got":int(len(df)) if not df.empty else 0}, ensure_ascii=False)); return
        out = rule_score(df)
        if not out:
            print(json.dumps({"error":"not_enough_for_rules"}, ensure_ascii=False)); return
        print(json.dumps(out, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error":f"{e}"}, ensure_ascii=False))

if __name__ == "__main__":
    main()
