"""
Delete junk fiscal-year rows created by mis-parsed PDF year detection
(e.g. 2031, 2050) and recompute screening summaries.

Usage (from repo root):
  python scripts/cleanup_junk_fiscal_years.py
"""
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src import db
from src.report_metrics import compute_screening_summary


def main():
    db.init_db()
    conn = db.get_connection()
    max_year = date.today().year
    cur = conn.cursor()
    junk = cur.execute(
        """
        SELECT id, company_id, fiscal_year
        FROM financials
        WHERE fiscal_year < 1995 OR fiscal_year > ?
        """,
        (max_year,),
    ).fetchall()
    if not junk:
        print("No junk fiscal-year rows found.")
    else:
        ids = [r["id"] for r in junk]
        cur.executemany("DELETE FROM financials WHERE id = ?", [(i,) for i in ids])
        conn.commit()
        print(f"Deleted {len(ids)} junk financial row(s):")
        for r in junk[:20]:
            print(f"  company_id={r['company_id']} year={r['fiscal_year']}")
        if len(junk) > 20:
            print(f"  ... and {len(junk) - 20} more")

    # Rebuild screening so CHECKS / dilution reflect cleaned years
    companies = cur.execute(
        "SELECT id, name, ticker, pe_ratio, pb_ratio, roe, market_cap, "
        "outstanding_shares, last_traded_price FROM companies"
    ).fetchall()
    updated = 0
    for company in companies:
        fins = cur.execute(
            """
            SELECT fiscal_year, revenue, net_income, eps, book_value,
                   total_assets, total_liabilities, current_ratio, quick_ratio,
                   outstanding_shares
            FROM financials WHERE company_id = ? ORDER BY fiscal_year
            """,
            (company["id"],),
        ).fetchall()
        divs = cur.execute(
            """
            SELECT ex_date, amount AS rate, type, security, is_common
            FROM dividends WHERE company_id = ?
            """,
            (company["id"],),
        ).fetchall()
        financial_rows = [dict(f) for f in fins]
        dividends = [dict(d) for d in divs]
        screening = compute_screening_summary(
            {
                "name": company["name"],
                "ticker": company["ticker"],
                "pe_ratio": company["pe_ratio"],
                "pb_ratio": company["pb_ratio"],
                "roe": company["roe"],
                "market_cap": company["market_cap"],
                "outstanding_shares": company["outstanding_shares"],
                "last_traded_price": company["last_traded_price"],
            },
            financial_rows,
            dividends=dividends,
        )
        db.update_company_screening(
            conn,
            company["id"],
            screening["check_pass_count"],
            screening["check_evaluable_total"],
            screening["info_incomplete"],
            div_yield=screening.get("div_yield"),
            roic=screening.get("roic"),
            debt_to_equity=screening.get("debt_to_equity"),
            check_struct_pass=screening.get("check_struct_pass"),
            check_struct_eval=screening.get("check_struct_eval"),
        )
        updated += 1

    conn.close()
    print(f"Rescreened {updated} compan(y/ies).")


if __name__ == "__main__":
    main()
