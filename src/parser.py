import io
import math
import re
from bs4 import BeautifulSoup
import pandas as pd
from src.utils import parse_scale_factor, safe_float

ABSOLUTE_METRICS = [
    'total_assets',
    'total_liabilities',
    'total_current_liabilities',
    'stockholders_equity',
    'gross_revenue',
    'net_income',
    'cash_and_equivalents',
    'operating_income',
    'income_before_tax',
    'income_tax_expense',
    'gross_profit',
    'ga_expense',
    'cost_of_sales',
    'interest_expense',
    'other_expenses',
]

# Profitability ratios on Form 17-A are usually reported as percentages (e.g. 14.54 = 14.54%).
# Some EDGE tables already store fractions (0.19 = 19%) — see normalize_percent_ratio.
PERCENT_RATIO_KEYS = {'roe', 'roa', 'net_profit_margin', 'gross_profit_margin'}


def normalize_percent_ratio(raw_value) -> float | None:
    """
    Convert a Form 17-A profitability cell to a fraction.

    |raw| > 1  → treat as percent points (14.54 → 0.1454)
    |raw| <= 1 → already a fraction (0.19 → 0.19); do not /100 again
    """
    try:
        val = float(raw_value)
    except (TypeError, ValueError):
        return None
    if abs(val) > 1.0:
        return val / 100.0
    return val

def _make_soup(html_text):
    try:
        return BeautifulSoup(html_text, "lxml")
    except Exception:
        return BeautifulSoup(html_text, "html.parser")

def _parse_optional_float(raw):
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text in {'-', '–', '—', 'n/a', 'N/A'}:
        return None
    cleaned = re.sub(r'[^\d.-]', '', text)
    if not cleaned or cleaned in {'.', '-', '-.'}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None

def _parse_money_tokens(text):
    """Extract numeric amounts from Item 13 style strings."""
    amounts = []
    for part in re.split(r'[;]', text):
        part = part.strip()
        if not part:
            continue
        val = _parse_optional_float(part)
        if val is not None:
            amounts.append(val)
    if amounts:
        return amounts
    for match in re.findall(r'(?:php|₱|p)\s*([\d,]+(?:\.\d+)?)', text, flags=re.I):
        val = _parse_optional_float(match)
        if val is not None:
            amounts.append(val)
    return amounts

def _pick_per_share_price(amounts):
    """
    Item 13 is usually: shares; price; aggregate market value.
    Per-share price is the smallest positive amount that looks like a stock price.
    """
    if not amounts:
        return None
    reasonable = [a for a in amounts if 0 < a <= 100_000]
    if reasonable:
        return min(reasonable)
    return None

def sanitize_per_share_price(price, market_cap=None, outstanding_shares=None):
    """Reject aggregate/share-count values mistaken for a per-share price."""
    price = _parse_optional_float(price)
    market_cap = _parse_optional_float(market_cap)
    outstanding_shares = _parse_optional_float(outstanding_shares)

    if price is not None and price > 100_000:
        price = None

    if price is not None and outstanding_shares:
        # Price should never equal (or nearly equal) the share count.
        if abs(price - outstanding_shares) / outstanding_shares < 0.05:
            price = None

    if market_cap and outstanding_shares:
        implied = market_cap / outstanding_shares
        if implied > 0:
            if price is None:
                return implied, "market_cap_per_share"
            if abs(price - implied) / implied > 10:
                return implied, "market_cap_per_share"

    if price is not None:
        return price, None
    return None, None

def parse_aggregate_market_price(html_text):
    """
    Extract the share price from Item 13 aggregate market value.
    Typical EDGE value: '5,283,794,223; P102.50; P541,588,907,857.50'
    Some filers prefix every segment with P — always pick the per-share amount.
    """
    soup = _make_soup(html_text)
    for dt in soup.find_all("dt"):
        text = dt.get_text(" ", strip=True).lower()
        if "aggregate market value" not in text:
            continue
        dd = dt.find_next_sibling("dd")
        if not dd:
            continue
        value = dd.get_text(" ", strip=True)
        return _pick_per_share_price(_parse_money_tokens(value))
    return None

def parse_financial_ratios_table(html_text):
    """
    Parse Form 17-A Financial Ratios table (#FR).
    Returns {fiscal_year: {pe_ratio, pb_ratio, roe, roa, ...}} using the latest column first.
    """
    soup = _make_soup(html_text)
    table = soup.find("table", id="FR")
    if not table:
        return {}

    rows = table.find_all("tr")
    year_cells = []
    for row in rows:
        spans = row.find_all("span", class_="valInput")
        if len(spans) >= 2 and all(re.search(r'\d{4}', s.get_text()) for s in spans[:2]):
            year_cells = spans
            break

    years = []
    for span in year_cells:
        m = re.search(r'(\d{4})', span.get_text(strip=True))
        if m:
            years.append(int(m.group(1)))
    if not years:
        return {}

    label_map = {
        'pe_ratio': ['price/earnings', 'price / earnings', 'p/e ratio'],
        'pb_ratio': ['price/book', 'price / book', 'price to book', 'p/bv', 'p/b ratio'],
        'roe': ['return on equity'],
        'roa': ['return on assets'],
        'net_profit_margin': ['net profit margin'],
        'gross_profit_margin': ['gross profit margin'],
        'current_ratio': ['current ratio', 'working capital ratio'],
        'quick_ratio': ['quick ratio'],
        'debt_to_equity': ['debt-to-equity', 'debt to equity'],
    }

    results = {y: {} for y in years}
    for row in rows:
        ths = row.find_all("th")
        if not ths:
            continue
        label = ths[0].get_text(" ", strip=True).lower()
        label = re.sub(r'\s+', ' ', label).strip()
        metric_key = None
        for key, patterns in label_map.items():
            if any(pat in label for pat in patterns):
                metric_key = key
                break
        if not metric_key:
            continue

        tds = row.find_all("td")
        if not tds:
            continue
        for idx, year in enumerate(years):
            if idx >= len(tds):
                break
            span = tds[idx].find("span", class_="valInput")
            raw = span.get_text(strip=True) if span else tds[idx].get_text(strip=True)
            val = _parse_optional_float(raw)
            if val is None:
                continue
            if metric_key in PERCENT_RATIO_KEYS:
                val = normalize_percent_ratio(val)
                if val is None:
                    continue
            results[year][metric_key] = val

    return {year: metrics for year, metrics in results.items() if metrics}

