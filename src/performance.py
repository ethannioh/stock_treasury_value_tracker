from __future__ import annotations

from collections import defaultdict

import pandas as pd
import plotly.graph_objects as go

from .price_fetcher import PriceFetcher
from .utils import (
    first_index_on_or_after,
    format_compact_number,
    format_percent,
    infer_currency_from_ticker,
    unique_preserve_order,
)


BG = "#F0F0F0"
PANEL = "#FAFAFA"
GRID = "rgba(82, 88, 98, 0.14)"
GRID_STRONG = "rgba(82, 88, 98, 0.24)"
TEXT = "#475569"
TITLE = "#111827"
MUTED = "#64748B"
BLUE = "#1F7BD8"
GREEN = "#0F9F72"
RED = "#D83F56"
ORANGE = "#F97316"
TEAL = "#2563EB"
REFERENCE_GRAY = "#8D9995"
DEFAULT_REFERENCE_TICKER_TWD = "0050.TW"
PERIOD_OPTIONS = [
    ("1w", "1W"),
    ("1m", "1M"),
    ("ytd", "YTD"),
    ("1y", "1Y"),
    ("3y", "3Y"),
    ("5y", "5Y"),
    ("all", "全部"),
]


def calculate_stock_summary(
    transactions: pd.DataFrame,
    dividends: pd.DataFrame,
    fetcher: PriceFetcher,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    grouped_transactions = transactions.groupby("ticker", sort=False)
    dividend_totals = dividends.groupby("ticker")["amount"].sum().to_dict()

    for ticker, tx_df in grouped_transactions:
        total_cost = float(tx_df["transaction_cost"].sum())
        shares = float(tx_df["quantity"].sum())
        if shares <= 0:
            continue

        snapshot = fetcher.get_price_snapshot(ticker)
        market_value = shares * snapshot.last_price
        unrealized_pnl = market_value - total_cost
        dividends_income = float(dividend_totals.get(ticker, 0.0))
        total_pnl = unrealized_pnl + dividends_income

        rows.append(
            {
                "ticker": ticker,
                "name": snapshot.name,
                "currency": snapshot.currency or infer_currency_from_ticker(ticker),
                "shares": shares,
                "avg_cost": total_cost / shares if shares else 0.0,
                "last_price": snapshot.last_price,
                "total_cost": total_cost,
                "market_value": market_value,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_return_pct": (unrealized_pnl / total_cost) if total_cost else 0.0,
                "dividends": dividends_income,
                "total_pnl": total_pnl,
                "total_return_pct": (total_pnl / total_cost) if total_cost else 0.0,
            }
        )

    summary = pd.DataFrame(rows)
    if summary.empty:
        return summary
    return summary.sort_values(["currency", "ticker"], ignore_index=True)


def calculate_portfolio_snapshot(stock_summary: pd.DataFrame) -> dict[str, dict[str, float]]:
    snapshot: dict[str, dict[str, float]] = {}
    if stock_summary.empty:
        return snapshot

    for currency, group in stock_summary.groupby("currency"):
        total_cost = float(group["total_cost"].sum())
        total_market_value = float(group["market_value"].sum())
        total_dividends = float(group["dividends"].sum())
        total_pnl = float(group["total_pnl"].sum())
        snapshot[currency] = {
            "total_cost": total_cost,
            "total_market_value": total_market_value,
            "total_dividends": total_dividends,
            "total_pnl": total_pnl,
            "total_return_pct": (total_pnl / total_cost) if total_cost else 0.0,
        }
    return snapshot


def calculate_timeline(
    transactions: pd.DataFrame,
    dividends: pd.DataFrame,
    fetcher: PriceFetcher,
) -> dict[str, pd.DataFrame]:
    if transactions.empty:
        return {}

    tickers = unique_preserve_order(transactions["ticker"].tolist())
    histories: dict[str, pd.DataFrame] = {}
    ticker_currency: dict[str, str] = {}

    for ticker in tickers:
        histories[ticker] = fetcher.get_price_history(ticker)
        ticker_currency[ticker] = fetcher.get_security_currency(ticker)

    all_dates = pd.DatetimeIndex(sorted(set().union(*[history.index for history in histories.values()])))
    timelines: dict[str, dict[str, pd.Series]] = defaultdict(dict)

    for ticker in tickers:
        history = histories[ticker]
        currency = ticker_currency[ticker]
        close_series = history["Close"].reindex(all_dates).ffill()

        shares_delta = pd.Series(0.0, index=all_dates)
        cost_delta = pd.Series(0.0, index=all_dates)
        dividend_delta = pd.Series(0.0, index=all_dates)

        for _, row in transactions[transactions["ticker"] == ticker].iterrows():
            effective_date = first_index_on_or_after(all_dates, row["buy_date"])
            if effective_date is not None:
                shares_delta.loc[effective_date] += float(row["quantity"])
                cost_delta.loc[effective_date] += float(row["transaction_cost"])

        for _, row in dividends[dividends["ticker"] == ticker].iterrows():
            effective_date = first_index_on_or_after(all_dates, row["dividend_date"])
            if effective_date is not None:
                dividend_delta.loc[effective_date] += float(row["amount"])

        shares_held = shares_delta.cumsum()
        cost_basis = cost_delta.cumsum()
        cumulative_dividends = dividend_delta.cumsum()
        market_value = close_series * shares_held

        bucket = timelines[currency]
        bucket["market_value"] = bucket.get("market_value", pd.Series(0.0, index=all_dates)).add(
            market_value, fill_value=0.0
        )
        bucket["cost_basis"] = bucket.get("cost_basis", pd.Series(0.0, index=all_dates)).add(
            cost_basis, fill_value=0.0
        )
        bucket["dividends"] = bucket.get("dividends", pd.Series(0.0, index=all_dates)).add(
            cumulative_dividends, fill_value=0.0
        )

    result: dict[str, pd.DataFrame] = {}
    for currency, series_map in timelines.items():
        df = pd.DataFrame(series_map).sort_index()
        df["total_pnl"] = df["market_value"] - df["cost_basis"] + df["dividends"]
        df["return_pct"] = df["total_pnl"].divide(df["cost_basis"].where(df["cost_basis"] != 0))
        result[currency] = df.fillna(0.0)
    return result


def _fill_gradient(start: str, end: str) -> dict[str, object]:
    return {"type": "vertical", "colorscale": [(0.0, start), (1.0, end)]}


def _formatted_hover(values: pd.Series, is_percent: bool = False) -> list[str]:
    if is_percent:
        return [format_percent(value) for value in values]
    return [format_compact_number(value) for value in values]


def _formatted_pnl_hover(values: pd.Series) -> list[str]:
    formatted_values: list[str] = []
    for value in values:
        if pd.isna(value):
            formatted_values.append("-")
            continue
        number = float(value)
        prefix = "+" if number > 0 else ""
        formatted_values.append(f"{prefix}{format_compact_number(number)}")
    return formatted_values


def _apply_common_layout(fig: go.Figure, title: str, yaxis_title: str) -> None:
    fig.update_layout(
        title=title,
        xaxis_title="日期",
        yaxis_title=yaxis_title,
        hovermode="x unified",
        legend_title="曲線",
        paper_bgcolor=BG,
        plot_bgcolor=PANEL,
        font=dict(color=TEXT, family="Consolas, Microsoft JhengHei, Segoe UI, sans-serif"),
        margin=dict(l=44, r=24, t=108, b=44),
        title_font=dict(size=20, color=TITLE),
        legend=dict(
            bgcolor="rgba(255, 255, 255, 0.82)",
            bordercolor=GRID,
            borderwidth=1,
            font=dict(color=MUTED),
        ),
        hoverlabel=dict(
            bgcolor="rgba(255, 255, 255, 0.96)",
            bordercolor=GRID_STRONG,
            font=dict(color=TITLE),
        ),
    )
    fig.update_xaxes(
        rangeselector=dict(
            buttons=[
                dict(count=7, label="1w", step="day", stepmode="backward"),
                dict(count=1, label="1m", step="month", stepmode="backward"),
                dict(count=1, label="YTD", step="year", stepmode="todate"),
                dict(count=1, label="1y", step="year", stepmode="backward"),
                dict(count=3, label="3y", step="year", stepmode="backward"),
                dict(count=5, label="5y", step="year", stepmode="backward"),
                dict(step="all", label="全部"),
            ],
            bgcolor="rgba(255, 255, 255, 0.92)",
            activecolor="rgba(37, 99, 235, 0.14)",
            bordercolor=GRID,
            font=dict(color=MUTED),
        ),
        rangeslider=dict(visible=False),
        gridcolor=GRID,
        zerolinecolor=GRID,
        showline=True,
        linecolor=GRID,
        tickfont=dict(color=MUTED),
    )
    fig.update_yaxes(
        gridcolor=GRID,
        zerolinecolor=GRID_STRONG,
        showline=True,
        linecolor=GRID,
        tickfont=dict(color=MUTED),
    )


def _slice_period(df: pd.DataFrame, period_key: str) -> pd.DataFrame:
    if df.empty or period_key == "all":
        return df.copy()

    last_date = df.index.max()
    if period_key == "1w":
        start_date = last_date - pd.Timedelta(days=7)
    elif period_key == "1m":
        start_date = last_date - pd.DateOffset(months=1)
    elif period_key == "ytd":
        start_date = pd.Timestamp(year=last_date.year, month=1, day=1)
    elif period_key == "1y":
        start_date = last_date - pd.DateOffset(years=1)
    elif period_key == "3y":
        start_date = last_date - pd.DateOffset(years=3)
    elif period_key == "5y":
        start_date = last_date - pd.DateOffset(years=5)
    else:
        start_date = df.index.min()

    subset = df.loc[df.index >= start_date].copy()
    return subset if not subset.empty else df.tail(1).copy()


def _build_period_return_series(df: pd.DataFrame) -> pd.Series:
    period_return, _ = _build_period_return_metrics(df)
    return period_return


def _build_period_return_metrics(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    equity = df["market_value"] + df["dividends"]
    base_equity = float(equity.iloc[0]) if not equity.empty else 0.0
    base_cost = float(df["cost_basis"].iloc[0]) if not df.empty else 0.0
    denominator = base_equity if base_equity > 0 else base_cost

    if denominator <= 0:
        zero_series = pd.Series(0.0, index=df.index)
        return zero_series, zero_series

    period_pnl = (equity - base_equity) - (df["cost_basis"] - base_cost)
    period_return = period_pnl.divide(denominator).fillna(0.0) * 100
    return period_return, period_pnl.fillna(0.0)


def _build_reference_return_series(history: pd.DataFrame, target_index: pd.DatetimeIndex) -> pd.Series:
    if history.empty or "Close" not in history.columns or len(target_index) == 0:
        return pd.Series(dtype=float)

    close = history["Close"].reindex(target_index).ffill().bfill()
    base_price = float(close.iloc[0]) if not close.empty else 0.0
    if base_price <= 0:
        return pd.Series(0.0, index=target_index)

    return close.divide(base_price).subtract(1.0).fillna(0.0) * 100


def _format_legend_value(label: str, values: pd.Series) -> str:
    final_value = float(values.dropna().iloc[-1]) if not values.dropna().empty else 0.0
    return f"{label} 終值 {format_percent(final_value / 100)}"


def _align_metric_to_index(values: pd.Series, target_index: pd.DatetimeIndex) -> pd.Series:
    if values.empty:
        return pd.Series(0.0, index=target_index)

    aligned = values.astype(float).reindex(target_index)
    if isinstance(aligned.index, pd.DatetimeIndex):
        aligned = aligned.interpolate(method="time")
    return aligned.ffill().bfill().fillna(0.0)


def market_label_from_currency(currency: str) -> str:
    return "TW Stock" if str(currency).upper() == "TWD" else "US Stock"


def _market_colors(currency: str) -> tuple[str, str]:
    is_twd = str(currency).upper() == "TWD"
    positive_color = RED if is_twd else GREEN
    negative_color = GREEN if is_twd else RED
    return positive_color, negative_color


def _inject_zero_crossings(period_return: pd.Series) -> pd.Series:
    if period_return.empty or len(period_return) < 2:
        return period_return

    crossings: list[tuple[pd.Timestamp, float]] = []
    x_values = period_return.index
    y_values = period_return.astype(float).tolist()

    for i in range(len(y_values) - 1):
        y0 = y_values[i]
        y1 = y_values[i + 1]
        if y0 == 0 or y1 == 0 or y0 * y1 > 0:
            continue

        x0 = x_values[i]
        x1 = x_values[i + 1]
        fraction = -y0 / (y1 - y0)
        crossing_ns = x0.value + int((x1.value - x0.value) * fraction)
        crossings.append((pd.Timestamp(crossing_ns), 0.0))

    if not crossings:
        return period_return

    crossing_series = pd.Series(
        data=[value for _, value in crossings],
        index=pd.DatetimeIndex([timestamp for timestamp, _ in crossings]),
        dtype=float,
    )
    expanded = pd.concat([period_return.astype(float), crossing_series]).sort_index(kind="mergesort")
    return expanded[~expanded.index.duplicated(keep="first")]


def _split_return_series(period_return: pd.Series) -> tuple[pd.Series, pd.Series]:
    expanded = _inject_zero_crossings(period_return)
    positive_series = expanded.where(expanded >= 0)
    negative_series = expanded.where(expanded <= 0)
    return positive_series, negative_series


def _add_return_period_buttons(fig: go.Figure, labels: list[str], title: str, traces_per_period: int) -> None:
    buttons = []
    trace_count = len(labels) * traces_per_period

    for index, label in enumerate(labels):
        visible = [False] * trace_count
        start = index * traces_per_period
        for trace_offset in range(traces_per_period):
            visible[start + trace_offset] = True
        buttons.append(
            dict(
                label=label,
                method="update",
                args=[
                    {"visible": visible},
                    {"title": f"{title} - {label}"},
                ],
            )
        )

    fig.update_layout(
        updatemenus=[
            dict(
                type="buttons",
                direction="right",
                x=1.0,
                y=1.2,
                xanchor="right",
                yanchor="top",
                showactive=True,
                buttons=buttons,
                bgcolor="rgba(255, 255, 255, 0.92)",
                bordercolor=GRID,
                font=dict(color=MUTED),
            )
        ]
    )
    fig.update_xaxes(rangeselector=None)


def build_figures_by_currency(
    timeline: dict[str, pd.DataFrame],
    fetcher: PriceFetcher | None = None,
    reference_ticker_twd: str = DEFAULT_REFERENCE_TICKER_TWD,
) -> dict[str, dict[str, go.Figure]]:
    figures: dict[str, dict[str, go.Figure]] = {}
    reference_ticker_twd = str(reference_ticker_twd or "").strip().upper()
    try:
        reference_history = (
            fetcher.get_price_history(reference_ticker_twd)
            if fetcher is not None and reference_ticker_twd
            else pd.DataFrame()
        )
    except Exception:
        reference_history = pd.DataFrame()

    for currency, df in timeline.items():
        value_fig = go.Figure()
        value_fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["market_value"],
                mode="lines",
                name="投資組合市值",
                line=dict(color=BLUE, width=3),
                fill="tozeroy",
                fillgradient=_fill_gradient("rgba(31, 123, 216, 0.18)", "rgba(31, 123, 216, 0.02)"),
                customdata=_formatted_hover(df["market_value"]),
                hovertemplate="投資組合市值: %{customdata}<extra></extra>",
            )
        )
        value_fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["cost_basis"],
                mode="lines",
                name="累積成本",
                line=dict(color="#9AABA6", width=2, dash="dot"),
                customdata=_formatted_hover(df["cost_basis"]),
                hovertemplate="累積成本: %{customdata}<extra></extra>",
            )
        )
        value_fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["total_pnl"],
                mode="lines",
                name="總損益",
                line=dict(color=TEAL, width=2.5),
                fill="tozeroy",
                fillgradient=_fill_gradient("rgba(37, 99, 235, 0.14)", "rgba(37, 99, 235, 0.01)"),
                customdata=_formatted_hover(df["total_pnl"]),
                hovertemplate="總損益: %{customdata}<extra></extra>",
            )
        )
        _apply_common_layout(value_fig, "投資組合價值與損益", "金額")

        return_fig = go.Figure()
        labels: list[str] = []
        positive_color, negative_color = _market_colors(currency)
        show_twd_reference = str(currency).upper() == "TWD" and reference_ticker_twd and not reference_history.empty
        traces_per_period = 3 if show_twd_reference else 2
        positive_fill = (
            ("rgba(216, 63, 86, 0.18)", "rgba(216, 63, 86, 0.02)")
            if positive_color == RED
            else ("rgba(15, 159, 114, 0.18)", "rgba(15, 159, 114, 0.02)")
        )
        negative_fill = (
            ("rgba(216, 63, 86, 0.18)", "rgba(216, 63, 86, 0.02)")
            if negative_color == RED
            else ("rgba(15, 159, 114, 0.18)", "rgba(15, 159, 114, 0.02)")
        )

        for position, (period_key, label) in enumerate(PERIOD_OPTIONS):
            period_df = _slice_period(df, period_key)
            period_return, period_pnl = _build_period_return_metrics(period_df)
            positive_series, negative_series = _split_return_series(period_return)
            positive_pnl = _align_metric_to_index(period_pnl, positive_series.index)
            negative_pnl = _align_metric_to_index(period_pnl, negative_series.index)
            portfolio_legend = _format_legend_value("投資組合", period_return)

            return_fig.add_trace(
                go.Scatter(
                    x=positive_series.index,
                    y=positive_series,
                    mode="lines",
                    name=portfolio_legend,
                    visible=position == 0,
                    showlegend=True,
                    line=dict(color=positive_color, width=3),
                    fill="tozeroy",
                    fillgradient=_fill_gradient(*positive_fill),
                    customdata=list(
                        zip(
                            _formatted_hover(positive_series / 100, is_percent=True),
                            _formatted_pnl_hover(positive_pnl),
                        )
                    ),
                    hovertemplate="投資組合報酬率: %{customdata[0]}<br>區間損益: %{customdata[1]}<extra></extra>",
                )
            )
            return_fig.add_trace(
                go.Scatter(
                    x=negative_series.index,
                    y=negative_series,
                    mode="lines",
                    name=portfolio_legend,
                    visible=position == 0,
                    showlegend=False,
                    line=dict(color=negative_color, width=3),
                    fill="tozeroy",
                    fillgradient=_fill_gradient(*negative_fill),
                    customdata=list(
                        zip(
                            _formatted_hover(negative_series / 100, is_percent=True),
                            _formatted_pnl_hover(negative_pnl),
                        )
                    ),
                    hovertemplate="投資組合報酬率: %{customdata[0]}<br>區間損益: %{customdata[1]}<extra></extra>",
                )
            )

            if show_twd_reference:
                reference_df = _slice_period(reference_history, period_key)
                reference_return = _build_reference_return_series(reference_df, period_df.index)
                return_fig.add_trace(
                    go.Scatter(
                        x=reference_return.index,
                        y=reference_return,
                        mode="lines",
                        name=_format_legend_value(reference_ticker_twd, reference_return),
                        visible=position == 0,
                        showlegend=True,
                        line=dict(color=REFERENCE_GRAY, width=2.2),
                        customdata=_formatted_hover(reference_return / 100, is_percent=True),
                        hovertemplate=f"{reference_ticker_twd} 報酬率: %{{customdata}}<extra></extra>",
                    )
                )
            labels.append(label)

        _apply_common_layout(return_fig, f"投資組合報酬率 - {labels[0]}", "報酬率 (%)")
        _add_return_period_buttons(return_fig, labels, "投資組合報酬率", traces_per_period)

        figures[currency] = {"value": value_fig, "return": return_fig}

    return figures
