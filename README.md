# stock-management-system


待更新


一個「帳號登入 + 股票資料庫 + 日更抓取 + 預測」的全端範例。前端單頁（Tailwind）透過 PHP API 操作 MySQL，並呼叫 Python 腳本批次/單檔更新 Yahoo Finance 日 K，同時提供簡單的線性回歸預測。

> 前端：`index.html`（登入、查詢、預測 UI）
>
> 後端：`auth.php`（註冊/登入/登出/忘記密碼）、`api.php`（股票查詢與預測 API）、`config.php`（資料庫設定）
>
> 批次/工具：`stock_scraper.py`（批量日更 TW + S\&P500）、`backfill_one.py`（單檔補資料）、`stock_predictor.py`（下一日收盤預測）、`fetch_stock.py`（區間抓資料/趨勢）

---

## ✨ 特色

* **帳號系統（PHP/Session）**：註冊、登入、登出、忘記密碼（產生臨時密碼）。
* **MySQL 結構化資料**：以 `(symbol, date)` 為複合主鍵，避免重複資料；對 `industry` 建索引，產業查詢更快。
* **資料更新策略**：

  * `stock_scraper.py` 批量抓取台股 + S\&P500（預設 3→7 年回溯補齊；end 設為「明天」讓當日未收盤回到最後完成日）。
  * `backfill_one.py` 針對單一代號嘗試多種代碼寫法（`2330.TW`/`2330`/`2330.TWO` 等），確保最小筆數門檻後才寫入。
* **前端操作齊全**：基本資料、歷史資料、最高價、依產業查詢、預測、以及「更新到今日」。
* **簡單預測**：以線性回歸擬合日期序列，輸出 `next_close_pred`（下一交易日收盤價的數值預估）。

---

## 📂 專案結構

```
.
├─ index.html              # 前端單頁（Tailwind + Fetch API）
├─ auth.php                # 帳號：register/login/logout/forgot（以 session 維持登入）
├─ api.php                 # 股票 API：info/history/highest/by_industry/predict/update_today
├─ config.php              # PHP DB 設定（host/user/pass/db）
├─ db_init.sql             # MySQL 結構初始化（users/login_attempts/stock_data/user_search_log）
├─ stock_scraper.py        # 批量日更（TWSE + S&P500）、自動回溯補齊
├─ backfill_one.py         # 單一代號補資料（多別名嘗試、滿足筆數後寫入）
├─ stock_predictor.py      # 線性回歸預測 next_close_pred
└─ fetch_stock.py          # 區間抓資料 + 簡單趨勢（上漲/下跌）
```

---

## 🔧 系統需求

* **Web/PHP**：XAMPP / WAMP / LAMP 皆可（PHP 7.4+）
* **MySQL**：8.x（或相容版本）
* **Python**：3.9+，建議使用虛擬環境
* **Pip 套件**：`yfinance`、`pandas`、`numpy`、`scikit-learn`、`mysql-connector-python`、`requests`、`beautifulsoup4`

安裝範例：

```bash
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install yfinance pandas numpy scikit-learn mysql-connector-python requests beautifulsoup4
```

---

## 🚀 安裝與初始化

1. **放置檔案**：把整個資料夾放到 `htdocs/stock-management-system/`（或你慣用目錄）。
2. **建立資料庫**：在 phpMyAdmin / MySQL CLI 匯入 `db_init.sql` 後會自動建立 `stock_db` 與必要資料表。
3. **設定 DB**：編輯 `config.php`（host/user/password/database）。
4. **啟動 Apache + MySQL**：以 XAMPP 控制台或系統服務啟動。
5. **開啟前端**：`http://localhost/stock-management-system/index.html`。
6. **首次註冊並登入**：於彈窗輸入帳號/密碼。

> 若使用遠端或區網機器，請以該主機 IP 開啟。例如 `http://192.168.1.10/stock-management-system/`。

---

## 🧭 前端操作流程

1. 登入成功後，於「股票查詢」輸入代號（`2330`/`2330.TW`/`AAPL`）。
2. 依序嘗試：**基本資料** / **歷史資料** / **最高價** / **依產業查詢**。
3. 在「股票預測」輸入代號，按 **預測** 查看 `next_close_pred`。
4. 按 **更新到今日** 會觸發 `api.php?action=update_today&symbol=...`（後端以 Python 補到最後可用日 K）。

---

## 🔌 API 介面（摘要）

