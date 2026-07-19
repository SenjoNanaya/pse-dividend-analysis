"""
Null absurd or non-meaningful companies.pe_ratio / roic values.

Clears PE when:
  - |pe_ratio| > 100 (persist ceiling)
  - pe_ratio == 0 (placeholder)
  - secondary listings (MFC, SLF)
  - ETF / funds (FMETF, FFI)

Clears ROIC when:
  - |roic| > 1.0 (100%)

Usage (from repo root):
  python scripts/cleanup_absurd_pe.py
  python scripts/cleanup_absurd_pe.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from src import db
from src.parser import (
    NON_OPERATING_PE_TICKERS,
    PE_COMPUTE_ABS_MAX,
    SECONDARY_LISTING_TICKERS,
)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Null absurd PE / dual-list / fund PE and absurd ROIC"
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Write changes (default is dry-run)",
    )
    args = ap.parse_args()

    db.init_db()
    conn = db.get_connection()
    cur = conn.cursor()

    pe_tickers = sorted(SECONDARY_LISTING_TICKERS | NON_OPERATING_PE_TICKERS)
    placeholders = ",".join("?" for _ in pe_tickers)

    pe_rows = cur.execute(
        f"""
        SELECT id, ticker, name, pe_ratio
        FROM companies
        WHERE pe_ratio IS NOT NULL
          AND (
            ABS(pe_ratio) > ?
            OR pe_ratio = 0
            OR UPPER(COALESCE(ticker, '')) IN ({placeholders})
          )
        ORDER BY ABS(pe_ratio) DESC
        """,
        (PE_COMPUTE_ABS_MAX, *pe_tickers),
    ).fetchall()

    roic_rows = cur.execute(
        """
        SELECT id, ticker, name, roic
        FROM companies
        WHERE roic IS NOT NULL AND ABS(roic) > 1.0
        ORDER BY ABS(roic) DESC
        """
    ).fetchall()

    print(
        f"Would clear pe_ratio on {len(pe_rows)} company(ies) "
        f"(threshold={PE_COMPUTE_ABS_MAX}):"
    )
    for r in pe_rows:
        print(f"  {r['ticker'] or '?':8} PE={r['pe_ratio']!r}  {r['name']}")

    print(f"\nWould clear roic on {len(roic_rows)} company(ies) (|roic| > 1):")
    for r in roic_rows:
        pct = (r["roic"] or 0) * 100.0
        print(f"  {r['ticker'] or '?':8} ROIC%={pct:.1f}  {r['name']}")

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to write.")
        conn.close()
        return 0

    cur.execute(
        f"""
        UPDATE companies
        SET pe_ratio = NULL, last_updated = CURRENT_TIMESTAMP
        WHERE pe_ratio IS NOT NULL
          AND (
            ABS(pe_ratio) > ?
            OR pe_ratio = 0
            OR UPPER(COALESCE(ticker, '')) IN ({placeholders})
          )
        """,
        (PE_COMPUTE_ABS_MAX, *pe_tickers),
    )
    pe_n = cur.rowcount

    cur.execute(
        """
        UPDATE companies
        SET roic = NULL, last_updated = CURRENT_TIMESTAMP
        WHERE roic IS NOT NULL AND ABS(roic) > 1.0
        """
    )
    roic_n = cur.rowcount
    conn.commit()
    print(f"\nCleared pe_ratio on {pe_n} company(ies); roic on {roic_n} company(ies).")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
