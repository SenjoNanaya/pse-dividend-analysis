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
            check_struct_pass INTEGER,
            check_struct_eval INTEGER,
            info_incomplete INTEGER,
            div_yield REAL,
            roic REAL,
            debt_to_equity REAL,
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
            stockholders_equity REAL,
            total_current_liabilities REAL,
            cash_and_equivalents REAL,
            operating_income REAL,
            income_before_tax REAL,
            income_tax_expense REAL,
            gross_profit REAL,
            ga_expense REAL,
            cost_of_sales REAL,
            interest_expense REAL,
            other_expenses REAL,
            total_loans REAL,
            total_deposits REAL,
            npl REAL,
            net_interest_income REAL,
            allowance_for_credit_losses REAL,
            statement_scope TEXT,
            current_ratio REAL,
            quick_ratio REAL,
            outstanding_shares REAL,
            field_sources TEXT,
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
        ("roic", "REAL"),
        ("debt_to_equity", "REAL"),
        ("check_struct_pass", "INTEGER"),
        ("check_struct_eval", "INTEGER"),
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
        ("stockholders_equity", "REAL"),
        ("total_current_liabilities", "REAL"),
        ("cash_and_equivalents", "REAL"),
        ("operating_income", "REAL"),
        ("income_before_tax", "REAL"),
        ("income_tax_expense", "REAL"),
        ("gross_profit", "REAL"),
        ("ga_expense", "REAL"),
        ("cost_of_sales", "REAL"),
        ("interest_expense", "REAL"),
        ("other_expenses", "REAL"),
        ("total_loans", "REAL"),
        ("total_deposits", "REAL"),
        ("npl", "REAL"),
        ("net_interest_income", "REAL"),
        ("allowance_for_credit_losses", "REAL"),
        ("statement_scope", "TEXT"),
        ("field_sources", "TEXT"),
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
    from src.parser import sanitize_pe_for_persist

    cursor = conn.cursor()
    snapshot = snapshot or {}
    pe_write = (
        sanitize_pe_for_persist(snapshot.get("pe_ratio"))
        if "pe_ratio" in snapshot
        else None
    )

    cursor.execute("SELECT id FROM companies WHERE symbol = ?", (symbol,))
    row = cursor.fetchone()
    
    if row:
        company_id = row[0]
        # pe_ratio: when key is present, assign including NULL (clear absurd PE).
        # Other snapshot fields keep COALESCE so partial updates do not wipe them.
        if "pe_ratio" in snapshot:
            cursor.execute("""
                UPDATE companies
                SET name = ?, sector = ?, subsector = COALESCE(?, subsector),
                    ticker = COALESCE(?, ticker),
                    market_cap = COALESCE(?, market_cap),
                    outstanding_shares = COALESCE(?, outstanding_shares),
                    last_traded_price = COALESCE(?, last_traded_price),
                    pe_ratio = ?,
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
                pe_write,
                snapshot.get("pb_ratio"),
                snapshot.get("roe"),
                company_id,
            ))
        else:
            cursor.execute("""
                UPDATE companies
                SET name = ?, sector = ?, subsector = COALESCE(?, subsector),
                    ticker = COALESCE(?, ticker),
                    market_cap = COALESCE(?, market_cap),
                    outstanding_shares = COALESCE(?, outstanding_shares),
                    last_traded_price = COALESCE(?, last_traded_price),
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
        sanitize_pe_for_persist(snapshot.get("pe_ratio")),
        snapshot.get("pb_ratio"),
        snapshot.get("roe"),
    ))
    conn.commit()
    return cursor.lastrowid


def sanitize_roic_for_persist(roic):
    """Null absurd ROIC fractions (|ROIC| > 100%)."""
    from src.utils import safe_float

    v = safe_float(roic)
    if v is None or abs(v) > 1.0:
        return None
    return v