def resolve_valuation_fallbacks(stock_info, yearly_metrics, filing_prices=None, disclosure_ratios=None):
    """
    Fill missing price / P/E / P/B / ROE using disclosure fallbacks then filing math.
    Priority: stock page → disclosure ratios / Item 13 price → derive from EPS & BVPS.
    """
    stock = dict(stock_info or {})
    filing_prices = filing_prices or []
    disclosure_ratios = disclosure_ratios or {}

    years = sorted(
        y for y, m in (yearly_metrics or {}).items()
        if m.get("eps") is not None
        or m.get("book_value_per_share") is not None
        or m.get("gross_revenue") is not None
        or m.get("net_income") is not None
        or m.get("total_assets") is not None
    )
    latest_year = years[-1] if years else None
    latest = yearly_metrics.get(latest_year, {}) if latest_year else {}
    ratio_years = sorted(disclosure_ratios.keys())
    latest_ratios = disclosure_ratios.get(ratio_years[-1], {}) if ratio_years else {}

    if stock.get("last_traded_price") in (None, ''):
        if filing_prices:
            filing_prices_sorted = sorted(
                ((y, p) for y, p in filing_prices if p is not None),
                key=lambda item: item[0],
            )
            if filing_prices_sorted:
                stock["last_traded_price"] = filing_prices_sorted[-1][1]
                stock["price_source"] = "disclosure_item13"

    sanitized_price, price_source = sanitize_per_share_price(
        stock.get("last_traded_price"),
        stock.get("market_cap"),
        stock.get("outstanding_shares"),
    )
    price_was_corrected = (
        sanitized_price is not None
        and stock.get("last_traded_price") not in (None, '')
        and abs(safe_float(stock.get("last_traded_price")) - sanitized_price) > 1e-6
    )
    if sanitized_price is not None:
        if price_source and stock.get("price_source") != "stock_page":
            stock["price_source"] = price_source
        stock["last_traded_price"] = sanitized_price
    elif stock.get("last_traded_price") not in (None, ''):
        stock["last_traded_price"] = None

    price = stock.get("last_traded_price")
    eps = latest.get("eps")
    book_value = latest.get("book_value_per_share") or stock.get("stock_book_value")

    def _ratio_looks_bad(value, upper=1000):
        v = safe_float(value)
        return v is None or abs(v) > upper

    if stock.get("pe_ratio") in (None, '') or price_was_corrected or _ratio_looks_bad(stock.get("pe_ratio")):
        if latest_ratios.get("pe_ratio") is not None and not price_was_corrected:
            stock["pe_ratio"] = latest_ratios["pe_ratio"]
            stock["pe_source"] = "disclosure_fr"
        elif price and eps:
            stock["pe_ratio"] = price / eps
            stock["pe_source"] = "computed"

    if stock.get("pb_ratio") in (None, '') or price_was_corrected or _ratio_looks_bad(stock.get("pb_ratio")):
        if latest_ratios.get("pb_ratio") is not None and not price_was_corrected:
            stock["pb_ratio"] = latest_ratios["pb_ratio"]
            stock["pb_source"] = "disclosure_fr"
        elif price and book_value:
            stock["pb_ratio"] = price / book_value
            stock["pb_source"] = "computed"

    if stock.get("roe") in (None, '') and latest_ratios.get("roe") is not None:
        stock["roe"] = latest_ratios["roe"]
        stock["roe_source"] = "disclosure_fr"

    return stock

def get_value_from_tables(tables, label, exact=False):
    target = label.lower()
    for table in tables:
        for row in table.find_all("tr"):
            ths = row.find_all("th")
            for th in ths:
                text = th.get_text(strip=True).lower()
                matched = text == target if exact else target in text
                if not matched:
                    continue
                td = th.find_next_sibling("td")
                if td:
                    raw = td.get_text(strip=True)
                    try:
                        cleaned = re.sub(r'[^\d.-]', '', raw)
                        if cleaned:
                            return float(cleaned)
                    except Exception:
                        pass
                    return raw if raw else None
    return None

