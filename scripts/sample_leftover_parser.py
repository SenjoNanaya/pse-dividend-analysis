"""Bounded parser attribution for leftover priority tickers."""
from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from src import db
from scripts.parser_review_misses import review_company
from scripts.review_common import (
    diagnose_company,
    load_companies,
    load_financials_by_company,
    write_csv,
    write_text,
)

TICKERS = [
    # revenue / NI incomplete sample
    "ABG",
    "DD",
    "ENEX",
    "CHP",
    "FGEN",
    "MRC",
    "LODE",
    "AB",
    # cash mega-caps / stubborn
    "SM",
    "AP",
    "JGS",
    "AREIT",
    "CEI",
    "ORE",
    # bank NPL
    "BDO",
    "MBT",
    "PNB",
    "SECB",
    "EW",
]

OUT = Path("data/reviews/20260719_leftovers_parser")
MISS_FIELDS = [
    "ticker",
    "company_id",
    "year",
    "field",
    "warn_token",
    "miss_class",
    "db_value",
    "pdf_value",
    "source_tag",
    "sample_pdf_path",
    "pdf_file_count",
]


def main() -> None:
    db.init_db()
    cur = db.get_connection().cursor()
    fins_by = load_financials_by_company(cur)
    misses = []
    for i, t in enumerate(TICKERS, 1):
        cos = load_companies(cur, ticker=t)
        if not cos:
            print(f"[{i}/{len(TICKERS)}] {t}: not in DB")
            continue
        co = cos[0]
        diag = diagnose_company(co, fins_by.get(int(co["id"]), []))
        print(
            f"[{i}/{len(TICKERS)}] {t} incomplete={diag['incomplete_reasons'] or '-'} "
            f"warns={diag['actionable_warnings'] or '-'} pdfs={diag['pdf_file_count']}",
            flush=True,
        )
        rows = review_company(diag, max_pdfs=2, pdf_only=False)
        misses.extend(rows)
        for r in rows:
            print(f"  {r['field']} → {r['miss_class']} pdf={r.get('pdf_value')}", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUT / "parser_review_misses.csv", misses, MISS_FIELDS)
    by_class = Counter(m["miss_class"] for m in misses)
    by_field = Counter(m["field"] for m in misses)
    lines = [
        "# Leftover parser sample",
        "",
        f"- Tickers: {', '.join(TICKERS)}",
        f"- Miss rows: **{len(misses)}**",
        "",
        "## miss_class histogram",
        "",
    ]
    for k, n in by_class.most_common():
        lines.append(f"- `{k}`: {n}")
    if not by_class:
        lines.append("- (none)")
    lines.extend(["", "## Field histogram", ""])
    for k, n in by_field.most_common():
        lines.append(f"- `{k}`: {n}")
    lines.extend(["", "## Rows", ""])
    for m in misses:
        lines.append(
            f"- **{m['ticker']}** {m['year']} `{m['field']}` → `{m['miss_class']}`"
            f" pdf={m.get('pdf_value')}"
        )
    write_text(OUT / "parser_review_summary.md", "\n".join(lines) + "\n")
    print(f"\nWrote {OUT}")
    print("classes", dict(by_class))


if __name__ == "__main__":
    main()
