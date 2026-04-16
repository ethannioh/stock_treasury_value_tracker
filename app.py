from __future__ import annotations

import argparse
import platform
import sys
import traceback
from pathlib import Path

try:
    import pandas as pd

    from src.data_loader import ensure_sample_data, load_dividends, load_transactions
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


def run_cli(args: argparse.Namespace) -> int:
    if IMPORT_ERROR is not None:
        raise RuntimeError("Application startup failed during import.") from IMPORT_ERROR

    ensure_directories(DATA_DIR, args.cache_dir, OUTPUT_DIR)
    ensure_sample_data(args.transactions, args.dividends)

    transactions = load_transactions(args.transactions)
    dividends = load_dividends(args.dividends)
    fetcher = PriceFetcher(cache_dir=args.cache_dir, cache_hours=args.cache_hours)

    stock_summary = calculate_stock_summary(transactions, dividends, fetcher)
    snapshot = calculate_portfolio_snapshot(stock_summary)
    timeline = calculate_timeline(transactions, dividends, fetcher)
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
            --tv-bg: #f0f0f0;
            --tv-bg-2: #f7f7f7;
            --tv-panel: rgba(250, 250, 250, 0.92);
            --tv-panel-strong: rgba(255, 255, 255, 0.96);
            --tv-text: #475569;
            --tv-heading: #111827;
            --tv-muted: #64748b;
            --tv-soft: #475569;
            --tv-dim: #94a3b8;
            --tv-line: rgba(82, 88, 98, 0.14);
            --tv-line-strong: rgba(82, 88, 98, 0.24);
            --tv-blue: #1f7bd8;
            --tv-green: #0f9f72;
            --tv-red: #d83f56;
            --tv-orange: #f97316;
            --tv-accent: #2563eb;
            --tv-accent-warm: #f97316;
        }
        html, body, [class*="css"]  {
            font-family: Consolas, "Microsoft JhengHei", "Segoe UI", sans-serif;
            font-size: 13px;
        }
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(255, 255, 255, 0.72), transparent 28%),
                radial-gradient(circle at top right, rgba(31, 123, 216, 0.055), transparent 34%),
                linear-gradient(180deg, #f7f7f7 0%, var(--tv-bg) 100%);
            color: var(--tv-soft);
        }
        .stApp::before {
            content: "";
            position: fixed;
            inset: 0;
            pointer-events: none;
            background-image:
                linear-gradient(rgba(82, 88, 98, 0.035) 1px, transparent 1px),
                linear-gradient(90deg, rgba(82, 88, 98, 0.035) 1px, transparent 1px);
            background-size: 32px 32px;
            mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.58), transparent);
        }
        .block-container {
            padding-top: 1.25rem;
            padding-bottom: 3rem;
            max-width: 1440px;
        }
        h1, h2, h3 {
            color: var(--tv-heading) !important;
        }
        p, label, .stCaption, .stMarkdown, .stTextInput label, .stNumberInput label {
            color: var(--tv-soft) !important;
        }
        .stMarkdown strong {
            color: var(--tv-accent-warm);
        }
        .tv-hero {
            position: relative;
            overflow: hidden;
            margin-bottom: 1.2rem;
            padding: 1.25rem 1.35rem;
            border-radius: 0;
            border: 1px solid var(--tv-line);
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, var(--tv-panel) 100%);
            box-shadow: 0 22px 52px rgba(82, 88, 98, 0.12);
        }
        .tv-hero::after {
            content: "";
            position: absolute;
            inset: auto -20px -70px auto;
            width: 220px;
            height: 220px;
            border-radius: 0;
            background: radial-gradient(circle, rgba(31, 123, 216, 0.12), transparent 68%);
            filter: blur(14px);
        }
        .tv-eyebrow,
        .tv-section-kicker,
        .tv-kpi-label {
            text-transform: uppercase;
            letter-spacing: 0.18em;
            font-size: 10px;
        }
        .tv-eyebrow,
        .tv-section-kicker {
            color: var(--tv-dim) !important;
        }
        .tv-hero h1 {
            margin: 0.45rem 0 0.45rem;
            font-size: 1.75rem;
            line-height: 1.08;
            letter-spacing: 0.02em;
            color: var(--tv-heading) !important;
        }
        .tv-hero p {
            position: relative;
            z-index: 1;
            margin: 0;
            max-width: 880px;
            color: var(--tv-muted) !important;
            line-height: 1.6;
            font-size: 0.88rem;
        }
        .tv-panel {
            margin: 0.85rem 0 1rem;
            padding: 1rem;
            border-radius: 0;
            border: 1px solid var(--tv-line);
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.95) 0%, var(--tv-panel) 100%);
            box-shadow: 0 18px 42px rgba(82, 88, 98, 0.1);
        }
        .tv-panel p {
            color: var(--tv-dim) !important;
        }
        .tv-card-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 10px;
            margin: 8px 0 16px;
        }
        .tv-kpi-card {
            position: relative;
            overflow: hidden;
            border-radius: 0;
            padding: 12px 14px;
            min-height: 96px;
            border: 1px solid var(--tv-line);
            box-shadow: 0 16px 36px rgba(82, 88, 98, 0.1);
            color: var(--tv-soft);
        }
        .tv-kpi-card::after {
            content: "";
            position: absolute;
            inset: auto -24px -48px auto;
            width: 120px;
            height: 120px;
            border-radius: 0;
            background: radial-gradient(circle, rgba(255,255,255,0.52), transparent 70%);
            filter: blur(10px);
        }
        .tv-kpi-card.green {
            background:
                linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(250, 250, 250, 0.95)),
                linear-gradient(135deg, rgba(15, 159, 114, 0.2), rgba(31, 123, 216, 0.1));
            border-color: rgba(15, 159, 114, 0.28);
        }
        .tv-kpi-card.red {
            background:
                linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(250, 248, 249, 0.95)),
                linear-gradient(135deg, rgba(216, 63, 86, 0.18), rgba(249, 115, 22, 0.1));
            border-color: rgba(216, 63, 86, 0.28);
        }
        .tv-kpi-card.orange {
            background:
                linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(251, 249, 245, 0.95)),
                linear-gradient(135deg, rgba(249, 115, 22, 0.18), rgba(37, 99, 235, 0.08));
            border-color: rgba(249, 115, 22, 0.28);
        }
        .tv-kpi-label {
            opacity: 0.92;
            margin-bottom: 7px;
            color: var(--tv-dim);
        }
        .tv-kpi-value {
            font-size: 22px;
            font-weight: 700;
            letter-spacing: -0.02em;
            color: var(--tv-heading);
        }
        .tv-kpi-card.green .tv-kpi-value { color: #0f9f72; }
        .tv-kpi-card.red .tv-kpi-value { color: #bf3349; }
        .tv-kpi-card.orange .tv-kpi-value { color: #ea580c; }
        .tv-table-wrap {
            background: rgba(250, 250, 250, 0.88);
            border: 1px solid var(--tv-line);
            border-radius: 0;
            box-shadow: 0 14px 32px rgba(82, 88, 98, 0.09);
            overflow: auto;
        }
        .tv-table-wrap table {
            width: 100%;
            border-collapse: collapse;
        }
        .tv-table-wrap thead th {
            background: linear-gradient(180deg, rgba(238, 241, 245, 0.98), rgba(222, 227, 235, 0.98));
            color: var(--tv-accent) !important;
        }
        .tv-table-wrap th, .tv-table-wrap td {
            padding: 9px 9px;
            border-bottom: 1px solid var(--tv-line);
            white-space: nowrap;
            font-size: 12px;
            color: var(--tv-soft);
        }
        .tv-table-wrap td:first-child,
        .tv-table-wrap td:nth-child(2) {
            color: #1e293b;
        }
        .tv-table-wrap tbody tr:nth-child(even) {
            background: rgba(82, 88, 98, 0.035);
        }
        .tv-table-wrap tbody tr:hover {
            background: rgba(31, 123, 216, 0.075);
        }
        .stButton > button {
            background: linear-gradient(135deg, rgba(37, 99, 235, 0.96) 0%, rgba(249, 115, 22, 0.9) 100%);
            color: #ffffff;
            border: 1px solid rgba(37, 99, 235, 0.32);
            border-radius: 0;
            padding: 0.52rem 1rem;
            font-weight: 800;
            box-shadow: 0 12px 28px rgba(37, 99, 235, 0.18);
        }
        .stButton > button:hover {
            background: linear-gradient(135deg, rgba(59, 130, 246, 0.96) 0%, rgba(251, 146, 60, 0.92) 100%);
            color: #ffffff;
        }
        .stTextInput > div > div > input,
        .stNumberInput input {
            background: rgba(255, 255, 255, 0.92);
            color: #1e293b;
            border: 1px solid var(--tv-line) !important;
            border-radius: 0 !important;
            font-size: 12px;
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
            border-radius: 0;
        }
        .stPlotlyChart {
            border-radius: 0;
            overflow: hidden;
            border: 1px solid var(--tv-line);
            box-shadow: 0 14px 32px rgba(82, 88, 98, 0.09);
        }
        .tv-settings-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 0.8rem;
        }
        @media (max-width: 768px) {
            .tv-hero {
                padding: 1rem;
                border-radius: 0;
            }
            .tv-panel {
                padding: 0.9rem;
                border-radius: 0;
            }
            .tv-hero h1 {
                font-size: 1.5rem;
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
            f'<div class="tv-section-kicker">Market</div><h3 style="margin:0.35rem 0 0.2rem;">{card_group["market_label"]}</h3>',
            unsafe_allow_html=True,
        )
        cards_html = "".join(
            [
                f'<div class="tv-kpi-card {item["tone"]}">'
                f'<div class="tv-kpi-label">{item["label"]}</div>'
                f'<div class="tv-kpi-value">{item["value"]}</div>'
                f"</div>"
                for item in card_group["card_items"]
            ]
        )
        st.markdown(f'<div class="tv-card-grid">{cards_html}</div>', unsafe_allow_html=True)


def run_streamlit() -> None:
    if IMPORT_ERROR is not None:
        raise RuntimeError("Application startup failed during import.") from IMPORT_ERROR

    import streamlit as st

    ensure_directories(DATA_DIR, CACHE_DIR, OUTPUT_DIR)
    ensure_sample_data(DATA_DIR / "transactions.csv", DATA_DIR / "dividends.csv")

    st.set_page_config(page_title="股票庫存績效追蹤工具", layout="wide")
    inject_streamlit_theme()
    st.markdown(
        """
        <section class="tv-hero">
          <div class="tv-eyebrow">Performance Overview</div>
          <h1>股票庫存績效追蹤工具</h1>
          <p>以明亮科技儀表板風格呈現台股與美股投資組合，保留區間報酬率、0% 穿越分段上色、以及台股紅漲綠跌 / 美股綠漲紅跌邏輯。</p>
        </section>
        """,
        unsafe_allow_html=True,
    )

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
        transactions = load_transactions(Path(transactions_path))
        dividends = load_dividends(Path(dividends_path))
        fetcher = PriceFetcher(cache_dir=CACHE_DIR, cache_hours=int(cache_hours))
        stock_summary = calculate_stock_summary(transactions, dividends, fetcher)
        snapshot = calculate_portfolio_snapshot(stock_summary)
        timeline = calculate_timeline(transactions, dividends, fetcher)
        figures = build_figures_by_currency(timeline, fetcher, reference_ticker_twd)
    except Exception as exc:
        st.error(f"載入資料或抓取股價時發生錯誤：{exc}")
        st.stop()

    st.markdown(
        """
        <section class="tv-panel">
          <div class="tv-section-kicker">Portfolio Snapshot</div>
          <h2 style="margin:0.45rem 0 0.5rem;">投資組合總覽</h2>
        </section>
        """,
        unsafe_allow_html=True,
    )
    render_kpi_cards(snapshot)

    st.markdown(
        """
        <section class="tv-panel">
          <div class="tv-section-kicker">Holdings Table</div>
          <h2 style="margin:0.45rem 0 0.5rem;">股票明細</h2>
          <p style="margin:0;">即時查看成本、市值、配息、總損益與總報酬率。</p>
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
        <section class="tv-panel">
          <div class="tv-section-kicker">History & Return</div>
          <h2 style="margin:0.45rem 0 0.5rem;">歷史績效圖</h2>
          <p style="margin:0;">保留折線塗色、區間報酬率、台美股配色規則與 0% 穿越分段上色。</p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    for currency, figure_set in figures.items():
        st.markdown(
            f'<div class="tv-section-kicker">Market</div><h3 style="margin:0.35rem 0 0.75rem;">{market_label_from_currency(currency)}</h3>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(figure_set["value"], use_container_width=True)
        st.plotly_chart(figure_set["return"], use_container_width=True)

    st.markdown(
        """
        <section class="tv-panel">
          <div class="tv-section-kicker">Settings</div>
          <h2 style="margin:0.45rem 0 0.5rem;">設定</h2>
          <p style="margin:0;">設定區已移到頁面底部，調整後 Streamlit 會自動重新載入資料。</p>
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
        parsed_args = parse_args()
        try:
            raise SystemExit(run_cli(parsed_args))
        except SystemExit:
            raise
        except Exception as exc:
            log_path = write_error_log(exc, parsed_args)
            print(f"ERROR: {exc}")
            print(f"Error log saved to: {log_path}")
            raise SystemExit(1)
