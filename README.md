# PSE Edge scraper, database, and screening UI

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Python ETL from the Philippine Stock Exchange EDGE portal into SQLite, a Django REST API on that database, and a React (Vite) registry for filters, checklists, watchlist, and multi-ticker compare. Personal / educational research only. Read [DISCLAIMER.md](DISCLAIMER.md) before use.

The scraper pulls EDGE HTML and ranked 17-A/AFS PDFs. It does not use Yahoo-style quote APIs for Philippine dividend history (those fail on tickers such as `LTG.PS`).

Oral walkthrough notes: [`docs/INTERVIEW_TALK_TRACK.md`](docs/INTERVIEW_TALK_TRACK.md).

## Pipeline

```
companies.csv → PSEScraper → HTML / PDF → Parser → SQLite (pse_analysis.db)
                                                      ↓
                                          Django REST API → React UI
                                                      ↘
                                          report_generator (optional charts)
```

| EDGE endpoint | Role |
|---------------|------|
| `search.ax` | Find disclosures (Annual Report, SEC Form 17-C, …) |
| `openDiscViewer.do` | Document viewer |
| `downloadHtml.do` | HTML report body (PDFs fetched separately) |
| `dividends_and_rights_list.ax` | Dividend history (XHR) |
| `stockData.do` | Last price, market cap, outstanding shares |

Delay between requests: random 1.5–5.5 s (`MIN_DELAY` / `MAX_DELAY`).

SQLite holds company snapshots (`div_yield`, `roic`, `debt_to_equity`, `info_incomplete`, checklist counts), fiscal-year financials, dividends with `cash` / `property` type, and a `processing_log` per run. TTM yield is common cash DPS over the last 12 months ÷ last price.

### Parsing rules that broke numbers when ignored

Filings state amounts in thousands, millions, or billions; skip the scale note and every ratio is wrong. Property / non-cash dividend rows can look numeric; yield ignores them. Structural checklist bits (growth, dilution, liquidity, D/E when applicable) stay in the DB. P/E, P/B, ROE, and live pass counts rescore from request thresholds so Apply cannot leave a stale CHECKS column.