def update_company_screening(
    conn,
    company_id,
    check_pass_count,
    check_evaluable_total,
    info_incomplete,
    div_yield=None,
    check_struct_pass=None,
    check_struct_eval=None,
    roic=None,
    debt_to_equity=None,
):
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE companies
        SET check_pass_count = ?,
            check_evaluable_total = ?,
            info_incomplete = ?,
            div_yield = ?,
            roic = ?,
            debt_to_equity = ?,
            check_struct_pass = ?,
            check_struct_eval = ?
        WHERE id = ?
    """, (
        check_pass_count,
        check_evaluable_total,
        1 if info_incomplete else 0,
        div_yield,
        sanitize_roic_for_persist(roic),
        debt_to_equity,
        check_struct_pass,
        check_struct_eval,
        company_id,
    ))
    conn.commit()

_FINANCIAL_COLUMNS = (
    "revenue",
    "net_income",
    "eps",
    "book_value",
    "total_assets",
    "total_liabilities",
    "stockholders_equity",
    "total_current_liabilities",
    "cash_and_equivalents",
    "operating_income",
    "income_before_tax",
    "income_tax_expense",
    "gross_profit",
    "ga_expense",
    "cost_of_sales",
    "interest_expense",
    "other_expenses",
    "total_loans",
    "total_deposits",
    "npl",
    "net_interest_income",
    "allowance_for_credit_losses",
    "statement_scope",
    "current_ratio",
    "quick_ratio",
    "outstanding_shares",
)


def insert_financials(conn, company_id, fiscal_year, data):
    """
    Insert or replace financial data for a company/year.
    Optional data['field_sources']: dict or JSON string of column → source tag.
    """
    from src.field_sources import sources_to_json

    cursor = conn.cursor()
    raw_sources = data.get("field_sources")
    if isinstance(raw_sources, dict):
        sources_json = sources_to_json(raw_sources)
    elif isinstance(raw_sources, str) and raw_sources.strip():
        sources_json = raw_sources
    else:
        sources_json = None

    cursor.execute("""
        INSERT OR REPLACE INTO financials (
            company_id, fiscal_year, revenue, net_income, eps, 
            book_value, total_assets, total_liabilities, stockholders_equity,
            total_current_liabilities,
            cash_and_equivalents, operating_income, income_before_tax,
            income_tax_expense, gross_profit, ga_expense,
            cost_of_sales, interest_expense, other_expenses,
            total_loans, total_deposits, npl, net_interest_income,
            allowance_for_credit_losses,
            statement_scope,
            current_ratio, quick_ratio, outstanding_shares, field_sources
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        fiscal_year,
        data.get('revenue'),
        data.get('net_income'),
        data.get('eps'),
        data.get('book_value'),
        data.get('total_assets'),
        data.get('total_liabilities'),
        data.get('stockholders_equity'),
        data.get('total_current_liabilities'),
        data.get('cash_and_equivalents'),
        data.get('operating_income'),
        data.get('income_before_tax'),
        data.get('income_tax_expense'),
        data.get('gross_profit'),
        data.get('ga_expense'),
        data.get('cost_of_sales'),
        data.get('interest_expense'),
        data.get('other_expenses'),
        data.get('total_loans'),
        data.get('total_deposits'),
        data.get('npl'),
        data.get('net_interest_income'),
        data.get('allowance_for_credit_losses'),
        data.get('statement_scope'),
        data.get('current_ratio'),
        data.get('quick_ratio'),
        data.get('outstanding_shares'),
        sources_json,
    ))
    conn.commit()


def fill_financial_nulls(
    conn,
    company_id,
    fiscal_year,
    data,
    *,
    commit=True,
    treat_zero_as_null=(),
):
    """
    Update only columns that are currently NULL for company_id/fiscal_year.
    Tags filled columns as source ``backfill`` in field_sources.
    Returns list of column names that were filled.

    ``treat_zero_as_null``: columns (e.g. ``eps``) where stored 0.0 is treated
    as missing so EDGE-rounded placeholders can be replaced.
    """
    from src.field_sources import merge_source_tags, sources_from_json, sources_to_json

    zero_null = frozenset(treat_zero_as_null or ())
    cursor = conn.cursor()
    row = cursor.execute(
        """
        SELECT * FROM financials
        WHERE company_id = ? AND fiscal_year = ?
        """,
        (company_id, fiscal_year),
    ).fetchone()
    if not row:
        return []
    existing = dict(row)
    sets = []
    vals = []
    filled = []
    for col in _FINANCIAL_COLUMNS:
        if col not in data or data[col] is None:
            continue
        cur_val = existing.get(col)
        if cur_val is not None:
            if col not in zero_null:
                continue
            try:
                if float(cur_val) != 0.0:
                    continue
            except (TypeError, ValueError):
                continue
        sets.append(f"{col} = ?")
        vals.append(data[col])
        filled.append(col)
    if not filled:
        return []
    sources = merge_source_tags(
        sources_from_json(existing.get("field_sources")),
        filled,
        "backfill",
    )
    # Prefer derived/pdf tags from the merge row when present
    metric_sources = data.get("_field_sources") or {}
    for col in filled:
        tag = metric_sources.get(col)
        if tag in ("derived", "pdf", "html"):
            sources[col] = tag
    sources_json = sources_to_json(sources)
    sets.append("field_sources = ?")
    vals.append(sources_json)
    vals.extend([company_id, fiscal_year])
    cursor.execute(
        f"""
        UPDATE financials
        SET {", ".join(sets)}
        WHERE company_id = ? AND fiscal_year = ?
        """,
        vals,
    )
    if commit:
        conn.commit()
    return filled