def parse_stock_data(html_text):
    soup = _make_soup(html_text)
    comp_p = soup.select_one('.compInfo p')
    company_name = comp_p.text.strip() if comp_p else None
    
    ticker_elem = soup.find("option", selected=True)
    ticker = ticker_elem.text.strip() if ticker_elem else None
    tables = soup.find_all("table", class_="view")
    
    return {
        "company_name": company_name,
        "ticker": ticker,
        "market_cap": get_value_from_tables(tables, "Market Capitalization"),
        "outstanding_shares": get_value_from_tables(tables, "Outstanding Shares"),
        "last_traded_price": get_value_from_tables(tables, "Last Traded Price"),
        # Exact match so "Sector P/E Ratio" does not steal "P/E Ratio"
        "pe_ratio": get_value_from_tables(tables, "P/E Ratio", exact=True),
        "pb_ratio": get_value_from_tables(tables, "P/BV Ratio", exact=True),
        "stock_book_value": get_value_from_tables(tables, "Book Value", exact=True),
    }

def _normalize_security_label(raw):
    text = re.sub(r'\s+', ' ', str(raw or '').strip())
    return text


def _is_common_security(security):
    """True for common equity rows; false for preferred / other series."""
    label = _normalize_security_label(security).upper()
    if not label:
        return False
    if label in {'COMMON', 'COMMON STOCK', 'COMMON SHARES'}:
        return True
    # Prefer series often labeled BRNP / Series A / Preferred
    if 'PREFERRED' in label or 'SERIES' in label:
        return False
    if re.search(r'\bBRN[PCAB]?\b', label) and 'COMMON' not in label:
        return False
    return label.startswith('COMMON')


def _normalize_dividend_type(raw):
    """Map EDGE 'Type of Dividend' to cash | stock | property | other."""
    text = str(raw or "cash").strip().lower()
    if "stock" in text:
        return "stock"
    if "property" in text or "scrip" in text:
        return "property"
    if "cash" in text or text in ("", "nan", "none"):
        return "cash"
    return text.replace(" ", "_") or "cash"


def _is_entitlement_or_share_payout_text(raw) -> bool:
    """
    True for property/stock entitlement prose (not a PHP cash DPS).

    LFM-style: 'Every 1 share … entitlement of 97 shares of LFM Properties…'
    Old digit-strip parsers turned that into cash rate 197 (1||97).
    """
    text = str(raw or "").strip().lower()
    if not text:
        return False
    if "entitlement" in text:
        return True
    if "for every" in text and "share" in text:
        return True
    if re.search(r"\b\d+\s*shares?\s+of\b", text):
        return True
    if re.search(r"\b\d+\s*:\s*\d+\b", text) and "share" in text:
        return True
    if "property dividend" in text or "stock dividend" in text:
        return True
    return False


def _digit_concat_trap(text: str, value: float) -> bool:
    """True when value equals digits concatenated from multiple integers in text."""
    ints = re.findall(r"\d+", text)
    if len(ints) < 2:
        return False
    try:
        joined = float("".join(ints))
    except ValueError:
        return False
    return abs(joined - value) < 1e-9


def _parse_dividend_rate(raw):
    """
    Extract per-share PHP amount from EDGE dividend rate cells.

    Prose like 'Thirteen and 51/100 centavos (Php0.1351) per share' must not
    be digit-stripped (that yields 511000.1351 from 51+100+0.1351).
    Entitlement / share-ratio cells return None (not cash DPS).
    """
    text = str(raw or "").strip()
    if not text or text.lower() in {"nan", "none", "-", "–", "—"}:
        return None

    if _is_entitlement_or_share_payout_text(text):
        return None

    # Prefer explicit currency amount (Php0.1351 / PHP 1.25 / ₱0.50)
    currency = re.search(
        r"(?:₱|Php|PHP)\s*([\d,]+(?:\.\d+)?)",
        text,
        flags=re.IGNORECASE,
    )
    if currency:
        try:
            val = float(currency.group(1).replace(",", ""))
        except ValueError:
            val = None
        if val is not None and not _digit_concat_trap(text, val):
            return val

    # Simple numeric cell: "0.50" / "1.25"
    if re.fullmatch(r"[\d,]+(?:\.\d+)?", text):
        try:
            return float(text.replace(",", ""))
        except ValueError:
            return None

    # Last resort: first standalone decimal that looks like a per-share rate
    candidates = re.findall(r"\d+(?:\.\d+)?", text)
    for c in candidates:
        try:
            val = float(c)
        except ValueError:
            continue
        # Per-share cash rates are almost never huge integers formed from prose
        if 0 < val < 10_000 and ("." in c or val < 100):
            if _digit_concat_trap(text, val):
                continue
            return val
    return None


def _scrub_cash_vs_property_siblings(dividends: list) -> list:
    """
    Drop cash rows that share an ex-date with a property/stock payout when the
    cash 'rate' looks like an entitlement misparse (LFM 197 beside property).
    """
    non_cash_dates = {
        d["ex_date"]
        for d in dividends
        if str(d.get("type") or "").lower() in ("property", "stock")
    }
    out = []
    for d in dividends:
        dtype = str(d.get("type") or "cash").lower()
        rate = d.get("rate")
        if (
            dtype == "cash"
            and d.get("ex_date") in non_cash_dates
            and rate is not None
            and float(rate) >= 5.0
        ):
            continue
        out.append(d)
    return out


