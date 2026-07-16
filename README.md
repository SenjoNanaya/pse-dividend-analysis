# PSE Edge — Scraper, Database & Analysis Dashboard

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A modular pipeline that scrapes, parses, and stores financial data from the Philippine Stock Exchange (PSE) Edge portal. Built for **educational and personal Value Investing research**, it persists company fundamentals to SQLite, serves them through a Django REST API, and presents them in a React registry dashboard (YoRHa-inspired UI) with growth metrics, ratios, dividend yield, screening checklists, and multi-ticker compare.

> **Important**: This tool is for educational research only. Please review the [Disclaimer](DISCLAIMER.md) before use.

---

## Portfolio brief

**One-liner:** Full-stack research tool that turns PSE EDGE disclosures into a screenable fundamentals database—scrape → parse → SQLite → Django REST → React dashboard.

### Problem

Philippine listed-company fundamentals for value-style screening are awkward to use: EDGE is a legacy portal (HTML disclosures, XHR endpoints), global APIs often fail on PSE tickers, and raw filings need scale-aware parsing before ratios or yields mean anything. I wanted a personal research loop: pull data carefully, store it once, then explore companies with filters, checklists, and compares—not a brokerage product.

### What I built

| Layer | Choices | Why it matters |
|-------|---------|----------------|
| **ETL** | Python `requests` + BeautifulSoup → SQLite | Owns the hard part: navigation, table cleanup, units, cash vs property dividends |
| **API** | Django REST on the same DB (unmanaged models) | Thin, queryable surface for list/detail/facets/news without re-scraping |
| **UI** | React (Vite) registry + report + compare | Interactive screening: thresholds, live CHECKS, side preview, multi-ticker matrix |
| **News** | Server-proxied Google News RSS | Lightweight context next to fundamentals; soft-fails if unavailable |

### Design decisions I’d defend in review

1. **EDGE as source of truth for PH dividends** — Yahoo-style endpoints were unreliable for tickers like `LTG.PS`; TTM yield is cash DPS over the last 12 months ÷ last price.
2. **Structural vs live screening** — checklist bits that don’t depend on user thresholds stay in the DB; P/E, P/B, ROE (and threshold-sensitive counts) rescore when filters change so the UI doesn’t lie after Apply.
3. **Polite scraping + educational disclaimer** — rate limits, research-only framing, and explicit non-affiliation with PSE.

### Hardest bugs / correctness work (good interview depth)

- Scale notes in filings (thousands / millions / billions) quietly wreck ratios if ignored.
- Dividend rows that look numeric but are property or non-cash; yield must exclude them.
- Showing a fixed “CHECKS” score while the user tightens P/E or yield thresholds—fixed by hybrid live rescoring.

### What I’d ship next (honest roadmap)

- Focused automated tests for parser yield/scale cases and threshold→checklist behavior
- One-command local demo (e.g. Compose or a scripted sample DB)
- Stronger resilience when EDGE HTML layout drifts

### Interview talk track

A rehearsable **2–3 minute** pitch plus likely questions: [`docs/INTERVIEW_TALK_TRACK.md`](docs/INTERVIEW_TALK_TRACK.md).

---

## What This Project Does

| Phase | What It Does |
|-------|--------------|
| **Extract** | Fetches stock data, dividends, annual reports, and SEC Form 17-C share disclosures from PSE Edge |
| **Transform** | Parses HTML, extracts tabular financials, applies scale factors, classifies cash vs property dividends, and resolves valuation fallbacks |
| **Load** | Persists companies, financials, and dividends to SQLite; optionally generates matplotlib reports |
| **Serve** | Exposes stored data via Django REST API and a React registry / preview / report / compare UI |

### Data Flow

```
companies.csv → PSEScraper → HTML Pages → Parser → SQLite (pse_analysis.db)
                                                          ↓
                                              Django REST API → React dashboard
                                                          ↘
                                              report_generator (optional charts)
```

The pipeline navigates PSE Edge's complex architecture:

- `search.ax` — discovers disclosures by type (Annual Report, SEC Form 17-C, etc.)
- `openDiscViewer.do` — retrieves the document viewer page
- `downloadHtml.do` — downloads the report as HTML (parsable) or PDF (future fallback)
- `dividends_and_rights_list.ax` — fetches dividend history via XHR

---

## Features

### Pipeline

