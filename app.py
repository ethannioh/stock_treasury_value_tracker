from __future__ import annotations

import argparse
import platform
import sys
import traceback
from pathlib import Path

try:
    import pandas as pd

    from src.data_loader import ensure_sample_data, load_dividends, load_rate_config, load_transactions
    from src.performance import (
        DEFAULT_REFERENCE_TICKER_TWD,
        build_figures_by_currency,
        calculate_portfolio_snapshot,
        calculate_stock_summary,
        calculate_timeline,
        market_label_from_currency,
    )
    from src.price_fetcher import PriceFetcher
    from src.report_generator import (
        build_allocation_figure,
        build_report_overview,
        build_stock_summary_styler,
        build_summary_cards,
        render_html_report,
        render_json_report,
        render_pwa_icon_svg,
        render_pwa_manifest,
        render_service_worker,
    )
    from src.utils import ensure_directories, write_text
    IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    IMPORT_ERROR = exc


ROOT_DIR = Path(__file__).parent
DATA_DIR = ROOT_DIR / "data"
CACHE_DIR = ROOT_DIR / "cache"
OUTPUT_DIR = ROOT_DIR / "output"


def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return ROOT_DIR


def write_error_log(exc: Exception, args: argparse.Namespace | None = None) -> Path:
    log_path = get_app_dir() / "stock_treasury_value_tracker_error.log"
    lines = [
        "stock_treasury_value_tracker error log",
        f"python: {sys.version}",
        f"platform: {platform.platform()}",
        f"frozen: {getattr(sys, 'frozen', False)}",
    ]
    if args is not None:
        lines.extend(
            [
                f"transactions: {args.transactions}",
                f"dividends: {args.dividends}",
                f"output: {args.output}",
                f"json_output: {args.json_output}",
                f"cache_dir: {args.cache_dir}",
                f"cache_hours: {args.cache_hours}",
                f"rate_config: {args.rate_config}",
                f"reference_ticker_twd: {args.reference_ticker_twd}",
            ]
        )
    lines.extend(
        [
            "",
            f"error_type: {type(exc).__name__}",
            f"error_message: {exc}",
            "",
            "traceback:",
            traceback.format_exc(),
        ]
    )
    with log_path.open("w", encoding="utf-8-sig", newline="\n") as file:
        file.write("\n".join(lines))
    return log_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="股票庫存績效追蹤工具")
    parser.add_argument("--transactions", type=Path, default=DATA_DIR / "transactions.csv", help="交易資料 CSV 路徑")
    parser.add_argument("--dividends", type=Path, default=DATA_DIR / "dividends.csv", help="配息資料 CSV 路徑")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR / "report.html", help="輸出的 HTML 報表路徑")
    parser.add_argument("--json-output", type=Path, default=OUTPUT_DIR / "report.json", help="輸出的 JSON 資料路徑")
    parser.add_argument("--cache-dir", type=Path, default=CACHE_DIR, help="股價快取資料夾")
    parser.add_argument("--cache-hours", type=int, default=12, help="快取有效小時數")
    parser.add_argument(
        "--reference-ticker-twd",
        default=DEFAULT_REFERENCE_TICKER_TWD,
        help="台股報酬率比較用的 reference ticker，例如 0050.TW 或 006208.TW",
    )
    return parser.parse_args()


def parse_args_v2() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stock Treasury Value Tracker")
    parser.add_argument("--transactions", type=Path, default=DATA_DIR / "transactions.csv", help="交易資料 CSV 路徑")
    parser.add_argument("--dividends", type=Path, default=DATA_DIR / "dividends.csv", help="配息資料 CSV 路徑")
    parser.add_argument("--rate-config", type=Path, default=DATA_DIR / "market_fee_rates.csv", help="費率設定 CSV 路徑")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR / "report.html", help="HTML 報表輸出路徑")
    parser.add_argument("--json-output", type=Path, default=OUTPUT_DIR / "report.json", help="JSON 報表輸出路徑")
    parser.add_argument("--cache-dir", type=Path, default=CACHE_DIR, help="價格快取資料夾")
    parser.add_argument("--cache-hours", type=int, default=12, help="價格快取有效小時")
    parser.add_argument(
        "--reference-ticker-twd",
        default=DEFAULT_REFERENCE_TICKER_TWD,
        help="台股報酬率參考 ticker，例如 0050.TW 或 006208.TW",
    )
    return parser.parse_args()


def run_cli(args: argparse.Namespace) -> int:
    if IMPORT_ERROR is not None:
        raise RuntimeError("Application startup failed during import.") from IMPORT_ERROR

    ensure_directories(DATA_DIR, args.cache_dir, OUTPUT_DIR)
    ensure_sample_data(args.transactions, args.dividends, args.rate_config)

    rate_config = load_rate_config(args.rate_config)
    transactions = load_transactions(args.transactions, rate_config)
    dividends = load_dividends(args.dividends)
    fetcher = PriceFetcher(cache_dir=args.cache_dir, cache_hours=args.cache_hours)

    stock_summary = calculate_stock_summary(transactions, dividends, fetcher, rate_config)
    timeline = calculate_timeline(transactions, dividends, fetcher, rate_config)
    snapshot = calculate_portfolio_snapshot(timeline)
    figures = build_figures_by_currency(timeline, fetcher, args.reference_ticker_twd)

    generated_at = pd.Timestamp.now()
    html = render_html_report(
        snapshot=snapshot,
        stock_summary=stock_summary,
        figures=figures,
        generated_at=generated_at,
    )
    write_text(args.output, html)
    json_report = render_json_report(
        snapshot=snapshot,
        stock_summary=stock_summary,
        generated_at=generated_at,
        reference_ticker_twd=args.reference_ticker_twd,
    )
    write_text(args.json_output, json_report)
    write_text(args.output.parent / "manifest.webmanifest", render_pwa_manifest())
    write_text(args.output.parent / "service-worker.js", render_service_worker())
    write_text(args.output.parent / "icon.svg", render_pwa_icon_svg())
    print(f"報表已輸出：{args.output}")
    print(f"JSON 已輸出：{args.json_output}")
    return 0


