from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .performance import market_label_from_currency
from .utils import display_security_label, display_ticker, format_compact_number, format_percent, pnl_css, return_css, return_tone


TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
PWA_APP_NAME = "Stock Treasury Tracker"
PWA_SHORT_NAME = "Treasury"
PWA_THEME_COLOR = "#132238"
PWA_BG_COLOR = "#F7F3EC"
CHART_FONT_FAMILY = "'Aptos', 'Segoe UI Variable Display', 'Microsoft JhengHei', sans-serif"
PWA_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="outer" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#132238"/>
      <stop offset="100%" stop-color="#0F9F72"/>
    </linearGradient>
    <linearGradient id="spark" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#F2E6C9"/>
      <stop offset="100%" stop-color="#FFFFFF"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="112" fill="#F7F3EC"/>
  <rect x="28" y="28" width="456" height="456" rx="104" fill="url(#outer)"/>
  <rect x="86" y="92" width="340" height="252" rx="44" fill="rgba(255,255,255,0.08)" stroke="rgba(255,255,255,0.16)" stroke-width="8"/>
  <path d="M118 358h276" stroke="rgba(255,255,255,0.24)" stroke-width="18" stroke-linecap="round"/>
  <path d="M138 312l70-68 52 40 92-116" fill="none" stroke="url(#spark)" stroke-width="26" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="138" cy="312" r="16" fill="#FFFFFF"/>
  <circle cx="208" cy="244" r="16" fill="#F4E8C7"/>
  <circle cx="260" cy="284" r="16" fill="#FFFFFF"/>
  <circle cx="352" cy="168" r="16" fill="#F4E8C7"/>
