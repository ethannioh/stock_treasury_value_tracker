from __future__ import annotations

from pathlib import Path

import pandas as pd

from .utils import (
    infer_currency_from_ticker,
    normalize_ticker,
    parse_date_column,
    write_text,
)


LEGACY_TRANSACTION_COLUMNS = [
    "ticker",
    "buy_date",
    "buy_price",
    "quantity",
    "fee",
    "tax",
    "account",
    "note",
]

TRANSACTION_COLUMNS = [
    "trade_date",
    "ticker",
    "side",
    "price",
    "quantity",
    "fee",
    "tax",
    "account",
    "currency",
    "note",
]

DIVIDEND_COLUMNS = [
    "ticker",
    "dividend_date",
    "amount",
    "currency",
    "note",
]

RATE_CONFIG_COLUMNS = [
    "currency",
    "side",
    "fee",
    "tax",
]


SAMPLE_TRANSACTIONS = """trade_date,ticker,side,price,quantity,fee,tax,account,currency,note
2024-01-15,2330.TW,buy,585,1000,0.001425,0,broker1,TWD,first buy
2024-09-20,2330.TW,buy,910,500,0.001425,0,broker1,TWD,add on weakness
2025-03-18,2330.TW,sell,980,300,0.001425,0.003,broker1,TWD,trim position
2024-02-05,0050.TW,buy,145.2,2000,0.001425,0,broker1,TWD,core ETF
2024-03-01,AAPL,buy,182.5,10,0,0,broker2,USD,long term
2025-02-14,AAPL,sell,210.4,4,0,0,broker2,USD,rebalance
2024-04-18,MSFT,buy,412.3,8,0,0,broker2,USD,AI theme
2024-06-10,NVDA,buy,121.4,15,0,0,broker2,USD,growth
"""

SAMPLE_DIVIDENDS = """ticker,dividend_date,amount,currency,note
2330.TW,2024-07-10,3000,TWD,cash dividend
0050.TW,2024-07-19,4200,TWD,ETF dividend
AAPL,2024-08-15,9.2,USD,quarterly dividend
MSFT,2024-09-12,6.0,USD,quarterly dividend
"""

SAMPLE_RATE_CONFIG = """currency,side,fee,tax
TWD,buy,0.001425,0
TWD,sell,0.001425,0.003
USD,buy,0,0
USD,sell,0,0
"""


def ensure_sample_data(transactions_path: Path, dividends_path: Path, rate_config_path: Path) -> None:
    if not transactions_path.exists():
        write_text(transactions_path, SAMPLE_TRANSACTIONS)
    if not dividends_path.exists():
        write_text(dividends_path, SAMPLE_DIVIDENDS)
    if not rate_config_path.exists():
        write_text(rate_config_path, SAMPLE_RATE_CONFIG)


def validate_columns(df: pd.DataFrame, required_columns: list[str], filename: str) -> None:
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(f"{filename} is missing required columns: {missing}")


def _is_legacy_transaction_format(df: pd.DataFrame) -> bool:
    return all(column in df.columns for column in LEGACY_TRANSACTION_COLUMNS)


def _is_v2_transaction_format(df: pd.DataFrame) -> bool:
    return all(column in df.columns for column in ["trade_date", "ticker", "side", "price", "quantity"])


def _normalize_transaction_frame(df: pd.DataFrame, filename: str) -> pd.DataFrame:
    if _is_legacy_transaction_format(df):
        normalized = df.rename(
            columns={
                "buy_date": "trade_date",
                "buy_price": "price",
            }
        ).copy()
        normalized["side"] = "buy"
        normalized["currency"] = normalized["ticker"].astype(str).map(infer_currency_from_ticker)
    elif _is_v2_transaction_format(df):
        normalized = df.copy()
        for column, default_value in {"fee": pd.NA, "tax": pd.NA, "account": "", "currency": "", "note": ""}.items():
            if column not in normalized.columns:
                normalized[column] = default_value
    else:
        raise ValueError(
            f"{filename} must use either legacy columns {LEGACY_TRANSACTION_COLUMNS} "
            f"or v2 columns {TRANSACTION_COLUMNS}"
        )

    validate_columns(normalized, TRANSACTION_COLUMNS, filename)
    return normalized[TRANSACTION_COLUMNS].copy()


