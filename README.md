# PSE Edge — Scraper, Database & Analysis Dashboard

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A modular pipeline that scrapes, parses, and stores financial data from the Philippine Stock Exchange (PSE) Edge portal. Built for **educational and personal Value Investing research**, it persists company fundamentals to SQLite, serves them through a Django REST API, and presents them in a React dashboard with growth metrics, ratios, and fundamental checklists.

> **Important**: This tool is for educational research only. Please review the [Disclaimer](DISCLAIMER.md) before use.

---

## What This Project Does

| Phase | What It Does |
|-------|--------------|
| **Extract** | Fetches stock data, dividends, annual reports, and SEC Form 17-C share disclosures from PSE Edge |
| **Transform** | Parses HTML, extracts tabular financial data, detects and applies scale factors (thousands/millions/billions), and resolves valuation fallbacks |
| **Load** | Persists companies, financials, and dividends to SQLite; optionally generates matplotlib reports |
| **Serve** | Exposes stored data via Django REST API and a React registry/report UI |

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

- **Automated data fetching** with polite delays (`1.5–5.5` second random intervals)
- **SQLite persistence** — companies, multi-year financials, dividends, and processing logs
- **Scale-aware parsing** — detects if amounts are in thousands, millions, or billions
- **Multi-year financial extraction** — captures current year, previous year, and beyond
- **Historical shares tracking** — parses SEC Form 17-C to detect shareholder dilution
- **REST API** — paginated company list with search; detail endpoint with financials and dividends
- **React dashboard** — company registry, search, pagination, and fundamental report views
- **Comprehensive analysis** (CLI reports and web UI):
  - YoY growth rates and 3-year CAGR
  - P/E, P/B, ROE, Dividend Yield, Dividend Cover
  - Fundamental checklist (pass/fail)
  - DCF valuation (zero-growth scenario)
- **Optional visualization** — bar charts of YoY growth rates via `matplotlib`
- **Modular architecture** — `scraper.py`, `parser.py`, `db.py`, `report_generator.py`, `utils.py`, `main.py`

---

## Project Structure

```
Edge/
├── api/                        # Django REST app (unmanaged models → SQLite tables)
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   └── urls.py
├── django_backend/             # Django project settings and URL routing
├── frontend/                   # Vite + React dashboard
│   └── src/
│       ├── App.jsx
│       ├── components/
│       └── lib/metrics.js
├── data/
│   ├── companies.csv           # Master company list (you provide this)
│   └── pse_analysis.db         # Created by the pipeline (gitignored)
├── logs/
│   └── scraper.log             # Pipeline execution logs (gitignored)
├── reports/                    # Optional matplotlib chart output (gitignored)
├── src/
│   ├── scraper.py              # Extract: HTTP requests, session management
│   ├── parser.py               # Transform: HTML parsing, data cleaning, scaling
│   ├── db.py                   # SQLite schema, inserts, processing logs
│   ├── report_generator.py     # Optional CLI reports and charts
│   └── utils.py                # Logging, delays, headers, env config
├── main.py                     # Scrape-and-persist pipeline (loops all companies)
├── manage.py                   # Django management entry point
├── requirements.txt            # Python dependencies
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
You can obtain it by scraping the PSE company directory. A simple way is to use the XHR endpoint:  
`https://edge.pse.com.ph/companyDirectory/search.ax` — fetch this from your browser's Developer Tools and parse the HTML table.

We **do not** include `companies.csv` in the repository. To generate your own, you can run a one-time script like:

```python
# generate_companies.py
import requests
from bs4 import BeautifulSoup
import csv

response = requests.get('https://edge.pse.com.ph/companyDirectory/search.ax')
soup = BeautifulSoup(response.text, 'lxml')
rows = soup.find_all('tr')

with open('data/companies.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['company_name', 'ticker', 'cmpy_id', 'security_id'])
    for row in rows:
        links = row.find_all('a')
        if len(links) >= 2:
            company_name = links[0].get_text(strip=True)
            ticker = links[1].get_text(strip=True)
            onclick = links[0].get('onclick', '')
            if 'cmDetail' in onclick:
                parts = onclick.split("'")
                if len(parts) >= 4:
                    cmpy_id = parts[1]
                    security_id = parts[3]
                    writer.writerow([company_name, ticker, cmpy_id, security_id])
```

