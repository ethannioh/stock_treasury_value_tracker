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


BG = "#FFFFFF"
PANEL = "#F7F9FC"
GRID = "rgba(30, 35, 41, 0.10)"
GRID_STRONG = "rgba(30, 35, 41, 0.18)"
TEXT = "#1E2329"
TITLE = "#1E2329"
MUTED = "#677281"
BLUE = "#5E5ADB"
GREEN = "#0F9F72"
RED = "#D83F56"
TEAL = "#704214"
REFERENCE_GRAY = "#A2A9B3"
DEFAULT_REFERENCE_TICKER_TWD = "0050.TW"
EPSILON = 1e-9
PERIOD_OPTIONS = [
    ("1d", "1D"),
    ("1w", "1W"),
    ("1m", "1M"),
    ("ytd", "YTD"),
    ("1y", "1Y"),
    ("3y", "3Y"),
    ("5y", "5Y"),
    ("all", "全部"),
]


def _compute_ticker_position_metrics(tx_df: pd.DataFrame) -> dict[str, float | str]:
    ordered = tx_df.sort_values(["trade_date", "sort_order"], ignore_index=True)
    shares = 0.0
    remaining_cost = 0.0
    gross_buy_outlay = 0.0
    net_sell_proceeds = 0.0
    realized_pnl = 0.0

    for row in ordered.itertuples(index=False):
        quantity = float(row.quantity)
        gross_amount = float(row.gross_amount)
        fees_and_tax = float(row.total_charge_amount)

        if row.side == "buy":
            shares += quantity
            remaining_cost += gross_amount + fees_and_tax
            gross_buy_outlay += gross_amount + fees_and_tax
            continue

        if quantity > shares + EPSILON:
            raise ValueError(
                f"{row.ticker} sell quantity {quantity} exceeds current holdings {shares} on {row.trade_date:%Y-%m-%d}"
            )

        average_cost = remaining_cost / shares if shares > EPSILON else 0.0
        removed_cost = average_cost * quantity
        proceeds = gross_amount - fees_and_tax

        realized_pnl += proceeds - removed_cost
        net_sell_proceeds += proceeds
        shares -= quantity
        remaining_cost -= removed_cost

        if shares <= EPSILON:
            shares = 0.0
            remaining_cost = 0.0

    return {
        "shares": shares,
        "remaining_cost": remaining_cost,
        "gross_buy_outlay": gross_buy_outlay,
        "net_sell_proceeds": net_sell_proceeds,
        "realized_pnl": realized_pnl,
    }


def _net_holdings_value(
    shares: float,
    price: float,
    currency: str,
    rate_config: dict[tuple[str, str], dict[str, float]] | None = None,
) -> float:
    gross_market_value = shares * price
    exit_cost_rate = _sell_cost_rate(rate_config, currency)
    return gross_market_value * (1 - exit_cost_rate)


def _sell_cost_rate(rate_config: dict[tuple[str, str], dict[str, float]] | None, currency: str) -> float:
    if rate_config is None:
        return 0.0
    sell_rates = rate_config.get((str(currency).upper(), "sell"), {})
    return float(sell_rates.get("fee", 0.0)) + float(sell_rates.get("tax", 0.0))