- **Automated data fetching** with polite delays (`1.5–5.5` second random intervals)
- **SQLite persistence** — companies, multi-year financials, dividends, and processing logs
- **Scale-aware parsing** — detects amounts in thousands / millions / billions
- **Multi-year financial extraction** — current and prior fiscal years
- **Historical shares tracking** — SEC Form 17-C for dilution checks
- **Dividend yield** — strict trailing-12-month common **cash** DPS ÷ last price (persisted as `div_yield`)
- **Balance sheet** — total assets, total liabilities, current liabilities, cash & equivalents (from EDGE HTML and/or 17-A PDF attachments), stockholders' equity
- **ROIC** — not blocked by PDF parsing; coverage is sparse. See [ROIC: proper vs proxy](#roic-proper-vs-proxy) below.

### API & dashboard

- **REST API** — paginated list with search, ordering, and filters; detail endpoint with financials and dividends; facet endpoint for filter options
- **React registry** — sortable columns (price, market cap, yield, checks, …), sector / cap-tier / qualified / incomplete filters
- **Screening thresholds** — freeform P/E, P/B, ROE %, and yield % inputs Apply to the list and rewrite Screening Preview / report checklist labels; CHECKS / &gt;5 PASS rescore live
- **Row preview** — checklist + ratios without leaving the directory
- **Compare matrix** — select up to 4 tickers; metrics table + YoY chart overlays
- **Fundamental report** — growth charts, liabilities / balance-sheet history for BV derivation (A−L), ratios, checklist, dividend history, fair-value scenarios, ticker news feed
- **Ticker news** — server-proxied Google News RSS (PH locale); short tickers get stricter queries + relevance filter; Google redirect URLs unwrapped to publishers when possible; `?all=1` shows less-relevant hits
- **Accessibility pass** — focus outlines, reduced-motion, labeled controls, keyboard registry rows and compare tabs

### Analysis metrics

- YoY growth and 3-year CAGR
- P/E, P/B, ROE, ROIC (proper when cash+CL+NOPAT inputs exist; else NI proxy), TTM dividend yield, dividend cover
- Fundamental checklist (pass / fail / N/A)
- DCF-style zero-growth fair value scenarios
- Optional matplotlib bar charts via the CLI pipeline

### ROIC: proper vs proxy

| Mode | Numerator | Invested capital | When used |
|------|-----------|------------------|-----------|
| **Proper** | NOPAT = operating income (or GP−GA) × (1−t) | Assets − Cash − Current liabilities | Cash + CL present on ≥1 year |
| **Proxy** | Net income | Assets − CL (else Assets) | Fallback when proper inputs missing |
| **N/A** | — | — | Banks / insurance |

**PDF is a fill-nulls helper, not a requirement.** EDGE HTML pulls cash & CL when those line items appear in disclosure tables (expanded synonyms such as “cash on hand and in banks”; year-header junk like `cash=2024` is dropped). Ranked 17-A/AFS PDFs overlay the closed whitelist (`cash`, `CL`, op income / GP / GA, tax, IBT) only onto existing fiscal years and only when HTML left the field null. Page routing requires statement titles plus tabular peso density so PFRS/MD&A prose does not invent fake FS pages.

**Image-only AFS:** when a ranked attachment has almost no text layer, the extractor OCRs up to the first ~40 pages via PyMuPDF + Tesseract tessdata, then reuses the same router/adapters. Soft-skips (no crash) if tessdata is missing — set `TESSDATA_PREFIX` or install Tesseract language data. Integrated / ESG filenames are never OCR’d.

| Goal | Status |
|------|--------|
| Proxy ROIC | Available widely from HTML assets / NI / CL |
| Proper ROIC (HTML cash or text-layer FS PDF) | Works when cash + CL + op/GP−GA land |
| Proper ROIC on image-only AFS | Works when Tesseract tessdata is available; otherwise soft-skip |

Cash capture uses expanded BS synonyms plus a cash-flow **ending balance** fallback when the BS cash line is missing. Ranked AFS/17-A PDFs can OCR sparse packs and pull ending cash from CF pages as a fill-nulls source.

Cash-null backfill (re-fetch HTML+PDFs or cached PDFs only; never overwrites non-nulls):

```bash
python scripts/backfill_cash_for_roic.py --dry-run --limit 20
python scripts/backfill_cash_for_roic.py --limit 50
python scripts/backfill_cash_for_roic.py --cached-pdfs-only --limit 50
```

Sanity audit after rescrape: `python scripts/sanity_check_rescrape.py`. ROIC PDF smoke tests: `python scripts/test_roic_pipeline.py`.

---

## Project Structure

```
Edge/
├── api/                        # Django REST app (unmanaged models → SQLite)
│   ├── filters.py              # sector, cap_tier, thresholds, qualified, …
│   ├── screening.py            # live CHECKS rescore helpers
│   ├── news.py                 # Google News RSS proxy for tickers
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   └── urls.py
├── django_backend/             # Django project settings
├── frontend/                   # Vite + React (Tailwind v4)
│   └── src/
│       ├── App.jsx
│       ├── components/         # report, preview, compare, NierSelect, …
│       └── lib/metrics.js      # shared screening / yield math (JS)
├── data/
│   ├── companies.csv           # Master company list (you provide)
│   └── pse_analysis.db         # Created by the pipeline (gitignored)
├── logs/                       # scraper.log (gitignored)
├── reports/                    # optional matplotlib output (gitignored)
├── scripts/
│   ├── backfill_div_yield.py       # recompute persisted div_yield
│   ├── backfill_struct_checks.py   # structural checklist bits for live CHECKS
│   ├── backfill_stockholders_equity.py  # equity from A − L when missing
├── fixtures/roic/              # small text fixtures for ROIC PDF smoke tests
├── src/
│   ├── scraper.py
│   ├── parser.py
│   ├── filing_triage.py        # attachment rank / skip heuristics
│   ├── pdf_page_router.py      # Financial Position / Income page finder
│   ├── pdf_adapters/           # sequential, notes-column, scaled multi-column
│   ├── pdf_roic_extract.py     # whitelist ROIC fields from PDFs
│   ├── db.py
│   ├── report_metrics.py       # screening / TTM yield (Python)
│   ├── report_generator.py
│   └── utils.py
├── main.py
├── manage.py
├── requirements.txt
├── DISCLAIMER.md
└── README.md
```

---

## Installation

### Prerequisites

- Python 3.8+
- Node.js 18+ (for the frontend)

### 1. Clone the repository

```bash
git clone https://github.com/SenjoNanaya/pse-dividend-analysis.git
cd pse-dividend-analysis
```

### 2. Python environment

```bash
python -m venv venv
source venv/bin/activate      # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Frontend dependencies

```bash
cd frontend
npm install
cd ..
```

### 4. Environment variables (optional)

Create a `.env` file in the project root:

```ini
LOG_LEVEL=INFO
LOG_FILE=logs/scraper.log
MIN_DELAY=1.5
MAX_DELAY=5.5
DB_PATH=data/pse_analysis.db
```

---

## Preparing `companies.csv`

The pipeline requires a CSV file at `data/companies.csv` with at least these columns:

| Column | Description | Example |
|--------|-------------|---------|
| `company_name` | Full company name | Ayala Corporation |
| `ticker` | Stock ticker symbol | AC |
| `cmpy_id` | Internal PSE company ID | 57 |
| `security_id` | Internal PSE security ID | 180 |

An optional `sector` column is used when present.

**Where to get this data?**  
Scrape the PSE company directory via the XHR endpoint  
`https://edge.pse.com.ph/companyDirectory/search.ax` (browser DevTools → Network), or generate it with a one-off script against that table.

We **do not** ship `companies.csv` in the repository. Place your file under `data/` before running the pipeline.

---

## Usage

Run these in separate terminals after `companies.csv` is in place.

### 1. Scrape and populate the database

```bash
python main.py
```

Loops every row in `companies.csv`, scrapes PSE Edge, and writes to `data/pse_analysis.db`. Incomplete companies are skipped and logged in `processing_log`. Optional matplotlib reports land in `reports/`.

To refresh persisted yields after dividend/parser fixes:

```bash
python scripts/backfill_div_yield.py
```

### 2. Start the Django API

```bash
python manage.py runserver
```

API base: `http://127.0.0.1:8000/`

| Endpoint | Description |
|----------|-------------|
| `GET /api/companies/` | Paginated list (default ordering: live checklist pass count) |
| `GET /api/companies/?search=<q>` | Search symbol, name, ticker, sector, subsector |
| `GET /api/companies/?ordering=div_yield` | Sort (prefix `-` for descending); checks use `live_check_pass` |
| `GET /api/companies/?sector=...&cap_tier=MID&qualified=true&incomplete=false` | Registry filters |
| `GET /api/companies/?pe_max=10&pb_max=0.5&roe_min=0.2&yield_min=0.04` | Screening thresholds |
| `GET /api/companies/facets/` | Distinct sectors / subsectors / cap tier / threshold presets |
| `GET /api/companies/<id>/` | Detail with financials and dividends |
| `GET /api/companies/<id>/news/` | Recent headlines (Google News RSS proxy, cached ~20 min) |

**Cap tiers** (by market cap, PHP): MICRO &lt; ₱3B · SMALL &lt; ₱20B · MID &lt; ₱100B · LARGE ≥ ₱100B.

**Screening thresholds** (freeform numbers in the UI filter bar; Apply to commit):

| UI field | API param | Checklist |
|----------|-----------|-----------|
| P/E max (e.g. `10`) | `pe_max` | `P/E Ratio < {n}` |
| P/B max (e.g. `0.5`) | `pb_max` | `P/B < {n}` |
| ROE min **%** (e.g. `20` → `0.2`) | `roe_min` (fraction) | `ROE > {n}%` |
| Yield min **%** (e.g. `4` → `0.04`) | `yield_min` (fraction) | List filter only |

Leave a field blank for “All” — checklist still uses classic defaults (P/E &lt; 22, P/B &lt; 1, ROE &gt; 10%). Invalid or negative values are rejected on Apply.

**CHECKS / &gt;5 PASS** on the registry list are rescored live: persisted structural checks (growth, dilution, liquidity) plus PE/P/B/ROE evaluated against the request thresholds. After a scrape or schema change, run:

```bash
python scripts/backfill_struct_checks.py
```

ROIC PDF triage / adapter smoke tests (fixtures under `fixtures/roic/`):

```bash
python scripts/test_roic_pipeline.py
```

Example:

```bash
curl "http://127.0.0.1:8000/api/companies/?pe_max=10&roe_min=0.15&ordering=-live_check_pass"
```

### 3. Start the React frontend

```bash
cd frontend
npm run dev
```

Open the URL from Vite (typically `http://localhost:5173`). Keep Django running — the UI calls `http://127.0.0.1:8000/api/companies/`.

**Registry keyboard shortcuts (focused row):** Enter / Space = preview · `O` = open full report · checkbox = add to compare (max 4).

---

## Expected Output

### Database

| Table | Contents |
|-------|----------|
| `companies` | Symbol, name, sector, price, market cap, `div_yield`, checklist scores, incompleteness flags |
| `financials` | Per-year revenue, net income, EPS, book value, assets, liabilities, outstanding shares |
| `dividends` | Ex-date, payment date, amount, type (`cash` / `property` / …) |
| `processing_log` | Per-company run status and errors |

### Web dashboard

- Landing → central registry with filters, sort, pagination, and side preview
- Full company report (growth, ratios, checklist, dividends, fair value)
- Compare matrix (metrics + shared YoY charts)

### Optional CLI reports

When enabled in `main.py`, `report_generator.py` writes matplotlib charts to `reports/`.

---

## Data Sources

| Source | Data Retrieved |
|--------|----------------|
| `stockData.do` | Last price, market cap, outstanding shares |
| `dividends_and_rights_list.ax` | Dividend history (ex-date, rate, type) |
| `search.ax` (Annual Report) | SEC Form 17-A disclosures |
| `search.ax` (Shares) | SEC Form 17-C share-count changes |
| `openDiscViewer.do` → `downloadHtml.do` | HTML financial reports |

Yahoo Finance and similar global APIs are **not** reliable for PSE tickers; EDGE remains the primary source for PH dividend history.

---

## Technical Challenges Overcome

| Challenge | Solution |
|-----------|----------|
| **XHR-based navigation** | Discovered and used `search.ax` and `dividends_and_rights_list.ax` |
| **Scale factor detection** | Parsed currency/unit notes; applied multipliers to absolute metrics |
| **Multiple years extraction** | Cleaned/merged tables; deduplicated by fiscal year |
| **Missing stock-page ratios** | Filled P/E, P/B, price, ROE from filings when the quote page is thin |
| **Dividend mis-parses** | Prefer `Php…` amounts; classify property vs cash; TTM yield ignores non-cash |
| **Liabilities vs A=L+E total** | Exclude “liabilities and equity” captions; reconcile missing A/L/E; backfill equity from A−L |
| **17-A PDF layouts** | Triage attachments; substance-gated page router; thin adapters into a closed ROIC whitelist; **fill-nulls only** onto HTML years; **OCR** (Tesseract tessdata) only for sparse/image-only ranked AFS packs |
| **Rate limiting** | Random delays (`1.5–5.5s`) |

---

## LLM Acknowledgments

This project was developed with the assistance of **Large Language Models** for:

- Refactoring the initial script into a modular ETL pipeline
- Designing error-handling patterns and scale-factor logic
- Structuring report generation, persistence, and the web dashboard
- Understanding and navigating PSE Edge's legacy architecture

LLMs served as pair-programming assistants to accelerate learning and implementation.

---

## Disclaimer

This project is for **educational and personal research** purposes only. Users are responsible for complying with the `robots.txt` and Terms of Use of PSE Edge and any other websites accessed through this tool.

For full details, please read the [DISCLAIMER.md](DISCLAIMER.md).

---

## License

This project is licensed under the MIT License. See [LICENSE.md](LICENSE.md) for details.

---

## Acknowledgements

- **Philippine Stock Exchange (PSE)** for public access to financial data
- The open-source community for `requests`, `BeautifulSoup`, `pandas`, `matplotlib`, Django, React, and Recharts
- The LLM providers that assisted with architecture and debugging

---

## Contact

Questions, suggestions, or concerns? Please [open an issue](https://github.com/SenjoNanaya/pse-dividend-analysis/issues) on GitHub.
