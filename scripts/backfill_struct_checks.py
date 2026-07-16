"""Backfill check_struct_pass / check_struct_eval for hybrid live checklist rescoring."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db
from src.report_metrics import compute_screening_summary


def main():
    db.init_db()
    conn = db.get_connection()
    cur = conn.cursor()
    companies = cur.execute(
        "SELECT id, name, ticker, sector, subsector, pe_ratio, pb_ratio, roe, "
        "market_cap, outstanding_shares, last_traded_price FROM companies"
    ).fetchall()

    updated = 0
    for row in companies:
        cid = row["id"]
        fins = cur.execute(
            """
            SELECT fiscal_year, revenue, net_income, eps, book_value,
                   total_assets, total_liabilities, stockholders_equity,
                   current_ratio, quick_ratio, outstanding_shares
            FROM financials WHERE company_id = ? ORDER BY fiscal_year
            """,
            (cid,),
        ).fetchall()
        financial_rows = [dict(f) for f in fins]
        divs = cur.execute(
            """
            SELECT ex_date, record_date, payment_date, amount, type, security, is_common
            FROM dividends WHERE company_id = ?
            """,
            (cid,),
        ).fetchall()
        dividends = [dict(d) for d in divs]

        screening = compute_screening_summary(
            {
                "name": row["name"],
                "ticker": row["ticker"],
                "sector": row["sector"],
                "subsector": row["subsector"],
                "pe_ratio": row["pe_ratio"],
                "pb_ratio": row["pb_ratio"],
                "roe": row["roe"],
                "market_cap": row["market_cap"],
                "outstanding_shares": row["outstanding_shares"],
                "last_traded_price": row["last_traded_price"],
            },
            financial_rows,
            dividends=dividends,
        )
        db.update_company_screening(
            conn,
            cid,
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
        if updated % 50 == 0:
            print(f"... {updated}/{len(companies)}")

    print(f"updated structural scores for {updated} companies")
    conn.close()


if __name__ == "__main__":
    main()
