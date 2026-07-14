import sqlite3
import os
from datetime import datetime
from src.utils import logger, DB_PATH  # Import DB_PATH from utils

def get_connection():
    """Get a database connection with foreign keys enabled."""
    # Ensure the data directory exists
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row  # Allows accessing columns by name
    return conn

def init_db():
    """Create all tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Companies table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT UNIQUE NOT NULL,
            name TEXT,
            sector TEXT,
            ticker TEXT,
            market_cap REAL,
            outstanding_shares REAL,
            last_traded_price REAL,
            pe_ratio REAL,
            pb_ratio REAL,
            roe REAL,
            subsector TEXT,
            check_pass_count INTEGER,
            check_evaluable_total INTEGER,
            info_incomplete INTEGER,
            div_yield REAL,
            last_updated DATETIME
        )
    """)
    _ensure_company_columns(cursor)
    
    # Financials table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS financials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER,
            fiscal_year INTEGER,
            revenue REAL,
            net_income REAL,
            eps REAL,
            book_value REAL,
            total_assets REAL,
            total_liabilities REAL,
            current_ratio REAL,
            quick_ratio REAL,
            outstanding_shares REAL,
            UNIQUE(company_id, fiscal_year),
            FOREIGN KEY(company_id) REFERENCES companies(id)
        )
    """)
    _ensure_financial_columns(cursor)
    
    # Dividends table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dividends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER,
            ex_date DATE,
            record_date DATE,
            payment_date DATE,
            amount REAL,
            type TEXT,
            security TEXT,
            is_common INTEGER,
            FOREIGN KEY(company_id) REFERENCES companies(id)
        )
    """)
    _ensure_dividend_columns(cursor)
    
    # Processing log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processing_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER,
            run_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT,
            error_message TEXT,
            FOREIGN KEY(company_id) REFERENCES companies(id)
        )
    """)
    
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully.")

def _ensure_company_columns(cursor):
    """Add snapshot columns on existing SQLite DBs created before they existed."""
    existing = {row[1] for row in cursor.execute("PRAGMA table_info(companies)").fetchall()}
    for col, decl in (
        ("ticker", "TEXT"),
        ("market_cap", "REAL"),
        ("outstanding_shares", "REAL"),
        ("last_traded_price", "REAL"),
        ("pe_ratio", "REAL"),
        ("pb_ratio", "REAL"),
        ("roe", "REAL"),
    ):
        if col not in existing:
            cursor.execute(f"ALTER TABLE companies ADD COLUMN {col} {decl}")

    for col, decl in (
        ("subsector", "TEXT"),
        ("check_pass_count", "INTEGER"),
        ("check_evaluable_total", "INTEGER"),
        ("info_incomplete", "INTEGER"),
        ("div_yield", "REAL"),
    ):
        if col not in existing:
            cursor.execute(f"ALTER TABLE companies ADD COLUMN {col} {decl}")


def _ensure_financial_columns(cursor):
    """Add ratio columns on existing SQLite DBs created before they existed."""
    existing = {row[1] for row in cursor.execute("PRAGMA table_info(financials)").fetchall()}
    for col, decl in (
        ("current_ratio", "REAL"),
        ("quick_ratio", "REAL"),
        ("outstanding_shares", "REAL"),
    ):
        if col not in existing:
            cursor.execute(f"ALTER TABLE financials ADD COLUMN {col} {decl}")


def _ensure_dividend_columns(cursor):
    """Add dividend detail columns on existing SQLite DBs."""
    existing = {row[1] for row in cursor.execute("PRAGMA table_info(dividends)").fetchall()}
    for col, decl in (
        ("record_date", "DATE"),
        ("security", "TEXT"),
        ("is_common", "INTEGER"),
    ):
        if col not in existing:
            cursor.execute(f"ALTER TABLE dividends ADD COLUMN {col} {decl}")


def get_or_create_company(conn, symbol, name, sector=None, subsector=None, snapshot=None):
    """Get company ID, or insert if not exists. Optional market snapshot updates."""
    cursor = conn.cursor()
    snapshot = snapshot or {}
    
    cursor.execute("SELECT id FROM companies WHERE symbol = ?", (symbol,))
    row = cursor.fetchone()
    
    if row:
        company_id = row[0]
        cursor.execute("""
            UPDATE companies 
            SET name = ?, sector = ?, subsector = COALESCE(?, subsector), ticker = COALESCE(?, ticker),
                market_cap = COALESCE(?, market_cap),
                outstanding_shares = COALESCE(?, outstanding_shares),
                last_traded_price = COALESCE(?, last_traded_price),
                pe_ratio = COALESCE(?, pe_ratio),
                pb_ratio = COALESCE(?, pb_ratio),
                roe = COALESCE(?, roe),
                last_updated = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, (
            name,
            sector,
            subsector,
            snapshot.get("ticker"),
            snapshot.get("market_cap"),
            snapshot.get("outstanding_shares"),
            snapshot.get("last_traded_price"),
            snapshot.get("pe_ratio"),
            snapshot.get("pb_ratio"),
            snapshot.get("roe"),
            company_id,
        ))
        conn.commit()
        return company_id

    cursor.execute("""
        INSERT INTO companies (
            symbol, name, sector, subsector, ticker, market_cap,
            outstanding_shares, last_traded_price, pe_ratio, pb_ratio, roe, last_updated
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (
        symbol,
        name,
        sector,
        subsector,
        snapshot.get("ticker"),
        snapshot.get("market_cap"),
        snapshot.get("outstanding_shares"),
        snapshot.get("last_traded_price"),
        snapshot.get("pe_ratio"),
        snapshot.get("pb_ratio"),
        snapshot.get("roe"),
    ))
    conn.commit()
    return cursor.lastrowid


def update_company_screening(conn, company_id, check_pass_count, check_evaluable_total, info_incomplete, div_yield=None):
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE companies
        SET check_pass_count = ?,
            check_evaluable_total = ?,
            info_incomplete = ?,
            div_yield = ?
        WHERE id = ?
    """, (
        check_pass_count,
        check_evaluable_total,
        1 if info_incomplete else 0,
        div_yield,
        company_id,
    ))
    conn.commit()

