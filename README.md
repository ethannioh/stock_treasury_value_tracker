# 股票庫存績效追蹤工具

這是一個可在本機執行的 Python 專案，用來追蹤台股與美股的股票庫存績效。

## 功能

- 從 `transactions.csv` 載入每筆買進交易
- 從 `dividends.csv` 載入每筆配息
- 使用 Yahoo Finance 自動抓取最新價格與近五年歷史股價
- 以快取減少重複抓取
- 計算單一股票與整體投資組合績效
- 依買進日期逐日展開歷史持股，產生投資組合曲線
- 產出離線可開啟的 Plotly HTML 報表
- 提供中文化的 Streamlit 本機互動介面

## 專案結構

```text
stock_treasury_value_tracker/
├─ app.py
├─ requirements.txt
├─ README.md
├─ data/
│  ├─ transactions.csv
│  └─ dividends.csv
├─ cache/
├─ output/
├─ src/
│  ├─ __init__.py
│  ├─ data_loader.py
│  ├─ models.py
│  ├─ performance.py
│  ├─ price_fetcher.py
│  ├─ report_generator.py
│  └─ utils.py
└─ templates/
   └─ report.html.j2
```

## 安裝

建議使用 Python 3.11。

```powershell
py -3.11 -m pip install -r requirements.txt
```

## 使用方式

### 1. 啟動中文化本機介面

```powershell
py -3.11 -m streamlit run app.py
```

### 2. 直接輸出 HTML 報表

```powershell
py -3.11 app.py --transactions data/transactions.csv --dividends data/dividends.csv --output output/report.html
```

## 資料格式

### transactions.csv

```csv
ticker,buy_date,buy_price,quantity,fee,tax,account,note
2330.TW,2024-01-15,585,1000,20,0,broker1,first buy
AAPL,2024-03-01,182.5,10,1,0,broker2,long term
```

### dividends.csv

```csv
ticker,dividend_date,amount,currency,note
2330.TW,2024-07-10,3000,TWD,cash dividend
AAPL,2024-08-15,9.2,USD,quarterly dividend
```

## 設計取捨

- 目前以「買進」交易為主，尚未實作賣出，但資料模型已預留擴充空間。
- 若投資組合同時有 `TWD` 與 `USD`，報表會分幣別顯示，不會做錯誤的硬轉換加總。
- 歷史績效依每筆買進日期展開持股，交易日以抓到的歷史股價日期為準。
- 若 Yahoo Finance 某檔資料抓不到，程式會在畫面或錯誤訊息中指出，不會讓整個專案默默算錯。

## 注意事項

- 第一次執行若 `data/transactions.csv` 或 `data/dividends.csv` 不存在，程式會自動建立 sample data。
- `cache/` 與 `output/` 會自動建立。
- HTML 報表可直接用瀏覽器離線開啟。
## Error Log

- If the CLI or packaged exe fails, the app writes `stock_treasury_value_tracker_error.log`
- The log is created beside `app.py` or beside the exe file
- The log includes arguments, the error message, and the full traceback
