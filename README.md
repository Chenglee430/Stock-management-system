Stock-management-system


智慧股票分析、預測與風險評估平台（台股 / 美股）

PHP + MySQL + Python + yfinance + Plotly.js + TailwindCSS
即時報價｜公司資訊｜K 線（日/週/月）｜MA / MACD / RSI / BB｜AI 預測｜目標價｜操作建議｜風險評估｜登入/註冊

目錄

功能特色

系統架構

檔案一覽（15 個）

安裝與執行

資料庫結構

後端 API 一覽

Python 模組說明

quote_live.py（即時報價與OHLC）

其他模型腳本

前端 UI 與互動

排程建議

授權

功能特色

即時報價：最新價、漲跌幅、成交量；不足時自動以最近日線補值

公司基本資料：公司名稱、產業、市值、PE、殖利率等

K 線圖：日/週/月顆粒度切換；1M/3M/6M/1Y/YTD/ALL 區間；可縮放/拖曳

技術指標：MA(5/20/60)、MACD(12/26/9)、RSI(14)、布林通道(20,2)

互動 HUD：滑鼠移動顯示日期/收盤/漲跌%/量/RSI/MACD（TradingView 風格）

AI：明日收盤預測、目標價預估、操作建議、風險評估（含信心估計）

主題：深色 / 淺色切換

帳號系統：註冊、登入、忘記密碼（驗證碼）

系統架構
Frontend (index.html)
 ├─ Plotly.js：互動 K 線、指標與 HUD
 └─ TailwindCSS：樣式與 RWD

Backend (PHP)
 ├─ api.php        ← 統一 API 入口（quote/info/history/update/predict/...）
 ├─ auth.php       ← 註冊、登入、忘記密碼
 ├─ admin.php      ← 管理端
 └─ config.php     ← DB 設定

Python (ML / Data)
 ├─ quote_live.py               ← 即時報價 + 近一年 OHLC
 ├─ company_info.py             ← 公司基本資料
 ├─ fetch_stock.py / stock_scraper.py / backfill_one.py ← 歷史資料抓取與回填
 ├─ stock_predictor.py          ← 明日收盤預測
 ├─ stock_target_predictor.py   ← 目標價預測
 ├─ trade_signal.py             ← 操作建議
 └─ risk_engine.py              ← 風險評估

檔案一覽（15 個）

index.html（前端頁面，含 K 線、指標、HUD、各功能按鈕）

api.php（主要 API 路由與 Python 執行器）

auth.php（註冊/登入/忘記密碼）

admin.php（管理介面）

config.php（DB 連線設定）

db_init.sql（資料表 schema）

quote_live.py（即時報價 + 近一年 OHLC，詳見下節）

company_info.py

fetch_stock.py

stock_scraper.py

backfill_one.py

stock_predictor.py

stock_target_predictor.py

trade_signal.py

risk_engine.py

安裝與執行

環境

Windows + XAMPP（Apache + PHP + MySQL）

Python 3.10+

放置

C:\xampp\htdocs\stock_project\


安裝 Python 套件

py -3 -m pip install --upgrade pip
py -3 -m pip install yfinance pandas numpy scikit-learn mysql-connector-python


建立資料庫

phpMyAdmin 匯入 db_init.sql

DB 設定

編輯 config.php（host/user/pass/db）

啟動服務

http://localhost/stock_project/index.html


首次使用建議

登入後先按「更新到最新日K」回填資料 → K 線出現後再跑「預測 / 目標價 / 建議 / 風險」

資料庫結構

主要表（示意）：

users：帳號、密碼雜湊、建立時間等

stock_data：symbol, date, open, high, low, close, volume

user_search_log：查詢紀錄（可擴充）

實際 schema 以 db_init.sql 為準。

後端 API 一覽

皆以 POST api.php + action 參數呼叫（auth.php 為登入相關）

Action	說明	主要參數	回傳要點
diag	健康檢查	-	ok, time
quote_live	即時報價 + 近一年 OHLC	symbol	last, prevClose, open, high, low, volume, changePct, ohlc[]
info	公司基本資料	symbol	company_name, industry, market_cap, pe, dividend_*
history	從 DB 取近 400 根（日線）	symbol	ohlc[]
update_today	回填至最新	symbol	updated
predict_next	明日收盤預測	symbol	next_close_pred, components{rf,lr,ridge}...
predict_target	目標價預估	symbol, horizon	suggested_target / tech_target / val_target ...
signal	操作建議	symbol	bias, setup, summary, timeframe_days ...
risk	風險評估	symbol, horizon	risk.var95_daily, risk.atr14, plan.kelly_fraction_cap20pct ...
Python 模組說明
quote_live.py（即時報價與OHLC）

用途：回傳「最新價/漲跌幅/量」與「近一年日線 OHLC」給前端 K 線即時繪圖

台/美股自動正規化：2330 自動補成 2330.TW

資料策略：

先用 Ticker.fast_info 取 lastPrice/previousClose/...

取不到就以 history(5d,1d) 補：last = 最新 close、prev = 前一日 close

另取 history(1y,1d) 組 ohlc[]（最多 ~220 根）

典型輸出

{
  "symbol": "2330.TW",
  "last": 638.0,
  "prevClose": 632.0,
  "open": 635.0,
  "high": 641.0,
  "low":  631.0,
  "volume": 31234567,
  "changePct": 0.95,
  "ohlc": [{"date":"2025-09-01","open":...,"high":...,"low":...,"close":...,"volume":...}, ...]
}


實作重點：fast_info → history 回補、ohlc 結構、一年日線限制與台股代號處理。

quote_live

相依套件

yfinance, pandas, numpy（間接）, warnings

其他模型腳本

stock_predictor.py：明日收盤價預測（多模型組合），前端對應欄位：next_close_pred；若需要建議與信心，前端已提供推導邏輯（以變異係數/模型一致性估計）。

stock_target_predictor.py：目標價預估；常見鍵名：suggested_target / tech_target / val_target。

trade_signal.py：操作建議；典型鍵名：bias（偏多/偏空/觀望）、setup（型態）、summary、timeframe_days。

risk_engine.py：風險評估；典型鍵名：risk.var95_daily（VaR%）、risk.atr14、plan.kelly_fraction_cap20pct（Kelly 倉位上限%）。

前端已做 鍵名容錯與顯示映射，避免欄位不同導致空白。

前端 UI 與互動

K 線顆粒度：日 / 週 / 月（前端重採樣）

時間區間：1M / 3M / 6M / 1Y / YTD / ALL

指標：MA5/20/60、BB(20,2)、RSI(14)、MACD(12,26,9)

主題：深 / 淺

互動：拖曳 / 滾輪縮放 / 十字 spikeline / HUD（右上角顯示游標對應數值）

排程建議

Windows 任務排程器（Task Scheduler）：

py -3 "C:\xampp\htdocs\stock_project\stock_scraper.py"


台股：每日收盤後 18:30

美股：每日早上 09:00（台灣時間）

授權

License：MIT

作者：李承勳 (Li Cheng-Hsun)

最後更新：2025-10
