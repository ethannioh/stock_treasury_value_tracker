# Stock Treasury Value Tracker

這個專案會讀取交易與股利 CSV，抓取 Yahoo Finance 歷史價格，產生可部署的靜態 HTML / JSON 報表，也可以用 Streamlit 在本機檢視。

## 功能

- 讀取 `transactions.csv` 與 `dividends.csv`
- 支援舊版 buy-only CSV 與新版 buy/sell CSV
- 追蹤剩餘成本、已實現損益、未實現損益、股利收入與總報酬
- 產出 Plotly HTML 報表與 JSON 摘要
- 支援 iPhone / PWA 顯示模式

## 安裝

建議使用 Python 3.11：

```powershell
py -3.11 -m pip install -r requirements.txt
```

## 使用方式

### 1. 本機互動檢視

```powershell
py -3.11 -m streamlit run app.py
```

### 2. 產生靜態 HTML / JSON

```powershell
py -3.11 app.py --transactions data/transactions.csv --dividends data/dividends.csv --output output/report.html --json-output output/report.json
```

## 交易 CSV

### 新版格式

```csv
trade_date,ticker,side,price,quantity,fee,tax,account,currency,note
2024-01-15,2330.TW,buy,585,1000,0.001425,0,broker1,TWD,first buy
2025-03-18,2330.TW,sell,980,300,0.001425,0.003,broker1,TWD,trim position
2024-03-01,AAPL,buy,182.5,10,0,0,broker2,USD,long term
2025-02-14,AAPL,sell,210.4,4,0,0,broker2,USD,rebalance
```

欄位說明：

- `trade_date`: 交易日期
- `ticker`: 股票代號
- `side`: `buy` 或 `sell`
- `price`: 成交單價
- `quantity`: 成交股數，永遠填正數
- `fee`: 手續費率，`0.001425` 代表 `0.1425%`
- `tax`: 交易稅率，`0.003` 代表 `0.3%`
- `account`: 帳戶或券商代號
- `currency`: 幣別，留空時會依 ticker 推測
- `note`: 備註

台股若留白，程式會自動套用這些預設值：

- 買進：`fee=0.001425`、`tax=0`
- 賣出：`fee=0.001425`、`tax=0.003`
- 美股：`fee=0`、`tax=0`

### 舊版格式

舊版 buy-only CSV 仍可使用，程式會自動轉成新版欄位：

```csv
ticker,buy_date,buy_price,quantity,fee,tax,account,note
2330.TW,2024-01-15,585,1000,0.001425,0,broker1,first buy
AAPL,2024-03-01,182.5,10,0,0,broker2,long term
```

## 股利 CSV

```csv
ticker,dividend_date,amount,currency,note
2330.TW,2024-07-10,3000,TWD,cash dividend
AAPL,2024-08-15,9.2,USD,quarterly dividend
```

## 計算邏輯

- 買進會用 `交易金額 * (1 + fee + tax)` 增加剩餘成本與累積投入成本
- 賣出會用 `交易金額 * (1 - fee - tax)` 計算淨收入，並使用移動平均成本法計算已實現損益
- 台股未賣出的部位，在圖表與摘要中的市值/損益會先扣掉預估賣出成本 `0.1425% + 0.3%`
- 美股不套用預估賣出成本
- 持股表只顯示目前仍有持股的 ticker
- 組合摘要與歷史曲線會保留已賣出部位的已實現損益與賣出現金流

## 其他檔案

- `data/transactions_v2_example.csv`: 新版 buy/sell 範例
- `output/report.html`: 靜態報表輸出
- `output/report.json`: JSON 摘要輸出

## Error Log

- CLI 或封裝執行失敗時，會寫出 `stock_treasury_value_tracker_error.log`
- log 會包含啟動參數、錯誤訊息與完整 traceback