# Absolute peso columns that may be rewritten when HTML was stored in thousands.
_SCALE_LIFT_COLUMNS = (
    "revenue",
    "net_income",
    "total_assets",
    "total_liabilities",
    "stockholders_equity",
    "total_current_liabilities",
    "operating_income",
    "income_before_tax",
    "income_tax_expense",
    "gross_profit",
    "ga_expense",
    "cost_of_sales",
    "interest_expense",
    "other_expenses",
    "total_loans",
    "total_deposits",
    "npl",
    "net_interest_income",
    "allowance_for_credit_losses",
)


def overwrite_financial_scale_lift(
    conn, company_id, fiscal_year, data, *, commit=True
):
    """
    Overwrite absolute columns when the merge lifted HTML thousands → pesos
    (new total_assets ≈ existing × 1000). Returns columns rewritten.
    """
    from src.field_sources import merge_source_tags, sources_from_json, sources_to_json

    cursor = conn.cursor()
    row = cursor.execute(
        """
        SELECT * FROM financials
        WHERE company_id = ? AND fiscal_year = ?
        """,
        (company_id, fiscal_year),
    ).fetchone()
    if not row:
        return []
    existing = dict(row)
    try:
        old_a = float(existing["total_assets"]) if existing.get("total_assets") is not None else None
        new_a = float(data["total_assets"]) if data.get("total_assets") is not None else None
    except (TypeError, ValueError, KeyError):
        return []
    if old_a is None or new_a is None or old_a <= 0:
        return []
    ratio = new_a / old_a
    if ratio < 800.0 or ratio > 1200.0:
        return []

    sets = []
    vals = []
    updated = []
    for col in _SCALE_LIFT_COLUMNS:
        if col not in data or data[col] is None:
            continue
        try:
            new_v = float(data[col])
        except (TypeError, ValueError):
            continue
        old_v = existing.get(col)
        if old_v is not None:
            try:
                if abs(float(old_v) - new_v) / max(abs(new_v), 1.0) < 1e-9:
                    continue
            except (TypeError, ValueError):
                pass
        sets.append(f"{col} = ?")
        vals.append(new_v)
        updated.append(col)
    if not updated:
        return []
    sources = merge_source_tags(
        sources_from_json(existing.get("field_sources")),
        updated,
        "scale_lift",
    )
    sources_json = sources_to_json(sources)
    sets.append("field_sources = ?")
    vals.append(sources_json)
    vals.extend([company_id, fiscal_year])
    cursor.execute(
        f"""
        UPDATE financials
        SET {", ".join(sets)}
        WHERE company_id = ? AND fiscal_year = ?
        """,
        vals,
    )
    if commit:
        conn.commit()
    return updated


def delete_out_of_range_financials(conn, company_id=None):
    """
    Delete financial rows with fiscal_year < 1995 or > current calendar year.
    Returns number of deleted rows.
    """
    from datetime import date

    cursor = conn.cursor()
    max_year = date.today().year
    if company_id is None:
        cur = cursor.execute(
            """
            DELETE FROM financials
            WHERE fiscal_year < 1995 OR fiscal_year > ?
            """,
            (max_year,),
        )
    else:
        cur = cursor.execute(
            """
            DELETE FROM financials
            WHERE company_id = ?
              AND (fiscal_year < 1995 OR fiscal_year > ?)
            """,
            (company_id, max_year),
        )
    conn.commit()
    return cur.rowcount

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