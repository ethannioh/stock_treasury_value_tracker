from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.io as pio
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .performance import market_label_from_currency
from .utils import format_compact_number, format_percent, pnl_css, return_css, return_tone


TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
PWA_APP_NAME = "股票庫存績效報表"
PWA_SHORT_NAME = "股票報表"
PWA_THEME_COLOR = "#5E5ADB"
PWA_BG_COLOR = "#FFFFFF"
PWA_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#5E5ADB"/>
      <stop offset="100%" stop-color="#704214"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="108" fill="#FFFFFF"/>
  <rect x="32" y="32" width="448" height="448" rx="96" fill="url(#bg)"/>
  <path d="M120 342h272" stroke="#FFFFFF" stroke-width="20" stroke-linecap="round"/>
  <path d="M160 300l62-78 61 46 69-102" fill="none" stroke="#FFFFFF" stroke-width="24" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="160" cy="300" r="14" fill="#FFFFFF"/>
  <circle cx="222" cy="222" r="14" fill="#FFFFFF"/>
  <circle cx="283" cy="268" r="14" fill="#FFFFFF"/>
  <circle cx="352" cy="166" r="14" fill="#FFFFFF"/>
</svg>"""

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
        # Inline Plotly once so Safari/content blockers do not depend on cdn.plot.ly.
        include_plotlyjs = True if not plot_sections else False
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
    return """const CACHE_NAME = "stock-treasury-pwa-v1";
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
