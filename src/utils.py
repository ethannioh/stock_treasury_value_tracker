from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

DEFAULT_TW_BUY_FEE_RATE = 0.001425
DEFAULT_TW_SELL_FEE_RATE = 0.001425
DEFAULT_TW_SELL_TAX_RATE = 0.003


def ensure_directories(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def infer_currency_from_ticker(ticker: str) -> str:
    ticker_upper = ticker.upper()
    if ticker_upper.endswith(".TW") or ticker_upper.endswith(".TWO"):
        return "TWD"
    return "USD"


def parse_date_column(series: pd.Series, column_name: str) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    if parsed.isna().any():
        bad_rows = series[parsed.isna()].tolist()
        raise ValueError(f"{column_name} 含有無效日期：{bad_rows}")
    return parsed.dt.tz_localize(None)


def normalize_ticker(ticker: str) -> str:
    if pd.isna(ticker):
        return ""
    return str(ticker).strip().upper()


def display_ticker(ticker: str) -> str:
    normalized = normalize_ticker(ticker)
    for suffix in (".TW", ".TWO"):
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)]
    return normalized


def display_security_label(ticker: str, name: str | None = None) -> str:
    code = display_ticker(ticker)
    title = str(name or "").strip()
    return f"{code} {title}" if title else code


def first_index_on_or_after(index: pd.DatetimeIndex, target: pd.Timestamp) -> pd.Timestamp | None:
    pos = index.searchsorted(target)
    if pos >= len(index):
        return None
    return index[pos]


def latest_of_series(series: pd.Series) -> float:
    cleaned = series.dropna()
    if cleaned.empty:
        raise ValueError("查無有效價格資料")
    return float(cleaned.iloc[-1])


def unique_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def format_compact_number(value: float | int | None, decimals: int = 2) -> str:
    if value is None or pd.isna(value):
        return "-"

    number = float(value)
    sign = "-" if number < 0 else ""
    magnitude = abs(number)

    if magnitude >= 1_000_000_000:
        scaled, suffix = magnitude / 1_000_000_000, "B"
    elif magnitude >= 1_000_000:
        scaled, suffix = magnitude / 1_000_000, "M"
    elif magnitude >= 1_000:
        scaled, suffix = magnitude / 1_000, "k"
    else:
        scaled, suffix = magnitude, ""

    return f"{sign}{scaled:.{decimals}f}{suffix}"


def format_percent(value: float | int | None, decimals: int = 2) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value) * 100:.{decimals}f}%"


def pnl_css(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return ""
    if float(value) > 0:
        return "color: #687f5d; font-weight: 700;"
    if float(value) < 0:
        return "color: #bd655c; font-weight: 700;"
    return "color: #7f756a; font-weight: 600;"


def is_taiwan_market(currency: str | None) -> bool:
    return (currency or "").upper() == "TWD"


def default_fee_rate(currency: str | None, side: str | None) -> float:
    if is_taiwan_market(currency):
        if str(side or "").lower() == "buy":
            return DEFAULT_TW_BUY_FEE_RATE
        if str(side or "").lower() == "sell":
            return DEFAULT_TW_SELL_FEE_RATE
    return 0.0


def default_tax_rate(currency: str | None, side: str | None) -> float:
    if is_taiwan_market(currency) and str(side or "").lower() == "sell":
        return DEFAULT_TW_SELL_TAX_RATE
    return 0.0


def expected_sell_cost_rate(currency: str | None) -> float:
    if is_taiwan_market(currency):
        return DEFAULT_TW_SELL_FEE_RATE + DEFAULT_TW_SELL_TAX_RATE
    return 0.0


def return_tone(value: float | int | None, currency: str | None) -> str:
    if value is None or pd.isna(value):
        return "orange"

    number = float(value)
    if is_taiwan_market(currency):
        return "red" if number >= 0 else "green"
    return "green" if number >= 0 else "red"


def return_css(value: float | int | None, currency: str | None) -> str:
    tone = return_tone(value, currency)
    color = {"green": "#687f5d", "red": "#bd655c", "orange": "#b99255"}[tone]
    return f"color: {color}; font-weight: 700;"