def calculate_stock_summary(
    transactions: pd.DataFrame,
    dividends: pd.DataFrame,
    fetcher: PriceFetcher,
    rate_config: dict[tuple[str, str], dict[str, float]] | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    grouped_transactions = transactions.groupby("ticker", sort=False)
    dividend_totals = dividends.groupby("ticker")["amount"].sum().to_dict()

    for ticker, tx_df in grouped_transactions:
        position_metrics = _compute_ticker_position_metrics(tx_df)
        shares = float(position_metrics["shares"])
        if shares <= 0:
            continue

        snapshot = fetcher.get_price_snapshot(ticker)
        total_cost = float(position_metrics["remaining_cost"])
        gross_buy_outlay = float(position_metrics["gross_buy_outlay"])
        realized_pnl = float(position_metrics["realized_pnl"])
        market_value = _net_holdings_value(
            shares,
            snapshot.last_price,
            snapshot.currency or infer_currency_from_ticker(ticker),
            rate_config,
        )
        unrealized_pnl = market_value - total_cost
        dividends_income = float(dividend_totals.get(ticker, 0.0))
        total_pnl = unrealized_pnl + realized_pnl + dividends_income
        total_return_denominator = gross_buy_outlay if gross_buy_outlay > 0 else total_cost

        rows.append(
            {
                "ticker": ticker,
                "name": snapshot.name,
                "currency": snapshot.currency or infer_currency_from_ticker(ticker),
                "shares": shares,
                "avg_cost": total_cost / shares if shares else 0.0,
                "last_price": snapshot.last_price,
                "total_cost": total_cost,
                "gross_buy_outlay": gross_buy_outlay,
                "market_value": market_value,
                "realized_pnl": realized_pnl,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_return_pct": (unrealized_pnl / total_cost) if total_cost else 0.0,
                "dividends": dividends_income,
                "total_pnl": total_pnl,
                "total_return_pct": (total_pnl / total_return_denominator) if total_return_denominator else 0.0,
            }
        )

    summary = pd.DataFrame(rows)
    if summary.empty:
        return summary
    return summary.sort_values(["currency", "ticker"], ignore_index=True)


def calculate_portfolio_snapshot(timeline: dict[str, pd.DataFrame]) -> dict[str, dict[str, float]]:
    snapshot: dict[str, dict[str, float]] = {}
    for currency, df in timeline.items():
        if df.empty:
            continue

        latest = df.iloc[-1]
        total_cost = float(latest["cost_basis"])
        total_market_value = float(latest["market_value"])
        total_dividends = float(latest["dividends"])
        total_pnl = float(latest["total_pnl"])
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
    rate_config: dict[tuple[str, str], dict[str, float]] | None = None,
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
        buy_outlay_delta = pd.Series(0.0, index=all_dates)
        sell_proceeds_delta = pd.Series(0.0, index=all_dates)
        dividend_delta = pd.Series(0.0, index=all_dates)

        tx_df = transactions[transactions["ticker"] == ticker].sort_values(["trade_date", "sort_order"], ignore_index=True)
        _compute_ticker_position_metrics(tx_df)

        for _, row in tx_df.iterrows():
            effective_date = first_index_on_or_after(all_dates, row["trade_date"])
            if effective_date is None:
                continue

            if row["side"] == "buy":
                shares_delta.loc[effective_date] += float(row["quantity"])
                buy_outlay_delta.loc[effective_date] += float(row["gross_buy_outlay"])
            else:
                shares_delta.loc[effective_date] -= float(row["quantity"])
                sell_proceeds_delta.loc[effective_date] += float(row["net_sell_proceeds"])

        for _, row in dividends[dividends["ticker"] == ticker].iterrows():
            effective_date = first_index_on_or_after(all_dates, row["dividend_date"])
            if effective_date is not None:
                dividend_delta.loc[effective_date] += float(row["amount"])

        shares_held = shares_delta.cumsum()
        cumulative_buy_outlay = buy_outlay_delta.cumsum()
        cumulative_sell_proceeds = sell_proceeds_delta.cumsum()
        cumulative_dividends = dividend_delta.cumsum()
        holdings_value = close_series * shares_held * (1 - _sell_cost_rate(rate_config, currency))
        portfolio_value = holdings_value + cumulative_sell_proceeds

        bucket = timelines[currency]
        bucket["market_value"] = bucket.get("market_value", pd.Series(0.0, index=all_dates)).add(
            portfolio_value, fill_value=0.0
        )
        bucket["cost_basis"] = bucket.get("cost_basis", pd.Series(0.0, index=all_dates)).add(
            cumulative_buy_outlay, fill_value=0.0
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
        font=dict(color=TEXT, family="Inter, Roboto, 'SF Pro Text', 'Helvetica Neue', Arial, 'Microsoft JhengHei', sans-serif"),
        margin=dict(l=44, r=24, t=108, b=44),
        title_font=dict(size=20, color=TITLE),
        legend=dict(
            bgcolor="rgba(255, 255, 255, 0.96)",
            bordercolor=GRID,
            borderwidth=1,
            font=dict(color=MUTED),
        ),
        hoverlabel=dict(
            bgcolor="rgba(255, 255, 255, 0.98)",
            bordercolor=GRID_STRONG,
            font=dict(color=TITLE),
        ),
    )
    fig.update_xaxes(
        rangeselector=dict(
            buttons=[
                dict(count=1, label="1D", step="day", stepmode="backward"),
                dict(count=7, label="1W", step="day", stepmode="backward"),
                dict(count=1, label="1M", step="month", stepmode="backward"),
                dict(count=1, label="YTD", step="year", stepmode="todate"),
                dict(count=1, label="1Y", step="year", stepmode="backward"),
                dict(count=3, label="3Y", step="year", stepmode="backward"),
                dict(count=5, label="5Y", step="year", stepmode="backward"),
                dict(step="all", label="全部"),
            ],
            bgcolor="rgba(255, 255, 255, 0.98)",
            activecolor="rgba(94, 90, 219, 0.14)",
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
    if period_key == "1d":
        return df.tail(2).copy()
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

    for index in range(len(y_values) - 1):
        y0 = y_values[index]
        y1 = y_values[index + 1]
        if y0 == 0 or y1 == 0 or y0 * y1 > 0:
            continue

        x0 = x_values[index]
        x1 = x_values[index + 1]
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
                bgcolor="rgba(255, 255, 255, 0.98)",
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
                fillgradient=_fill_gradient("rgba(94, 90, 219, 0.18)", "rgba(94, 90, 219, 0.02)"),
                customdata=_formatted_hover(df["market_value"]),
                hovertemplate="投資組合市值: %{customdata}<extra></extra>",
            )
        )
        value_fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["cost_basis"],
                mode="lines",
                name="累積投入成本",
                line=dict(color="#A2A9B3", width=2, dash="dot"),
                customdata=_formatted_hover(df["cost_basis"]),
                hovertemplate="累積投入成本: %{customdata}<extra></extra>",
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
                fillgradient=_fill_gradient("rgba(112, 66, 20, 0.14)", "rgba(112, 66, 20, 0.01)"),
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

        _apply_common_layout(return_fig, f"投資組合報酬率 - {labels[0]}", "報酬率(%)")
        _add_return_period_buttons(return_fig, labels, "投資組合報酬率", traces_per_period)

        figures[currency] = {"value": value_fig, "return": return_fig}

    return figures
