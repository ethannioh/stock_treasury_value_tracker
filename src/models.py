from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd


@dataclass(slots=True)
class Transaction:
    ticker: str
    trade_date: pd.Timestamp
    side: str
    price: float
    quantity: float
    fee: float = 0.0
    tax: float = 0.0
    account: str = ""
    currency: str = ""
    note: str = ""


@dataclass(slots=True)
class Dividend:
    ticker: str
    dividend_date: pd.Timestamp
    amount: float
    currency: str
    note: str = ""


@dataclass(slots=True)
class PriceSnapshot:
    ticker: str
    last_price: float
    currency: str
    name: str


@dataclass(slots=True)
class CachedPriceData:
    ticker: str
    path: Path
    fetched_at: pd.Timestamp
    expires_at: pd.Timestamp
    latest_price: Optional[float] = None
