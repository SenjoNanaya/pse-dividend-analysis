"""
Repair financials OI / GP / GA / cash using sanity + intra-year scale guards.

- ga_expense → abs(ga) when negative
- Intra-year ×1000 harmonize for OI/GP/GA and cash vs NI/revenue/assets
- Insane GP → NULL; insane OI → NULL, then sane GP−|GA| when possible
- Rescreen touched companies (incl. persisted ROIC)

Usage (from repo root):
  python scripts/repair_operating_income.py --dry-run
  python scripts/repair_operating_income.py
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
    normalize_ga_expense,
    sanitize_operating_metrics,
)
from src.scale_guard import harmonize_intra_year_pl_scale
from src.utils import safe_float

_TRACK_COLS = (
    "operating_income",
    "gross_profit",
    "ga_expense",
    "cash_and_equivalents",
    "revenue",
    "net_income",
    "income_before_tax",
    "total_assets",
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db.init_db()
    conn = db.get_connection()
    cur = conn.cursor()

    rows = cur.execute(
        """
        SELECT f.id AS fin_id, f.company_id, f.fiscal_year,
               f.revenue, f.operating_income, f.gross_profit, f.ga_expense,
               f.net_income, f.income_before_tax, f.income_tax_expense,
               f.total_assets, f.total_liabilities, f.stockholders_equity,
               f.cash_and_equivalents, f.total_current_liabilities,
               f.statement_scope,
               c.ticker
        FROM financials f
        JOIN companies c ON c.id = f.company_id
        ORDER BY c.ticker, f.fiscal_year
        """
    ).fetchall()

    ga_flipped = 0
    oi_nulled = 0
    oi_derived = 0
    gp_nulled = 0
    scale_fixes = 0
    touched_companies: set[int] = set()
    samples: list[str] = []

    for r in rows:
        d = dict(r)
        before = {k: d.get(k) for k in _TRACK_COLS}
        metrics = {k: d.get(k) for k in _TRACK_COLS}
        metrics["income_tax_expense"] = d.get("income_tax_expense")
        metrics["total_liabilities"] = d.get("total_liabilities")
        metrics["stockholders_equity"] = d.get("stockholders_equity")
        metrics["total_current_liabilities"] = d.get("total_current_liabilities")

        ga = safe_float(metrics.get("ga_expense"))
        nga = normalize_ga_expense(ga)
        if ga is not None and nga is not None and ga < 0:
            metrics["ga_expense"] = nga
            ga_flipped += 1

        scale_msgs = harmonize_intra_year_pl_scale(metrics)
        if scale_msgs:
            scale_fixes += 1

        sanitize_operating_metrics(metrics)

        updates: dict[str, float | None] = {}
        for col in (
            "operating_income",
            "gross_profit",
            "ga_expense",
            "cash_and_equivalents",
        ):
            old = before.get(col)
            new = metrics.get(col)
            # Normalize None comparisons
            if old != new and not (
                old is None and new is None
            ):
                # float equality
                try:
                    if old is not None and new is not None and abs(float(old) - float(new)) < 1e-6:
                        continue
                except (TypeError, ValueError):
                    pass
                updates[col] = new

        if before.get("operating_income") is not None and metrics.get("operating_income") is None:
            oi_nulled += 1
        if (
            before.get("operating_income") != metrics.get("operating_income")
            and metrics.get("operating_income") is not None
            and metrics.get("operating_income_derived")
        ):
            oi_derived += 1
        if before.get("gross_profit") is not None and metrics.get("gross_profit") is None:
            gp_nulled += 1

        if not updates:
            continue

        touched_companies.add(int(d["company_id"]))
        if len(samples) < 24:
            bits = [f"{k}:{before.get(k)}→{updates[k]}" for k in updates]
            samples.append(f"{d['ticker']} FY{d['fiscal_year']}: " + "; ".join(bits))

        if args.dry_run:
            continue

        sets = []
        vals: list = []
        for col, val in updates.items():
            sets.append(f"{col} = ?")
            vals.append(val)
        vals.append(d["fin_id"])
        cur.execute(
            f"UPDATE financials SET {', '.join(sets)} WHERE id = ?",
            vals,
        )

    if not args.dry_run and touched_companies:
        for cid in sorted(touched_companies):
            co = cur.execute(
                """
                SELECT id, ticker, name, sector, subsector,
                       pe_ratio, pb_ratio, roe, market_cap,
                       outstanding_shares, last_traded_price
                FROM companies WHERE id = ?
                """,
                (cid,),
            ).fetchone()
            fins = [
                dict(x)
                for x in cur.execute(
                    """
                    SELECT fiscal_year, revenue, net_income, eps, book_value,
                           total_assets, total_liabilities, stockholders_equity,
                           outstanding_shares, current_ratio, quick_ratio,
                           cash_and_equivalents, total_current_liabilities,
                           operating_income, income_before_tax, income_tax_expense,
                           gross_profit, ga_expense, statement_scope
                    FROM financials WHERE company_id = ? ORDER BY fiscal_year
                    """,
                    (cid,),
                ).fetchall()
            ]
            divs = cur.execute(
                """
                SELECT ex_date, amount AS rate, type, security, is_common
                FROM dividends WHERE company_id = ?
                """,
                (cid,),
            ).fetchall()
            screening = compute_screening_summary(
                dict(co),
                fins,
                dividends=[dict(d) for d in divs],
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

    if not args.dry_run:
        conn.commit()
    conn.close()

    for line in samples:
        print(line)
    print(
        f"{'[dry-run] ' if args.dry_run else ''}"
        f"GA flipped: {ga_flipped}; scale years: {scale_fixes}; "
        f"OI nulled: {oi_nulled}; OI derived: {oi_derived}; GP nulled: {gp_nulled}; "
        f"companies touched: {len(touched_companies)}"
    )


if __name__ == "__main__":
    main()
