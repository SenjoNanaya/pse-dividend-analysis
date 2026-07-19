"""
Offline DB inventory of incompleteness and soft data warnings.

Usage (from repo root):
  python scripts/db_review_dq.py
  python scripts/db_review_dq.py --limit 50
  python scripts/db_review_dq.py --ticker BPI
  python scripts/db_review_dq.py --warns-only
  python scripts/db_review_dq.py --incomplete-only
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from src import db
from src.utils import DB_PATH

from review_common import (  # noqa: E402
    ACTIONABLE_WARNINGS,
    diagnose_company,
    ensure_reviews_dir,
    field_inventory_rows,
    load_companies,
    load_financials_by_company,
    stamp,
    write_csv,
    write_text,
)

COMPANY_FIELDS = [
    "company_id",
    "ticker",
    "name",
    "sector",
    "subsector",
    "bank",
    "info_incomplete",
    "incomplete_reasons",
    "data_warnings",
    "actionable_warnings",
    "core_years",
    "share_years",
    "fiscal_years",
    "latest_year",
    "null_cash_latest",
    "null_shares_latest",
    "missing_latest",
    "latest_sources",
    "pdf_file_count",
    "pdf_dir_count",
    "has_actionable",
]

FIELD_FIELDS = [
    "ticker",
    "company_id",
    "fiscal_year",
    "field",
    "present",
    "source_tag",
    "value",
]


def _build_summary(diags: list[dict], out_dir: Path, db_path: str) -> str:
    n = len(diags)
    incomplete = [d for d in diags if d["info_incomplete"]]
    with_actionable = [d for d in diags if d["has_actionable"]]
    reason_counts: Counter[str] = Counter()
    warn_counts: Counter[str] = Counter()
    missing_latest_counts: Counter[str] = Counter()
    for d in diags:
        for r in d["_reasons"]:
            reason_counts[r] += 1
        for w in d["_warnings"]:
            warn_counts[w] += 1
        for m in (d["missing_latest"] or "").split(";"):
            if m:
                missing_latest_counts[m] += 1

    lines = [
        "# DB data-quality review",
        "",
        f"- Generated: `{stamp()}`",
        f"- DB: `{db_path}`",
        f"- Companies scanned: **{n}**",
        f"- Incomplete (hard gate): **{len(incomplete)}**",
        f"- Actionable issue (incomplete or soft warn): **{len(with_actionable)}**",
        "",
        "## Incomplete reason histogram",
        "",
    ]
    if reason_counts:
        for token, count in reason_counts.most_common():
            lines.append(f"- `{token}`: {count}")
    else:
        lines.append("- (none)")

    lines.extend(["", "## Soft warning histogram", ""])
    if warn_counts:
        for token, count in warn_counts.most_common():
            note = (
                " (expected for banks; not a parser miss)"
                if token == "industrial_roic_na_use_equity"
                else ""
            )
            lines.append(f"- `{token}`: {count}{note}")
    else:
        lines.append("- (none)")

    lines.extend(["", "## Actionable soft warnings only", ""])
    actionable_hist = {
        k: v for k, v in warn_counts.items() if k in ACTIONABLE_WARNINGS
    }
    if actionable_hist:
        for token, count in sorted(
            actionable_hist.items(), key=lambda kv: (-kv[1], kv[0])
        ):
            lines.append(f"- `{token}`: {count}")
    else:
        lines.append("- (none)")

    lines.extend(["", "## Latest-year missing fields (inventory)", ""])
    if missing_latest_counts:
        for field, count in missing_latest_counts.most_common():
            lines.append(f"- `{field}`: {count}")
    else:
        lines.append("- (none)")

    lines.extend(["", "## Top incomplete tickers", ""])
    top_inc = sorted(
        incomplete,
        key=lambda d: (-len(d["_reasons"]), d["ticker"]),
    )[:25]
    if top_inc:
        for d in top_inc:
            lines.append(
                f"- **{d['ticker']}**: {d['incomplete_reasons'] or '(flagged)'}"
                f" · core_years={d['core_years']} · pdfs={d['pdf_file_count']}"
            )
    else:
        lines.append("- (none)")

    lines.extend(["", "## Top actionable soft-warn tickers", ""])
    top_warn = sorted(
        [d for d in diags if d["_actionable"] and not d["info_incomplete"]],
        key=lambda d: (-len(d["_actionable"]), d["ticker"]),
    )[:25]
    if top_warn:
        for d in top_warn:
            lines.append(
                f"- **{d['ticker']}**: {d['actionable_warnings']}"
                f" · share_years={d['share_years']} · null_cash={d['null_cash_latest']}"
                f" · pdfs={d['pdf_file_count']}"
            )
    else:
        lines.append("- (none)")

    lines.extend(
        [
            "",
            "## Outputs",
            "",
            f"- `{out_dir / 'db_review_summary.md'}`",
            f"- `{out_dir / 'db_review_companies.csv'}`",
            f"- `{out_dir / 'db_review_fields.csv'}`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="DB inventory of DQ warnings / incompleteness"
    )
    ap.add_argument("--limit", type=int, default=0, help="Max companies (0 = all)")
    ap.add_argument("--ticker", default=None, help="Single ticker filter")
    ap.add_argument(
        "--warns-only",
        action="store_true",
        help="Keep companies with actionable soft warnings",
    )
    ap.add_argument(
        "--incomplete-only",
        action="store_true",
        help="Keep companies failing the hard incompleteness gate",
    )
    ap.add_argument(
        "--out",
        default=None,
        help="Output directory (default data/reviews/<timestamp>)",
    )
    args = ap.parse_args()

    db.init_db()
    conn = db.get_connection()
    cur = conn.cursor()

    companies = load_companies(cur, ticker=args.ticker)
    fins_by_id = load_financials_by_company(cur)

    diags = []
    for co in companies:
        fins = fins_by_id.get(int(co["id"]), [])
        diag = diagnose_company(co, fins)
        if args.incomplete_only and not diag["info_incomplete"]:
            continue
        if args.warns_only and not diag["_actionable"]:
            continue
        diags.append(diag)

    if args.limit and args.limit > 0:
        diags = diags[: args.limit]

    out_dir = Path(args.out) if args.out else ensure_reviews_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    write_csv(out_dir / "db_review_companies.csv", diags, COMPANY_FIELDS)

    field_rows = []
    for d in diags:
        field_rows.extend(field_inventory_rows(d))
    write_csv(out_dir / "db_review_fields.csv", field_rows, FIELD_FIELDS)

    summary = _build_summary(diags, out_dir, os.path.abspath(DB_PATH))
    write_text(out_dir / "db_review_summary.md", summary)

    print(summary)
    print(f"\nWrote review to {out_dir}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
