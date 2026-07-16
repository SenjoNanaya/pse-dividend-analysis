"""
Remove misparsed entitlement / digit-strip dividend rows, then recompute yields.

- DELETE rows with amount >= 5 that share an ex-date with a property/stock
  sibling (LFM 197 beside a real property entitlement) — any type, including
  prior cash→property retags that still display as ₱197 in the UI.
- DELETE cash amount > 1000 PHP/share (JOH-scale junk).
- Recompute companies.div_yield via strict TTM cash DPS.

Usage (from repo root):
  python scripts/repair_dividend_anomalies.py --dry-run
  python scripts/repair_dividend_anomalies.py
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from src import db
from src.report_metrics import compute_div_yield


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db.init_db()
    conn = db.get_connection()
    cur = conn.cursor()

    # Keep the smaller property/stock marker; drop large sibling "rates"
    # (entitlement misparses like LFM 197 next to property amount 1).
    sibling_rows = cur.execute(
        """
        SELECT d.id, c.ticker, d.ex_date, d.amount, d.type
        FROM dividends d
        JOIN companies c ON c.id = d.company_id
        WHERE d.amount >= 5
          AND EXISTS (
            SELECT 1 FROM dividends d2
            WHERE d2.company_id = d.company_id
              AND d2.ex_date = d.ex_date
              AND d2.id != d.id
              AND d2.type IN ('property', 'stock')
              AND (d2.amount IS NULL OR d2.amount < 5)
          )
        ORDER BY c.ticker, d.ex_date
        """
    ).fetchall()

    absurd_rows = cur.execute(
        """
        SELECT d.id, c.ticker, d.ex_date, d.amount, d.type
        FROM dividends d
        JOIN companies c ON c.id = d.company_id
        WHERE d.type IN ('cash', 'other') AND d.amount > 1000
        ORDER BY d.amount DESC
        """
    ).fetchall()

    delete_ids = {r["id"] for r in sibling_rows} | {r["id"] for r in absurd_rows}

    print(f"Sibling junk delete candidates: {len(sibling_rows)}")
    for r in sibling_rows[:20]:
        print(f"  {r['ticker']} {r['ex_date']} amount={r['amount']} type={r['type']}")
    print(f"Absurd delete candidates: {len(absurd_rows)}")
    for r in absurd_rows[:10]:
        print(f"  {r['ticker']} {r['ex_date']} amount={r['amount']}")

    if not args.dry_run and delete_ids:
        cur.executemany(
            "DELETE FROM dividends WHERE id = ?",
            [(i,) for i in sorted(delete_ids)],
        )

    # Legacy null-security duplicates of a COMMON twin
    legacy = cur.execute(
        """
        SELECT d.id, c.ticker, d.ex_date, d.amount
        FROM dividends d
        JOIN companies c ON c.id = d.company_id
        WHERE (d.security IS NULL OR d.security = '')
          AND EXISTS (
            SELECT 1 FROM dividends d2
            WHERE d2.company_id = d.company_id
              AND d2.ex_date = d.ex_date
              AND ABS(COALESCE(d2.amount, 0) - COALESCE(d.amount, 0)) < 1e-9
              AND COALESCE(d2.type, 'cash') = COALESCE(d.type, 'cash')
              AND d2.security IS NOT NULL AND d2.security != ''
          )
        """
    ).fetchall()
    print(f"Legacy null-security dupes: {len(legacy)}")
    if not args.dry_run and legacy:
        cur.executemany(
            "DELETE FROM dividends WHERE id = ?",
            [(r["id"],) for r in legacy],
        )
        delete_ids |= {r["id"] for r in legacy}

    # Recompute yields for all companies
    companies = cur.execute(
        "SELECT id, ticker, last_traded_price FROM companies"
    ).fetchall()
    updated = 0
    for co in companies:
        divs = [
            dict(d)
            for d in cur.execute(
                """
                SELECT ex_date, amount, type, security, is_common
                FROM dividends WHERE company_id = ?
                """,
                (co["id"],),
            ).fetchall()
        ]
        y = compute_div_yield(co["last_traded_price"], divs)
        if not args.dry_run:
            cur.execute(
                "UPDATE companies SET div_yield = ? WHERE id = ?",
                (y, co["id"]),
            )
        updated += 1

    if not args.dry_run:
        conn.commit()

    # Spot-check LFM
    lfm = cur.execute(
        """
        SELECT d.ex_date, d.amount, d.type, d.security
        FROM dividends d
        JOIN companies c ON c.id = d.company_id
        WHERE c.ticker = 'LFM'
        ORDER BY d.ex_date DESC, d.amount DESC
        """
    ).fetchall()
    print("LFM dividends after repair:")
    for r in lfm:
        print(f"  {dict(r)}")
    y = cur.execute(
        "SELECT div_yield, last_traded_price FROM companies WHERE ticker='LFM'"
    ).fetchone()
    if y:
        print(
            f"LFM yield={None if y['div_yield'] is None else round(y['div_yield']*100, 2)}% "
            f"price={y['last_traded_price']}"
        )

    conn.close()
    print(
        f"{'[dry-run] ' if args.dry_run else ''}"
        f"sibling deletes={len(sibling_rows)}; absurd deletes={len(absurd_rows)}; "
        f"rows removed={len(delete_ids)}; yields refreshed={updated}"
    )


if __name__ == "__main__":
    main()
