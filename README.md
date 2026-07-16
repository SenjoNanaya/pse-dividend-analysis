# PSE Edge scraper, database, and screening UI

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Python ETL from the Philippine Stock Exchange EDGE portal into SQLite, a Django REST API on that same database, and a React (Vite) registry for filters, checklists, and multi-ticker compare. Personal / educational research only. Read [DISCLAIMER.md](DISCLAIMER.md) before use.

Scrapes EDGE HTML and ranked 17-A/AFS PDFs, parses scale notes and cash vs property dividends, then serves fundamentals without calling Yahoo-style quote APIs for PH dividend history (those break on tickers such as `LTG.PS`).

For a short oral walkthrough and likely questions, see [`docs/INTERVIEW_TALK_TRACK.md`](docs/INTERVIEW_TALK_TRACK.md).

## Pipeline

```
companies.csv → PSEScraper → HTML / PDF → Parser → SQLite (pse_analysis.db)
                                                      ↓
                                          Django REST API → React UI
                                                      ↘
                                          report_generator (optional charts)
```

EDGE endpoints the scraper uses:

| Endpoint | Role |
|----------|------|
| `search.ax` | Find disclosures by type (Annual Report, SEC Form 17-C, …) |
| `openDiscViewer.do` | Document viewer page |
| `downloadHtml.do` | HTML report body (PDF attachments handled separately) |
| `dividends_and_rights_list.ax` | Dividend history (XHR) |
| `stockData.do` | Last price, market cap, outstanding shares |

Requests wait a random 1.5 to 5.5 seconds between calls (`MIN_DELAY` / `MAX_DELAY`).

### What lands in SQLite

- Companies: symbol, name, sector, price, market cap, `div_yield`, screening fields, incompleteness flags
- Financials by fiscal year: revenue, net income, EPS, book value, assets, liabilities, cash, equity, shares
- Dividends with type (`cash` / `property` / …); TTM yield is common cash DPS over the last 12 months ÷ last price
- `processing_log` per company run

### Correctness rules that bit us in practice

Filings state amounts in thousands, millions, or billions; ignore the note and every ratio is wrong. Dividend rows can look numeric but be property or non-cash; yield ignores those. Structural checklist bits (growth, dilution, liquidity, debt/equity when applicable) stay in the DB; P/E, P/B, ROE, and pass counts that depend on the user's thresholds rescore on each API request so Apply cannot leave a stale CHECKS column.

Liabilities captions that mean "liabilities and equity" are excluded. Missing equity can be backfilled as assets − liabilities. Ranked 17-A/AFS PDFs fill null whitelist fields only onto fiscal years that already exist from HTML; they do not invent years. Banks and insurance use NI ÷ average equity (labeled as capital return in the UI), not industrial ROIC.

## ROIC modes

| Mode | Numerator | Invested capital | When |
|------|-----------|------------------|------|
| Proper | NOPAT = operating income (or GP−GA) × (1−t) | Assets − cash − current liabilities | Cash + CL on at least one year |
| Proxy | Net income | Assets − CL (else assets) | Proper inputs missing |
| Equity | Net income | Average stockholders' equity | Banks / insurance |

PDF overlay is fill-nulls only: cash, CL, operating income / GP / GA, tax, IBT, and related whitelist fields when HTML left them null. Page routing needs statement titles plus tabular peso density so PFRS/MD&A prose is not treated as FS pages. Image-only AFS: OCR up to the first ~40 pages (PyMuPDF + Tesseract tessdata); soft-skip if tessdata is missing (`TESSDATA_PREFIX`). Integrated / ESG filenames are never OCR'd.

Cash-null backfill (never overwrites non-nulls):

```bash
python scripts/backfill_cash_for_roic.py --dry-run --limit 20
python scripts/backfill_cash_for_roic.py --limit 50
python scripts/backfill_cash_for_roic.py --cached-pdfs-only --limit 50
```

Sanity audit: `python scripts/sanity_check_rescrape.py`. ROIC PDF smoke tests: `python scripts/test_roic_pipeline.py`.

## API and UI

