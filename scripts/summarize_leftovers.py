"""
Build leftovers_summary.md from a db_review_dq stamp (or live DB).

Usage:
  python scripts/db_review_dq.py --out data/reviews/20260719_leftovers
  python scripts/summarize_leftovers.py data/reviews/20260719_leftovers
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from src import db
from src.filing_triage import is_banks_subsector
from src.report_metrics import data_warnings, incomplete_reasons


def _bank_gaps(cur) -> list[tuple[str, int, list[str]]]:
    out = []
    for co in cur.execute(
        "SELECT id, ticker, sector, subsector FROM companies ORDER BY ticker"
    ).fetchall():
        if not is_banks_subsector(co["sector"], co["subsector"]):
            continue
        latest = cur.execute(
            """
            SELECT fiscal_year, total_loans, total_deposits, npl,
                   net_interest_income, allowance_for_credit_losses
            FROM financials WHERE company_id=?
            ORDER BY fiscal_year DESC LIMIT 1
            """,
            (co["id"],),
        ).fetchone()
        if not latest:
            continue
        miss = [
            k
            for k in (
                "total_loans",
                "total_deposits",
                "npl",
                "net_interest_income",
                "allowance_for_credit_losses",
            )
            if latest[k] is None
        ]
        if miss:
            out.append((co["ticker"], int(latest["fiscal_year"]), miss))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("review_dir", help="data/reviews/<stamp> with db_review_companies.csv")
    args = ap.parse_args()
    review_dir = Path(args.review_dir)
    csv_path = review_dir / "db_review_companies.csv"
    if not csv_path.is_file():
        raise SystemExit(f"missing {csv_path}")

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    incomplete = [r for r in rows if str(r.get("info_incomplete")) in ("1", "True", "true")]
    soft = []
    for r in rows:
        warns = [
            w
            for w in (r.get("actionable_warnings") or "").split(";")
            if w and w != "industrial_roic_na_use_equity"
        ]
        if warns:
            soft.append((r, warns))

    reason_hist: Counter[str] = Counter()
    for r in incomplete:
        for tok in (r.get("incomplete_reasons") or "").split(";"):
            if tok:
                reason_hist[tok] += 1
    warn_hist: Counter[str] = Counter()
    for _, warns in soft:
        for w in warns:
            warn_hist[w] += 1

    db.init_db()
    cur = db.get_connection().cursor()
    banks = _bank_gaps(cur)

    lines = [
        "# Leftover DQ summary",
        "",
        f"- Source: `{review_dir.as_posix()}`",
        f"- Companies in stamp: **{len(rows)}**",
        f"- Hard incomplete: **{len(incomplete)}**",
        f"- Actionable soft-warn rows: **{len(soft)}**",
        f"- Banks with latest-year field gaps: **{len(banks)}**",
        "",
        "## Incomplete reason histogram",
        "",
    ]
    for tok, n in reason_hist.most_common():
        lines.append(f"- `{tok}`: {n}")
    lines.extend(["", "## Soft-warn histogram", ""])
    for tok, n in warn_hist.most_common():
        lines.append(f"- `{tok}`: {n}")

    lines.extend(["", "## Incomplete tickers", ""])
    for r in sorted(incomplete, key=lambda x: x.get("ticker") or ""):
        lines.append(
            f"- **{r.get('ticker')}**: `{r.get('incomplete_reasons')}`"
            f" · core_years={r.get('core_years')}"
            f" · pdfs={r.get('pdf_file_count')}"
        )

    lines.extend(["", "## Soft-warn tickers", ""])
    for r, warns in sorted(soft, key=lambda x: x[0].get("ticker") or ""):
        lines.append(
            f"- **{r.get('ticker')}**: `{';'.join(warns)}`"
            f" · pdfs={r.get('pdf_file_count')}"
            f" · null_cash={r.get('null_cash_latest')}"
        )

    lines.extend(["", "## Bank latest-year gaps", ""])
    if banks:
        for t, y, miss in banks:
            lines.append(f"- **{t}** FY{y}: `{';'.join(miss)}`")
    else:
        lines.append("- (none)")

    out = review_dir / "leftovers_summary.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out}")
    print(f"incomplete={len(incomplete)} soft={len(soft)} bank_gaps={len(banks)}")


if __name__ == "__main__":
    main()
