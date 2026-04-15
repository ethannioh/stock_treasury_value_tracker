from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import yfinance as yf

from .models import PriceSnapshot
from .utils import infer_currency_from_ticker, latest_of_series, normalize_ticker


class PriceFetcher:
    """Fetch Yahoo Finance prices with a simple local-file cache."""

    def __init__(self, cache_dir: Path, cache_hours: int = 12) -> None:
        self.cache_dir = cache_dir
        self.cache_hours = cache_hours
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _history_cache_path(self, ticker: str) -> Path:
        return self.cache_dir / f"{ticker.replace('.', '_')}_history.csv"

    def _meta_cache_path(self, ticker: str) -> Path:
        return self.cache_dir / f"{ticker.replace('.', '_')}_meta.json"

    def _cache_is_fresh(self, path: Path) -> bool:
        if not path.exists():
            return False
        modified = pd.Timestamp(path.stat().st_mtime, unit="s")
        return (pd.Timestamp.now() - modified) <= pd.Timedelta(hours=self.cache_hours)

    def get_price_snapshot(self, ticker: str) -> PriceSnapshot:
        ticker = normalize_ticker(ticker)
        meta_path = self._meta_cache_path(ticker)

        if self._cache_is_fresh(meta_path):
            cached = json.loads(meta_path.read_text(encoding="utf-8"))
            return PriceSnapshot(**cached)

        history = self.get_price_history(ticker)
        latest_price = latest_of_series(history["Close"])

        try:
            info = yf.Ticker(ticker).info or {}
        except Exception:
            info = {}

        snapshot = PriceSnapshot(
            ticker=ticker,
            last_price=latest_price,
            currency=str(info.get("currency") or infer_currency_from_ticker(ticker)).upper(),
            name=str(info.get("shortName") or info.get("longName") or ticker),
        )
        meta_path.write_text(json.dumps(asdict(snapshot), ensure_ascii=False, indent=2), encoding="utf-8")
        return snapshot

    def get_price_history(self, ticker: str, period: str = "5y") -> pd.DataFrame:
        ticker = normalize_ticker(ticker)
        cache_path = self._history_cache_path(ticker)

        if self._cache_is_fresh(cache_path):
            cached = pd.read_csv(cache_path, parse_dates=["Date"])
            cached["Date"] = pd.to_datetime(cached["Date"]).dt.tz_localize(None)
            return cached.set_index("Date")

        try:
            history = yf.download(
                tickers=ticker,
                period=period,
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
            )
        except Exception as exc:
            raise RuntimeError(f"抓取 {ticker} 股價失敗，請檢查網路或稍後再試：{exc}") from exc

        if history.empty:
            raise ValueError(f"Yahoo Finance 沒有回傳 {ticker} 的有效歷史資料")

        history = history.copy()
        history.index = pd.to_datetime(history.index).tz_localize(None)
        history = history.sort_index()

        if isinstance(history.columns, pd.MultiIndex):
            history.columns = history.columns.get_level_values(0)

        columns = [col for col in ["Open", "High", "Low", "Close", "Volume"] if col in history.columns]
        history = history[columns]
        history.reset_index().rename(columns={"index": "Date", "Date": "Date"}).to_csv(cache_path, index=False)
        return history

    def get_security_currency(self, ticker: str) -> str:
        return self.get_price_snapshot(ticker).currency

    def get_security_name(self, ticker: str) -> str:
        return self.get_price_snapshot(ticker).name
