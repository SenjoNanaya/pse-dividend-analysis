# PSE Edge ETL Pipeline — Philippine Stock Exchange Data Scraper & Analyzer

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A modular ETL (Extract, Transform, Load) pipeline that scrapes, parses, and analyzes financial data from the Philippine Stock Exchange (PSE) Edge portal. Built for **educational and personal Value Investing research**, this tool extracts company fundamentals, stock data, dividends, and historical disclosures—then generates comprehensive investment reports with growth metrics, ratios, and visualizations.

> 📌 **Important**: This tool is for educational research only. Please review the [Disclaimer](DISCLAIMER.md) before use.

---

## 📊 What This Pipeline Does

| Phase | What It Does |
|-------|--------------|
| **Extract** | Fetches stock data, dividends, annual reports, and SEC Form 17‑C share disclosures from PSE Edge |
| **Transform** | Parses HTML, extracts tabular financial data, detects and applies scale factors (thousands/millions/billions), and calculates growth rates |
| **Load** | Generates a comprehensive investment report with growth overview, ratios, fundamental checklist, and valuation scenarios (plus a matplotlib bar chart) |

### Data Flow

```
companies.csv → PSEScraper → HTML Pages → Parser → Clean Data → Report Generation → Console Output + Chart
```

The pipeline navigates PSE Edge's complex architecture:
- `search.ax` → discovers disclosures by type (Annual Report, SEC Form 17‑C, etc.)
- `openDiscViewer.do` → retrieves the document viewer page
- `downloadHtml.do` → downloads the report as HTML (parsable) or PDF (future fallback)
- `dividends_and_rights_list.ax` → fetches dividend history via XHR

---

## 🛠️ Features

- **Automated data fetching** with polite delays (`1.5–5.5` second random intervals)
- **Scale‑aware parsing** — detects if amounts are in thousands, millions, or billions
- **Multi‑year financial extraction** — captures current year, previous year, and beyond
- **Historical shares tracking** — parses SEC Form 17‑C to detect shareholder dilution
- **Comprehensive analysis**:
  - YoY growth rates & 3‑year CAGR
  - P/E, P/B, ROE, Dividend Yield, Dividend Cover
  - Fundamental checklist (✓/✗)
  - DCF valuation (zero‑growth scenario)
- **Visualization** — bar chart of YoY growth rates using `matplotlib`
- **Modular architecture** — `scraper.py`, `parser.py`, `database.py`, `utils.py`, `main.py`

---

## 🏗️ Project Structure

```
pse-research-project/
├── data/
│   └── companies.csv          # Master company list (you provide this)
├── logs/
│   └── scraper.log            # Pipeline execution logs
├── src/
│   ├── __init__.py
│   ├── scraper.py             # Extract: HTTP requests, session management
│   ├── parser.py              # Transform: HTML parsing, data cleaning, scaling
│   ├── database.py            # Load & Analyze: report generation, growth calc, charts
│   └── utils.py               # Helpers: logging, delays, headers, scale parsing
├── .env                       # Environment variables (optional)
├── .gitignore
├── main.py                    # Orchestrates the full ETL pipeline
├── requirements.txt           # Python dependencies
├── DISCLAIMER.md              # Legal & ethical usage terms
└── README.md                  # This file
```

---

## 🔧 Installation

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/pse-research-project.git
cd pse-research-project
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate      # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables (optional)

Create a `.env` file in the project root (adjust as needed):

```ini
LOG_LEVEL=INFO
MIN_DELAY=1.5
MAX_DELAY=5.5
```

---

## 📋 Preparing `companies.csv`

The pipeline requires a CSV file with the following columns:

| Column          | Description                              | Example          |
|-----------------|------------------------------------------|------------------|
| `company_name`  | Full company name                        | Ayala Corporation |
| `ticker`        | Stock ticker symbol                      | AC               |
| `cmpy_id`       | Internal PSE company ID                  | 57               |
| `security_id`   | Internal PSE security ID                 | 180              |

**Where to get this data?**  
You can obtain it by scraping the PSE company directory. A simple way is to use the XHR endpoint we discovered:  
`https://edge.pse.com.ph/companyDirectory/search.ax` – you can fetch this from your browser's Developer Tools and parse the HTML table.

We **do not** include our own `companies.csv` in the repository. To generate your own, you can run a one‑time script like:

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
            # Extract company name and ticker
            company_name = links[0].get_text(strip=True)
            ticker = links[1].get_text(strip=True)
            # Extract cmpy_id and security_id from onclick
            onclick = links[0].get('onclick', '')
            if 'cmDetail' in onclick:
                parts = onclick.split("'")
                if len(parts) >= 4:
                    cmpy_id = parts[1]
                    security_id = parts[3]
                    writer.writerow([company_name, ticker, cmpy_id, security_id])