Liabilities captions that mean "liabilities and equity" are dropped. Missing equity can be filled as assets - liabilities. Ranked 17-A/AFS PDFs fill null whitelist fields only on fiscal years that already exist from HTML. See [Banking names](#banking-names) for bank capital return, checklist slots, and PDF field labels. After changing bank checklist rules, rescore with `python scripts/backfill_struct_checks.py`.

## ROIC modes

| Mode | Numerator | Invested capital | When |
|------|-----------|------------------|------|
| Proper | NOPAT = operating income (or GP−GA) × (1−t) | Assets − cash − current liabilities | Cash + CL on at least one year |
| Proxy | Net income | Assets − CL (else assets) | Proper inputs missing |
| Equity | Net income | Average stockholders' equity | Banks / insurance |

PDF overlay is fill-nulls only (cash, CL, OI / GP / GA, tax, IBT, related whitelist). Page routing needs statement titles plus tabular peso density so PFRS/MD&A prose is not treated as FS pages.

## Banking names

Deposit banks (`subsector` Banks) do not use industrial invested capital (assets - cash - current liabilities). The UI calls the equity-mode series **capital return** (net income / average equity), not ROIC. Brokers and other financial institutions stay on equity capital return without the loan/NPL checklist.

| UI / checklist | What it measures | Filing labels the PDF path accepts |
|----------------|------------------|-------------------------------------|
| Capital return | NI / avg equity | (computed; not a line item) |
| Loan growth | YoY `total_loans` | Loans and advances / receivables - net; loans and other receivables - net |
| Deposit growth | YoY `total_deposits` | Deposit liabilities |
| Loans/Deposits | LDR proxy | same loan + deposit lines |
| NPL ratio | `npl` / loans | Non-performing loans; BSP performing/NPL table totals |
| NII growth | YoY `net_interest_income` | Net interest income |
| ACL (data quality) | Loan-loss allowance stock | Allowance for credit losses / impairment |

Cash / CL / OI columns in the data-quality grid are industrial ROIC inputs. On Banks the grid shows Loans / Dep / NII / NPL / ACL instead. In the one-command demo, open **BPI** for a three-year filled bank series.

Fill or refresh bank checklist fields from cached AFS under `data/filings/<EDGE cmpy_id>/` (`companies.symbol`):

```bash
python scripts/backfill_bank_fields.py --dry-run --limit 5
python scripts/backfill_bank_fields.py --tickers PNB,SECB,BDO,AUB
python scripts/backfill_bank_fields.py
```

Hybrid / image AFS OCR: native text on every page; sparse pages (&lt; 80 alnum chars) get a cheap 72 DPI probe, then up to 40 full **300 DPI** OCR passes on the best-scoring statement candidates anywhere in the file (not only pages 1–40). Full OCR uses a PyMuPDF pixmap → Pillow (grayscale, autocontrast, threshold) → Tesseract (`pytesseract`, `--psm 6`), with MuPDF OCR as fallback. Soft-skip if tessdata is missing (`TESSDATA_PREFIX`). Needs `Pillow` / `pytesseract` from `requirements.txt` plus a system Tesseract install. Integrated / ESG filenames are never OCR'd.

Holdings / miners often lack commercial sales. Revenue surrogates (gross revenue, equity in associates, interest income) and NI/EPS/BV repair:

```bash
python scripts/backfill_revenue_surrogates.py --dry-run
python scripts/backfill_revenue_surrogates.py
python scripts/backfill_ni_eps_bv.py --tickers CHP,FGEN,ABSP
python scripts/backfill_ni_eps_bv.py
```

Network cash backfill (never overwrites non-nulls):

```bash
python scripts/backfill_cash_for_roic.py --dry-run --limit 20
python scripts/backfill_cash_for_roic.py --limit 50
python scripts/backfill_cash_for_roic.py --cached-pdfs-only --limit 50
```

Thin core history (rescrape older annuals; `--skip-recent 0`):

```bash
python scripts/backfill_thin_core_history.py --dry-run
python scripts/backfill_thin_core_history.py --limit 8
```

Share history from EDGE `tmplNm=Shares` (Form 17-C and 17-12-A Top 100 Stockholders). Fills null fiscal years only; use for `thin_shares_series` names that had only the stock-page count:

```bash
python scripts/backfill_shares_history.py --dry-run --limit 10
python scripts/backfill_shares_history.py --tickers AB,BLOOM
python scripts/backfill_shares_history.py --limit 50
```

Post-scrape DB audit: `python scripts/sanity_check_rescrape.py`.

### Data-quality reviews (offline)

Inventory incompleteness and soft warnings from the warehouse, then attribute likely parser/pipeline misses using cached PDFs under `data/filings/`:

```bash
python scripts/db_review_dq.py
python scripts/db_review_dq.py --warns-only
python scripts/parser_review_misses.py --limit 40
python scripts/parser_review_misses.py --from-db-review data/reviews/<stamp>
```

Writes under `data/reviews/<timestamp>/`:

| File | Contents |
|------|----------|
| `db_review_summary.md` | Histograms of incomplete reasons and soft warnings |
| `db_review_companies.csv` | Per-ticker reasons, warn tokens, core/share years, PDF cache counts |
| `db_review_fields.csv` | Per year/field presence + `field_sources` tag |
| `parser_review_summary.md` | `miss_class` counts and fixture/merge-gap candidates |
| `parser_review_misses.csv` | Per field: DB vs re-extracted PDF value and class |

`miss_class` values:

- `html_core_miss_needs_rescrape_or_fixture`: core EDGE HTML gap (HTML bodies are not cached)
- `thin_shares_form17c_or_stock_page`: fewer than two years with outstanding shares
- `no_pdf_cache`: cash/whitelist gap with no files under `data/filings/<EDGE cmpy_id>/` (same key as `companies.symbol`)
- `pdf_extract_ok_merge_or_write_gap`: PDF re-extract found a value; DB cell still empty
- `pdf_label_or_page_router_miss`: cached PDF re-extract still null

`industrial_roic_na_use_equity` is counted in the DB summary but is not treated as a parser miss (expected for banks). Soft warnings never flip `info_incomplete`.

Offline column recompute (no EDGE):

```bash
python scripts/backfill_all.py
```

Order: stockholders equity → div yield → ROIC → structural / screening checks.

## Fixture tests

```bash
python scripts/run_fixture_tests.py
```

Covers `fixtures/parser/` (thousands / millions scale, zero parent NI, EDGE layout canary), screening guards (yield scrub, threshold checklist labels, D/E, bank equity ROIC), `fixtures/demo/pse_demo.db` (BPI equity mode + NPL), `fixtures/roic/` PDF text, and news relevance filters. No EDGE calls.

When EDGE changes table captions or scale-note wording, the canary in `fixtures/parser/canary_edge_tables.html` fails with expected-vs-got keys. Update that fixture after you verify filings still parse correctly.

Detail responses include `field_sources` per fiscal year (`html` / `pdf` / `backfill` / `derived` / `form17c` / `disclosure`) and soft `data_warnings` (`no_cash_for_proper_roic`, `thin_shares_series`, `thin_core_history`). Soft warnings do not set `info_incomplete`.

## API

Django: `http://127.0.0.1:8000/`. Vite UI (usually `http://localhost:5173`) calls it.

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/companies/` | Paginated list; default order `live_check_pass` |
| GET | `/api/companies/?ids=1,2,3` | Watchlist load; returns `dilution_pass`; threshold params rescore CHECKS without dropping pinned ids |
| GET | `/api/companies/?search=<q>` | Symbol, name, ticker, sector, subsector |
| GET | `/api/companies/?ordering=div_yield` | Prefix `-` for descending |
| GET | `/api/companies/?sector=...&cap_tier=MID&qualified=true&incomplete=false` | Registry filters |
| GET | `/api/companies/?pe_max=10&pb_max=0.5&roe_min=0.2&yield_min=0.04&roic_min=0.08&de_max=2` | Screening thresholds |
| GET | `/api/companies/facets/` | Distinct sectors, subsectors, cap tiers, threshold presets |
| GET | `/api/companies/<id>/` | Detail + financials + dividends + `incomplete_reasons` |
| GET | `/api/companies/<id>/news/` | Google News RSS (PH locale), ~20 min cache; `?all=1` relaxes relevance |

Cap tiers (PHP market cap): MICRO &lt; ₱3B, SMALL &lt; ₱20B, MID &lt; ₱100B, LARGE ≥ ₱100B.

| UI field | API param | Effect |
|----------|-----------|--------|
| P/E max | `pe_max` | Checklist `P/E Ratio < {n}` |
| P/B max | `pb_max` | Checklist `P/B < {n}` |
| ROE min % (`20` → `0.2`) | `roe_min` | Checklist `ROE > {n}%` |
| Yield min % | `yield_min` | List filter; watchlist yield alerts when set |
| ROIC min % | `roic_min` | List filter |
| D/E max (default `2`) | `de_max` | Liabilities ÷ equity; N/A for banks / insurance |

Blank UI fields mean "All". Unset checklist defaults: P/E &lt; 22, P/B &lt; 1, ROE &gt; 10%, D/E &lt; 2. Negative values are rejected on Apply.

`info_incomplete` is true when latest usable year lacks revenue, net income, total assets, EPS, or book value (exact 0 counts as missing for revenue and EPS). Detail responses list those tokens in `incomplete_reasons` (also `no_financials`, `no_identity`).

```bash
curl "http://127.0.0.1:8000/api/companies/?pe_max=10&roe_min=0.15&de_max=2&ordering=-live_check_pass"
```

## UI

**Registry.** Sector / cap tier / qualified / incomplete filters, freeform thresholds, sort headers, compare checkboxes (max 4), star → watchlist (max 50). Focused row: Enter / Space opens preview, `O` opens the full report. **EXPORT CSV** pages the current applied query and downloads `pse-registry-YYYYMMDD.csv`.

**Watchlist.** Shared thresholds in `localStorage` (`pse_edge_watchlist_v2`). Apply refetches `?ids=&pe_max=…`. Alerts fire on open / Apply when dilution, D/E, yield (if yield min set), or live check count flips vs `pse_edge_watchlist_signals_v1`. Missing ids are pruned after fetch. Compare tray and **EXPORT CSV** (`pse-watchlist-YYYYMMDD.csv`) on this page. Nothing is emailed or polled in the background.

**Report.** Growth charts, balance-sheet history (book value as A−L), ratios, checklist (including no share dilution), dividends, zero-growth fair-value scenarios, data-quality panel (coverage grid + `MISSING: …`), news feed. Outstanding shares and ROIC YoY charts render only when the series has at least 3 points and ≥50% fill across the year span; latest ROIC ratio and dilution checklist stay visible regardless.

**Compare.** Overlay charts for selected tickers; shares / ROIC cards omitted unless at least one ticker passes the same density rule.

## Layout

```
Edge/
├── api/                    # Django REST (unmanaged models → SQLite)
├── django_backend/
├── frontend/               # Vite + React + Tailwind v4 + Recharts
├── data/
│   ├── companies.csv       # You provide (not in git)
│   └── pse_analysis.db     # Created by the pipeline (gitignored)
├── fixtures/
│   ├── demo/               # Sample DB for run_demo.py
│   ├── parser/             # HTML scale / NI fixtures
│   └── roic/               # PDF text fixtures
├── scripts/                # backfills, demo, fixture tests, smokes
├── src/                    # scraper, parser, PDF ROIC path, db, metrics
├── main.py
├── manage.py
├── requirements.txt
├── DISCLAIMER.md
└── README.md
```

Frontend screening math mirrors Python in `frontend/src/lib/metrics.js`. Notable `src/` modules: `filing_triage.py`, `pdf_page_router.py`, `pdf_adapters/`, `pdf_roic_extract.py`, `report_metrics.py`.

## Install

Python 3.8+ and Node.js 18+.

```bash
git clone https://github.com/SenjoNanaya/pse-dividend-analysis.git
cd pse-dividend-analysis

python -m venv venv
# Windows: venv\Scripts\activate
source venv/bin/activate
pip install -r requirements.txt

cd frontend && npm install && cd ..
```

Optional root `.env` (see [`.env.example`](.env.example)). Scraper keys:

```ini
LOG_LEVEL=INFO
LOG_FILE=logs/scraper.log
MIN_DELAY=1.5
MAX_DELAY=5.5
DB_PATH=data/pse_analysis.db
```

Local Vite talks to `http://127.0.0.1:8000` when `VITE_API_BASE` is unset. Copy [`frontend/.env.example`](frontend/.env.example) if you need to override.

## Deploy (Vercel UI + Render API)

Split hosting: static SPA on Vercel, Django + SQLite on Render. The API has no auth; treat the public URL as a personal research endpoint.

**Order:** Render first, then Vercel, then put the Vercel origin into Render `CORS_ALLOWED_ORIGINS` and redeploy the API.

### Render (API)

1. Connect the repo and apply [`render.yaml`](render.yaml) (Blueprint), or create a Python web service with the same build/start commands.
2. Persistent disk mounts at `data/` (`DB_PATH=data/pse_analysis.db`). Disk needs a paid instance (Starter+). On an ephemeral filesystem, `scripts/ensure_sqlite_db.py` re-copies the demo DB each boot.
3. Confirm env: `DJANGO_DEBUG=false`, generated `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS=.onrender.com` (or your custom host), `CORS_ALLOWED_ORIGINS` starting with `http://localhost:5173`.
4. After the service is live, note `https://<service>.onrender.com`.

First boot with an empty disk seeds [`fixtures/demo/pse_demo.db`](fixtures/demo/pse_demo.db). Warehouse models are unmanaged; do not expect `migrate` to build `companies` / `financials`.

To ship a full scrape: run `main.py` locally, then replace `data/pse_analysis.db` on the Render disk (shell upload or SFTP). Do not run the EDGE scraper on the web request path.

### Vercel (UI)

1. Import the same repo; set **Root Directory** to `frontend`.
2. Framework: Vite. Build: `npm run build`. Output: `dist`.
3. Env: `VITE_API_BASE=https://<service>.onrender.com` (no trailing slash).
4. Deploy. Then set Render `CORS_ALLOWED_ORIGINS` to `https://<your-app>.vercel.app,http://localhost:5173` and restart the API.

[`frontend/vercel.json`](frontend/vercel.json) rewrites unknown paths to `index.html`.

| Variable | Where | Role |
|----------|--------|------|
| `VITE_API_BASE` | Vercel (build-time) | API origin for `fetch` |
| `DJANGO_SECRET_KEY` | Render | Required when `DJANGO_DEBUG=false` |
| `DJANGO_ALLOWED_HOSTS` | Render | Host header allowlist |
| `CORS_ALLOWED_ORIGINS` | Render | Comma-separated UI origins |
| `DB_PATH` | Render | SQLite path on the disk |

## `data/companies.csv`

| Column | Example |
|--------|---------|
| `company_name` | Ayala Corporation |
| `ticker` | AC |
| `cmpy_id` | 57 |
| `security_id` | 180 |

Optional `sector` when present. Not shipped in git. Build from the company directory XHR at `https://edge.pse.com.ph/companyDirectory/search.ax` (browser DevTools → Network) or a one-off script against that table.

## One-command demo

No scrape and no `companies.csv`. Needs Python 3.8+ and Node.js 18+ on PATH.

```bash
python scripts/run_demo.py
```

Creates `.venv` if needed, installs deps, copies [`fixtures/demo/pse_demo.db`](fixtures/demo/pse_demo.db) to `data/pse_analysis.db` (one-time backup `pse_analysis.db.bak-before-demo` if a DB already exists), then starts Django (`:8000`) and Vite (`:5173`).

Flags: `--skip-install`, `--api-only`, `--no-browser`.

Rebuild the sample DB from a full scrape:

```bash
python scripts/export_demo_db.py
```

Sample tickers: ALI (dense / proper ROIC), **BPI** (dense bank series; click this for capital return + loan/NPL checklist), AUB/BDO (thinner banks), AB (incomplete; detail shows `incomplete_reasons`), plus AC, JFC, SM, and others.

## Scrape

Full rebuild of every CSV row:

```bash
python main.py --skip-recent 0
python manage.py runserver
cd frontend && npm run dev
```

`main.py` writes `data/pse_analysis.db`, logs incomplete field reasons on upsert, and can emit matplotlib charts under `reports/` when that path is enabled.

### Incremental rescrape

Default: skip companies with a successful `processing_log` entry in the last 24 hours. Queue order: `info_incomplete=1` first, then oldest `last_updated`, then never-scraped CSV rows.

```bash
python main.py
python main.py --dry-run --limit 20
python main.py --incomplete-only --limit 50
python main.py --tickers ALI,JFC,AB --skip-recent 0
```

No in-app scheduler. Windows Task Scheduler: daily action `python E:\path\to\Edge\main.py`, Start in = repo root. cron:

```bash
0 3 * * * cd /path/to/Edge && .venv/bin/python main.py >> logs/incremental.log 2>&1
```

## Roadmap

- Harder recovery when EDGE HTML layout changes

## LLM use

LLMs helped with: splitting an early script into ETL modules; scale-factor and error-handling patterns; report persistence and the web UI; reading EDGE XHR/HTML flow. Numbers still need checking against filings.

## Disclaimer and license

Educational and personal research only. Follow EDGE `robots.txt` and Terms of Use. Full text: [DISCLAIMER.md](DISCLAIMER.md).

MIT: [LICENSE.md](LICENSE.md).

Issues: [github.com/SenjoNanaya/pse-dividend-analysis/issues](https://github.com/SenjoNanaya/pse-dividend-analysis/issues).
