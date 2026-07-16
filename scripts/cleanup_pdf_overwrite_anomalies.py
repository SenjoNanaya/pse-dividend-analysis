"""
Repair rows corrupted by PDF overwrite of EDGE HTML figures:
  - negative cash_and_equivalents → NULL
  - identity-broken total_assets (A ≉ L+E by >15%) → A = L + E

Usage (from repo root):
  python scripts/cleanup_pdf_overwrite_anomalies.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src import db
from src.report_metrics import compute_screening_summary


IDENTITY_DRIFT = 0.15


def _identity_broken(a: float, l: float, e: float) -> bool:
    le = l + e
    denom = max(abs(a), abs(le))
    if denom <= 0:
        return False
    return abs(a - le) / denom > IDENTITY_DRIFT and l > 0 and e > 0 and l < le


def main():
    db.init_db()
    conn = db.get_connection()
    cur = conn.cursor()

    cash_rows = cur.execute(
        """
        SELECT f.id, c.ticker, f.fiscal_year, f.cash_and_equivalents
        FROM financials f
        JOIN companies c ON c.id = f.company_id
        WHERE f.cash_and_equivalents IS NOT NULL AND f.cash_and_equivalents < 0
        ORDER BY c.ticker, f.fiscal_year
        """
    ).fetchall()
    for r in cash_rows:
        print(
            f"NULL cash {r['ticker']} {r['fiscal_year']}: "
            f"{r['cash_and_equivalents']} → NULL"
        )
        cur.execute(
            "UPDATE financials SET cash_and_equivalents = NULL WHERE id = ?",
            (r["id"],),
        )

    asset_rows = cur.execute(
        """
        SELECT f.id, c.ticker, f.fiscal_year,
               f.total_assets, f.total_liabilities, f.stockholders_equity
        FROM financials f
        JOIN companies c ON c.id = f.company_id
        WHERE f.total_assets IS NOT NULL
          AND f.total_liabilities IS NOT NULL
          AND f.stockholders_equity IS NOT NULL
        ORDER BY c.ticker, f.fiscal_year
        """
    ).fetchall()
    asset_fixed = 0
    for r in asset_rows:
        a = float(r["total_assets"])
        l = float(r["total_liabilities"])
        e = float(r["stockholders_equity"])
        if not _identity_broken(a, l, e):
            continue
        new_a = l + e
        print(
            f"fix assets {r['ticker']} {r['fiscal_year']}: "
            f"{a:.4g} → {new_a:.4g} (L+E)"
        )
        cur.execute(
            "UPDATE financials SET total_assets = ? WHERE id = ?",
            (new_a, r["id"]),
        )
        asset_fixed += 1

    conn.commit()
    print(
        f"Updated {len(cash_rows)} negative cash row(s), "
        f"{asset_fixed} identity-broken asset row(s)."
    )

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
            [dict(f) for f in fins],
            dividends=[dict(d) for d in divs],
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
    print(f"Rescreened {updated} companies.")


if __name__ == "__main__":
    main()