def inject_streamlit_theme() -> None:
    import streamlit as st

    st.markdown(
        """
        <style>
        :root {
            --tv-bg: #f7f3ec;
            --tv-bg-soft: #fffcf7;
            --tv-bg-tint: #eef4ef;
            --tv-panel: rgba(255, 255, 255, 0.76);
            --tv-panel-strong: rgba(255, 252, 247, 0.9);
            --tv-panel-deep: #132238;
            --tv-panel-ink: #1b2d45;
            --tv-text: #344054;
            --tv-heading: #102038;
            --tv-muted: #667085;
            --tv-soft: #344054;
            --tv-dim: #8b95a7;
            --tv-line: rgba(19, 34, 56, 0.08);
            --tv-line-strong: rgba(19, 34, 56, 0.14);
            --tv-green: #0f9f72;
            --tv-red: #d83f56;
            --tv-amber: #bc7a25;
            --tv-shadow-lg: 0 28px 70px rgba(15, 23, 42, 0.08);
            --tv-shadow-md: 0 18px 44px rgba(15, 23, 42, 0.06);
            --tv-shadow-sm: 0 10px 26px rgba(15, 23, 42, 0.05);
            --tv-radius-xl: 30px;
            --tv-radius-lg: 24px;
            --tv-radius-md: 20px;
            --tv-radius-sm: 16px;
            --tv-font-sans: "Aptos", "Segoe UI Variable Display", "Microsoft JhengHei", sans-serif;
            --tv-font-numeric: "Bahnschrift", "Aptos", "Segoe UI Variable Display", "Microsoft JhengHei", sans-serif;
        }
        html, body, [class*="css"] {
            font-family: var(--tv-font-sans);
            font-size: 13px;
        }
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(19, 34, 56, 0.08), transparent 28%),
                radial-gradient(circle at top right, rgba(15, 159, 114, 0.12), transparent 24%),
                linear-gradient(180deg, var(--tv-bg-soft) 0%, var(--tv-bg) 54%, #f3efe7 100%);
            color: var(--tv-soft);
        }
        .stApp::before {
            content: "";
            position: fixed;
            inset: 0;
            pointer-events: none;
            background-image:
                linear-gradient(rgba(19, 34, 56, 0.028) 1px, transparent 1px),
                linear-gradient(90deg, rgba(19, 34, 56, 0.028) 1px, transparent 1px);
            background-size: 28px 28px;
            mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.72), transparent);
            opacity: 0.48;
        }
        .block-container {
            padding-top: 1rem;
            padding-bottom: 3rem;
            max-width: 1480px;
        }
        h1, h2, h3 {
            color: var(--tv-heading) !important;
        }
        p, label, .stCaption, .stMarkdown, .stTextInput label, .stNumberInput label, .stTextInput label p {
            color: var(--tv-soft) !important;
        }
        .tv-topbar,
        .tv-hero,
        .tv-panel,
        .tv-kpi-card,
        .tv-rail-card {
            border: 1px solid var(--tv-line);
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.82) 0%, var(--tv-panel) 100%);
            backdrop-filter: blur(18px);
            box-shadow: var(--tv-shadow-md);
        }
        .tv-topbar:hover,
        .tv-hero:hover,
        .tv-panel:hover {
            transform: translateY(-2px);
            box-shadow: var(--tv-shadow-lg);
            border-color: var(--tv-line-strong);
        }
        .tv-topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            margin-bottom: 0.9rem;
            padding: 0.85rem 1.1rem;
            border-radius: 999px;
        }
        .tv-topbar-left {
            display: flex;
            align-items: center;
            gap: 0.8rem;
        }
        .tv-brand-mark {
            width: 42px;
            height: 42px;
            border-radius: 14px;
            background:
                radial-gradient(circle at 25% 22%, rgba(255, 255, 255, 0.72), transparent 28%),
                linear-gradient(135deg, var(--tv-panel-deep) 0%, var(--tv-green) 100%);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.28);
            flex: 0 0 auto;
        }
        .tv-brand-eyebrow,
        .tv-eyebrow,
        .tv-section-kicker,
        .tv-kpi-label,
        .tv-mini-label {
            text-transform: uppercase;
            letter-spacing: 0.18em;
            font-size: 10px;
            color: var(--tv-dim) !important;
        }
        .tv-brand-title {
            font-size: 17px;
            font-weight: 800;
            letter-spacing: -0.02em;
            color: var(--tv-heading) !important;
        }
        .tv-topbar-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 0.65rem;
            justify-content: flex-end;
        }
        .tv-pill,
        .tv-chip,
        .tv-market-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.55rem 0.85rem;
            border-radius: 999px;
            border: 1px solid var(--tv-line);
            background: rgba(255, 255, 255, 0.76);
            color: var(--tv-soft) !important;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            box-shadow: var(--tv-shadow-sm);
        }
        .tv-pill strong {
            color: var(--tv-heading);
            font-family: var(--tv-font-numeric);
            letter-spacing: 0;
        }
        .tv-hero {
            position: relative;
            overflow: hidden;
            margin-bottom: 1.2rem;
            padding: 1.5rem;
            border-radius: var(--tv-radius-xl);
        }
        .tv-hero::before {
            content: "";
            position: absolute;
            inset: 0;
            background:
                radial-gradient(circle at 82% 22%, rgba(15, 159, 114, 0.18), transparent 24%),
                radial-gradient(circle at 14% 16%, rgba(19, 34, 56, 0.1), transparent 30%);
            pointer-events: none;
        }
        .tv-hero::after {
            content: "";
            position: absolute;
            inset: auto -32px -92px auto;
            width: 240px;
            height: 240px;
            border-radius: 0;
            background: radial-gradient(circle, rgba(188, 122, 37, 0.16), transparent 68%);
            filter: blur(18px);
        }
        .tv-hero-grid {
            position: relative;
            z-index: 1;
            display: block;
        }
        .tv-hero-copy {
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }
        .tv-hero h1 {
            margin: 0.45rem 0 0.45rem;
            font-size: 2.4rem;
            line-height: 0.98;
            letter-spacing: -0.04em;
            color: var(--tv-heading) !important;
        }
        .tv-hero p {
            position: relative;
            z-index: 1;
            margin: 0;
            max-width: 820px;
            color: var(--tv-muted) !important;
            line-height: 1.75;
            font-size: 0.9rem;
        }
        .tv-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.65rem;
        }
        .tv-chip {
            background: rgba(255, 252, 247, 0.84);
        }
        .tv-panel {
            margin: 0.85rem 0 1rem;
            padding: 1.15rem;
            border-radius: var(--tv-radius-lg);
        }
        .tv-panel-head {
            display: flex;
            align-items: end;
            justify-content: space-between;
            gap: 1rem;
            margin-bottom: 0.8rem;
        }
        .tv-panel-head p,
        .tv-section-copy {
            margin: 0;
            max-width: 26rem;
            color: var(--tv-muted) !important;
            font-size: 0.78rem;
            line-height: 1.7;
            text-align: right;
        }
        .tv-section-title {
            margin: 0.25rem 0 0;
            font-size: 1.6rem;
            line-height: 1.06;
            letter-spacing: -0.03em;
            color: var(--tv-heading) !important;
        }
        .tv-card-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 0.85rem;
            margin: 0.7rem 0 1rem;
        }
        .tv-market-pill {
            margin-bottom: 0.85rem;
            border-color: rgba(15, 159, 114, 0.14);
            background: rgba(15, 159, 114, 0.08);
            color: var(--tv-panel-deep) !important;
        }
        .tv-kpi-card {
            position: relative;
            overflow: hidden;
            border-radius: var(--tv-radius-md);
            padding: 1rem 1.05rem;
            min-height: 118px;
            color: var(--tv-soft);
        }
        .tv-kpi-card::before {
            content: "";
            position: absolute;
            top: 0;
            left: 1rem;
            right: 1rem;
            height: 3px;
            border-radius: 999px;
            background: rgba(19, 34, 56, 0.16);
        }
        .tv-kpi-card::after {
            content: "";
            position: absolute;
            inset: auto -32px -62px auto;
            width: 150px;
            height: 150px;
            border-radius: 0;
            background: radial-gradient(circle, rgba(255,255,255,0.4), transparent 70%);
            filter: blur(12px);
        }
        .tv-kpi-card.slate {
            background:
                linear-gradient(180deg, rgba(255, 255, 255, 0.82), rgba(249, 246, 239, 0.94)),
                linear-gradient(135deg, rgba(19, 34, 56, 0.08), rgba(19, 34, 56, 0));
        }
        .tv-kpi-card.slate::before { background: rgba(19, 34, 56, 0.18); }
        .tv-kpi-card.slate .tv-kpi-value { color: var(--tv-panel-ink); }
        .tv-kpi-card.brand {
            background:
                linear-gradient(180deg, rgba(19, 34, 56, 0.98), rgba(27, 45, 69, 0.96)),
                linear-gradient(135deg, rgba(15, 159, 114, 0.14), rgba(255, 255, 255, 0));
            border-color: rgba(19, 34, 56, 0.18);
            box-shadow: 0 20px 48px rgba(19, 34, 56, 0.16);
        }
        .tv-kpi-card.brand::before { background: rgba(255, 255, 255, 0.36); }
        .tv-kpi-card.brand .tv-kpi-label,
        .tv-kpi-card.brand .tv-kpi-value { color: #f8fafc !important; }
        .tv-kpi-card.gold {
            background:
                linear-gradient(180deg, rgba(255, 250, 240, 0.98), rgba(244, 228, 187, 0.98)),
                linear-gradient(135deg, rgba(188, 122, 37, 0.22), rgba(255, 255, 255, 0));
            border-color: rgba(188, 122, 37, 0.2);
            box-shadow: 0 18px 42px rgba(188, 122, 37, 0.16);
        }
        .tv-kpi-card.gold::before { background: rgba(188, 122, 37, 0.5); }
        .tv-kpi-card.gold .tv-kpi-label { color: rgba(93, 57, 11, 0.72) !important; }
        .tv-kpi-card.gold .tv-kpi-value { color: #8d5b14; }
        .tv-kpi-card.teal {
            background:
                linear-gradient(180deg, rgba(240, 250, 248, 0.98), rgba(215, 239, 235, 0.98)),
                linear-gradient(135deg, rgba(19, 140, 125, 0.2), rgba(255, 255, 255, 0));
            border-color: rgba(19, 140, 125, 0.18);
            box-shadow: 0 18px 42px rgba(19, 140, 125, 0.14);
        }
        .tv-kpi-card.teal::before { background: rgba(19, 140, 125, 0.46); }
        .tv-kpi-card.teal .tv-kpi-label { color: rgba(17, 86, 78, 0.72) !important; }
        .tv-kpi-card.teal .tv-kpi-value { color: #11756b; }
        .tv-kpi-card.amber {
            background:
                linear-gradient(180deg, rgba(255, 249, 239, 0.96), rgba(245, 234, 211, 0.96)),
                linear-gradient(135deg, rgba(188, 122, 37, 0.18), rgba(255, 255, 255, 0));
            border-color: rgba(188, 122, 37, 0.16);
        }
        .tv-kpi-card.amber::before { background: rgba(188, 122, 37, 0.42); }
        .tv-kpi-card.amber .tv-kpi-value { color: #9b631d; }
        .tv-kpi-card.green {
            background:
                linear-gradient(180deg, rgba(242, 250, 247, 0.96), rgba(227, 245, 236, 0.96)),
                linear-gradient(135deg, rgba(15, 159, 114, 0.18), rgba(255, 255, 255, 0));
            border-color: rgba(15, 159, 114, 0.18);
        }
        .tv-kpi-card.green::before { background: rgba(15, 159, 114, 0.44); }
        .tv-kpi-card.red {
            background:
                linear-gradient(180deg, rgba(252, 243, 245, 0.96), rgba(250, 230, 235, 0.96)),
                linear-gradient(135deg, rgba(216, 63, 86, 0.16), rgba(255, 255, 255, 0));
            border-color: rgba(216, 63, 86, 0.18);
        }
        .tv-kpi-card.red::before { background: rgba(216, 63, 86, 0.42); }
        .tv-kpi-label {
            position: relative;
            z-index: 1;
            opacity: 0.92;
            margin-bottom: 0.8rem;
            color: var(--tv-dim);
        }
        .tv-kpi-value {
            position: relative;
            z-index: 1;
            font-family: var(--tv-font-numeric);
            font-size: 1.8rem;
            font-weight: 800;
            letter-spacing: -0.04em;
            color: var(--tv-heading);
        }
        .tv-kpi-card.green .tv-kpi-value { color: #0f9f72; }
        .tv-kpi-card.red .tv-kpi-value { color: #c1324a; }
        .tv-table-wrap {
            background: rgba(255, 255, 255, 0.92);
            border: 1px solid var(--tv-line);
            border-radius: var(--tv-radius-md);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.32);
            overflow: auto;
        }
        .tv-table-wrap table {
            width: 100%;
            border-collapse: collapse;
        }
        .tv-table-wrap thead th {
            background: linear-gradient(180deg, rgba(249, 246, 239, 0.98), rgba(243, 238, 228, 0.98));
            color: var(--tv-heading) !important;
        }
        .tv-table-wrap th, .tv-table-wrap td {
            padding: 11px 11px;
            border-bottom: 1px solid var(--tv-line);
            white-space: nowrap;
            font-size: 12px;
            color: var(--tv-soft);
        }
        .tv-table-wrap td:first-child,
        .tv-table-wrap td:nth-child(2) {
            color: var(--tv-heading);
        }
        .tv-table-wrap td:first-child {
            font-family: var(--tv-font-numeric);
            font-weight: 700;
            letter-spacing: 0.02em;
        }
        .tv-table-wrap tbody tr:nth-child(even) {
            background: rgba(19, 34, 56, 0.024);
        }
        .tv-table-wrap tbody tr:hover {
            background: rgba(15, 159, 114, 0.06);
        }
        .stButton > button {
            background: linear-gradient(135deg, rgba(19, 34, 56, 0.98) 0%, rgba(15, 159, 114, 0.92) 100%);
            color: #ffffff;
            border: 1px solid rgba(19, 34, 56, 0.24);
            border-radius: 999px;
            padding: 0.56rem 1rem;
            font-weight: 800;
            box-shadow: 0 14px 30px rgba(19, 34, 56, 0.18);
        }
        .stButton > button:hover {
            background: linear-gradient(135deg, rgba(28, 47, 72, 0.98) 0%, rgba(20, 176, 128, 0.92) 100%);
            color: #ffffff;
        }
        .stTextInput > div > div > input,
        .stNumberInput input {
            background: rgba(255, 255, 255, 0.92);
            color: var(--tv-heading);
            border: 1px solid var(--tv-line) !important;
            border-radius: 16px !important;
            font-size: 12px;
        }
        div[data-baseweb="input"] {
            border-radius: 16px;
        }
        div[data-baseweb="select"] > div,
        .stTextInput > div > div,
        .stNumberInput > div > div {
            background: transparent;
        }
        .stAlert, div[data-testid="stInfo"], div[data-testid="stSuccess"], div[data-testid="stError"] {
            background: rgba(255, 255, 255, 0.92);
            color: var(--tv-soft);
            border: 1px solid var(--tv-line);
            border-radius: var(--tv-radius-md);
        }
        .stPlotlyChart {
            border-radius: var(--tv-radius-md);
            overflow: hidden;
            border: 1px solid var(--tv-line);
            box-shadow: var(--tv-shadow-sm);
        }
        .tv-settings-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 0.8rem;
        }
        @media (max-width: 768px) {
            .tv-topbar {
                flex-direction: column;
                align-items: stretch;
                border-radius: 28px;
            }
            .tv-topbar-meta {
                justify-content: flex-start;
            }
            .tv-hero {
                padding: 1.1rem;
            }
            .tv-panel {
                padding: 1rem;
            }
            .tv-hero h1 {
                font-size: 1.85rem;
            }
            .tv-panel-head {
                flex-direction: column;
                align-items: flex-start;
            }
            .tv-panel-head p {
                text-align: left;
            }
        }
        @media (max-width: 430px) {
            .tv-card-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 0.65rem;
                margin: 0.55rem 0 0.9rem;
            }
            .tv-kpi-card {
                min-height: 88px;
                padding: 0.8rem 0.8rem 0.75rem;
            }
            .tv-kpi-card::before {
                left: 0.8rem;
                right: 0.8rem;
            }
            .tv-kpi-label {
                margin-bottom: 0.55rem;
                font-size: 9px;
                letter-spacing: 0.14em;
            }
            .tv-kpi-value {
                font-size: 1.45rem;
            }
        }
        /* Flux Bento overrides */
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&display=swap');
        :root {
            --tv-bg: #0d1824;
            --tv-bg-soft: #09111a;
            --tv-bg-tint: #112131;
            --tv-panel: rgba(255, 255, 255, 0.07);
            --tv-panel-strong: rgba(255, 255, 255, 0.11);
            --tv-panel-deep: #0f1d2b;
            --tv-panel-ink: #f2fbff;
            --tv-text: #eef8ff;
            --tv-heading: #ffffff;
            --tv-muted: rgba(231, 249, 255, 0.66);
            --tv-soft: #d7eef4;
            --tv-dim: rgba(231, 249, 255, 0.44);
            --tv-line: rgba(255, 255, 255, 0.10);
            --tv-line-strong: rgba(255, 255, 255, 0.18);
            --tv-shadow-lg: 0 28px 72px rgba(0, 0, 0, 0.40);
            --tv-shadow-md: 0 18px 44px rgba(0, 0, 0, 0.30);
            --tv-shadow-sm: 0 12px 28px rgba(0, 0, 0, 0.24);
            --tv-font-sans: "Space Grotesk", "Segoe UI Variable Display", "Microsoft JhengHei", sans-serif;
            --tv-font-numeric: "Space Grotesk", "Bahnschrift", "Segoe UI Variable Display", "Microsoft JhengHei", sans-serif;
            --tv-green: #88ff98;
            --tv-red: #ff768e;
            --tv-amber: #e8ff85;
        }
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(71, 230, 255, 0.32), transparent 28%),
                radial-gradient(circle at 80% 18%, rgba(139, 255, 129, 0.18), transparent 24%),
                linear-gradient(180deg, #0d1824 0%, #09111a 100%);
        }
        .stApp::before {
            background:
                linear-gradient(180deg, rgba(88, 234, 255, 0.03) 0%, transparent 52%),
                linear-gradient(90deg, rgba(255, 255, 255, 0.02) 1px, transparent 1px);
            background-size: auto, 48px 48px;
            opacity: 1;
        }
        h1, h2, h3, p, label, .stCaption, .stMarkdown, .stTextInput label, .stNumberInput label, .stTextInput label p {
            font-family: var(--tv-font-sans) !important;
        }
        .tv-topbar,
        .tv-hero,
        .tv-panel {
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.09), rgba(255, 255, 255, 0.04));
            border-color: rgba(255, 255, 255, 0.10);
            box-shadow: var(--tv-shadow-md);
            backdrop-filter: blur(18px);
        }
        .tv-brand-mark {
            background:
                radial-gradient(circle at 30% 30%, rgba(255, 255, 255, 0.78), transparent 28%),
                linear-gradient(135deg, #58eaff 0%, #88ff98 58%, #e8ff85 100%);
            box-shadow: 0 0 20px rgba(88, 234, 255, 0.24);
        }
        .tv-brand-eyebrow,
        .tv-eyebrow,
        .tv-section-kicker,
        .tv-kpi-label,
        .tv-mini-label {
            color: rgba(231, 249, 255, 0.48) !important;
        }
        .tv-brand-title,
        .tv-section-title,
        .tv-hero h1 {
            color: #ffffff !important;
            letter-spacing: -0.05em;
        }
        .tv-hero {
            position: relative;
            padding: 1.6rem;
            border-radius: 30px;
            overflow: hidden;
        }
        .tv-hero::before,
        .tv-hero::after {
            display: none;
        }
        .tv-hero-copy {
            display: grid;
            gap: 1rem;
        }
        .tv-hero h1 {
            font-size: clamp(2.7rem, 5vw, 4.6rem);
            line-height: 0.96;
            max-width: 8ch;
        }
        .tv-hero-copy p,
        .tv-panel-head p {
            color: var(--tv-muted) !important;
        }
        .tv-chip-row {
            margin-top: 0.2rem;
        }
        .tv-chip-row::after {
            content: "";
            display: block;
            width: 100%;
            height: 96px;
            margin-top: 0.95rem;
            border-radius: 18px;
            background:
                linear-gradient(180deg, rgba(83, 250, 213, 0.22), transparent),
                linear-gradient(135deg, transparent 8%, #58eaff 25%, transparent 29%, transparent 43%, #88ff98 58%, transparent 63%, transparent 80%, #e8ff85 94%, transparent 96%);
            mask-image: linear-gradient(180deg, #000 65%, transparent);
            opacity: 0.95;
        }
        .tv-pill,
        .tv-chip,
        .tv-market-pill {
            background: rgba(255, 255, 255, 0.08);
            border-color: rgba(255, 255, 255, 0.10);
            color: rgba(255, 255, 255, 0.82) !important;
            box-shadow: none;
        }
        .tv-pill strong,
        .tv-chip strong {
            color: #ffffff;
        }
        .tv-chip {
            padding: 0.72rem 0.98rem;
        }
        .tv-card-grid {
            grid-template-columns: 1.15fr 0.85fr;
            grid-template-areas:
                "feature cost"
                "feature pnl"
                "return return";
            gap: 12px;
            margin-top: 0.75rem;
            align-items: stretch;
        }
        .tv-kpi-card {
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.09), rgba(255, 255, 255, 0.04));
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: 24px;
            box-shadow: none;
            min-height: 118px;
            backdrop-filter: blur(10px);
            color: #eef8ff;
        }
        .tv-kpi-card.feature { grid-area: feature; min-height: 248px; padding: 1.2rem 1.15rem; }
        .tv-kpi-card.cost { grid-area: cost; }
        .tv-kpi-card.pnl { grid-area: pnl; }
        .tv-kpi-card.return { grid-area: return; min-height: 108px; }
        .tv-kpi-card.feature .tv-kpi-value {
            font-size: clamp(2.5rem, 4vw, 3.2rem);
            letter-spacing: -0.06em;
        }
        .tv-kpi-card.feature::after {
            content: "";
            position: absolute;
            left: 1rem;
            right: 1rem;
            bottom: 1rem;
            height: 72px;
            border-radius: 16px;
            background:
                linear-gradient(180deg, rgba(83, 250, 213, 0.22), transparent),
                linear-gradient(135deg, transparent 8%, #58eaff 25%, transparent 29%, transparent 43%, #88ff98 58%, transparent 63%, transparent 80%, #e8ff85 94%, transparent 96%);
            mask-image: linear-gradient(180deg, #000 65%, transparent);
            opacity: 0.92;
        }
        .tv-kpi-card.feature .tv-kpi-label,
        .tv-kpi-card.feature .tv-kpi-value {
            position: relative;
            z-index: 1;
        }
        .tv-kpi-card::before {
            left: 1rem;
            right: 1rem;
            top: 0.9rem;
            height: 2px;
            background: linear-gradient(90deg, rgba(88, 234, 255, 0.56), rgba(136, 255, 152, 0.42), rgba(232, 255, 133, 0.28));
        }
        .tv-kpi-card::after {
            display: none;
        }
        .tv-kpi-label {
            color: rgba(231, 249, 255, 0.56) !important;
        }
        .tv-kpi-value {
            color: #ffffff;
        }
        .tv-kpi-card.slate,
        .tv-kpi-card.gold,
        .tv-kpi-card.teal,
        .tv-kpi-card.amber,
        .tv-kpi-card.green,
        .tv-kpi-card.red {
            border-color: rgba(255, 255, 255, 0.10);
        }
        .tv-kpi-card.slate {
            background:
                linear-gradient(180deg, rgba(17, 32, 45, 0.96), rgba(11, 22, 33, 0.94)),
                linear-gradient(135deg, rgba(88, 234, 255, 0.08), rgba(255, 255, 255, 0));
        }
        .tv-kpi-card.gold,
        .tv-kpi-card.amber {
            background:
                linear-gradient(180deg, rgba(27, 36, 24, 0.96), rgba(18, 24, 17, 0.94)),
                linear-gradient(135deg, rgba(232, 255, 133, 0.08), rgba(255, 255, 255, 0));
        }
        .tv-kpi-card.teal,
        .tv-kpi-card.green {
            background:
                linear-gradient(180deg, rgba(14, 34, 33, 0.96), rgba(10, 22, 25, 0.94)),
                linear-gradient(135deg, rgba(136, 255, 152, 0.08), rgba(255, 255, 255, 0));
        }
        .tv-kpi-card.red {
            background:
                linear-gradient(180deg, rgba(34, 20, 28, 0.96), rgba(20, 13, 20, 0.94)),
                linear-gradient(135deg, rgba(255, 118, 142, 0.08), rgba(255, 255, 255, 0));
        }
        .tv-kpi-card.slate::before { background: linear-gradient(90deg, rgba(88, 234, 255, 0.58), rgba(88, 234, 255, 0.12)); }
        .tv-kpi-card.gold::before,
        .tv-kpi-card.amber::before { background: linear-gradient(90deg, rgba(232, 255, 133, 0.58), rgba(232, 255, 133, 0.12)); }
        .tv-kpi-card.teal::before,
        .tv-kpi-card.green::before { background: linear-gradient(90deg, rgba(136, 255, 152, 0.58), rgba(136, 255, 152, 0.12)); }
        .tv-kpi-card.red::before { background: linear-gradient(90deg, rgba(255, 118, 142, 0.54), rgba(255, 118, 142, 0.12)); }
        .tv-kpi-card.slate .tv-kpi-label,
        .tv-kpi-card.gold .tv-kpi-label,
        .tv-kpi-card.amber .tv-kpi-label,
        .tv-kpi-card.teal .tv-kpi-label,
        .tv-kpi-card.green .tv-kpi-label,
        .tv-kpi-card.red .tv-kpi-label {
            color: rgba(231, 249, 255, 0.54) !important;
        }
        .tv-kpi-card.gold .tv-kpi-value,
        .tv-kpi-card.amber .tv-kpi-value { color: #e8ff85; }
        .tv-kpi-card.teal .tv-kpi-value,
        .tv-kpi-card.green .tv-kpi-value { color: #88ff98; }
        .tv-kpi-card.red .tv-kpi-value { color: #ff8fa5; }
        .stPlotlyChart .updatemenu-button rect,
        .stPlotlyChart .rangeselector rect {
            fill: rgba(15, 29, 43, 0.98) !important;
            stroke: rgba(255, 255, 255, 0.10) !important;
        }
        .stPlotlyChart .updatemenu-button text,
        .stPlotlyChart .rangeselector text {
            fill: rgba(255, 255, 255, 0.84) !important;
        }
        .stPlotlyChart .updatemenu-button:hover rect,
        .stPlotlyChart .rangeselector:hover rect {
            fill: rgba(24, 43, 61, 0.98) !important;
        }
        .stPlotlyChart .updatemenu-button.active rect,
        .stPlotlyChart .rangeselector .button.active rect,
        .stPlotlyChart g.updatemenu-button.active rect {
            fill: rgba(22, 47, 67, 0.98) !important;
            stroke: rgba(88, 234, 255, 0.42) !important;
        }
        .stPlotlyChart .updatemenu-button.active text,
        .stPlotlyChart .rangeselector .button.active text,
        .stPlotlyChart g.updatemenu-button.active text {
            fill: #ffffff !important;
        }
        .tv-table-wrap,
        .stPlotlyChart {
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.04));
            border-color: rgba(255, 255, 255, 0.10);
            box-shadow: var(--tv-shadow-sm);
        }
        .tv-table-wrap thead th {
            background: rgba(255, 255, 255, 0.08);
            color: #ffffff !important;
        }
        .tv-table-wrap th,
        .tv-table-wrap td {
            color: rgba(231, 249, 255, 0.84);
            border-bottom-color: rgba(255, 255, 255, 0.08);
        }
        .tv-table-wrap td:first-child,
        .tv-table-wrap td:nth-child(2) {
            color: #ffffff;
        }
        .tv-table-wrap tbody tr:nth-child(even) {
            background: rgba(255, 255, 255, 0.02);
        }
        .tv-table-wrap tbody tr:hover {
            background: rgba(255, 255, 255, 0.05);
        }
        .stButton > button,
        .stTextInput > div > div > input,
        .stNumberInput input {
            background: rgba(255, 255, 255, 0.08);
            color: #ffffff;
            border-color: rgba(255, 255, 255, 0.10) !important;
            box-shadow: none;
        }
        .stButton > button:hover {
            background: rgba(255, 255, 255, 0.14);
            color: #ffffff;
        }
        .tv-hero h1 {
            font-size: 0 !important;
            line-height: 1 !important;
            margin-bottom: 0 !important;
        }
        .tv-hero h1::after {
            content: "Ethan's Portfolio";
            display: inline-block;
            font-size: clamp(2.9rem, 6vw, 5.3rem);
            line-height: 0.95;
            letter-spacing: -0.06em;
            color: #ffffff;
            white-space: nowrap;
            word-break: normal;
            overflow-wrap: normal;
            max-width: none;
        }
        @media (max-width: 430px) {
            .tv-hero {
                padding: 1.2rem;
            }
            .tv-hero h1 {
                font-size: 0 !important;
            }
            .tv-hero h1::after {
                font-size: 2.35rem;
                white-space: normal;
                word-break: keep-all;
            }
            .tv-chip-row::after {
                height: 76px;
            }
            .tv-card-grid {
                grid-template-columns: minmax(0, 1fr);
                grid-template-areas:
                    "feature"
                    "cost"
                    "pnl"
                    "return";
                gap: 10px;
            }
            .tv-kpi-card {
                min-height: auto;
                border-radius: 22px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 0.9rem;
                padding: 1.2rem 0.95rem 0.85rem;
            }
            .tv-kpi-card.feature {
                min-height: auto;
            }
            .tv-kpi-card.feature::after {
                display: none;
            }
            .tv-kpi-card.feature,
            .tv-kpi-card.cost,
            .tv-kpi-card.pnl,
            .tv-kpi-card.return {
                grid-area: auto;
            }
            .tv-kpi-card::before {
                top: 0.72rem;
                left: 0.95rem;
                right: 0.95rem;
            }
            .tv-kpi-label {
                margin-top: 0.25rem;
                font-size: 0.74rem;
                line-height: 1.2;
                white-space: nowrap;
            }
            .tv-kpi-value,
            .tv-kpi-card.feature .tv-kpi-value {
                font-size: 1.15rem;
                line-height: 1;
                text-align: right;
                white-space: nowrap;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_kpi_cards(snapshot: dict[str, dict[str, float]]) -> None:
    import streamlit as st

    for card_group in build_summary_cards(snapshot):
        st.markdown(
            f'<div class="tv-market-pill">{card_group["market_label"]}</div>',
            unsafe_allow_html=True,
        )
        cards_html = "".join(
            [
                f'<div class="tv-kpi-card {item["tone"]} {item.get("layout_class", "")}">'
                f'<div class="tv-kpi-label">{item["label"]}</div>'
                f'<div class="tv-kpi-value">{item["value"]}</div>'
                f"</div>"
                for item in card_group["card_items"]
            ]
        )
        st.markdown(f'<div class="tv-card-grid">{cards_html}</div>', unsafe_allow_html=True)


def render_dashboard_hero(snapshot: dict[str, dict[str, float]], stock_summary: pd.DataFrame) -> None:
    import streamlit as st

    overview = build_report_overview(snapshot, stock_summary)
    generated_at = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    st.markdown(
        f"""
        <section class="tv-topbar">
          <div class="tv-topbar-left">
            <div class="tv-brand-mark"></div>
            <div>
              <div class="tv-brand-eyebrow">Stock Treasury Tracker</div>
              <div class="tv-brand-title">Portfolio Command Center</div>
            </div>
          </div>
          <div class="tv-topbar-meta">
            <div class="tv-pill">Updated <strong>{generated_at}</strong></div>
            <div class="tv-pill">Markets <strong>{overview["market_scope"]}</strong></div>
            <div class="tv-pill">Holdings <strong>{overview["holdings_count"]}</strong></div>
          </div>
        </section>
        <section class="tv-hero">
          <div class="tv-hero-grid">
            <div class="tv-hero-copy">
              <div>
                <div class="tv-eyebrow">Modern Finance Dashboard</div>
                <h1>股票庫存績效追蹤工具</h1>
              </div>
              <div class="tv-chip-row">
                <div class="tv-chip">Live Snapshot</div>
                <div class="tv-chip">PWA Ready</div>
              </div>
            </div>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def run_streamlit() -> None:
    if IMPORT_ERROR is not None:
        raise RuntimeError("Application startup failed during import.") from IMPORT_ERROR

    import streamlit as st

    rate_config_path = DATA_DIR / "market_fee_rates.csv"
    ensure_directories(DATA_DIR, CACHE_DIR, OUTPUT_DIR)
    ensure_sample_data(DATA_DIR / "transactions.csv", DATA_DIR / "dividends.csv", rate_config_path)

    st.set_page_config(page_title="Ethan's Portfolio", layout="wide")
    inject_streamlit_theme()

    if "transactions_path" not in st.session_state:
        st.session_state.transactions_path = str(DATA_DIR / "transactions.csv")
    if "dividends_path" not in st.session_state:
        st.session_state.dividends_path = str(DATA_DIR / "dividends.csv")
    if "cache_hours" not in st.session_state:
        st.session_state.cache_hours = 12
    if "reference_ticker_twd" not in st.session_state:
        st.session_state.reference_ticker_twd = DEFAULT_REFERENCE_TICKER_TWD
    if "output_path" not in st.session_state:
        st.session_state.output_path = str(OUTPUT_DIR / "report.html")
    if "json_output_path" not in st.session_state:
        st.session_state.json_output_path = str(OUTPUT_DIR / "report.json")

    transactions_path = st.session_state.transactions_path
    dividends_path = st.session_state.dividends_path
    cache_hours = st.session_state.cache_hours
    reference_ticker_twd = st.session_state.reference_ticker_twd
    output_path = st.session_state.output_path
    json_output_path = st.session_state.json_output_path

    try:
        rate_config = load_rate_config(rate_config_path)
        transactions = load_transactions(Path(transactions_path), rate_config)
        dividends = load_dividends(Path(dividends_path))
        fetcher = PriceFetcher(cache_dir=CACHE_DIR, cache_hours=int(cache_hours))
        stock_summary = calculate_stock_summary(transactions, dividends, fetcher, rate_config)
        timeline = calculate_timeline(transactions, dividends, fetcher, rate_config)
        snapshot = calculate_portfolio_snapshot(timeline)
        figures = build_figures_by_currency(timeline, fetcher, reference_ticker_twd)
    except Exception as exc:
        st.error(f"載入資料或抓取股價時發生錯誤：{exc}")
        st.stop()

    render_dashboard_hero(snapshot, stock_summary)
    render_kpi_cards(snapshot)

    st.markdown(
        """
        <section class="tv-panel">
          <div class="tv-panel-head">
            <div>
              <div class="tv-section-kicker">Holdings Table</div>
              <h2 class="tv-section-title">股票明細</h2>
            </div>
            <p class="tv-section-copy">即時查看剩餘成本、持股淨值、已實現損益、未實現損益與總報酬率。</p>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    styler = build_stock_summary_styler(stock_summary)
    if styler is None:
        st.info("目前沒有可顯示的股票明細。")
    else:
        st.markdown(f'<div class="tv-table-wrap">{styler.to_html()}</div>', unsafe_allow_html=True)

    st.markdown(
        """
        <section class="tv-panel" style="display:none;">
          <div class="tv-panel-head">
            <div>
              <div class="tv-section-kicker">History & Return</div>
              <h2 class="tv-section-title">歷史績效圖</h2>
            </div>
            <p class="tv-section-copy">保留既有折線顏色與互動區間，外框、容器與展示節奏改成更像產品化的 finance app 模組。</p>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    for currency, figure_set in figures.items():
        st.markdown(
            f'<div class="tv-market-pill">{market_label_from_currency(currency)}</div>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(figure_set["value"], use_container_width=True)
        st.plotly_chart(figure_set["return"], use_container_width=True)
        st.plotly_chart(build_allocation_figure(stock_summary, currency), use_container_width=True)

    st.markdown(
        """
        <section class="tv-panel">
          <div class="tv-panel-head">
            <div>
              <div class="tv-section-kicker">Settings</div>
              <h2 class="tv-section-title">設定</h2>
            </div>
            <p class="tv-section-copy">設定區維持在底部，方便把這頁當成主要觀看儀表板。</p>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    settings_col_1, settings_col_2, settings_col_3 = st.columns([2, 2, 1])
    with settings_col_1:
        st.text_input("交易資料 CSV", key="transactions_path")
    with settings_col_2:
        st.text_input("配息資料 CSV", key="dividends_path")
    with settings_col_3:
        st.number_input("快取有效小時", min_value=1, max_value=168, key="cache_hours")

    settings_col_4, settings_col_5, settings_col_6 = st.columns([1.4, 2, 2])
    with settings_col_4:
        st.text_input("台股 Reference", key="reference_ticker_twd", help="例如 0050.TW、006208.TW；清空則不顯示 reference 線")
    with settings_col_5:
        st.text_input("HTML 報表輸出路徑", key="output_path")
    with settings_col_6:
        st.text_input("JSON 資料輸出路徑", key="json_output_path")

    if st.button("套用設定 / 重新載入資料"):
        st.rerun()

    if st.button("輸出 HTML / JSON 報表", type="primary"):
        generated_at = pd.Timestamp.now()
        html = render_html_report(
            snapshot=snapshot,
            stock_summary=stock_summary,
            figures=figures,
            generated_at=generated_at,
        )
        write_text(Path(st.session_state.output_path), html)
        json_report = render_json_report(
            snapshot=snapshot,
            stock_summary=stock_summary,
            generated_at=generated_at,
            reference_ticker_twd=st.session_state.reference_ticker_twd,
        )
        write_text(Path(st.session_state.json_output_path), json_report)
        output_parent = Path(st.session_state.output_path).parent
        write_text(output_parent / "manifest.webmanifest", render_pwa_manifest())
        write_text(output_parent / "service-worker.js", render_service_worker())
        write_text(output_parent / "icon.svg", render_pwa_icon_svg())
        st.success(f"報表已輸出到：{st.session_state.output_path}；JSON 已輸出到：{st.session_state.json_output_path}")


def in_streamlit_runtime() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        return get_script_run_ctx() is not None
    except Exception:
        return False


if __name__ == "__main__":
    if in_streamlit_runtime():
        run_streamlit()
    else:
        parsed_args = parse_args_v2()
        try:
            raise SystemExit(run_cli(parsed_args))
        except SystemExit:
            raise
        except Exception as exc:
            log_path = write_error_log(exc, parsed_args)
            print(f"ERROR: {exc}")
            print(f"Error log saved to: {log_path}")
            raise SystemExit(1)