</svg>"""

SUMMARY_LABELS = {
    "total_cost": "累積投入成本",
    "total_market_value": "投資組合淨值",
    "total_dividends": "股利收入",
    "total_pnl": "總損益",
    "total_return_pct": "總報酬率",
}

TABLE_COLUMNS = {
    "ticker": "Ticker",
    "name": "名稱",
    "currency": "幣別",
    "shares": "持股",
    "avg_cost": "剩餘均價成本",
    "last_price": "最新價",
    "total_cost": "剩餘成本",
    "market_value": "持股淨值",
    "realized_pnl": "已實現損益",
    "unrealized_pnl": "未實現損益",
    "unrealized_return_pct": "未實現報酬率",
    "dividends": "股利收入",
    "total_pnl": "總損益",
    "total_return_pct": "總報酬率",
}

VISIBLE_TABLE_COLUMNS = [
    "Ticker",
    "名稱",
    "持股",
    "剩餘均價成本",
    "最新價",
    "剩餘成本",
    "持股淨值",
    "已實現損益",
    "未實現損益",
    "未實現報酬率",
    "股利收入",
    "總損益",
    "總報酬率",
]

PIE_COLORS = [
    "#5B8FF9",
    "#61DDAA",
    "#F6BD16",
    "#E8684A",
    "#6DC8EC",
    "#9270CA",
    "#FF9D4D",
    "#269A99",
    "#FF99C3",
    "#7E8BFF",
]


def _currency_sort_key(currency: str) -> tuple[int, str]:
    normalized = str(currency).upper()
    if normalized == "TWD":
        return (0, normalized)
    if normalized == "USD":
        return (1, normalized)
    return (2, normalized)


def build_summary_cards(snapshot: dict[str, dict[str, float]]) -> list[dict[str, object]]:
    cards: list[dict[str, object]] = []

    for currency, metrics in sorted(snapshot.items(), key=lambda item: _currency_sort_key(item[0])):
        card_items: list[dict[str, str]] = []
        for key in ["total_cost", "total_market_value", "total_pnl", "total_return_pct"]:
            value = metrics[key]
            if key == "total_cost":
                tone = "slate"
            elif key == "total_market_value":
                tone = "gold"
            elif key == "total_pnl":
                tone = return_tone(value, currency)
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


def build_report_overview(snapshot: dict[str, dict[str, float]], stock_summary: pd.DataFrame) -> dict[str, str | int]:
    market_tokens: list[str] = []
    for currency in sorted(snapshot.keys(), key=_currency_sort_key):
        normalized = str(currency).upper()
        if normalized == "TWD":
            market_tokens.append("TW")
        elif normalized == "USD":
            market_tokens.append("US")
        else:
            market_tokens.append(normalized)

    holdings_count = 0 if stock_summary is None or stock_summary.empty else int(len(stock_summary.index))
    return {
        "market_scope": " / ".join(market_tokens) if market_tokens else "Portfolio",
        "holdings_count": holdings_count,
        "market_count": len(market_tokens),
    }


def _row_styles(row: pd.Series) -> list[str]:
    styles = [""] * len(row)
    currency = row.get("幣別", "")
    columns = list(row.index)

    for column_name in ["已實現損益", "未實現損益", "總損益"]:
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
    if "Ticker" in display_table.columns:
        display_table["Ticker"] = display_table["Ticker"].map(display_ticker)
    ordered_columns = [column for column in VISIBLE_TABLE_COLUMNS if column in display_table.columns]
    if "幣別" in display_table.columns:
        ordered_columns.append("幣別")
    display_table = display_table[ordered_columns]
    styler = (
        display_table.style.hide(axis="index")
        .format(
            {
                "持股": format_compact_number,
                "剩餘均價成本": format_compact_number,
                "最新價": format_compact_number,
                "剩餘成本": format_compact_number,
                "持股淨值": format_compact_number,
                "已實現損益": format_compact_number,
                "未實現損益": format_compact_number,
                "未實現報酬率": format_percent,
                "股利收入": format_compact_number,
                "總損益": format_compact_number,
                "總報酬率": format_percent,
            }
        )
        .apply(_row_styles, axis=1)
    )
    if "幣別" in display_table.columns:
        styler = styler.hide(axis="columns", subset=["幣別"])
    styler.set_table_attributes('class="detail-table"')
    return styler


def build_allocation_figure(stock_summary: pd.DataFrame, currency: str) -> go.Figure:
    group = stock_summary[stock_summary["currency"] == currency].copy()
    fig = go.Figure()

    if group.empty:
        fig.update_layout(
            title="持股市值占比",
            paper_bgcolor="#FFFCF7",
            plot_bgcolor="#F4F1EA",
            font=dict(color="#162235", family=CHART_FONT_FAMILY),
            margin=dict(l=24, r=24, t=72, b=24),
            annotations=[
                dict(
                    text="目前沒有持股資料",
                    x=0.5,
                    y=0.5,
                    showarrow=False,
                    font=dict(size=16, color="#667085"),
                )
            ],
        )
        fig.update_layout(title=None, margin=dict(l=24, r=24, t=24, b=24))
        return fig

    group = group.sort_values("market_value", ascending=False, ignore_index=True)
    group["display_ticker"] = group["ticker"].map(display_ticker)
    group["display_label"] = group.apply(lambda row: display_security_label(row["ticker"], row.get("name", "")), axis=1)
    total_value = float(group["market_value"].sum())
    hover_text = [
        f"{name}<br>淨值: {format_compact_number(value)}<br>占比: {format_percent(value / total_value if total_value else 0)}"
        for name, value in zip(group["display_label"], group["market_value"])
    ]

    fig.add_trace(
        go.Pie(
            labels=group["display_label"],
            values=group["market_value"],
            hole=0.42,
            sort=False,
            direction="clockwise",
            marker=dict(colors=PIE_COLORS, line=dict(color="#FFFFFF", width=2)),
            text=group["display_ticker"],
            textinfo="text+percent",
            textposition="outside",
            customdata=hover_text,
            hovertemplate="%{customdata}<extra></extra>",
        )
    )
    fig.update_layout(
        title="持股市值占比",
        paper_bgcolor="#FFFCF7",
        plot_bgcolor="#F4F1EA",
        font=dict(color="#162235", family=CHART_FONT_FAMILY),
        margin=dict(l=24, r=24, t=72, b=24),
        legend=dict(
            orientation="h",
            x=0,
            y=-0.08,
            xanchor="left",
            yanchor="top",
            bgcolor="rgba(255, 252, 247, 0.96)",
            bordercolor="rgba(22, 34, 56, 0.10)",
            borderwidth=1,
            font=dict(color="#667085"),
        ),
    )
    fig.update_layout(title=None, margin=dict(l=24, r=24, t=24, b=24))
    fig.add_annotation(
        text=f"總淨值<br><b>{format_compact_number(total_value)}</b>",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(size=15, color="#162235"),
    )
    return fig


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

    currency_order = [currency for currency in sorted(snapshot.keys(), key=_currency_sort_key) if currency in figures]
    if stock_summary is not None and not stock_summary.empty:
        for currency in sorted(stock_summary["currency"].drop_duplicates().tolist(), key=_currency_sort_key):
            if currency in figures and currency not in currency_order:
                currency_order.append(currency)

    plot_sections = []
    include_plotlyjs = True
    for currency in currency_order:
        figure_set = figures[currency]
        allocation_figure = build_allocation_figure(stock_summary, currency)
        plot_sections.append(
            {
                "currency": currency,
                "market_label": market_label_from_currency(currency),
                "value_chart": pio.to_html(
                    figure_set["value"],
                    include_plotlyjs=include_plotlyjs,
                    full_html=False,
                    default_width="100%",
                    default_height="460px",
                    config={"responsive": True, "displayModeBar": False},
                ),
                "return_chart": pio.to_html(
                    figure_set["return"],
                    include_plotlyjs=False,
                    full_html=False,
                    default_width="100%",
                    default_height="500px",
                    config={"responsive": True, "displayModeBar": False},
                ),
                "allocation_chart": pio.to_html(
                    allocation_figure,
                    include_plotlyjs=False,
                    full_html=False,
                    default_width="100%",
                    default_height="440px",
                    config={"responsive": True, "displayModeBar": False},
                ),
            }
        )
        include_plotlyjs = False

    styler = build_stock_summary_styler(stock_summary)
    table_html = styler.to_html() if styler is not None else ""

    return template.render(
        generated_at=generated_at.strftime("%Y-%m-%d %H:%M:%S"),
        overview=build_report_overview(snapshot, stock_summary),
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


def render_pwa_manifest() -> str:
    payload = {
        "name": PWA_APP_NAME,
        "short_name": PWA_SHORT_NAME,
        "start_url": "./",
        "scope": "./",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": PWA_BG_COLOR,
        "theme_color": PWA_THEME_COLOR,
        "icons": [
            {
                "src": "./icon.svg",
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any maskable",
            }
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def render_service_worker() -> str:
    return """const CACHE_NAME = "stock-treasury-pwa-v2";
const ASSETS = ["./", "./report.json", "./manifest.webmanifest", "./icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") {
    return;
  }

  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put("./", copy));
          return response;
        })
        .catch(() => caches.match("./"))
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) {
        return cached;
      }
      return fetch(event.request).then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return response;
      });
    })
  );
});"""


def render_pwa_icon_svg() -> str:
    return PWA_ICON_SVG
