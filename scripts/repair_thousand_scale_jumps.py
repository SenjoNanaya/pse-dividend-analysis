"""
One-shot repair for ~1000× cross-year HTML scale mismatches.

Usage (from repo root):
  python scripts/repair_thousand_scale_jumps.py
  python scripts/repair_thousand_scale_jumps.py --tickers SM,JGS,PGOLD
  python scripts/repair_thousand_scale_jumps.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from src import db
from src.report_metrics import compute_screening_summary
from src.scale_guard import SCALE_ABSOLUTE_KEYS, repair_thousand_scale_jumps

DEFAULT_TICKERS = ("SM", "JGS", "PGOLD", "SHNG", "LC")

# DB columns that are absolute pesos (intersection with SCALE_ABSOLUTE_KEYS).
_DB_ABS_COLS = [
    k
    for k in (
        "revenue",
        "net_income",
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
    )
    if k in SCALE_ABSOLUTE_KEYS
]


def _rescreen(conn, company_id: int) -> None:
    cur = conn.cursor()
    company = cur.execute(
        """
        SELECT id, name, ticker, pe_ratio, pb_ratio, roe, market_cap,
               outstanding_shares, last_traded_price
        FROM companies WHERE id = ?
        """,
        (company_id,),
    ).fetchone()
    fins = cur.execute(
        """
        SELECT fiscal_year, revenue, net_income, eps, book_value,
               total_assets, total_liabilities, current_ratio, quick_ratio,
               outstanding_shares
        FROM financials WHERE company_id = ? ORDER BY fiscal_year
        """,
        (company_id,),
    ).fetchall()
    divs = cur.execute(
        """
        SELECT ex_date, amount AS rate, type, security, is_common
        FROM dividends WHERE company_id = ?
        """,
        (company_id,),
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
        company_id,
        screening["check_pass_count"],
        screening["check_evaluable_total"],
        screening["info_incomplete"],
        div_yield=screening.get("div_yield"),
        check_struct_pass=screening.get("check_struct_pass"),
        check_struct_eval=screening.get("check_struct_eval"),
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--tickers",
        default=",".join(DEFAULT_TICKERS),
        help="Comma-separated tickers (default: SM,JGS,PGOLD,SHNG,LC)",
    )
    ap.add_argument("--dry-run", action="store_true", help="Print actions only")
    args = ap.parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]

    db.init_db()
    conn = db.get_connection()
    cur = conn.cursor()

    repaired_companies = 0
    for ticker in tickers:
        co = cur.execute(
            "SELECT id, ticker, name, outstanding_shares FROM companies WHERE ticker = ?",
            (ticker,),
        ).fetchone()
        if not co:
            print(f"{ticker}: not found")
            continue

        rows = cur.execute(
            f"""
            SELECT id, fiscal_year, book_value, outstanding_shares,
                   {", ".join(_DB_ABS_COLS)}
            FROM financials
            WHERE company_id = ?
            ORDER BY fiscal_year
            """,
            (co["id"],),
        ).fetchall()
        if len(rows) < 2:
            print(f"{ticker}: <2 fiscal years, skip")
            continue

        yearly = {}
        for r in rows:
            y = int(r["fiscal_year"])
            row = {k: r[k] for k in _DB_ABS_COLS if r[k] is not None}
            # Anchors for equity ≈ BV×shares (never scaled)
            if r["book_value"] is not None:
                row["book_value"] = r["book_value"]
            if r["outstanding_shares"] is not None:
                row["outstanding_shares"] = r["outstanding_shares"]
            yearly[y] = row
        # Keep row ids for UPDATE
        id_by_year = {int(r["fiscal_year"]): r["id"] for r in rows}

        _, actions = repair_thousand_scale_jumps(
            yearly,
            inplace=True,
            shares_fallback=co["outstanding_shares"],
        )
        if not actions:
            print(f"{ticker}: no ~1000× jump to repair")
            continue

        print(f"{ticker} ({co['name']}):")
        for note in actions:
            print(f"  {note}")

        if args.dry_run:
            continue

        for year, row in yearly.items():
            sets = []
            vals = []
            for col in _DB_ABS_COLS:
                if col in row:
                    sets.append(f"{col} = ?")
                    vals.append(row[col])
            if not sets:
                continue
            vals.append(id_by_year[year])
            cur.execute(
                f"UPDATE financials SET {', '.join(sets)} WHERE id = ?",
                vals,
            )

        _rescreen(conn, co["id"])
        repaired_companies += 1

    if not args.dry_run:
        conn.commit()
    conn.close()
    print(
        f"Done. {'Dry-run; no writes.' if args.dry_run else f'Repaired {repaired_companies} company(ies).'}"
    )


if __name__ == "__main__":
    main()
