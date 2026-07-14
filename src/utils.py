import logging
import sqlite3 
import os
import random
import time
import re
import pandas as pd
import numpy as np
import sys
from dotenv import load_dotenv

load_dotenv()

LOG_FILE = os.getenv("LOG_FILE", "logs/scraper.log")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
MIN_DELAY = float(os.getenv("MIN_DELAY", 1.5))
MAX_DELAY = float(os.getenv("MAX_DELAY", 5.5))
DB_PATH = os.getenv("DB_PATH", "data/pse_analysis.db")

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
}

def setup_logger():
    # Force stdout/stderr to UTF-8 (supports emojis on Windows)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),  # Explicit UTF-8 for file
            logging.StreamHandler()  # Uses reconfigured stdout
        ]
    )
    return logging.getLogger("PSE_Scraper")

def random_delay():
    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))


def format_safe(value, format_spec=".2f"):
    if value is None:
        return "N/A"
    if isinstance(value, (int, float)):
        # Check for NaN or infinite
        if pd.isna(value) or np.isinf(value):  # Requires import numpy as np
            return "N/A"
        try:
            return f"{value:{format_spec}}"
        except (ValueError, TypeError):
            return "N/A"
    return "N/A"  # Fallback for strings or unexpected types

def safe_float(value):

    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        # Remove commas, spaces, currency symbols, and everything except digits, dots, and minus
        cleaned = re.sub(r'[^\d.-]', '', value.strip())
        if cleaned == '' or cleaned == '-':
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None

def parse_scale_factor(text):
    if not text:
        return 1
    text_lower = text.lower()
    if 'thousand' in text_lower:
        return 1000
    elif 'million' in text_lower:
        return 1_000_000
    elif 'billion' in text_lower:
        return 1_000_000_000
    else:
        return 1
def query_db(sql, params=None, fetch_all=True, verbose=True):
    """
    Run a SQL query and return results. Useful for debugging.
    
    Args:
        sql (str): SQL query string (use ? placeholders for parameters)
        params (list/tuple): Parameters to substitute into the query
        fetch_all (bool): If True, returns all rows; if False, returns one row
        verbose (bool): If True, prints query status
    
    Returns:
        list of sqlite3.Row (or single Row) if successful, None if failed
    """
    if params is None:
        params = []
    
    try:
        # Ensure the data directory exists
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row  # Allows accessing columns by name: row['symbol']
        cursor = conn.cursor()
        cursor.execute(sql, params)
        
        if fetch_all:
            results = cursor.fetchall()
        else:
            results = cursor.fetchone()
        
        conn.close()
        
        if verbose:
            count = len(results) if fetch_all and results else (1 if results else 0)
            print(f"✅ Query executed. Rows returned: {count}")
        return results
    except Exception as e:
        print(f"❌ Query failed: {e}")
        return None

def pretty_print_rows(rows, columns=None):
    """
    Pretty-print query results in a table format.
    Useful for quickly viewing data in the console.
    """
    if not rows:
        print("(No rows to display)")
        return
    
    # If rows is a single Row object, put it in a list
    if not isinstance(rows, list):
        rows = [rows]
    
    # Get column names from the first row
    if columns is None:
        columns = rows[0].keys() if hasattr(rows[0], 'keys') else []
    
    if not columns:
        print("(No column names available)")
        return
    
    # Calculate column widths
    col_widths = {col: len(col) for col in columns}
    for row in rows:
        for col in columns:
            val = str(row[col]) if row[col] is not None else 'NULL'
            col_widths[col] = max(col_widths[col], len(val))
    
    # Print header
    header = " | ".join([col.ljust(col_widths[col]) for col in columns])
    print("-" * len(header))
    print(header)
    print("-" * len(header))
    
    # Print rows
    for row in rows:
        row_str = " | ".join([
            (str(row[col]) if row[col] is not None else 'NULL').ljust(col_widths[col])
            for col in columns
        ])
        print(row_str)
    print("-" * len(header))
    print(f"Total: {len(rows)} rows")

logger = setup_logger()