def insert_financials(conn, company_id, fiscal_year, data):
    """
    Insert or replace financial data for a company/year.
    data: revenue, net_income, eps, book_value, total_assets, total_liabilities,
          current_ratio, quick_ratio, outstanding_shares
    """
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT OR REPLACE INTO financials (
            company_id, fiscal_year, revenue, net_income, eps, 
            book_value, total_assets, total_liabilities,
            current_ratio, quick_ratio, outstanding_shares
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        fiscal_year,
        data.get('revenue'),
        data.get('net_income'),
        data.get('eps'),
        data.get('book_value'),
        data.get('total_assets'),
        data.get('total_liabilities'),
        data.get('current_ratio'),
        data.get('quick_ratio'),
        data.get('outstanding_shares'),
    ))
    conn.commit()

def insert_dividend(conn, company_id, dividend_data):
    """
    Insert a dividend record.
    dividend_data: ex_date, record_date, payment_date, amount, type, security, is_common
    """
    cursor = conn.cursor()
    security = dividend_data.get('security') or 'COMMON'
    is_common = 1 if dividend_data.get('is_common', True) else 0
    ex_date = dividend_data.get('ex_date')
    amount = dividend_data.get('amount')

    cursor.execute("""
        SELECT id FROM dividends
        WHERE company_id = ? AND ex_date = ?
          AND COALESCE(security, '') = ?
          AND (
            (amount IS NULL AND ? IS NULL)
            OR (amount IS NOT NULL AND ABS(amount - ?) < 1e-12)
          )
    """, (company_id, ex_date, security, amount, amount))

    row = cursor.fetchone()
    fields = (
        dividend_data.get('record_date'),
        dividend_data.get('payment_date'),
        amount,
        dividend_data.get('type', 'cash'),
        security,
        is_common,
    )
    if row:
        cursor.execute("""
            UPDATE dividends
            SET record_date = ?, payment_date = ?, amount = ?, type = ?,
                security = ?, is_common = ?
            WHERE id = ?
        """, (*fields, row[0]))
    else:
        cursor.execute("""
            INSERT INTO dividends (
                company_id, ex_date, record_date, payment_date, amount, type, security, is_common
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (company_id, ex_date, *fields))
    conn.commit()

def log_processing(conn, company_id, status, error_message=None):
    """Log the processing result for a company."""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO processing_log (company_id, status, error_message)
        VALUES (?, ?, ?)
    """, (company_id, status, error_message))
    conn.commit()

def is_company_processed_recently(conn, company_id, hours=24):
    """
    Check if a company was successfully processed in the last X hours.
    Returns True if we should skip it.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 1 FROM processing_log 
        WHERE company_id = ? AND status = 'success' 
        AND run_timestamp > datetime('now', '-' || ? || ' hours')
        LIMIT 1
    """, (company_id, hours))
    return cursor.fetchone() is not None

def close_connection(conn):
    """Close the database connection."""
    if conn:
        conn.close()