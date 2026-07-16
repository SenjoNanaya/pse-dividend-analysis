"""
Sanity-check recently scraped companies (default: last calendar day in DB).

Usage (from any cwd):
  python scripts/sanity_check_rescrape.py
  python scripts/sanity_check_rescrape.py --since 2026-07-15
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from src import db
from src.utils import DB_PATH
from src.report_metrics import growth_rate, pe_check_pass, sanitize_pe_display

IDENTITY_DRIFT = 0.15
EXTREME_YOY = 3.0  # 300% absolute change
SCALE_JUMP = 50.0  # year-over-year magnitude ratio


def _identity_broken(a, l, e) -> bool:
    if a is None or l is None or e is None:
        return False
    a, l, e = float(a), float(l), float(e)
    le = l + e
    denom = max(abs(a), abs(le))
    if denom <= 0:
        return False
    return abs(a - le) / denom > IDENTITY_DRIFT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None, help="YYYY-MM-DD; default = latest day in DB")
    args = ap.parse_args()

    db.init_db()
    conn = db.get_connection()
    cur = conn.cursor()

    db_abs = os.path.abspath(DB_PATH)
    n_co = cur.execute("SELECT COUNT(*) AS c FROM companies").fetchone()["c"]
    n_lu = cur.execute(
        "SELECT COUNT(*) AS c FROM companies WHERE last_updated IS NOT NULL"
    ).fetchone()["c"]

    if args.since:
        since = args.since
    else:
        row = cur.execute(
            "SELECT substr(MAX(last_updated), 1, 10) AS d FROM companies"
        ).fetchone()
        since = row["d"] if row and row["d"] else None

    if not since:
        print("No companies with last_updated.")
        print(f"  cwd={os.getcwd()}")
        print(f"  db={db_abs} companies={n_co} with_last_updated={n_lu}")
        conn.close()
        return

    companies = cur.execute(
        """
        SELECT id, ticker, name, last_updated, pe_ratio, pb_ratio, roe,
               check_pass_count, check_evaluable_total, info_incomplete
        FROM companies
        WHERE substr(last_updated, 1, 10) >= ?
        ORDER BY last_updated DESC
        """,
        (since,),
    ).fetchall()

    findings = {
        "A_identity": [],
        "B_cash": [],
        "C_extreme_yoy": [],
        "D_pe": [],
        "E_scale_jump": [],
    }

    for co in companies:
        fins = cur.execute(
            """
            SELECT fiscal_year, revenue, net_income, eps, book_value,
                   total_assets, total_liabilities, stockholders_equity,
                   cash_and_equivalents, total_current_liabilities
            FROM financials
            WHERE company_id = ?
            ORDER BY fiscal_year
            """,
            (co["id"],),
        ).fetchall()
        ticker = co["ticker"]
        fin_rows = [dict(f) for f in fins]

        for f in fin_rows:
            if _identity_broken(
                f.get("total_assets"),
                f.get("total_liabilities"),
                f.get("stockholders_equity"),
            ):
                a = float(f["total_assets"])
                l = float(f["total_liabilities"])
                e = float(f["stockholders_equity"])
                findings["A_identity"].append(
                    {
                        "ticker": ticker,
                        "year": f["fiscal_year"],
                        "assets": a,
                        "liabilities": l,
                        "equity": e,
                        "implied": l + e,
                        "drift": abs(a - (l + e)) / max(abs(a), abs(l + e)),
                    }
                )

        for f in fin_rows:
            cash = f.get("cash_and_equivalents")
            assets = f.get("total_assets")
            if cash is None:
                continue
            cash = float(cash)
            if cash < 0:
                findings["B_cash"].append(
                    {
                        "ticker": ticker,
                        "year": f["fiscal_year"],
                        "cash": cash,
                        "reason": "negative",
                    }
                )
            elif (
                assets is not None
                and abs(float(assets)) > 0
                and cash > abs(float(assets)) * 1.05
            ):
                findings["B_cash"].append(
                    {
                        "ticker": ticker,
                        "year": f["fiscal_year"],
                        "cash": cash,
                        "assets": float(assets),
                        "reason": "exceeds_assets",
                    }
                )

        for key, flag_key in (("total_assets", "assets"), ("net_income", "net_income")):
            for i in range(1, len(fin_rows)):
                prev, curr = fin_rows[i - 1], fin_rows[i]
                rate = growth_rate(prev.get(key), curr.get(key), key=key)
                raw_prev = prev.get(key)
                raw_curr = curr.get(key)
                raw_ratio = None
                if raw_prev not in (None, 0) and raw_curr is not None:
                    try:
                        raw_ratio = abs(float(raw_curr) / float(raw_prev))
                    except (TypeError, ValueError, ZeroDivisionError):
                        raw_ratio = None
                if (rate is not None and abs(rate) > EXTREME_YOY) or (
                    raw_ratio is not None
                    and raw_ratio > (1 + EXTREME_YOY)
                    and key == "total_assets"
                ):
                    findings["C_extreme_yoy"].append(
                        {
                            "ticker": ticker,
                            "metric": flag_key,
                            "from": prev["fiscal_year"],
                            "to": curr["fiscal_year"],
                            "prev": raw_prev,
                            "curr": raw_curr,
                            "rate": rate,
                            "raw_ratio": raw_ratio,
                        }
                    )

        pe = co["pe_ratio"]
        pe_pass = pe_check_pass(pe, 22)
        pe_show = sanitize_pe_display(pe)
        if pe is not None and float(pe) <= 0:
            findings["D_pe"].append(
                {
                    "ticker": ticker,
                    "pe": pe,
                    "pe_pass": pe_pass,
                    "pe_display": pe_show,
                }
            )
        elif pe_pass is True and pe is not None and float(pe) > 100:
            findings["D_pe"].append(
                {
                    "ticker": ticker,
                    "pe": pe,
                    "pe_pass": pe_pass,
                    "reason": "very_high_but_pass",
                }
            )

        for i in range(1, len(fin_rows)):
            a0, a1 = fin_rows[i - 1].get("total_assets"), fin_rows[i].get("total_assets")
            if a0 in (None, 0) or a1 in (None, 0):
                continue
            a0, a1 = abs(float(a0)), abs(float(a1))
            ratio = max(a0, a1) / min(a0, a1)
            if ratio >= SCALE_JUMP:
                findings["E_scale_jump"].append(
                    {
                        "ticker": ticker,
                        "from": fin_rows[i - 1]["fiscal_year"],
                        "to": fin_rows[i]["fiscal_year"],
                        "a0": a0,
                        "a1": a1,
                        "ratio": ratio,
                    }
                )

    summary = {k: len(v) for k, v in findings.items()}
    print(f"Sanity check since {since}: {len(companies)} companies")
    print(f"  db={db_abs}")
    print(f"  A identity broken rows: {summary['A_identity']}")
    print(f"  B bad cash rows:        {summary['B_cash']}")
    print(f"  C extreme YoY events:   {summary['C_extreme_yoy']}")
    print(f"  D nonpositive/odd PE:   {summary['D_pe']}")
    print(f"  E asset scale jumps:    {summary['E_scale_jump']}")

    for label, key in (
        ("Identity", "A_identity"),
        ("Cash", "B_cash"),
        ("Extreme YoY", "C_extreme_yoy"),
        ("PE", "D_pe"),
        ("Scale jump", "E_scale_jump"),
    ):
        rows = findings[key]
        if not rows:
            continue
        print(f"\n{label} samples:")
        for row in rows[:12]:
            print(f"  {row}")

    conn.close()


if __name__ == "__main__":
    main()
