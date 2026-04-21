# Codex Handoff

Last updated: 2026-04-21 (Asia/Taipei)

## Repo

- Path: `D:\One-Drive\OneDrive - Realtek Semiconductor Corp\Python\stock_treasury_value_tracker`
- Branch: `main`
- Latest pushed commit: `a72be26`
- Useful tags: `V1`, `stable-V2`, `style0`

## Current local state

- `data/transactions.csv` has local uncommitted changes
- This file is now the single resume note
- Previous duplicate handoff file `交接.md` has been merged into this file
- Preview port normally used in this repo: `http://127.0.0.1:8502`
- The preview was not responding at the last check, so restart may be needed

## What this project is

- Streamlit stock inventory / portfolio tracking app
- Reads transactions and dividends CSV files
- Fetches market data from Yahoo Finance
- Generates:
  - Streamlit app UI
  - `output/report.html`
  - `output/report.json`
  - PWA assets such as manifest / service worker / icon

## Current UI direction

- Style direction: `01 / Flux Bento`
- Hero title: `Ethan's Portfolio`
- Hero chips kept: `Live Snapshot`, `PWA Ready`
- Donut palette uses stronger red / blue / green contrast

## Recent completed changes

- Removed x-axis title text from charts
- Removed legend title text from charts
- Fixed iPhone range buttons so active state stays dark with readable text
- Changed mobile KPI layout to a single-column stacked list
- Moved KPI labels away from the top accent line on mobile
- Hero title was adjusted for proper horizontal display

## Important files

- Main app: [app.py](D:\One-Drive\OneDrive - Realtek Semiconductor Corp\Python\stock_treasury_value_tracker\app.py)
- Chart logic: [src/performance.py](D:\One-Drive\OneDrive - Realtek Semiconductor Corp\Python\stock_treasury_value_tracker\src\performance.py)
- Report generation: [src/report_generator.py](D:\One-Drive\OneDrive - Realtek Semiconductor Corp\Python\stock_treasury_value_tracker\src\report_generator.py)
- Utilities: [src/utils.py](D:\One-Drive\OneDrive - Realtek Semiconductor Corp\Python\stock_treasury_value_tracker\src\utils.py)
- HTML template: [templates/report.html.j2](D:\One-Drive\OneDrive - Realtek Semiconductor Corp\Python\stock_treasury_value_tracker\templates\report.html.j2)

## Run commands

Start Streamlit:

```powershell
Set-Location "D:\One-Drive\OneDrive - Realtek Semiconductor Corp\Python\stock_treasury_value_tracker"
py -3.11 -m streamlit run app.py
```

Start the app on the usual preview port:

```powershell
Set-Location "D:\One-Drive\OneDrive - Realtek Semiconductor Corp\Python\stock_treasury_value_tracker"
py -3.11 -m streamlit run app.py --server.headless true --server.port 8502
```

Generate HTML / JSON report:

```powershell
Set-Location "D:\One-Drive\OneDrive - Realtek Semiconductor Corp\Python\stock_treasury_value_tracker"
py -3.11 app.py --cache-hours 999999 --output output\report.html --json-output output\report.json
```

## Git notes

- Do not blindly commit `data/transactions.csv`
- When pushing UI work, check `git status` first
- Normal flow:

```powershell
git status
git add app.py src/performance.py src/report_generator.py templates/report.html.j2
git commit -m "your message"
git push origin main
```

## Resume instructions

When reopening Codex app:

1. Open this repo
2. Read this file
3. Say: `Resume from CODEX_STATUS.md`

Optional extra reminder:

- Continue from the current Flux Bento mobile-polish version
