"""
Repair companies.roe when disclosure FR looks double-scaled vs NI/equity.

Also undoes prior over-repairs where |roe| > 100% was written from bad equity.

Usage (from repo root):
  python scripts/repair_roe_from_equity.py
  python scripts/repair_roe_from_equity.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from src import db
from src.report_metrics import (
    compute_screening_summary,
    equity_for_roe,
    prefer_roe,
)
from src.utils import safe_float


def _choose_roe(stored, nie) -> float | None:
    """
    stored: current companies.roe (may already be mangled to |roe|>1)
    nie: NI / statement equity
    """
    s = safe_float(stored)
    c = safe_float(nie)
    if c is not None and abs(c) > 2.0:
        c = None

    # Undo accidental write of absurd NI/E (e.g. -6.31 instead of -0.063)
    if s is not None and abs(s) > 1.0:
        undone = s / 100.0
        if c is not None:
            return prefer_roe(undone, c)
        return undone

    return prefer_roe(s, c)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db.init_db()
    conn = db.get_connection()
    cur = conn.cursor()
    companies = cur.execute(
        """
        SELECT id, ticker, name, pe_ratio, pb_ratio, roe, market_cap,
               outstanding_shares, last_traded_price
        FROM companies
        ORDER BY ticker
        """
    ).fetchall()

    fixed = 0
    for co in companies:
        fins = [
            dict(r)
            for r in cur.execute(
                """
                SELECT fiscal_year, revenue, net_income, eps, book_value,
                       total_assets, total_liabilities, stockholders_equity,
                       outstanding_shares, current_ratio, quick_ratio
                FROM financials WHERE company_id = ? ORDER BY fiscal_year
                """,
                (co["id"],),
            ).fetchall()
        ]
        if not fins:
            continue
        latest = fins[-1]
        ni = safe_float(latest.get("net_income"))
        equity = equity_for_roe(latest, dict(co))
        nie = (
            ni / equity if ni is not None and equity is not None and abs(equity) > 0 else None
        )
        scraped = safe_float(co["roe"])
        chosen = _choose_roe(scraped, nie)
        if chosen is None:
            continue
        if scraped is not None and abs(chosen - scraped) < 1e-6:
            continue
        if scraped is not None and abs(chosen - scraped) / max(abs(scraped), 1e-12) < 0.02:
            continue

        print(
            f"{co['ticker']}: roe {scraped} → {chosen:.6f} "
            f"(NI/E={nie})"
        )
        if args.dry_run:
            fixed += 1
            continue

        cur.execute(
            "UPDATE companies SET roe = ? WHERE id = ?",
            (chosen, co["id"]),
        )
        divs = cur.execute(
            """
            SELECT ex_date, amount AS rate, type, security, is_common
            FROM dividends WHERE company_id = ?
            """,
            (co["id"],),
        ).fetchall()
        screening = compute_screening_summary(
            {
                "name": co["name"],
                "ticker": co["ticker"],
                "pe_ratio": co["pe_ratio"],
                "pb_ratio": co["pb_ratio"],
                "roe": chosen,
                "market_cap": co["market_cap"],
                "outstanding_shares": co["outstanding_shares"],
                "last_traded_price": co["last_traded_price"],
            },
            fins,
            dividends=[dict(d) for d in divs],
        )
        db.update_company_screening(
            conn,
            co["id"],
            screening["check_pass_count"],
            screening["check_evaluable_total"],
            screening["info_incomplete"],
            div_yield=screening.get("div_yield"),
            roic=screening.get("roic"),
            debt_to_equity=screening.get("debt_to_equity"),
            check_struct_pass=screening.get("check_struct_pass"),
            check_struct_eval=screening.get("check_struct_eval"),
        )
        fixed += 1

    if not args.dry_run:
        conn.commit()
    conn.close()
    print(
        f"Done. {'Would fix' if args.dry_run else 'Fixed'} {fixed} company ROE row(s)."
    )


if __name__ == "__main__":
    main()
