import io
import re
from bs4 import BeautifulSoup
import pandas as pd
from src.utils import parse_scale_factor, safe_float

ABSOLUTE_METRICS = ['total_assets', 'total_liabilities', 'stockholders_equity', 'gross_revenue', 'net_income']

# Profitability ratios on Form 17-A are usually reported as percentages (e.g. 14.54 = 14.54%).
PERCENT_RATIO_KEYS = {'roe', 'roa', 'net_profit_margin', 'gross_profit_margin'}

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
                # Form values like 14.54 mean 14.54%
                val = val / 100.0
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

    years = sorted(yearly_metrics.keys()) if yearly_metrics else []
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

def parse_dividends(html_text):
    soup = BeautifulSoup(html_text, "lxml")
    table = soup.find("table", class_="list")
    if not table:
        return []

    df_list = pd.read_html(io.StringIO(str(table)), flavor="bs4")
    if not df_list:
        return []
    
    df = df_list[0]
    df_common = df[df['Type of Security'].str.upper() == 'COMMON'].copy()
    
    df_common['Dividend Rate'] = df_common['Dividend Rate'].astype(str).str.replace(r'[^\d.-]', '', regex=True)
    df_common['Dividend Rate'] = pd.to_numeric(df_common['Dividend Rate'], errors='coerce')
    
    for col in ['Ex-Dividend Date', 'Record Date', 'Payment Date']:
        df_common[col] = pd.to_datetime(df_common[col], errors='coerce')
        
    df_common = df_common.dropna(subset=['Ex-Dividend Date', 'Record Date', 'Payment Date', 'Dividend Rate'])
    
    dividends = []
    for _, row in df_common.iterrows():
        dividends.append({
            'ex_date': row['Ex-Dividend Date'].strftime('%Y-%m-%d'),
            'record_date': row['Record Date'].strftime('%Y-%m-%d'),
            'payment_date': row['Payment Date'].strftime('%Y-%m-%d'),
            'rate': float(row['Dividend Rate']),
        })
    dividends.sort(key=lambda x: x['ex_date'])
    return dividends

def parse_disclosure_edge_numbers(html_text):
    soup = BeautifulSoup(html_text, "lxml")
    edge_no_tags = soup.find_all("a", href="#viewer", onclick=True)
    edge_numbers = []
    for item in edge_no_tags:
        onclick = item['onclick']
        start = onclick.find("'") + 1
        end = onclick.find("'", start)
        edge_numbers.append(onclick[start:end])
    return edge_numbers

def parse_iframe_source(html_text):
    soup = BeautifulSoup(html_text, "lxml")
    iframes = soup.find_all('iframe')
    return iframes[0]['src'] if iframes else None

def clean_table(df):
    if df.shape[1] < 3:
        return pd.DataFrame()
    header_row_idx = None
    for i in range(min(3, len(df))):
        val = df.iloc[i, 1]
        if isinstance(val, str) and re.search(r'\d{4}', val):
            header_row_idx = i
            break
    if header_row_idx is None:
        header_row_idx = 0

    years = df.iloc[header_row_idx, 1:].tolist()
    df_clean = df.iloc[header_row_idx + 1:].copy()
    if df_clean.empty:
        return pd.DataFrame()

    df_clean = df_clean.set_index(df_clean.columns[0])
    df_clean.columns = years

    for col in df_clean.columns:
        df_clean[col] = df_clean[col].astype(str).str.replace(',', '').str.strip()
        df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')
    return df_clean

def extract_all_years_metrics(tables_list, scale_factor=1):
    cleaned_tables = []
    for df in tables_list:
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
        'total_liabilities': ['total liabilities'],
        'stockholders_equity': ['stockholders equity', "stockholders' equity", 'total equity'],
        'book_value_per_share': ['book value per share'],
        'gross_revenue': ['gross revenue'],
        'net_income': ['net income attributable to parent', 'net income/(loss) attributable to parent', 'net income after tax', 'net income'],
        'eps': ['earnings per share (basic)', 'earnings/(loss) per share (basic)', 'earnings per share', 'eps'],
    }
    
    for col in combined.columns:
        year_match = re.search(r'\d{4}', str(col))
        if not year_match:
            continue
        year = int(year_match.group())
        if year in yearly_results:
            continue
        
        metrics = {}
        for metric, pats in patterns.items():
            for pat in pats:
                matches = [idx for idx in combined.index if pat.lower() in str(idx).lower()]
                if matches:
                    row_label = matches[0]
                    val = combined.loc[row_label, col]
                    if pd.notna(val):
                        val = float(val) * scale_factor if metric in ABSOLUTE_METRICS else float(val)
                        metrics[metric] = val
                    break
        yearly_results[year] = metrics
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
    # can change this to have more info down the line
    soup = _make_soup(html_text)
    sector = None
    
    tables = soup.find_all("table", class_="view")
    for table in tables:
        caption = table.find("caption")
        if caption and "Security Information" in caption.get_text():
            for row in table.find_all("tr"):
                th = row.find("th")
                if th and "Sector" in th.get_text(strip=True):
                    td = row.find("td")
                    if td:
                        sector = td.get_text(strip=True)
                    break
            break
    
    return {"sector": sector}