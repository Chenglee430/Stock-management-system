# 📈 Stock-management-system
智慧股票分析、預測與風險評估平台（台股 / 美股）

> PHP + MySQL + Python + yfinance + Plotly.js + TailwindCSS  
> 即時報價｜公司資訊｜K 線（日/週/月）｜MA / MACD / RSI / BB｜AI 預測｜目標價｜操作建議｜風險評估｜登入/註冊

---

## 📌 功能特色

- **即時報價**：最新價、漲跌幅、成交量，自動補最近日線
- **公司基本資料**：公司名稱、產業、市值、PE、本益比、殖利率
- **K 線圖**：日/週/月顆粒度切換、1M~ALL 區間、可縮放/拖曳
- **技術指標**：MA(5/20/60)、MACD(12/26/9)、RSI(14)、布林通道(20,2)
- **互動 HUD**：滑鼠移動即時顯示（日期/收盤/漲跌%/量/RSI/MACD）
- **AI 模型**：明日收盤預測、目標價、操作建議、風險評估（含信心值）
- **主題**：深色 / 淺色切換
- **帳號系統**：註冊、登入、忘記密碼（含 4 碼驗證碼）

---

## 🧱 系統架構

```plaintext
Frontend (index.html)
 ├─ Plotly.js：互動 K 線與指標
 └─ TailwindCSS：樣式與 RWD

Backend (PHP)
 ├─ api.php        ← 統一 API 入口（quote/info/history/update/predict/...）
 ├─ auth.php       ← 註冊、登入、忘記密碼
 ├─ admin.php      ← 管理介面
 └─ config.php     ← DB 設定

Python (AI / Data)
 ├─ quote_live.py               ← 即時報價 + 近一年 OHLC
 ├─ company_info.py             ← 公司基本資料
 ├─ fetch_stock.py              ← 歷史資料擷取
 ├─ stock_scraper.py            ← 自動更新每日行情
 ├─ backfill_one.py             ← 批次補資料
 ├─ stock_predictor.py          ← 明日收盤預測
 ├─ stock_target_predictor.py   ← 目標價預測
 ├─ trade_signal.py             ← 操作建議
 └─ risk_engine.py              ← 風險評估


📁 檔案一覽（15 個）
類別	檔名	功能摘要
HTML	index.html	前端頁面，含 K 線、預測、建議、風險顯示
PHP	api.php	統一 API 接口，與 Python 模組整合
PHP	auth.php	註冊 / 登入 / 忘記密碼
PHP	admin.php	管理員頁面
PHP	config.php	MySQL 連線設定
SQL	db_init.sql	建立資料表（users, stock_data, logs）
Python	quote_live.py	取得最新報價與一年 OHLC（詳下）
Python	company_info.py	抓公司資訊與產業分類
Python	fetch_stock.py	下載股價資料
Python	stock_scraper.py	自動更新行情（排程使用）
Python	backfill_one.py	批次補資料
Python	stock_predictor.py	AI 模型預測明日收盤價
Python	stock_target_predictor.py	預測目標價（混合模型）
Python	trade_signal.py	產生操作建議
Python	risk_engine.py	風險評估與信心指標

1️⃣ 環境
Windows + XAMPP（Apache + PHP + MySQL）
Python 3.10+

2️⃣ 專案目錄
C:\xampp\htdocs\stock_project\

3️⃣ 安裝 Python 套件
pip install yfinance pandas numpy scikit-learn mysql-connector-python

4️⃣ 建立資料庫
phpMyAdmin → 匯入

5️⃣ 設定資料庫
// config.php
$DB_HOST 
$DB_USER 
$DB_PASS 
$DB_NAME 

6️⃣ 啟動 Apache + MySQL

💡 quote_live.py（即時報價與 OHLC）

用途
提供前端即時報價、漲跌幅與過去一年日線，用於繪製 K 線與技術分析。
______________________________________________________________
流程
使用 yfinance.Ticker(symbol) 抓取 fast_info。
若無法取得 → 自動 fallback 至 history(period='5d')。
回傳 ohlc[] 陣列（最多 1 年資料）。
支援台股 .TW、美股 .US 自動判別。
______________________________________________________________

其他 Python 模組摘要
______________________________________________________________
1️⃣ stock_predictor.py
明日收盤價預測（RandomForest + Linear + Ridge Ensemble）
回傳 next_close_pred 與模型信心。

2️⃣stock_target_predictor.py
長期目標價預測（技術面 + 基本面混合）
回傳 target_price、confidence。

3️⃣trade_signal.py
根據 MA / MACD / RSI / 量能 → 自動生成操作建議。
回傳 buy / hold / watch / stop_loss。

4️⃣risk_engine.py
計算波動率、VaR、RSI/ATR、漲跌異常等風險分數


🧭 API 一覽（api.php）
Action	                    說明	                      回傳內容
_________________________________________________________________________
quote_live          	即時報價 + OHLC	            最新價、漲跌幅、ohlc[]
info	                公司資訊	                   公司名稱、市值、PE、殖利率
history	             歷史 K 線	                 過去 400 根日線
update_today	        更新當日行情	               更新筆數
predict_next	        明日預測	                   收盤價預測
predict_target	      目標價預測	                 目標價、信心值
signal	              操作建議	                   建議文字、bias、信心
risk	                風險評估	                   數值化風險與建議


📊 前端互動特色

日 / 週 / 月 K 線切換（自動重採樣）
MA / MACD / RSI / BB 開關
1M / 3M / 6M / 1Y / YTD / ALL 區間
深色 / 淺色主題切換
滑鼠 hover 顯示即時 HUD（TradingView 風格）
支援拖曳 / 滾輪縮放（Plotly.scrollZoom）


🔄 自動化排程

Windows 任務排程器：
python "C:\xampp\htdocs\stock_project\stock_scraper.py"

台股：每日 18:30 更新
美股：每日早上 9:00 更新


🧠 系統流程圖
使用者輸入代號 → api.php
   ↓
呼叫 Python：
   ↳ quote_live.py      ← 即時報價 / OHLC
   ↳ company_info.py    ← 公司資訊
   ↳ stock_predictor.py ← 收盤預測
   ↳ stock_target_predictor.py ← 目標價
   ↳ trade_signal.py    ← 操作建議
   ↳ risk_engine.py     ← 風險評估
   ↓
整合 JSON → 前端 Plotly 繪圖顯示



🧰 授權與版本

License: MIT

作者：李承勳 (Li Cheng-Syun)

專案名稱：Stock-management-system

開發環境：Windows + XAMPP + Python 3.10

最後更新：2025-10
