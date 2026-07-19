"""
Rescrape thin_core_history tickers that have EDGE annual filings available.

Uses main.py queue with --skip-recent 0 so older years can be pulled again.

Usage:
  python scripts/backfill_thin_core_history.py --dry-run
  python scripts/backfill_thin_core_history.py --limit 5
  python scripts/backfill_thin_core_history.py
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from pathlib import Path

from scripts.review_common import filings_dir_for_company
from src import db
from src.report_metrics import data_warnings


def _pdf_count(company: dict) -> int:
    d = filings_dir_for_company(company)
    if not d or not Path(d).is_dir():
        return 0
    return sum(1 for _ in Path(d).rglob("*.pdf"))


def _thin_tickers(cur, *, min_pdfs: int = 0) -> list[str]:
    out = []
    for co in cur.execute(
        "SELECT * FROM companies ORDER BY ticker"
    ).fetchall():
        co = dict(co)
        fins = [
            dict(x)
            for x in cur.execute(
                "SELECT * FROM financials WHERE company_id=? ORDER BY fiscal_year",
                (co["id"],),
            ).fetchall()
        ]
        if "thin_core_history" not in data_warnings(co, fins):
            continue
        if min_pdfs and _pdf_count(co) < min_pdfs:
            continue
        out.append(co["ticker"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--tickers", default="")
    ap.add_argument(
        "--min-pdfs",
        type=int,
        default=3,
        help="Only tickers with at least this many cached PDFs (0 = all thin)",
    )
    args = ap.parse_args()

    db.init_db()
    cur = db.get_connection().cursor()
    if args.tickers.strip():
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = _thin_tickers(cur, min_pdfs=args.min_pdfs)
    if args.limit and args.limit > 0:
        tickers = tickers[: args.limit]

    print(f"Thin-core tickers: {len(tickers)} → {', '.join(tickers)}")
    if not tickers:
        return
    if args.dry_run:
        print("[dry-run] would run main.py --skip-recent 0 --tickers ...")
        return

    py = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
    if not os.path.isfile(py):
        py = sys.executable
    cmd = [
        py,
        "main.py",
        "--skip-recent",
        "0",
        "--tickers",
        ",".join(tickers),
    ]
    print("Running:", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, cwd=ROOT)


if __name__ == "__main__":
    main()
