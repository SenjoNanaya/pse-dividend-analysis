import io
import re
from bs4 import BeautifulSoup
import pandas as pd
from src.utils import parse_scale_factor

ABSOLUTE_METRICS = ['total_assets', 'total_liabilities', 'stockholders_equity', 'gross_revenue', 'net_income']

def get_value_from_tables(tables, label):
    for table in tables:
        for row in table.find_all("tr"):
            ths = row.find_all("th")
            for th in ths:
                if label.lower() in th.get_text(strip=True).lower():
                    td = th.find_next_sibling("td")
                    if td:
                        raw = td.get_text(strip=True)
                        try:
                            cleaned = re.sub(r'[^\d.-]', '', raw)
                            if cleaned:
                                return float(cleaned)
                        except:
                            pass
                        return raw
    return None

def parse_stock_data(html_text):
    soup = BeautifulSoup(html_text, "lxml")
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
    soup = BeautifulSoup(html_text, "lxml")
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

    return {"year": year, "tables": all_dfs, "scale_factor": scale_factor}