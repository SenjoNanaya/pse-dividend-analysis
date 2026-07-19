"""
Attribute parser / pipeline misses behind incompleteness and soft warnings.

Re-runs PDF whitelist extraction on cached filings under data/filings/ (offline).
HTML report bodies are not cached; core HTML misses are classified without re-parse.

Usage (from repo root):
  python scripts/parser_review_misses.py
  python scripts/parser_review_misses.py --limit 30
  python scripts/parser_review_misses.py --ticker BPI
  python scripts/parser_review_misses.py --pdf-only
  python scripts/parser_review_misses.py --from-db-review data/reviews/<stamp>
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from src import db
from src.pdf_roic_extract import (
    extract_roic_metrics_from_pdf_path,
    prefer_scope_metrics,
)
from src.utils import DB_PATH

from review_common import (  # noqa: E402
    HTML_CORE_FIELDS,
    PDF_WHITELIST_FIELDS,
    diagnose_company,
    ensure_reviews_dir,
    field_present,
    has_actionable_issue,
    iter_cached_pdfs,
    load_companies,
    load_financials_by_company,
    source_tag,
    stamp,
    write_csv,
    write_text,
)

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

# Map incomplete / warn tokens → fields to investigate
TOKEN_FIELDS = {
    "revenue": ["revenue"],
    "net_income": ["net_income"],
    "total_assets": ["total_assets"],
    "eps": ["eps"],
    "book_value": ["book_value"],
    "no_financials": list(HTML_CORE_FIELDS),
    "no_cash_for_proper_roic": ["cash_and_equivalents"],
    "thin_shares_series": ["outstanding_shares"],
    "thin_core_history": ["core_history"],
}


def _pdf_key_aliases(field: str) -> list[str]:
    """DB column → keys that may appear in PDF extractor rows."""
    if field == "revenue":
        return ["gross_revenue", "revenue"]
    if field == "book_value":
        return ["book_value_per_share", "book_value"]
    return [field]


def _pdf_value_for_year(
    pdf_yearly: dict[int, dict[str, Any]],
    year: int | None,
    field: str,
) -> Any:
    if not pdf_yearly:
        return None
    years = sorted(pdf_yearly.keys())
    if year is not None and int(year) in pdf_yearly:
        row = pdf_yearly[int(year)]
    elif years:
        row = pdf_yearly[years[-1]]
        year = years[-1]
    else:
        return None
    for key in _pdf_key_aliases(field):
        v = row.get(key)
        if v is not None:
            return v
    return None


def _extract_company_pdfs(
    company: dict[str, Any],
    max_files: int,
) -> tuple[dict[int, dict], str]:
    """Return merged yearly metrics and a sample pdf path."""
    paths = iter_cached_pdfs(company, max_files=max_files)
    if not paths:
        return {}, ""
    candidates: list[tuple[str, dict]] = []
    sample = ""
    for p in paths:
        sample = sample or str(p)
        try:
            yearly = extract_roic_metrics_from_pdf_path(
                str(p), filename_hint=p.name
            )
        except Exception:
            continue
        if not yearly:
            continue
        sample_row = next(iter(yearly.values()))
        scope = sample_row.get("statement_scope") or "unknown"
        candidates.append((scope, yearly))
    if not candidates:
        return {}, sample
    return prefer_scope_metrics(candidates), sample


def _miss_class_for_field(
    field: str,
    *,
    db_missing: bool,
    pdf_value: Any,
    pdf_file_count: int,
    warn_token: str,
) -> str | None:
    if not db_missing and warn_token not in (
        "thin_shares_series",
        "thin_core_history",
    ):
        return None

    if field == "outstanding_shares" or warn_token == "thin_shares_series":
        return "thin_shares_form17c_or_stock_page"

    if field == "core_history" or warn_token == "thin_core_history":
        return "html_core_miss_needs_rescrape_or_fixture"

    if field in HTML_CORE_FIELDS and field not in PDF_WHITELIST_FIELDS:
        return "html_core_miss_needs_rescrape_or_fixture"

    if field in PDF_WHITELIST_FIELDS or field == "cash_and_equivalents":
        if pdf_file_count <= 0:
            return "no_pdf_cache"
        if pdf_value is not None and db_missing:
            return "pdf_extract_ok_merge_or_write_gap"
        if pdf_value is None:
            return "pdf_label_or_page_router_miss"
        return None

    # Core fields that PDF can also fill (total_assets)
    if field in HTML_CORE_FIELDS:
        if pdf_file_count <= 0:
            return "html_core_miss_needs_rescrape_or_fixture"
        if pdf_value is not None and db_missing:
            return "pdf_extract_ok_merge_or_write_gap"
        if db_missing:
            return "html_core_miss_needs_rescrape_or_fixture"
    return None


def _targets_from_db_review_csv(path: Path) -> set[str] | None:
    """Return ticker set from db_review_companies.csv has_actionable=1."""
    csv_path = path
    if path.is_dir():
        csv_path = path / "db_review_companies.csv"
    if not csv_path.is_file():
        return None
    tickers: set[str] = set()
    with csv_path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("has_actionable") in ("1", "true", "True"):
                t = (row.get("ticker") or "").strip()
                if t:
                    tickers.add(t.upper())
    return tickers


def review_company(
    diag: dict[str, Any],
    *,
    max_pdfs: int,
    pdf_only: bool,
    pdf_cache: dict[int, tuple[dict, str]] | None = None,
) -> list[dict[str, Any]]:
    company = diag["_company"]
    financials = diag["_financials"]
    latest = diag["_latest"]
    year = latest.get("fiscal_year") if latest else None
    pdf_file_count = int(diag["pdf_file_count"] or 0)

    tokens: list[str] = list(diag["_reasons"]) + list(diag["_actionable"])
    fields_needed: dict[str, str] = {}
    for token in tokens:
        for field in TOKEN_FIELDS.get(token, []):
            fields_needed.setdefault(field, token)

    # Deposit banks: probe checklist gaps even when no other soft warns
    if diag["bank"] and latest:
        for field in (
            "total_loans",
            "total_deposits",
            "npl",
            "net_interest_income",
            "allowance_for_credit_losses",
        ):
            if not field_present(latest, field):
                fields_needed.setdefault(field, "bank_whitelist_gap")

    if not fields_needed:
        return []

    needs_pdf = any(
        f in PDF_WHITELIST_FIELDS or f == "cash_and_equivalents"
        for f in fields_needed
    )
    pdf_yearly: dict[int, dict] = {}
    sample_pdf = ""
    if needs_pdf and pdf_file_count > 0:
        cid = int(company["id"])
        if pdf_cache is not None and cid in pdf_cache:
            pdf_yearly, sample_pdf = pdf_cache[cid]
        else:
            pdf_yearly, sample_pdf = _extract_company_pdfs(company, max_pdfs)
            if pdf_cache is not None:
                pdf_cache[cid] = (pdf_yearly, sample_pdf)

    rows: list[dict[str, Any]] = []
    for field, warn_token in fields_needed.items():
        db_row = latest
        db_missing = db_row is None or not field_present(db_row, field)
        db_val = ""
        if db_row is not None and field_present(db_row, field):
            db_val = db_row.get(field)

        # thin_shares / thin_core always emit even if latest cell present
        force = warn_token in ("thin_shares_series", "thin_core_history")
        if not db_missing and not force:
            continue

        pdf_val = _pdf_value_for_year(pdf_yearly, year, field)
        miss_class = _miss_class_for_field(
            field,
            db_missing=db_missing or force,
            pdf_value=pdf_val,
            pdf_file_count=pdf_file_count,
            warn_token=warn_token,
        )
        if miss_class is None:
            continue
        if pdf_only and miss_class in (
            "html_core_miss_needs_rescrape_or_fixture",
            "thin_shares_form17c_or_stock_page",
        ):
            continue

        rows.append(
            {
                "ticker": diag["ticker"],
                "company_id": diag["company_id"],
                "year": year or "",
                "field": field,
                "warn_token": warn_token,
                "miss_class": miss_class,
                "db_value": db_val if db_val is not None else "",
                "pdf_value": pdf_val if pdf_val is not None else "",
                "source_tag": source_tag(db_row, field) if db_row else "",
                "sample_pdf_path": sample_pdf,
                "pdf_file_count": pdf_file_count,
            }
        )
    return rows


def _build_summary(misses: list[dict], out_dir: Path, db_path: str) -> str:
    by_class = Counter(m["miss_class"] for m in misses)
    by_field = Counter(m["field"] for m in misses)
    lines = [
        "# Parser miss review",
        "",
        f"- Generated: `{stamp()}`",
        f"- DB: `{db_path}`",
        f"- Miss rows: **{len(misses)}**",
        "",
        "## miss_class histogram",
        "",
    ]
    if by_class:
        for token, count in by_class.most_common():
            lines.append(f"- `{token}`: {count}")
    else:
        lines.append("- (none)")

    lines.extend(["", "## Field histogram", ""])
    if by_field:
        for token, count in by_field.most_common():
            lines.append(f"- `{token}`: {count}")
    else:
        lines.append("- (none)")

    lines.extend(
        [
            "",
            "## miss_class meanings",
            "",
            "- `html_core_miss_needs_rescrape_or_fixture`: core EDGE HTML fields missing; HTML not cached offline.",
            "- `thin_shares_form17c_or_stock_page`: fewer than 2 years with outstanding shares.",
            "- `no_pdf_cache`: whitelist/cash gap and no files under `data/filings/<EDGE cmpy_id>/` (`companies.symbol`).",
            "- `pdf_extract_ok_merge_or_write_gap`: re-extract found a value but DB cell is still empty.",
            "- `pdf_label_or_page_router_miss`: cached PDF re-extract still null for that field.",
            "",
            "## Fixture / merge gap candidates",
            "",
            "PDF extract returned a value while DB is missing (highest leverage fixes).",
            "",
        ]
    )
    gaps = [
        m
        for m in misses
        if m["miss_class"] == "pdf_extract_ok_merge_or_write_gap"
    ]
    gaps.sort(key=lambda m: (m["ticker"], m["field"]))
    if gaps:
        for m in gaps[:40]:
            lines.append(
                f"- **{m['ticker']}** {m['year']} `{m['field']}`"
                f" pdf={m['pdf_value']} · {m['sample_pdf_path']}"
            )
    else:
        lines.append("- (none)")

    lines.extend(
        [
            "",
            "## Label / router miss samples",
            "",
        ]
    )
    labels = [
        m
        for m in misses
        if m["miss_class"] == "pdf_label_or_page_router_miss"
    ]
    labels.sort(key=lambda m: (m["ticker"], m["field"]))
    if labels:
        for m in labels[:40]:
            lines.append(
                f"- **{m['ticker']}** {m['year']} `{m['field']}`"
                f" · pdfs={m['pdf_file_count']} · {m['sample_pdf_path']}"
            )
    else:
        lines.append("- (none)")

    lines.extend(
        [
            "",
            "## Outputs",
            "",
            f"- `{out_dir / 'parser_review_summary.md'}`",
            f"- `{out_dir / 'parser_review_misses.csv'}`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Attribute parser misses behind DQ warnings"
    )
    ap.add_argument("--limit", type=int, default=0, help="Max companies (0 = all actionable)")
    ap.add_argument("--ticker", default=None, help="Single ticker")
    ap.add_argument(
        "--pdf-only",
        action="store_true",
        help="Skip HTML-core and shares miss rows",
    )
    ap.add_argument(
        "--max-pdfs",
        type=int,
        default=6,
        help="Max cached PDFs to re-extract per company",
    )
    ap.add_argument(
        "--from-db-review",
        default=None,
        help="Directory or companies CSV from db_review_dq.py",
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

    ticker_filter: set[str] | None = None
    if args.from_db_review:
        ticker_filter = _targets_from_db_review_csv(Path(args.from_db_review))
        if ticker_filter is None:
            print(
                f"ERROR: no db_review_companies.csv under {args.from_db_review}",
                file=sys.stderr,
            )
            return 1

    diags = []
    for co in companies:
        fins = fins_by_id.get(int(co["id"]), [])
        diag = diagnose_company(co, fins)
        bank_gap = bool(diag.get("bank")) and any(
            f in (diag.get("missing_latest") or "")
            for f in (
                "total_loans",
                "total_deposits",
                "npl",
                "net_interest_income",
                "allowance_for_credit_losses",
            )
        )
        if not has_actionable_issue(diag["_reasons"], diag["_warnings"]) and not bank_gap:
            continue
        if ticker_filter is not None and diag["ticker"].upper() not in ticker_filter:
            continue
        diags.append(diag)

    # Prefer companies with PDF gaps / cash warns first
    diags.sort(
        key=lambda d: (
            0 if "no_cash_for_proper_roic" in d["_actionable"] else 1,
            0 if d["info_incomplete"] else 1,
            -d["pdf_file_count"],
            d["ticker"],
        )
    )
    if args.limit and args.limit > 0:
        diags = diags[: args.limit]

    out_dir = Path(args.out) if args.out else ensure_reviews_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    pdf_cache: dict[int, tuple[dict, str]] = {}
    misses: list[dict[str, Any]] = []
    for i, diag in enumerate(diags, 1):
        print(
            f"[{i}/{len(diags)}] {diag['ticker']} "
            f"reasons={diag['incomplete_reasons'] or '-'} "
            f"warns={diag['actionable_warnings'] or '-'} "
            f"pdfs={diag['pdf_file_count']}",
            flush=True,
        )
        misses.extend(
            review_company(
                diag,
                max_pdfs=args.max_pdfs,
                pdf_only=args.pdf_only,
                pdf_cache=pdf_cache,
            )
        )

    write_csv(out_dir / "parser_review_misses.csv", misses, MISS_FIELDS)
    summary = _build_summary(misses, out_dir, os.path.abspath(DB_PATH))
    write_text(out_dir / "parser_review_summary.md", summary)
    print(summary)
    print(f"\nWrote review to {out_dir}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
