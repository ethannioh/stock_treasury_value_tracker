from __future__ import annotations

from pathlib import Path

import pandas as pd

from .utils import normalize_ticker, parse_date_column, write_text


TRANSACTION_COLUMNS = [
    "ticker",
    "buy_date",
    "buy_price",
    "quantity",
    "fee",
    "tax",
    "account",
    "note",
]

DIVIDEND_COLUMNS = [
    "ticker",
    "dividend_date",
    "amount",
    "currency",
    "note",
]


SAMPLE_TRANSACTIONS = """ticker,buy_date,buy_price,quantity,fee,tax,account,note
2330.TW,2024-01-15,585,1000,20,0,broker1,first buy
2330.TW,2024-09-20,910,500,20,0,broker1,add on weakness
0050.TW,2024-02-05,145.2,2000,20,0,broker1,core ETF
AAPL,2024-03-01,182.5,10,1,0,broker2,long term
MSFT,2024-04-18,412.3,8,1,0,broker2,AI theme
NVDA,2024-06-10,121.4,15,1,0,broker2,growth
"""

SAMPLE_DIVIDENDS = """ticker,dividend_date,amount,currency,note
2330.TW,2024-07-10,3000,TWD,cash dividend
0050.TW,2024-07-19,4200,TWD,ETF dividend
AAPL,2024-08-15,9.2,USD,quarterly dividend
MSFT,2024-09-12,6.0,USD,quarterly dividend
"""


def ensure_sample_data(transactions_path: Path, dividends_path: Path) -> None:
    if not transactions_path.exists():
        write_text(transactions_path, SAMPLE_TRANSACTIONS)
    if not dividends_path.exists():
        write_text(dividends_path, SAMPLE_DIVIDENDS)


def validate_columns(df: pd.DataFrame, required_columns: list[str], filename: str) -> None:
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(f"{filename} 缺少必要欄位：{missing}")


def load_transactions(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"找不到交易資料：{path}")

    df = pd.read_csv(path)
    df = df.dropna(how="all")
    validate_columns(df, TRANSACTION_COLUMNS, path.name)
    df = df.copy()
    df["ticker"] = df["ticker"].astype(str).map(normalize_ticker)
    df["buy_date"] = parse_date_column(df["buy_date"], "buy_date")

    for col in ["buy_price", "quantity", "fee", "tax"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    df["account"] = df["account"].fillna("").astype(str)
    df["note"] = df["note"].fillna("").astype(str)
    df["transaction_cost"] = df["buy_price"] * df["quantity"] + df["fee"] + df["tax"]
    return df.sort_values(["buy_date", "ticker"], ignore_index=True)


def load_dividends(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"找不到配息資料：{path}")

    df = pd.read_csv(path)
    df = df.dropna(how="all")
    validate_columns(df, DIVIDEND_COLUMNS, path.name)
    df = df.copy()
    df["ticker"] = df["ticker"].astype(str).map(normalize_ticker)
    df["dividend_date"] = parse_date_column(df["dividend_date"], "dividend_date")
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    df["currency"] = df["currency"].fillna("").astype(str).str.upper()
    df["note"] = df["note"].fillna("").astype(str)
    return df.sort_values(["dividend_date", "ticker"], ignore_index=True)
