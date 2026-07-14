"""Backfill companies.div_yield from existing dividends + price."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db
from src.report_metrics import compute_div_yield


def main():
    db.init_db()
    conn = db.get_connection()
    cur = conn.cursor()

    companies = cur.execute("SELECT id, last_traded_price FROM companies").fetchall()
    updated = 0
    nulls = 0
    for row in companies:
        cid = row["id"]
        price = row["last_traded_price"]
        fin = cur.execute(
            """
            SELECT fiscal_year FROM financials
            WHERE company_id = ?
              AND (book_value IS NOT NULL OR net_income IS NOT NULL
                   OR total_assets IS NOT NULL OR revenue IS NOT NULL OR eps IS NOT NULL)
            ORDER BY fiscal_year DESC LIMIT 1
            """,
            (cid,),
        ).fetchone()
        latest_year = fin["fiscal_year"] if fin else None
        divs = cur.execute(
            """
            SELECT ex_date, amount, type, security, is_common
            FROM dividends WHERE company_id = ?
            """,
            (cid,),
        ).fetchall()
        dividends = [
            {
                "ex_date": d["ex_date"],
                "amount": d["amount"],
                "type": d["type"],
                "security": d["security"],
                "is_common": d["is_common"],
            }
            for d in divs
        ]
        y = compute_div_yield(price, dividends, latest_fiscal_year=latest_year)
        cur.execute("UPDATE companies SET div_yield = ? WHERE id = ?", (y, cid))
        if y is None:
            nulls += 1
        else:
            updated += 1
    conn.commit()
    sample = cur.execute(
        """
        SELECT ticker, last_traded_price, market_cap, div_yield
        FROM companies WHERE div_yield IS NOT NULL
        ORDER BY div_yield DESC LIMIT 8
        """
    ).fetchall()
    print(f"yields set: {updated}, null: {nulls}")
    for row in sample:
        print(dict(row))
    conn.close()


if __name__ == "__main__":
    main()