def parse_dividends(html_text):
    """
    Parse PSE EDGE dividends_and_rights_list.ax HTML.
    Returns all cash/stock/property rows (common + preferred) with dates.
    Yields/cover should filter is_common=True and type=cash.
    """
    soup = _make_soup(html_text)
    table = soup.find("table", class_="list")
    if not table:
        return []

    df_list = pd.read_html(io.StringIO(str(table)), flavor="bs4")
    if not df_list:
        return []

    df = df_list[0]
    required = {
        'Type of Security', 'Type of Dividend', 'Dividend Rate',
        'Ex-Dividend Date', 'Record Date', 'Payment Date',
    }
    if not required.issubset(set(df.columns)):
        return []

    df = df.copy()
    df['_div_type_raw'] = df['Type of Dividend'].astype(str)
    df['_rate_raw'] = df['Dividend Rate'].astype(str)
    for col in ['Ex-Dividend Date', 'Record Date', 'Payment Date']:
        df[col] = pd.to_datetime(df[col], errors='coerce')

    df = df.dropna(subset=['Ex-Dividend Date'])

    dividends = []
    for _, row in df.iterrows():
        security = _normalize_security_label(row.get('Type of Security'))
        div_type = _normalize_dividend_type(row.get('_div_type_raw'))
        rate_raw = row.get('_rate_raw')
        if _is_entitlement_or_share_payout_text(rate_raw):
            div_type = "property"
        rate = _parse_dividend_rate(rate_raw)
        # Property/stock entitlements may have no PHP rate — keep a marker row
        if rate is None:
            if div_type in ("property", "stock"):
                rate = 0.0
            else:
                continue
        record = row['Record Date']
        payment = row['Payment Date']
        dividends.append({
            'security': security,
            'is_common': _is_common_security(security),
            'ex_date': row['Ex-Dividend Date'].strftime('%Y-%m-%d'),
            'record_date': record.strftime('%Y-%m-%d') if pd.notna(record) else None,
            'payment_date': payment.strftime('%Y-%m-%d') if pd.notna(payment) else None,
            'rate': float(rate),
            'type': div_type,
        })

    dividends = _scrub_cash_vs_property_siblings(dividends)
    dividends.sort(key=lambda x: (x['ex_date'], x.get('security') or ''))
    return dividends

def parse_disclosure_edge_numbers(html_text):
    soup = _make_soup(html_text)
    edge_no_tags = soup.find_all("a", href="#viewer", onclick=True)
    edge_numbers = []
    for item in edge_no_tags:
        onclick = item['onclick']
        start = onclick.find("'") + 1
        end = onclick.find("'", start)
        edge_numbers.append(onclick[start:end])
    return edge_numbers

def parse_iframe_source(html_text):
    soup = _make_soup(html_text)
    iframes = soup.find_all('iframe')
    return iframes[0]['src'] if iframes else None


def parse_disclosure_attachments(html_text):
    """
    Parse EDGE openDiscViewer attachment list (#file_list).
    Returns [{file_id, filename}, ...] excluding the empty 'Select' option.
    """
    soup = _make_soup(html_text)
    select = soup.find("select", id="file_list") or soup.find("select", attrs={"name": "file_list"})
    if not select:
        return []
    attachments = []
    for opt in select.find_all("option"):
        file_id = (opt.get("value") or "").strip()
        if not file_id:
            continue
        filename = " ".join(opt.get_text(" ", strip=True).split())
        if not filename or filename.lower() == "select":
            continue
        attachments.append({"file_id": file_id, "filename": filename})
    return attachments


def clean_table(df):
    if df.shape[1] < 2:
        return pd.DataFrame()

    header_row_idx = None
    for i in range(min(5, len(df))):
        row = df.iloc[i]
        year_cells = [
            c for c in row
            if c is not None and not (isinstance(c, float) and pd.isna(c))
            and re.search(r'\d{4}', str(c))
        ]
        if year_cells:
            header_row_idx = i
            break
    if header_row_idx is None:
        return pd.DataFrame()

    header_row = df.iloc[header_row_idx]
    year_cols = []
    years = []
    for j, val in enumerate(header_row):
        if val is not None and not (isinstance(val, float) and pd.isna(val)) and re.search(r'\d{4}', str(val)):
            year_cols.append(j)
            years.append(str(val))
    if not year_cols:
        return pd.DataFrame()

    df_data = df.iloc[header_row_idx + 1 :]
    if df_data.empty:
        return pd.DataFrame()

    # PSE tables: year headers may share col 0 with metric labels on data rows (values shift right by 1)
    first_data_cell = df_data.iloc[0, 0]
    header_col0_is_year = re.search(r'\d{4}', str(header_row.iloc[0] or ''))
    data_col0_is_label = not re.search(r'\d{4}', str(first_data_cell or ''))
    if header_col0_is_year and data_col0_is_label:
        value_cols = [j + 1 for j in year_cols]
        label_col = 0
    else:
        value_cols = year_cols
        label_col = 0 if year_cols[0] > 0 else None
        if label_col is None:
            return pd.DataFrame()

    if max(value_cols) >= df_data.shape[1]:
        return pd.DataFrame()

    labels = df_data.iloc[:, label_col].astype(str).tolist()
    data = {years[i]: df_data.iloc[:, value_cols[i]].tolist() for i in range(len(years))}
    df_clean = pd.DataFrame(data, index=labels)

    for col in df_clean.columns:
        series = df_clean[col]
        if isinstance(series, pd.DataFrame):
            series = series.iloc[:, 0]
        converted = series.astype(str).str.replace(',', '').str.strip()
        df_clean[col] = pd.to_numeric(converted, errors='coerce')
    return df_clean

