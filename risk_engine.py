#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
import os, sys, json
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
os.environ["PYTHONIOENCODING"] = "utf-8"


import sys, json, warnings, math, random
import pandas as pd, numpy as np
import mysql.connector, yfinance as yf
warnings.filterwarnings("ignore", category=UserWarning)

DB = dict(host='127.0.0.1', user='stockapp', password='920430', database='stock_db')
MIN_ROWS = 120
HORIZON = 20            # 模擬視窗（交易日）
N_PATHS = 2000          # 模擬路徑數
ES_ALPHA = 0.95         # Expected Shortfall 信賴水準

def connect_db(): return mysql.connector.connect(**DB)

def alt_candidates(s):
    s = (s or '').strip().upper()
    if not s: return []
    if s.isdigit() and len(s)==4: return [f"{s}.TW", s, f"{s}.TWO"]
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
    for c in ['open','high','low','close','volume']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    for c in ['open','high','low']:
        df[c] = df[c].fillna(df['close'])
    df['volume'] = df['volume'].fillna(0)
    df = df.dropna(subset=['close']).sort_values('date').reset_index(drop=True)
    return df

# ===== 風險指標 =====
def sma(a, n): return pd.Series(a).rolling(n).mean().values
def atr(high, low, close, n=14):
    h, l, c = map(pd.Series, (high,low,close))
    pc = c.shift(1)
    tr = pd.concat([(h-l).abs(), (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean().values

def beta_vs_spy(df):
    try:
        spy = yf.download("SPY", period="2y", interval="1d", progress=False)['Adj Close'].pct_change().dropna()
    except Exception:
        return None
    me = pd.Series(df['close']).pct_change().dropna()
    j = me.align(spy, join='inner')
    if j[0].empty or j[1].empty: return None
    x, y = j[1].values, j[0].values
    vx = np.var(x)
    if vx <= 1e-12: return None
    return float(np.cov(x, y)[0,1] / vx)

def overnight_gap(df):
    # 當日開盤 / 前日收盤 -1
    oc = (df['open'].values[1:] / df['close'].values[:-1]) - 1.0
    if len(oc)==0: return None, None
    return float(np.percentile(np.abs(oc), 95)), float(np.nanmean(np.abs(oc)))

def max_drawdown(series):
    arr = np.array(series, dtype=float)
    peak = -1e30; mdd = 0.0
    for v in arr:
        peak = max(peak, v)
        mdd = max(mdd, (peak - v)/peak if peak>0 else 0.0)
    return float(mdd)

def earnings_flags(symbol_norm):
    try:
        tk = yf.Ticker(symbol_norm); cal = tk.calendar
        # 有些市場不提供；另外嘗試 get_earnings_dates
        nxt = None
        try:
            ed = tk.get_earnings_dates(limit=4)
            if ed is not None and not ed.empty:
                nxt = str(ed.index.min().date())
        except Exception:
            pass
        return nxt
    except Exception:
        return None

# ===== 模擬：殘差 bootstrap + 波動 EWMA 調節 =====
def simulate_paths(close, high, low, horizon=20, n_paths=2000, seed=0):
    rng = np.random.RandomState(seed or 0)
    ret = pd.Series(close).pct_change().dropna().values
    if len(ret)<60: raise RuntimeError("not enough returns")
    # EWMA 波動
    lam = 0.94
    vol = np.empty_like(ret); vol[0] = np.std(ret[:20]) or 1e-4
    for i in range(1,len(ret)):
        vol[i] = math.sqrt(lam*vol[i-1]**2 + (1-lam)*ret[i-1]**2)
    z = ret / (vol + 1e-12)
    z = z[np.isfinite(z)]
    last_close = float(close[-1])
    last_vol = float(vol[-1] if len(vol) else np.std(ret))
    # 高低影響：用歷史日內振幅分布
    day_rng = (np.array(high)-np.array(low))/np.array(close+1e-12)
    day_rng = day_rng[np.isfinite(day_rng)]
    rngs = day_rng[~np.isnan(day_rng)]
    res = []
    for _ in range(n_paths):
        price = last_close
        maxp = price
        v = last_vol
        for _d in range(horizon):
            zi = rng.choice(z)
            # 漸進波動：EWMA
            v = math.sqrt(lam*v*v + (1-lam)*(zi*v)**2)
            r = zi * v
            price *= (1.0 + r)
            # 以歷史振幅生成當日高點（近似）
            dr = rng.choice(rngs) if len(rngs) else 0.02
            high_today = max(price, price*(1+abs(dr)*0.5))
            maxp = max(maxp, high_today)
        res.append(maxp)
    return np.array(res)

def position_sizing_kelly(edge, winp, rr, cap=0.2):
    # 簡化 Kelly：f* = p - (1-p)/RR，限制上限
    if rr<=0: return 0.0
    f = winp - (1-winp)/rr
    return float(max(0.0, min(cap, f)))

def main():
    if len(sys.argv)<2:
        print(json.dumps({"error":"No symbol provided"})); return
    raw = sys.argv[1]
    horizon = int(sys.argv[2]) if len(sys.argv)>=3 and str(sys.argv[2]).isdigit() else HORIZON

    # 規範化代碼給 yfinance 查事件
    def norm(s):
        s = (s or '').upper()
        if s.isdigit() and len(s)==4: return s + '.TW'
        if s.endswith('.TW') or s.endswith('.TWO'): # C檢查台股
            return s
        return s.replace('.', '-')
    try:
        conn = connect_db()
        df = read_history(conn, raw)
        if df.empty or len(df) < MIN_ROWS:
            print(json.dumps({"error":"Not enough data","need":MIN_ROWS,"got":int(len(df)) if not df.empty else 0}, ensure_ascii=False)); return

        last_close = float(df['close'].iloc[-1])
        last_date  = str(df['date'].iloc[-1].date())

        # 風險指標
        vol20 = float(pd.Series(df['close']).pct_change().rolling(20).std().iloc[-1] or 0)  # 20日波動率
        atr14 = float(atr(df['high'], df['low'], df['close'], 14)[-1] or 0)
        adv20 = float(pd.Series(df['volume']).rolling(20).mean().iloc[-1] or 0)
        dollar_vol = float(adv20 * last_close)
        mdd60 = max_drawdown(df['close'].tail(60))
        gap95, gapMean = overnight_gap(df)
        beta = beta_vs_spy(df)
        earn_next = earnings_flags(norm(raw))

        # 模擬分佈（未來 N 日可能觸及的最高價）
        paths = simulate_paths(df['close'].values, df['high'].values, df['low'].values, horizon=horizon, n_paths=N_PATHS, seed=42)
        q = {k: float(np.percentile(paths, k)) for k in (5,10,25,50,60,75,90,95)}
        # Bear/Base/Bull 場景
        scenarios = {
            "bear": q[10],
            "base": q[60],   # 取略偏多的中位上方
            "bull": q[90]
        }
        # 下檔風險：VaR/ES 針對「持有一天」的日報酬（保守用 2×日波動）
        r = pd.Series(df['close']).pct_change().dropna().values
        if len(r)>20:
            var95 = float(np.percentile(r, 5))
            tail = r[r <= np.percentile(r,5)]
            es95 = float(tail.mean()) if len(tail)>0 else var95
        else:
            var95 = -2*vol20; es95 = var95*1.2

        # 推薦目標價：在事件前避險、取 base 與當前價的 max
        suggested = max(last_close, scenarios["base"])

        # 風險控管：以 ATR 設停損、用分位估勝率與RR估倉位
        stop = round(last_close - 1.5*atr14, 2)
        tp1  = round(scenarios["base"], 2)
        tp2  = round(scenarios["bull"], 2)
        winp = 0.4 + 0.6*( (q[60]-last_close) / max(1e-6, q[95]-last_close) )  # 粗估勝率（0.4~1.0）
        rr   = max(0.1, (tp1-last_close) / max(1e-6, last_close-stop))
        kelly= position_sizing_kelly(edge=0, winp=float(min(max(winp,0.05),0.95)), rr=float(rr), cap=0.2)

        out = {
            "success": True,
            "symbol": raw.upper(),
            "last_close": round(last_close,2),
            "last_close_date": last_date,
            "horizon_days": horizon,

            # 分佈 / 場景
            "target_distribution": {"p5":q[5],"p10":q[10],"p25":q[25],"p50":q[50],"p60":q[60],"p75":q[75],"p90":q[90],"p95":q[95]},
            "scenarios": scenarios,
            "suggested_target": round(float(suggested),2),

            # 風險指標
            "risk": {
                "vol20": round(vol20,4),
                "atr14": round(atr14,4),
                "beta_mkt": beta,
                "mdd60": round(mdd60,4),
                "gap95_abs": gap95,
                "gap_mean_abs": gapMean,
                "adv20": adv20,
                "dollar_vol": dollar_vol,
                "var95_daily": var95,
                "es95_daily": es95,
                "earnings_next": earn_next
            },

            # 操作參考
            "plan": {
                "entry": last_close,
                "stop": stop,
                "tp1": tp1,
                "tp2": tp2,
                "kelly_fraction_cap20pct": round(kelly,3)
            },

            # 摘要（可直接顯示）
            "summary": f"20日風險調整後目標：基準 {round(scenarios['base'],2)}（區間 {round(q[25],2)}~{round(q[90],2)}），ATR={round(atr14,2)}，日VaR95%={round(var95*100,2)}%，建議停損 {stop}、目標 {tp1}/{tp2}，建議倉位≤{round(kelly*100,1)}%{('；臨近財報' if earn_next else '')}。"
        }
        print(json.dumps(out, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error":f"{e}"}, ensure_ascii=False))

if __name__ == "__main__":
    main()