```

Place the resulting `companies.csv` in the `data/` folder before running the main pipeline.

---

## 🚀 Usage

### Run the pipeline for a single company

```bash
python main.py
```

By default, `main.py` processes the company at `row_index=45` (Bank of the Philippine Islands). To change which company is processed, modify the `row_index` in `main.py`:

```python
run_pipeline(row_index=45)   # Change 45 to any row index in companies.csv
```

### Expected output

The script will:

1. Print a comprehensive **investment report** to the console:
   - Growth overview
   - Ratios
   - Fundamental checklist
   - DCF valuation

2. Display a **bar chart** showing YoY growth rates for:
   - Book Value
   - Net Income
   - Total Assets
   - Revenue

### Example output (Bank of the Philippine Islands)

```
================================================================================
Bank of the Philippine Islands (BPI)
Last Price: 101.00 PHP
Market Cap: 521,956,551,279 PHP
================================================================================

GROWTH OVERVIEW
--------------------------------------------------------------------------------
Metric         YoY 2023→2024  YoY 2024→2025  3‑Year CAGR
Book Value     13.0%          10.5%          11.7%
Net Income     20.0%          7.4%           13.5%
Total Assets   14.9%          10.0%          12.4%
Revenue        23.0%          14.8%          18.8%
EPS            12.6%          7.1%           9.9%

RATIOS
--------------------------------------------------------------------------------
Metric           Value
P/E Ratio        8.01
P/B Ratio        1.12
ROE              13.9%
Dividend Yield   4.81%
Dividend Cover   2.58

FUNDAMENTAL CHECKLIST
--------------------------------------------------------------------------------
P/E Ratio < 22: ✅
P/B Ratio < 1: ❌
Book Value Increasing?: ✅
Net Income Increasing?: ✅
Total Assets Increasing?: ✅
Shares Diluting? (No = ✓): ❌
ROE > 10%: ✅

VALUATION SCENARIOS (DCF, Required Return = 10%)
--------------------------------------------------------------------------------
Zero Growth Fair Value: 126.10 PHP
Current Price: 101.00 PHP
Margin of Safety: 24.9%
```

*(A bar chart of YoY growth rates will also appear.)*

---

## 📋 Data Sources

| Source | Data Retrieved |
|--------|----------------|
| `stockData.do` | Last price, market cap, outstanding shares |
| `dividends_and_rights_list.ax` | Dividend history (ex‑date, rate, etc.) |
| `search.ax` (Annual Report) | Disclosure list → Annual Reports (SEC Form 17‑A) |
| `search.ax` (Shares) | Disclosure list → SEC Form 17‑C (share count changes) |
| `openDiscViewer.do` → `downloadHtml.do` | HTML version of financial reports |

---

## 🧠 Technical Challenges Overcome

| Challenge | Solution |
|-----------|----------|
| **XHR‑based navigation** | Discovered and used `search.ax` and `dividends_and_rights_list.ax` endpoints |
| **Scale factor detection** | Parsed "Currency(and units)" notes in reports; applied multiplier to absolute metrics |
| **Multiple years extraction** | Cleaned and merged tables, deduplicated by fiscal year |
| **Edge‑case handling** | Gracefully handles missing data, negative values, and incomplete years |
| **Rate limiting** | Built‑in random delays (`1.5–5.5s`) to avoid overloading servers |

---

## 🤖 LLM Acknowledgments

This project was developed with the assistance of **Large Language Models** (primarily Claude Sonnet, DeepSeek V4, and Gemini Flash 3.5) for:
- Refactoring the initial script into a modular ETL pipeline
- Designing error‑handling patterns and scale‑factor logic
- Structuring the report generation and visualization functions
- Understanding and navigating PSE Edge's legacy architecture

LLMs served as pair‑programming assistants to accelerate learning and implementation.

---

## ⚠️ Disclaimer

This project is for **educational and personal research** purposes only. Users are responsible for complying with the `robots.txt` and Terms of Use of PSE Edge and any other websites accessed through this tool.

For full details, please read the [DISCLAIMER.md](DISCLAIMER.md).

---

## 📝 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgements

- **Philippine Stock Exchange (PSE)** for providing public access to financial data
- The open‑source community for `requests`, `BeautifulSoup`, `pandas`, and `matplotlib`
- The LLM providers that assisted with architecture and debugging

---

## 📬 Contact

Questions, suggestions, or concerns? Please [open an issue](https://github.com/SenjoNanaya/pse-dividend-analysis/issues) on GitHub.

---

**Built with ❤️ for learning and Value Investing research.**