#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse, time
from datetime import date, timedelta, datetime
from typing import List, Tuple, Optional, Dict
import pandas as pd, requests, yfinance as yf
from bs4 import BeautifulSoup
import mysql.connector

DB_CONFIG = dict(host='localhost', user='root', password='', database='stock_db')

def today_str(): return date.today().isoformat()
def tomorrow_str(): return (date.today() + timedelta(days=1)).isoformat()

# 預設期間（可用 --start/--end 覆寫）
DEFAULT_START = (date.today().replace(year=max(1970, date.today().year-3))).isoformat()
DEFAULT_END   = tomorrow_str()   # 讓今日資料可含入

DEFAULT_MIN_ROWS = 60
DEFAULT_BATCH_SIZE = 800
DEFAULT_SLEEP = 0.6
DEFAULT_TRIES = 3
DEFAULT_TRY_SLEEP = 1.2

FALLBACK_TW = ['2330.TW','2317.TW','2303.TW','2603.TW','2882.TW','2881.TW']
FALLBACK_SP500 = ['AAPL','MSFT','NVDA','GOOGL','AMZN','META','BRK-B','XOM','LLY','JPM']

UA = {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

def normalize_us_ticker(t: str) -> str:
    # BRK.B -> BRK-B, BF.B -> BF-B, 等
    return t.replace('.', '-') if '.' in t else t

def normalize_symbol(raw: str) -> str:
    s = raw.strip().upper()
    if s.isdigit() and len(s) == 4: return f"{s}.TW"
    return normalize_us_ticker(s)

def connect_db(): return mysql.connector.connect(**DB_CONFIG)

def ensure_table(conn):
    cur = conn.cursor()
    sql = (
        "CREATE TABLE IF NOT EXISTS stock_data ("
        "  symbol VARCHAR(20) NOT NULL,"
        "  company_name VARCHAR(255) NOT NULL,"
        "  industry VARCHAR(255) NOT NULL,"
        "  date DATE NOT NULL,"
        "  open DOUBLE NULL, high DOUBLE NULL, low DOUBLE NULL, close DOUBLE NULL, volume BIGINT NULL,"
        "  PRIMARY KEY (symbol, date), INDEX (industry)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
    )
    cur.execute(sql); conn.commit(); cur.close()

def insert_batch(conn, rows: List[Tuple]):
    if not rows: return
    sql = (
        "INSERT INTO stock_data (symbol,company_name,industry,date,open,high,low,close,volume) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON DUPLICATE KEY UPDATE company_name=VALUES(company_name),industry=VALUES(industry),"
        "open=VALUES(open),high=VALUES(high),low=VALUES(low),close=VALUES(close),volume=VALUES(volume)"
    )
    cur=conn.cursor(); cur.executemany(sql, rows); conn.commit(); cur.close()

def safe_download(symbol: str, start: str, end: str, tries: int = DEFAULT_TRIES, base_sleep: float = DEFAULT_TRY_SLEEP) -> pd.DataFrame:
    last_exc = None
    for i in range(1, tries+1):
        try:
            df = yf.download(symbol, start=start, end=end, auto_adjust=False, progress=False, threads=False, interval='1d')
            if isinstance(df, pd.DataFrame) and not df.empty:
                return df
        except Exception as e:
            last_exc = e
        time.sleep(base_sleep * i)
    return pd.DataFrame()

def expand_years(end_ymd: str, years: int) -> Tuple[str,str]:
    end_d = datetime.strptime(end_ymd, '%Y-%m-%d').date()
    try:
        start_d = end_d.replace(year=end_d.year - years)
    except ValueError:
        start_d = (pd.Timestamp(end_d) - pd.DateOffset(years=years)).date()
    return start_d.isoformat(), end_ymd

def fetch_one(symbol: str, start: str, end: str, meta_hint: Optional[Dict[str,str]]=None,
              min_rows: int = DEFAULT_MIN_ROWS, tries: int = DEFAULT_TRIES, try_sleep: float = DEFAULT_TRY_SLEEP) -> Optional[pd.DataFrame]:
    """
    下載一檔並回傳整理好的 DataFrame（帶上公司名/產業，優先用 meta_hint，再用 yfinance.info）
    """
    tkr = yf.Ticker(symbol)
    company_name = (meta_hint or {}).get('name', 'N/A')
    industry     = (meta_hint or {}).get('industry', 'N/A')
    if company_name == 'N/A' or industry == 'N/A':
        try:
            info = tkr.info or {}
            if company_name == 'N/A':
                company_name = info.get('longName') or info.get('shortName') or company_name
            if industry == 'N/A':
                industry = info.get('industry') or industry
        except Exception:
            pass

    df = safe_download(symbol, start, end, tries=tries, base_sleep=try_sleep)
    if df.empty or len(df) < min_rows:
        s3,_ = expand_years(end, 3); df = safe_download(symbol, s3, end, tries=tries, base_sleep=try_sleep)
    if df.empty or len(df) < min_rows:
        s7,_ = expand_years(end, 7); df = safe_download(symbol, s7, end, tries=tries, base_sleep=try_sleep)
    if df.empty: return None

    df = df.reset_index().rename(columns={
        'Date':'date','Open':'open','High':'high','Low':'low','Close':'close','Adj Close':'adj_close','Volume':'volume'
    })
    if 'adj_close' in df.columns:
        df['close'] = df['adj_close'].where(df['adj_close'].notna(), df['close'])
    # 補齊欄位避免 None/NaN 傳染
    for col in ['open','high','low','close','volume']:
        if col not in df.columns: df[col] = None

    df['symbol']=symbol; df['company_name']=company_name or 'N/A'; df['industry']=industry or 'N/A'
    df = df[['symbol','company_name','industry','date','open','high','low','close','volume']].where(pd.notnull(df), None)
    return df

def get_tw_list() -> List[Dict[str,str]]:
    """
    從 TWSE ISIN 頁面抓：代碼、公司名、產業
    欄位：0=代碼＋名稱（中間全形空格）、4=產業別
    """
    url='https://isin.twse.com.tw/isin/C_public.jsp?strMode=2'
    out=[]
    try:
        r=requests.get(url, headers=UA, timeout=25); r.encoding='big5'
        soup=BeautifulSoup(r.text,'html.parser')
        for tr in soup.find_all('tr')[2:]:
            tds=tr.find_all('td')
            if len(tds) > 5:
                raw=tds[0].get_text(strip=True)
                parts = raw.split('　')  # 全形空格
                code = parts[0].strip() if parts else ''
                name = parts[1].strip() if len(parts)>=2 else ''
                industry = tds[4].get_text(strip=True)
                if code.isdigit() and len(code)==4:
                    out.append({'symbol': f'{code}.TW', 'name': name, 'industry': industry})
    except Exception:
        # 失敗則只回退代碼清單（無名稱/產業）
        return [{'symbol': s, 'name': 'N/A', 'industry': 'N/A'} for s in FALLBACK_TW]
    return out if out else [{'symbol': s, 'name': 'N/A', 'industry': 'N/A'} for s in FALLBACK_TW]

def get_sp500_list() -> List[Dict[str,str]]:
    """
    從 Wikipedia S&P 500 表抓：代號、公司名、GICS 子產業
    """
    url='https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    out=[]
    try:
        r=requests.get(url, headers=UA, timeout=25); r.raise_for_status()
        soup=BeautifulSoup(r.text,'html.parser')
        table=soup.find('table',{'id':'constituents'})
        if not table: raise RuntimeError('no table')
        for tr in table.find_all('tr')[1:]:
            tds = tr.find_all('td')
            if len(tds) < 5: continue
            sym = tds[0].get_text(strip=True)
            security = tds[1].get_text(strip=True)
            sub_industry = tds[4].get_text(strip=True)  # GICS Sub-Industry
            out.append({'symbol': normalize_us_ticker(sym), 'name': security, 'industry': sub_industry})
    except Exception:
        return [{'symbol': s, 'name': 'N/A', 'industry': 'N/A'} for s in FALLBACK_SP500]
    return out if out else [{'symbol': s, 'name': 'N/A', 'industry': 'N/A'} for s in FALLBACK_SP500]

def main():
    p=argparse.ArgumentParser(description='Daily-updating stock scraper')
    p.add_argument('--start', default=DEFAULT_START)
    p.add_argument('--end',   default=DEFAULT_END)  # 預設到「明天」
    p.add_argument('--min-rows', type=int, default=DEFAULT_MIN_ROWS)
    p.add_argument('--batch', type=int, default=DEFAULT_BATCH_SIZE)
    p.add_argument('--sleep', type=float, default=DEFAULT_SLEEP)
    p.add_argument('--tries', type=int, default=DEFAULT_TRIES)
    p.add_argument('--try-sleep', type=float, default=DEFAULT_TRY_SLEEP)
    args=p.parse_args()

    tw_list = get_tw_list()
    sp_list = get_sp500_list()
    symbols = tw_list + sp_list
    if not symbols:
        print('無可用代碼'); return

    conn=connect_db(); ensure_table(conn)
    buf=[]; ok=fail=0; total=len(symbols)
    for idx,item in enumerate(symbols, start=1):
        raw=item['symbol']; meta={'name': item.get('name','N/A'), 'industry': item.get('industry','N/A')}
        sym=normalize_symbol(raw); print(f"[{idx}/{total}] 下載 {sym} ...")
        try:
            df=fetch_one(sym, args.start, args.end, meta_hint=meta,
                         min_rows=args.min_rows, tries=args.tries, try_sleep=args.try_sleep)
            if df is None or df.empty:
                print("  -> 無資料"); fail+=1
            else:
                rows=[tuple(r) for r in df.itertuples(index=False, name=None)]
                buf.extend(rows); ok+=1
        except Exception as e:
            print(f"  -> 例外：{e}"); fail+=1
        if len(buf)>=args.batch:
            print(f"  寫入 {len(buf)} 筆 ..."); insert_batch(conn, buf); buf.clear()
        time.sleep(args.sleep)
    if buf: print(f"  寫入最後 {len(buf)} 筆 ..."); insert_batch(conn, buf)
    conn.close(); print(f"完成。成功 {ok} 檔，失敗 {fail} 檔。")

if __name__=='__main__': main()