> 路徑以專案根目錄為基準。

### 認證（`auth.php`）

* `POST ?action=register` Body: `{username, password}` → `{success|error}`
* `POST ?action=login` Body: `{username, password}` → `{success|error}`（以 Cookie/Session 維持登入）
* `POST ?action=forgot` Body: `{username}` → 產生臨時密碼（回傳於 JSON，便於測試）
* `GET  ?action=logout` → 清除 Session

### 股票（`api.php`）

* `GET    ?action=info&symbol=...` → 單檔基本資訊/最新價
* `GET    ?action=history&symbol=...` → 歷史價（自 DB）
* `GET    ?action=highest&symbol=...` → 歷史最高價
* `GET    ?action=by_industry&industry=...` → 依產業列出股票
* `GET/POST ?action=predict&symbol=...` → 呼叫 Python 回傳 `next_close_pred`
* `GET    ?action=update_today&symbol=...` → 以 Python 把該檔資料補到昨日/今日可用收盤

> 伺服器端會將查詢寫入 `user_search_log`（僅記 `user_id / stock_symbol / query_date`）。

---

## 🐍 Python 工具腳本

### `stock_scraper.py` — 批量日更

* 來源：台股清單（TWSE ISIN）+ 維基 S\&P500。
* 策略：先以 `end = 明天` 抓 1 日 K；不足門檻（預設 `60` 筆）時自動回溯 3 年→7 年。
* 寫入：`INSERT ... ON DUPLICATE KEY UPDATE`，避免重複。
* 快速使用：

  ```bash
  python stock_scraper.py --start 2022-01-01 --end 2030-01-01
  ```

### `backfill_one.py` — 單檔補資料

* 輸入代號會嘗試多種別名（如 `2330.TW`/`2330`/`2330.TWO`）直到滿足最小筆數才寫入。
* 自動查詢公司名稱與產業並一併存檔。
* 用法：

  ```bash
  python backfill_one.py 2330
  python backfill_one.py AAPL
  ```

### `stock_predictor.py` — 線性回歸預測

* 從 DB 讀出該檔歷史收盤，將日期轉 ordinal 後做線性回歸。
* 回傳 `next_close_pred`、`last_close`、`last_close_date`、`method`。
* 用法：

  ```bash
  python stock_predictor.py 2330
  ```

### `fetch_stock.py` — 區間抓資料/趨勢

* `yfinance` 下載指定區間，若筆數過少會自動向前回溯最多 7 年。
* 回傳日期/收盤列表與粗略「上漲/下跌」趨勢。
* 用法：

  ```bash
  python fetch_stock.py 2330 2024-01-01 2024-12-31
  ```

---

## 📅 每日自動排程（Windows 範例）

> 讓資料每天台北時間收盤後自動更新。

1. **建立批次檔** `update_stocks.bat`

   ```bat
   @echo off
   cd /d C:\xampp\htdocs\stock-management-system
   C:\Python39\python.exe stock_scraper.py --end 2099-01-01
   ```
2. **工作排程器** → 建立基本工作 → 觸發器：每天 **18:30**（台灣時間，台股收盤後）。
3. （美股）可另建一條，例如隔日早上 **07:30** 再跑一次。

---

## 🔐 安全與環境建議

* 將 `config.php` 移出可公開目錄或設定正確檔權限。
* 資料庫帳密請勿空白；建議建立有限權限帳號（僅存取 `stock_db`）。
* 若對外服務，請設定 HTTPS 與 CORS 白名單。

---

## 🧰 疑難排解

* **前端顯示「無法連線伺服器」**：確認 Apache/PHP 已啟動且 `AUTH_API`/`STOCK_API` 路徑正確。
* **Python 腳本連不到 DB**：檢查 `mysql-connector-python` 是否安裝、主機/帳密是否與 `config.php` 一致。
* **抓不到當日資料**：`yfinance` 的 `end` 不含該日，請確保腳本 `end = 明天`；若當日尚未收盤，會回到最後完成日。
* **S\&P500/TW 清單抓取失敗**：腳本已內建後備清單；可稍後重試或自行提供代碼清單。

---

## 📄 授權

MIT（可自訂）。

---

## 🙌 貢獻

PR/Issue 歡迎：

* 模型擴充（SMA/Ridge/Ensemble）
* 前端圖表化（K 線、移動平均）
* API 權限更細緻化（Token/JWT）
* Docker 化部署