Place the resulting `companies.csv` in the `data/` folder before running the pipeline.

---

## Usage

Run the three parts in separate terminals after `companies.csv` is in place.

### 1. Scrape and populate the database

```bash
python main.py
```

This loops over every row in `companies.csv`, scrapes PSE Edge, and writes results to `data/pse_analysis.db`. Companies without financial data are skipped and logged in `processing_log`. Optional matplotlib reports are saved to `reports/`.

### 2. Start the Django API

```bash
python manage.py runserver
```

The API runs at `http://127.0.0.1:8000/`.

| Endpoint | Description |
|----------|-------------|
| `GET /api/companies/` | Paginated company list (10 per page) |
| `GET /api/companies/?search=<query>` | Search by symbol, name, or ticker |
| `GET /api/companies/<id>/` | Company detail with financials and dividends |

Example:

```bash
curl http://127.0.0.1:8000/api/companies/?search=BPI
```

### 3. Start the React frontend

```bash
cd frontend
npm run dev
```

Open the URL shown in the terminal (typically `http://localhost:5173`). The dashboard fetches from `http://127.0.0.1:8000/api/companies/` — keep the Django server running.

---

## Expected Output

### Database

After a successful pipeline run, SQLite contains:

| Table | Contents |
|-------|----------|
| `companies` | Symbol, name, sector, market snapshot (price, P/E, P/B, ROE, etc.) |
| `financials` | Per-year revenue, net income, EPS, book value, assets, liabilities |
| `dividends` | Ex-date, payment date, amount, type |
| `processing_log` | Per-company run status and error messages |

### Web dashboard

The React UI provides:

- A searchable company registry with pagination
- Per-company fundamental reports: growth overview, ratios, checklist, valuation, and charts

### Optional CLI reports

When enabled in `main.py`, `report_generator.py` also writes matplotlib bar charts to `reports/` and can print analysis to the console.

---

## Data Sources

| Source | Data Retrieved |
|--------|----------------|
| `stockData.do` | Last price, market cap, outstanding shares |
| `dividends_and_rights_list.ax` | Dividend history (ex-date, rate, etc.) |
| `search.ax` (Annual Report) | Disclosure list → Annual Reports (SEC Form 17-A) |
| `search.ax` (Shares) | Disclosure list → SEC Form 17-C (share count changes) |
| `openDiscViewer.do` → `downloadHtml.do` | HTML version of financial reports |

---

## Technical Challenges Overcome

| Challenge | Solution |
|-----------|----------|
| **XHR-based navigation** | Discovered and used `search.ax` and `dividends_and_rights_list.ax` endpoints |
| **Scale factor detection** | Parsed "Currency(and units)" notes in reports; applied multiplier to absolute metrics |
| **Multiple years extraction** | Cleaned and merged tables, deduplicated by fiscal year |
| **Missing stock-page ratios** | Filled P/E, P/B, price, and ROE from disclosure filing prices and financial ratios |
| **Edge-case handling** | Gracefully handles missing data, negative values, and incomplete years |
| **Rate limiting** | Built-in random delays (`1.5–5.5s`) to avoid overloading servers |

---

## LLM Acknowledgments

This project was developed with the assistance of **Large Language Models** (primarily Claude Sonnet, DeepSeek V4, and Gemini Flash 3.5) for:

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

- **Philippine Stock Exchange (PSE)** for providing public access to financial data
- The open-source community for `requests`, `BeautifulSoup`, `pandas`, `matplotlib`, Django, and React
- The LLM providers that assisted with architecture and debugging

---

## Contact

Questions, suggestions, or concerns? Please [open an issue](https://github.com/SenjoNanaya/pse-dividend-analysis/issues) on GitHub.

---