def load_rate_config(path: Path) -> dict[tuple[str, str], dict[str, float]]:
    if not path.exists():
        raise FileNotFoundError(f"rate config file not found: {path}")

    df = pd.read_csv(path)
    df = df.dropna(how="all")
    validate_columns(df, RATE_CONFIG_COLUMNS, path.name)
    df = df.copy()
    df["currency"] = df["currency"].fillna("").astype(str).str.strip().str.upper()
    df["side"] = df["side"].fillna("").astype(str).str.strip().str.lower()

    invalid_side_mask = ~df["side"].isin(["buy", "sell"])
    if invalid_side_mask.any():
        bad_rows = df.loc[invalid_side_mask, ["currency", "side"]].to_dict(orient="records")
        raise ValueError(f"rate config side must be buy or sell: {bad_rows}")

    for column in ["fee", "tax"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
        if df[column].isna().any():
            bad_rows = df.loc[df[column].isna(), ["currency", "side", column]].to_dict(orient="records")
            raise ValueError(f"rate config {column} contains invalid numbers: {bad_rows}")
        if (df[column] < 0).any() or (df[column] >= 1).any():
            bad_rows = df.loc[(df[column] < 0) | (df[column] >= 1), ["currency", "side", column]].to_dict(orient="records")
            raise ValueError(f"rate config {column} must be between 0 and 1: {bad_rows}")

    duplicated = df.duplicated(subset=["currency", "side"], keep=False)
    if duplicated.any():
        bad_rows = df.loc[duplicated, ["currency", "side"]].to_dict(orient="records")
        raise ValueError(f"rate config contains duplicate currency/side rows: {bad_rows}")

    return {
        (row.currency, row.side): {"fee": float(row.fee), "tax": float(row.tax)}
        for row in df.itertuples(index=False)
    }


def load_transactions(path: Path, rate_config: dict[tuple[str, str], dict[str, float]] | None = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"transactions file not found: {path}")

    df = pd.read_csv(path)
    df = df.dropna(how="all")
    df = _normalize_transaction_frame(df, path.name)

    df["ticker"] = df["ticker"].astype(str).map(normalize_ticker)
    df["trade_date"] = parse_date_column(df["trade_date"], "trade_date")
    df["side"] = df["side"].fillna("").astype(str).str.strip().str.lower()

    invalid_side_mask = ~df["side"].isin(["buy", "sell"])
    if invalid_side_mask.any():
        bad_values = df.loc[invalid_side_mask, "side"].tolist()
        raise ValueError(f"side must be buy or sell: {bad_values}")

    for column in ["price", "quantity", "fee", "tax"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    for column in ["price", "quantity"]:
        if df[column].isna().any():
            bad_rows = df.loc[df[column].isna(), ["ticker", "trade_date", column]].to_dict(orient="records")
            raise ValueError(f"{column} contains invalid numbers: {bad_rows}")

    if (df["quantity"] <= 0).any():
        bad_rows = df.loc[df["quantity"] <= 0, ["ticker", "trade_date", "quantity"]].to_dict(orient="records")
        raise ValueError(f"quantity must be greater than 0: {bad_rows}")

    df["account"] = df["account"].fillna("").astype(str)
    df["currency"] = df["currency"].fillna("").astype(str).str.strip().str.upper()
    df["currency"] = df.apply(
        lambda row: row["currency"] or infer_currency_from_ticker(row["ticker"]),
        axis=1,
    )
    df["fee"] = df.apply(
        lambda row: _default_rate_value(rate_config, row["currency"], row["side"], "fee") if pd.isna(row["fee"]) else float(row["fee"]),
        axis=1,
    )
    df["tax"] = df.apply(
        lambda row: _default_rate_value(rate_config, row["currency"], row["side"], "tax") if pd.isna(row["tax"]) else float(row["tax"]),
        axis=1,
    )

    for column in ["price", "fee", "tax"]:
        if (df[column] < 0).any():
            bad_rows = df.loc[df[column] < 0, ["ticker", "trade_date", column]].to_dict(orient="records")
            raise ValueError(f"{column} must be non-negative: {bad_rows}")

    for column in ["fee", "tax"]:
        if (df[column] >= 1).any():
            bad_rows = df.loc[df[column] >= 1, ["ticker", "trade_date", column]].to_dict(orient="records")
            raise ValueError(f"{column} must be a rate below 1, for example 0.001425 = 0.1425%: {bad_rows}")

    df["note"] = df["note"].fillna("").astype(str)
    df["gross_amount"] = df["price"] * df["quantity"]
    df["fee_amount"] = df["gross_amount"] * df["fee"]
    df["tax_amount"] = df["gross_amount"] * df["tax"]
    df["total_charge_amount"] = df["fee_amount"] + df["tax_amount"]
    df["gross_buy_outlay"] = 0.0
    df.loc[df["side"] == "buy", "gross_buy_outlay"] = (
        df.loc[df["side"] == "buy", "gross_amount"]
        + df.loc[df["side"] == "buy", "total_charge_amount"]
    )
    df["net_sell_proceeds"] = 0.0
    df.loc[df["side"] == "sell", "net_sell_proceeds"] = (
        df.loc[df["side"] == "sell", "gross_amount"]
        - df.loc[df["side"] == "sell", "total_charge_amount"]
    )
    df["sort_order"] = range(len(df))
    return df.sort_values(["trade_date", "ticker", "sort_order"], ignore_index=True)


def _default_rate_value(
    rate_config: dict[tuple[str, str], dict[str, float]] | None,
    currency: str,
    side: str,
    field: str,
) -> float:
    if rate_config is None:
        return 0.0
    return float(rate_config.get((str(currency).upper(), str(side).lower()), {}).get(field, 0.0))


def load_dividends(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"dividends file not found: {path}")

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
