from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.io as pio
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .performance import market_label_from_currency
from .utils import format_compact_number, format_percent, pnl_css, return_css, return_tone


TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

SUMMARY_LABELS = {
    "total_cost": "總投入成本",
    "total_market_value": "目前總市值",
    "total_dividends": "總配息",
    "total_pnl": "總損益",
    "total_return_pct": "總報酬率",
}

TABLE_COLUMNS = {
    "ticker": "股票代號",
    "name": "名稱",
    "currency": "幣別",
    "shares": "股數",
    "avg_cost": "平均成本",
    "last_price": "最新價格",
    "total_cost": "總投入成本",
    "market_value": "目前市值",
    "unrealized_pnl": "未實現損益",
    "unrealized_return_pct": "未實現報酬率",
    "dividends": "配息收入",
    "total_pnl": "總損益",
    "total_return_pct": "總報酬率",
}


def build_summary_cards(snapshot: dict[str, dict[str, float]]) -> list[dict[str, object]]:
    cards: list[dict[str, object]] = []

    for currency, metrics in snapshot.items():
        card_items: list[dict[str, str]] = []
        for key in ["total_cost", "total_market_value", "total_dividends", "total_pnl", "total_return_pct"]:
            value = metrics[key]
            if key in {"total_cost", "total_market_value"}:
                tone = "green"
            elif key == "total_dividends":
                tone = "orange"
            elif key == "total_return_pct":
                tone = return_tone(value, currency)
            else:
                tone = "green" if value >= 0 else "red"

            card_items.append(
                {
                    "label": SUMMARY_LABELS[key],
                    "value": format_percent(value) if key.endswith("_pct") else format_compact_number(value),
                    "tone": tone,
                }
            )

        cards.append({"currency": currency, "market_label": market_label_from_currency(currency), "card_items": card_items})

    return cards


def _row_styles(row: pd.Series) -> list[str]:
    styles = [""] * len(row)
    currency = row.get("幣別", "")
    columns = list(row.index)

    for column_name in ["未實現損益", "總損益"]:
        if column_name in row.index:
            styles[columns.index(column_name)] = pnl_css(row[column_name])

    for column_name in ["未實現報酬率", "總報酬率"]:
        if column_name in row.index:
            styles[columns.index(column_name)] = return_css(row[column_name], currency)

    return styles


def build_stock_summary_styler(stock_summary: pd.DataFrame) -> pd.io.formats.style.Styler | None:
    if stock_summary.empty:
        return None

    display_table = stock_summary.rename(columns=TABLE_COLUMNS).copy()
    styler = (
        display_table.style.hide(axis="index")
        .format(
            {
                "股數": format_compact_number,
                "平均成本": format_compact_number,
                "最新價格": format_compact_number,
                "總投入成本": format_compact_number,
                "目前市值": format_compact_number,
                "未實現損益": format_compact_number,
                "未實現報酬率": format_percent,
                "配息收入": format_compact_number,
                "總損益": format_compact_number,
                "總報酬率": format_percent,
            }
        )
        .apply(_row_styles, axis=1)
        .hide(axis="columns", subset=["幣別"])
    )
    styler.set_table_attributes('class="detail-table"')
    return styler


def render_html_report(
    snapshot: dict[str, dict[str, float]],
    stock_summary: pd.DataFrame,
    figures: dict[str, dict[str, object]],
    generated_at: pd.Timestamp,
) -> str:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("report.html.j2")

    plot_sections = []
    for currency, figure_set in figures.items():
        plot_sections.append(
            {
                "currency": currency,
                "market_label": market_label_from_currency(currency),
                "value_chart": pio.to_html(figure_set["value"], include_plotlyjs="cdn", full_html=False),
                "return_chart": pio.to_html(figure_set["return"], include_plotlyjs=False, full_html=False),
            }
        )

    styler = build_stock_summary_styler(stock_summary)
    table_html = styler.to_html() if styler is not None else ""

    return template.render(
        generated_at=generated_at.strftime("%Y-%m-%d %H:%M:%S"),
        summary_cards=build_summary_cards(snapshot),
        table_html=table_html,
        plot_sections=plot_sections,
    )


def render_json_report(
    snapshot: dict[str, dict[str, float]],
    stock_summary: pd.DataFrame,
    generated_at: pd.Timestamp,
    reference_ticker_twd: str,
) -> str:
    payload = {
        "generated_at": generated_at.isoformat(),
        "reference_ticker_twd": reference_ticker_twd,
        "summary": snapshot,
        "holdings": stock_summary.to_dict(orient="records") if not stock_summary.empty else [],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