def _label_matches_metric(label, pat, metric):
    """Substring match with guards so balance-sheet totals are not mis-tagged."""
    text = str(label).lower()
    if pat.lower() not in text:
        return False
    if metric == 'total_liabilities':
        # "Total Liabilities and Stockholders' Equity" == Assets, not L
        if 'equity' in text or 'stockholder' in text:
            return False
        # Prefer the dedicated current-liabilities row for that metric
        if 'current' in text:
            return False
    if metric == 'total_current_liabilities':
        if 'equity' in text or 'stockholder' in text:
            return False
        if 'noncurrent' in text or 'non-current' in text or 'non current' in text:
            return False
        # Require "current" so bare "liabilities" does not match
        if 'current' not in text:
            return False
    if metric == 'cash_and_equivalents':
        # CF ending-cash rows are allowed via dedicated patterns; activity lines are not
        if _label_is_cf_ending_cash(text):
            return True
        if any(
            x in text
            for x in (
                "beginning",
                "start of",
                "at start",
                "from operating",
                "from investing",
                "from financing",
            )
        ):
            return False
        if 'flow' in text or 'flows' in text:
            return False
        if 'dividend' in text or 'generated' in text or 'used in' in text:
            return False
        # Bare "cash" / short labels only — avoid long P&L / notes prose
        if pat.lower() == 'cash':
            if len(text.strip()) > 40:
                return False
    if metric in ('operating_income', 'gross_profit', 'ga_expense'):
        if any(
            x in text
            for x in (
                'share of',
                'associate',
                'joint venture',
                'segment',
                'margin',
                'per share',
                '%',
            )
        ):
            return False
    if metric == 'operating_income':
        if 'working capital' in text or 'operating activities' in text:
            return False
        if 'discontinued' in text:
            return False
        # Bare EBIT only — avoid long notes prose
        if pat.lower() == 'ebit' and len(text.strip()) > 24:
            return False
    if metric == 'ga_expense':
        if 'cost of' in text or 'cost of sales' in text or 'cost of goods' in text:
            return False
        if 'operating activities' in text:
            return False
    if metric == 'interest_expense':
        if 'interest income' in text or 'investment income' in text:
            return False
        if 'from financing' in text:
            return False
    if metric == 'other_expenses':
        if len(text.strip()) > 48:
            return False
        if 'income' in text and 'operating' not in text:
            return False
    if metric == 'stockholders_equity':
        if 'liabilit' in text:
            return False
    if metric == 'total_assets':
        if 'liabilit' in text and 'equity' in text:
            return False
    return True


