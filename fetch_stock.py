# fetch_stock.py: 取得股票歷史價格並預測趨勢
import sys, json
from datetime import datetime, timedelta
try:
    import yfinance as yf
except ImportError:
    # 若未安裝套件則提示
    print(json.dumps({"error": "請先安裝yfinance套件"}))
    sys.exit(1)

if len(sys.argv) < 4:
    # 參數不足
    print(json.dumps({"error": "參數不足"}))
    sys.exit(1)

stock_code = sys.argv[1]      # 股票代碼 (如 "2330" or "AAPL")
start_date = sys.argv[2]      # 起始日期 (格式 YYYY-MM-DD)
end_date   = sys.argv[3]      # 結束日期 (格式 YYYY-MM-DD)

# 判斷市場並組合Yahoo股票代號
ticker = stock_code
if stock_code.isdigit():
    # 台股代碼（數字） - 預設為上市.TW，如需可擴展判斷上櫃
    ticker = stock_code + ".TW"
# （若有上櫃判斷需求，可擴充，例如檢查代碼清單或 twstock 函式）

# 下載指定區間的歷史資料
try:
    data = yf.download(ticker, start=start_date, end=end_date, progress=False)
except Exception as e:
    print(json.dumps({"error": f"取得資料時發生錯誤: {str(e)}"}))
    sys.exit(1)

# 若資料筆數很少且允許回溯，則嘗試往前最多推7年
if data.shape[0] < 5:  # 少於5筆可能是不足一週交易日
    try:
        start_obj = datetime.strptime(start_date, "%Y-%m-%d")
        # 最早回溯日期 (7年前)
        earliest = start_obj - timedelta(days=365*7)
        data = yf.download(ticker, start=earliest.strftime("%Y-%m-%d"), end=end_date, progress=False)
    except Exception as e:
        pass

if data is None or data.shape[0] == 0:
    # 找不到任何資料
    output = {"error": "無法取得該股票的歷史資料"}
else:
    # 將日期轉為字串，收盤價轉為列表
    dates = [d.strftime("%Y-%m-%d") for d in data.index]
    closes = [float(c) if not (c is None) else None for c in data['Close']]
    # 簡單趨勢預測：比較最後一天與第一天的收盤價
    trend = "上漲" if closes[-1] > closes[0] else "下跌"
    output = {
        "stock": stock_code,
        "start": start_date,
        "end": end_date,
        "dates": dates,
        "closes": closes,
        "prediction": trend
    }
# 輸出JSON結果
print(json.dumps(output, ensure_ascii=False))
