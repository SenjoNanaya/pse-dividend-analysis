"""Backfill companies.roic from latest computed ROIC (fraction)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db
from src.report_metrics import latest_roic_fraction


def _financials_for(cur, company_id):
    rows = cur.execute(
        """
        SELECT fiscal_year, revenue, net_income, eps, book_value,
               total_assets, total_liabilities, stockholders_equity,
               total_current_liabilities, cash_and_equivalents,
               operating_income, income_before_tax, income_tax_expense,
               gross_profit, ga_expense, statement_scope,
               current_ratio, quick_ratio, outstanding_shares
        FROM financials
        WHERE company_id = ?
        ORDER BY fiscal_year
        """,
        (company_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def main():
    db.init_db()
    conn = db.get_connection()
    cur = conn.cursor()

    companies = cur.execute(
        """
        SELECT id, ticker, sector, subsector, outstanding_shares
        FROM companies
        """
    ).fetchall()

    updated = 0
    nulls = 0
    for row in companies:
        company = dict(row)
        fin = _financials_for(cur, company["id"])
        roic = latest_roic_fraction(company, fin)
        cur.execute(
            "UPDATE companies SET roic = ? WHERE id = ?",
            (roic, company["id"]),
        )
        if roic is None:
            nulls += 1
        else:
            updated += 1

    conn.commit()
    print(f"roic set: {updated}, null: {nulls}")

    for t in ("BDO", "MBT", "ALI", "JFC", "SMC", "LFM", "TEL"):
        c = cur.execute(
            "SELECT ticker, sector, subsector, roic FROM companies WHERE ticker=?",
            (t,),
        ).fetchone()
        if not c:
            continue
        y = c["roic"]
        print(
            f"{t}: sector={c['sector']} "
            f"roic={None if y is None else round(y * 100, 2)}%"
        )

    conn.close()


if __name__ == "__main__":
    main()