Django serves `http://127.0.0.1:8000/`. Vite serves the registry (usually `http://localhost:5173`) and calls that API.

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/companies/` | Paginated list; default order is live checklist pass count |
| GET | `/api/companies/?search=<q>` | Symbol, name, ticker, sector, subsector |
| GET | `/api/companies/?ordering=div_yield` | Prefix `-` for descending; checks sort key is `live_check_pass` |
| GET | `/api/companies/?sector=...&cap_tier=MID&qualified=true&incomplete=false` | Registry filters |
| GET | `/api/companies/?pe_max=10&pb_max=0.5&roe_min=0.2&yield_min=0.04&roic_min=0.08&de_max=2` | Screening thresholds |
| GET | `/api/companies/facets/` | Distinct sectors, subsectors, cap tiers, threshold presets |
| GET | `/api/companies/<id>/` | Detail with financials and dividends |
| GET | `/api/companies/<id>/news/` | Google News RSS proxy (PH locale), cached ~20 min; `?all=1` relaxes relevance |

Cap tiers by market cap (PHP): MICRO &lt; ₱3B, SMALL &lt; ₱20B, MID &lt; ₱100B, LARGE ≥ ₱100B.

| UI field | API param | Checklist / filter |
|----------|-----------|--------------------|
| P/E max | `pe_max` | `P/E Ratio < {n}` |
| P/B max | `pb_max` | `P/B < {n}` |
| ROE min % (e.g. `20` → `0.2`) | `roe_min` | `ROE > {n}%` |
| Yield min % | `yield_min` | List filter only |
| ROIC min % | `roic_min` | List filter only |
| D/E max (default `2`) | `de_max` | Liabilities ÷ equity; N/A for banks / insurance |

Blank UI fields mean "All". Checklist defaults when thresholds are unset: P/E &lt; 22, P/B &lt; 1, ROE &gt; 10%, D/E &lt; 2. Invalid or negative values are rejected on Apply.

Registry (focused row): Enter / Space opens preview, `O` opens the full report, checkbox adds to compare (max 4). Reports include growth charts, balance-sheet history for book value (A−L), ratios, checklist, dividends, zero-growth fair-value scenarios, and the news feed.

After scrape or schema changes that touch structural checks:

```bash
python scripts/backfill_struct_checks.py
python scripts/backfill_div_yield.py
python scripts/backfill_roic.py
```

Example list query:

```bash
curl "http://127.0.0.1:8000/api/companies/?pe_max=10&roe_min=0.15&de_max=2&ordering=-live_check_pass"
```

## Layout

```
Edge/
├── api/                    # Django REST (unmanaged models → SQLite)
├── django_backend/
├── frontend/               # Vite + React + Tailwind v4 + Recharts
├── data/
│   ├── companies.csv       # You provide (not in git)
│   └── pse_analysis.db     # Created by the pipeline (gitignored)
├── scripts/                # backfills, ROIC / cash / sanity tests
├── fixtures/roic/
├── src/                    # scraper, parser, PDF ROIC path, db, metrics
├── main.py
├── manage.py
├── requirements.txt
├── DISCLAIMER.md
└── README.md
```

Notable modules under `src/`: `filing_triage.py`, `pdf_page_router.py`, `pdf_adapters/`, `pdf_roic_extract.py`, `report_metrics.py`. Frontend screening math mirrors Python in `frontend/src/lib/metrics.js`.

## Install

Needs Python 3.8+ and Node.js 18+.

```bash
git clone https://github.com/SenjoNanaya/pse-dividend-analysis.git
cd pse-dividend-analysis

python -m venv venv
# Windows: venv\Scripts\activate
source venv/bin/activate
pip install -r requirements.txt

cd frontend && npm install && cd ..
```

Optional `.env` in the project root:

```ini
LOG_LEVEL=INFO
LOG_FILE=logs/scraper.log
MIN_DELAY=1.5
MAX_DELAY=5.5
DB_PATH=data/pse_analysis.db
```

## `data/companies.csv`

Required columns:

| Column | Example |
|--------|---------|
| `company_name` | Ayala Corporation |
| `ticker` | AC |
| `cmpy_id` | 57 |
| `security_id` | 180 |

Optional `sector` is used when present. The file is not shipped in the repo. Build it from the company directory XHR at `https://edge.pse.com.ph/companyDirectory/search.ax` (browser DevTools → Network) or a one-off script against that table.

## Run locally

Three processes after `companies.csv` exists:

```bash
python main.py
python manage.py runserver
cd frontend && npm run dev
```

`main.py` walks every CSV row, writes `data/pse_analysis.db`, skips incomplete companies into `processing_log`, and can emit matplotlib charts under `reports/` when enabled in that script.

## Roadmap (not done yet)

- Automated tests focused on yield/scale parser cases and threshold → checklist rescoring
- One-command local demo (Compose or a scripted sample DB)
- Harder recovery when EDGE HTML layout changes

## LLM use

LLMs were used as pair-programming help for: splitting an early script into the ETL modules; scale-factor and error-handling patterns; report persistence and the web UI; reading EDGE's XHR/HTML flow. You still need to verify numbers against filings.

## Disclaimer and license

Educational and personal research only. You must follow EDGE `robots.txt` and Terms of Use. Full text: [DISCLAIMER.md](DISCLAIMER.md).

MIT License: [LICENSE.md](LICENSE.md).

Issues: [github.com/SenjoNanaya/pse-dividend-analysis/issues](https://github.com/SenjoNanaya/pse-dividend-analysis/issues).
