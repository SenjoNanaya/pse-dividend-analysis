# PSE Edge — Scraper, Database & Analysis Dashboard

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A modular pipeline that scrapes, parses, and stores financial data from the Philippine Stock Exchange (PSE) Edge portal. Built for **educational and personal Value Investing research**, it persists company fundamentals to SQLite, serves them through a Django REST API, and presents them in a React registry dashboard (YoRHa-inspired UI) with growth metrics, ratios, dividend yield, screening checklists, and multi-ticker compare.

> **Important**: This tool is for educational research only. Please review the [Disclaimer](DISCLAIMER.md) before use.

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

### API & dashboard

- **REST API** — paginated list with search, ordering, and filters; detail endpoint with financials and dividends; facet endpoint for filter options
- **React registry** — sortable columns (price, market cap, yield, checks, …), sector / cap-tier / qualified / incomplete filters
- **Row preview** — checklist + ratios without leaving the directory
- **Compare matrix** — select up to 4 tickers; metrics table + YoY chart overlays
- **Fundamental report** — growth charts, ratios, checklist, dividend history, simple fair-value scenarios
- **Accessibility pass** — focus outlines, reduced-motion, labeled controls, keyboard registry rows and compare tabs

### Analysis metrics

- YoY growth and 3-year CAGR
- P/E, P/B, ROE, TTM dividend yield, dividend cover
- Fundamental checklist (pass / fail / N/A)
- DCF-style zero-growth fair value scenarios
- Optional matplotlib bar charts via the CLI pipeline

---

## Project Structure

```
Edge/
├── api/                        # Django REST app (unmanaged models → SQLite)
│   ├── filters.py              # sector, cap_tier, qualified, incomplete
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
│   └── backfill_div_yield.py   # recompute persisted div_yield
├── src/
│   ├── scraper.py
│   ├── parser.py
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
| `GET /api/companies/` | Paginated list (default ordering: checklist pass count) |
| `GET /api/companies/?search=<q>` | Search symbol, name, ticker, sector, subsector |
| `GET /api/companies/?ordering=div_yield` | Sort (prefix `-` for descending) |
| `GET /api/companies/?sector=...&cap_tier=MID&qualified=true&incomplete=false` | Filters |
| `GET /api/companies/facets/` | Distinct sectors / subsectors / cap tier labels |
| `GET /api/companies/<id>/` | Detail with financials and dividends |

**Cap tiers** (by market cap, PHP): MICRO &lt; ₱3B · SMALL &lt; ₱20B · MID &lt; ₱100B · LARGE ≥ ₱100B.

Example:

```bash
curl "http://127.0.0.1:8000/api/companies/?search=LTG&ordering=-div_yield"
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