def _looks_like_year_amount(value) -> bool:
    """True when a balance column was filled with a fiscal-year header (e.g. 2024)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    return 1990 <= abs(v) <= 2100 and abs(v - round(v)) < 1e-9


def _label_is_cf_ending_cash(label) -> bool:
    """True for cash-flow 'cash at end of year/period' rows (not activity lines)."""
    text = str(label).lower()
    if not text.strip():
        return False
    if any(
        x in text
        for x in (
            "from operating",
            "from investing",
            "from financing",
            "dividend",
            "generated",
            "used in",
            "beginning",
            "start of",
            "at start",
        )
    ):
        return False
    if "cash" not in text:
        return False
    endings = (
        "at end of year",
        "at end of the year",
        "at end of period",
        "at end of the period",
        "end of year",
        "end of period",
        "ending balance",
        "ending cash",
        ", ending",
        "close of the year",
        "close of year",
    )
    return any(e in text for e in endings)


# Balance-sheet cash synonyms (order = preference)
CASH_BS_PATTERNS = [
    "cash and cash equivalents",
    "cash & cash equivalents",
    "cash and equivalents",
    "cash and short-term deposits",
    "cash and short term deposits",
    "cash and cash in banks",
    "cash in bank and on hand",
    "cash in banks and on hand",
    "cash on hand and in banks",
    "cash on hand and in bank",
    "cash in banks",
    "cash in bank",
    "cash and cash equivalents unrestricted",
    "unrestricted cash",
    "cash on hand",
    "cash",  # bare / short labels last; guarded in _label_matches_metric
]

# Cash-flow statement ending balance (fallback when BS cash missing)
CASH_CF_ENDING_PATTERNS = [
    "cash and cash equivalents at end of year",
    "cash and cash equivalents at end of the year",
    "cash and cash equivalents at end of period",
    "cash and cash equivalents at end of the period",
    "cash and cash equivalents, end of year",
    "cash and cash equivalents, ending",
    "cash at end of year",
    "cash at end of the year",
    "cash at end of period",
    "ending cash and cash equivalents",
]


# Metrics that score among multiple label matches using statement anchors.
_SCORED_METRICS = frozenset({
    'operating_income',
    'gross_profit',
    'ga_expense',
    'cash_and_equivalents',
})


def _label_quality_bonus(label) -> float:
    text = str(label).lower()
    bonus = 0.0
    if 'total' in text:
        bonus += 2.0
    if 'consolidated' in text:
        bonus += 1.5
    # Prefer shorter, cleaner labels over note prose
    bonus += max(0.0, 2.0 - len(text) / 40.0)
    return bonus


def _collect_metric_candidates(combined, col, pats, scale_factor, metric):
    """All (label, value) matches for a metric, de-duplicated by label."""
    seen = set()
    out = []
    for pat in pats:
        for idx in combined.index:
            if not _label_matches_metric(idx, pat, metric):
                continue
            key = str(idx)
            if key in seen:
                continue
            val = combined.loc[idx, col]
            if pd.isna(val):
                continue
            try:
                num = float(val)
            except (TypeError, ValueError):
                continue
            if metric in ABSOLUTE_METRICS:
                num *= scale_factor
            seen.add(key)
            out.append((key, num))
    return out


def _pick_scored_candidate(metric, candidates, anchors):
    """
    Choose best candidate using anchors (ibt/ni/revenue/assets).
    Returns None when no candidate clears the band (never keep a known-bad first hit).
    """
    if not candidates:
        return None
    ibt = anchors.get('income_before_tax')
    ni = anchors.get('net_income')
    rev = anchors.get('revenue')
    if rev is None:
        rev = anchors.get('gross_revenue')
    assets = anchors.get('total_assets')
    gp = anchors.get('gross_profit')

    scored = []
    for label, val in candidates:
        if val is None:
            continue
        abs_v = abs(val)
        if abs_v < 1e-9 and metric != 'net_income':
            continue
        q = _label_quality_bonus(label)
        if metric == 'operating_income':
            anchor = ibt if ibt is not None else ni
            if anchor is not None and abs(anchor) >= 1_000_000:
                if not (0.4 * abs(anchor) <= abs_v <= 5.0 * abs(anchor)):
                    continue
                # closer to anchor is better
                dist = abs(math.log10(abs_v) - math.log10(abs(anchor)))
                scored.append((dist - q * 0.05, -q, val))
            else:
                scored.append((0.0 - q * 0.05, -q, val))
        elif metric == 'gross_profit':
            if rev is not None and abs(rev) >= 1_000_000:
                if not (0.05 * abs(rev) <= abs_v <= 1.05 * abs(rev)):
                    continue
                dist = abs(math.log10(abs_v) - math.log10(abs(rev) * 0.4))
                scored.append((dist - q * 0.05, -q, val))
            elif ni is not None and abs(ni) >= 1_000_000:
                if abs_v > 50.0 * abs(ni):
                    continue
                scored.append((0.0 - q * 0.05, -q, val))
            else:
                scored.append((0.0 - q * 0.05, -q, val))
        elif metric == 'ga_expense':
            if rev is not None and abs(rev) >= 1_000_000 and abs_v > 0.8 * abs(rev):
                continue
            # GA can exceed GP (operating loss); only reject absurd multiples
            if gp is not None and abs(gp) > 0 and abs_v > abs(gp) * 5.0:
                continue
            scored.append((0.0 - q * 0.05, -q, val))
        elif metric == 'cash_and_equivalents':
            if assets is not None and abs(assets) >= 1_000_000:
                # Parents/holdcos can be cash-heavy; reject only absurd multiples
                if not (0.001 * abs(assets) <= abs_v <= 0.95 * abs(assets)):
                    continue
            if 1990 <= abs_v <= 2100 and abs(abs_v - round(abs_v)) < 1e-9:
                continue
            scored.append((0.0 - q * 0.05, -q, val))
        else:
            scored.append((0.0 - q * 0.05, -q, val))

    if not scored:
        return None
    scored.sort()
    return scored[0][2]


def _extract_metric_value(combined, col, pats, scale_factor, metric, anchors=None):
    """
    Pick a matching row for a metric pattern list.

    For operating_income / gross_profit / ga_expense / cash: score all candidates
    against anchors when provided. For net_income: skip zero placeholders.
    """
    if metric in _SCORED_METRICS and anchors is not None:
        cands = _collect_metric_candidates(combined, col, pats, scale_factor, metric)
        return _pick_scored_candidate(metric, cands, anchors)

    skip_zero = metric == 'net_income'
    fallback_zero = None
    for pat in pats:
        matches = [
            idx for idx in combined.index
            if _label_matches_metric(idx, pat, metric)
        ]
        if not matches:
            continue
        val = combined.loc[matches[0], col]
        if pd.isna(val):
            continue
        val = float(val) * scale_factor if metric in ABSOLUTE_METRICS else float(val)
        if not skip_zero or val != 0:
            return val
        if fallback_zero is None:
            fallback_zero = val
    return fallback_zero


def _reconcile_balance_sheet(metrics):
    """
    Fill missing A / L / E via Assets = Liabilities + Equity, and repair
    common mis-parses when equity is available.
    """
    a = metrics.get('total_assets')
    l = metrics.get('total_liabilities')
    e = metrics.get('stockholders_equity')
    cl = metrics.get('total_current_liabilities')
    cash = metrics.get('cash_and_equivalents')

    # Year header misread as total assets / cash (e.g. 2024.0)
    if a is not None and _looks_like_year_amount(a):
        metrics.pop('total_assets', None)
        a = None
    if cash is not None and _looks_like_year_amount(cash):
        metrics.pop('cash_and_equivalents', None)
        cash = None

    if a is not None and l is not None and e is None:
        metrics['stockholders_equity'] = a - l
        e = metrics['stockholders_equity']
    elif a is not None and e is not None and l is None:
        metrics['total_liabilities'] = a - e
        l = metrics['total_liabilities']
    elif l is not None and e is not None and a is None:
        metrics['total_assets'] = l + e
        a = metrics['total_assets']

    if a is not None and l is not None and e is not None and abs(a) > 0:
        le = l + e
        # Scale misparse: A is 1e3/1e6 too small vs L+E (DELM-style), even if E < 0
        if abs(le) > 0:
            for factor in (1_000.0, 1_000_000.0):
                if abs(a * factor - le) / abs(le) < 0.02:
                    metrics['total_assets'] = le
                    a = le
                    break
        # Parsed "liabilities" row was actually A≈L (balance-sheet total)
        if abs(l - a) / abs(a) < 0.02 and abs(le - a) / abs(a) > 0.05:
            metrics['total_liabilities'] = a - e
            l = metrics['total_liabilities']
            le = l + e
        else:
            # When A is the outlier vs coherent L+E, trust L+E (do not destroy L)
            denom = max(abs(a), abs(le))
            if (
                denom > 0
                and abs(a - le) / denom > 0.15
                and l > 0
                and e > 0
                and l < le
            ):
                metrics['total_assets'] = le
                a = le

    # Cash cannot exceed total assets when both present
    cash = metrics.get('cash_and_equivalents')
    a = metrics.get('total_assets')
    if cash is not None and a is not None and abs(a) > 0 and cash > abs(a) * 1.05:
        metrics.pop('cash_and_equivalents', None)

    # Current liabilities cannot exceed total liabilities
    if cl is not None and l is not None and cl > l * 1.02:
        metrics.pop('total_current_liabilities', None)

    return metrics


def extract_all_years_metrics(tables_list, scale_factor=1):
    cleaned_tables = []
    for df in tables_list:
        caption = (df.index.name or '').lower()
        if 'financial ratios' in caption or 'other relevant' in caption:
            continue
        cleaned = clean_table(df)
        if not cleaned.empty:
            cleaned_tables.append(cleaned)
    if not cleaned_tables:
        return {}
    
    combined = pd.concat(cleaned_tables, axis=0)
    combined = combined[~combined.index.duplicated(keep='first')]
    yearly_results = {}
    
    patterns = {
        'total_assets': ['total assets'],
        'total_liabilities': [
            'total liabilities',
            'total liability',
        ],
        'total_current_liabilities': [
            'total current liabilities',
            'total current liability',
            'current liabilities',
        ],
        'stockholders_equity': [
            "total stockholders' equity",
            'total stockholders equity',
            "stockholders' equity",
            'stockholders equity',
            "total shareholders' equity",
            'total shareholders equity',
            'total equity',
        ],
        'cash_and_equivalents': list(CASH_BS_PATTERNS),
        'operating_income': [
            'operating income',
            'operating profit',
            'income from operations',
            'earnings before interest and tax',
            'earnings before interest and taxes',
            'ebit',
        ],
        'gross_profit': [
            'gross profit',
            'gross income',
        ],
        'ga_expense': [
            'selling general and administrative expenses',
            'selling, general and administrative expenses',
            'selling general and administrative',
            'sg&a expenses',
            'sg&a',
            'general and administrative expenses',
            'general and administrative expense',
            'general & administrative expenses',
            'general and administrative',
            'administrative expenses',
            'administrative expense',
        ],
        'income_before_tax': [
            'income/(loss) before tax',
            'income before income tax',
            'income before tax',
        ],
        'income_tax_expense': [
            'provision for income tax',
            'income tax expense',
            'provision for tax',
        ],
        'cost_of_sales': [
            'cost of real estate sales',
            'cost of real estate',
            'cost of goods sold',
            'cost of sales',
            'cost of services',
        ],
        'interest_expense': [
            'interest and other financing charges',
            'interest and financing charges',
            'finance costs',
            'financing charges',
            'interest expense',
        ],
        'other_expenses': [
            'other operating expenses',
            'other expenses',
        ],
        'book_value_per_share': ['book value per share'],
        'gross_revenue': ['gross revenue'],
        'net_income': [
            'net income/(loss) after tax',
            'net income after tax',
            'net income/(loss) attributable to parent',
            'net income attributable to parent',
            'net income',
        ],
        'eps': ['earnings per share (basic)', 'earnings/(loss) per share (basic)', 'earnings per share', 'eps'],
    }
    
    for col in combined.columns:
        year_match = re.search(r'\d{4}', str(col))
        if not year_match:
            continue
        year = int(year_match.group())
        if year in yearly_results:
            continue
        
        # Pass 1: anchors and non-scored fields (OI/GP/GA/cash need IBT/NI/A)
        metrics = {}
        for metric, pats in patterns.items():
            if metric in _SCORED_METRICS:
                continue
            val = _extract_metric_value(combined, col, pats, scale_factor, metric)
            if val is not None:
                metrics[metric] = val
        # Pass 2: scored fields with anchors from pass 1
        anchors = dict(metrics)
        for metric in (
            'gross_profit',
            'ga_expense',
            'operating_income',
            'cash_and_equivalents',
        ):
            pats = patterns.get(metric)
            if not pats:
                continue
            # Refresh GP into anchors before OI/GA scoring when available
            if metric == 'ga_expense' and metrics.get('gross_profit') is not None:
                anchors['gross_profit'] = metrics['gross_profit']
            val = _extract_metric_value(
                combined, col, pats, scale_factor, metric, anchors=anchors
            )
            if val is not None:
                metrics[metric] = val
                anchors[metric] = val
        # CF ending-cash fallback when balance-sheet cash line is absent
        if metrics.get("cash_and_equivalents") is None:
            cf_cash = _extract_metric_value(
                combined,
                col,
                CASH_CF_ENDING_PATTERNS,
                scale_factor,
                "cash_and_equivalents",
                anchors=anchors,
            )
            if cf_cash is not None:
                metrics["cash_and_equivalents"] = cf_cash
        from src.report_metrics import sanitize_operating_metrics
        from src.scale_guard import harmonize_intra_year_pl_scale

        metrics = _reconcile_balance_sheet(metrics)
        harmonize_intra_year_pl_scale(metrics)
        yearly_results[year] = sanitize_operating_metrics(metrics)
    return yearly_results

def parse_report_html(html_text):
    soup = _make_soup(html_text)
    table_elements = soup.find_all("table", class_="type1", id=True)
    
    scale_factor = 1  
    currency_p = soup.find('p', class_='textCont', string=lambda t: t and 'Currency' in t)
    if currency_p:
        full_text = currency_p.get_text(strip=True)
        if ':' in full_text:
            scale_factor = parse_scale_factor(full_text.split(':')[-1].strip())
    else:
        currency_th = soup.find('th', string=lambda t: t and 'Currency' in t)
        if currency_th:
            td = currency_th.find_next('td')
            if td:
                span = td.find('span', class_='valInput')
                currency_text = span.get_text(strip=True) if span else td.get_text(strip=True)
                scale_factor = parse_scale_factor(currency_text)
    
    if 'SEC FORM 17-C' in html_text:
        date_text = None
        dt = soup.find('dt', string=lambda t: t and 'Date of Report' in t)
        if dt and dt.find_next('dd'):
            span = dt.find_next('dd').find('span', class_='valInput')
            if span: date_text = span.get_text(strip=True)

        shares = None
        sec_table = soup.find('table', id='Securities')
        if sec_table:
            for row in sec_table.find_all('tr'):
                tds = row.find_all('td')
                if len(tds) >= 2 and 'common' in tds[0].get_text(strip=True).lower():
                    shares = int(re.sub(r'[^\d]', '', tds[1].get_text(strip=True)))
                    break
        if shares is None:
            os_table = soup.find('table', id='OS')
            if os_table:
                for row in os_table.find_all('tr'):
                    tds = row.find_all('td')
                    if len(tds) >= 3 and 'common' in tds[0].get_text(strip=True).lower():
                        shares = int(re.sub(r'[^\d]', '', tds[2].get_text(strip=True)))
                        break
        year = int(re.search(r'\d{4}', date_text).group()) if date_text and re.search(r'\d{4}', date_text) else None
        return {
            'type': 'form17c', 'year': year, 'date': date_text,
            'common_shares_outstanding': shares, "scale_factor": scale_factor
        }
    
    year = None
    header = soup.find('th', string=lambda t: t and 'fiscal year ended' in t.lower()) or \
             soup.find('th', string=lambda t: t and 'for the year ended' in t.lower())
    if header:
        date_span = header.find_next('span', class_='valInput')
        date_text = date_span.get_text(strip=True) if date_span else (header.find_next('td').get_text(strip=True) if header.find_next('td') else None)
        if date_text and re.search(r'\d{4}', date_text):
            year = int(re.search(r'\d{4}', date_text).group())
    
    all_dfs = []
    for table in table_elements:
        caption = table.find("caption")
        table_caption = caption.get_text(strip=True) if caption else "Unnamed Table"
        df_list = pd.read_html(io.StringIO(str(table)), flavor="bs4")
        if df_list:
            df = df_list[0]
            if 'Item' in df.columns: df = df.set_index('Item')
            df.index.name = table_caption
            all_dfs.append(df)

    filing_price = parse_aggregate_market_price(html_text)
    financial_ratios = parse_financial_ratios_table(html_text)

    return {
        "year": year,
        "tables": all_dfs,
        "scale_factor": scale_factor,
        "filing_price": filing_price,
        "financial_ratios": financial_ratios,
    }

def parse_company_info(html_text):
    soup = _make_soup(html_text)
    sector = None
    subsector = None

    tables = soup.find_all("table", class_="view")
    for table in tables:
        caption = table.find("caption")
        if not caption or "Security Information" not in caption.get_text():
            continue
        for row in table.find_all("tr"):
            th = row.find("th")
            td = row.find("td")
            if not th or not td:
                continue
            label = th.get_text(strip=True).lower()
            value = td.get_text(strip=True) or None
            if "subsector" in label or "sub-sector" in label or "sub sector" in label:
                subsector = value
            elif label == "sector" or label.startswith("sector"):
                sector = value
        break

    return {"sector": sector, "subsector": subsector}