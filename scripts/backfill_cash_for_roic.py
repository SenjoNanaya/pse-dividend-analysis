"""
Backfill missing cash (and other null ROIC whitelist fields) for proper ROIC.

Re-fetches Annual Report HTML + ranked AFS/17-A PDFs (OCR on image-only),
then fill-nulls into existing fiscal years. Never overwrites non-null DB values.

Usage (from repo root):
  python scripts/backfill_cash_for_roic.py --dry-run
  python scripts/backfill_cash_for_roic.py --limit 20
  python scripts/backfill_cash_for_roic.py --tickers SM,JGS
  python scripts/backfill_cash_for_roic.py --cached-pdfs-only --limit 50
"""
from __future__ import annotations

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from src import db
from src import parser
from src.filing_triage import is_financial_sector, select_attachments_to_download
from src.pdf_roic_extract import (
    extract_roic_metrics_from_pdf_bytes,
    extract_roic_metrics_from_pdf_path,
    fill_html_whitelist,
    prefer_scope_metrics,
)
from src.report_metrics import compute_screening_summary
from src.scale_guard import repair_thousand_scale_jumps
from src.scraper import PSEScraper
from src.utils import logger, random_delay

# Extracted metric key → DB column
_METRIC_TO_DB = {
    "gross_revenue": "revenue",
    "net_income": "net_income",
    "eps": "eps",
    "book_value_per_share": "book_value",
    "total_assets": "total_assets",
    "total_liabilities": "total_liabilities",
    "stockholders_equity": "stockholders_equity",
    "total_current_liabilities": "total_current_liabilities",
    "cash_and_equivalents": "cash_and_equivalents",
    "operating_income": "operating_income",
    "income_before_tax": "income_before_tax",
    "income_tax_expense": "income_tax_expense",
    "gross_profit": "gross_profit",
    "ga_expense": "ga_expense",
    "total_loans": "total_loans",
    "total_deposits": "total_deposits",
    "npl": "npl",
    "net_interest_income": "net_interest_income",
    "allowance_for_credit_losses": "allowance_for_credit_losses",
    "statement_scope": "statement_scope",
}


def _companies_needing_cash(cur, tickers: list[str] | None) -> list[dict]:
    """Companies with ≥1 year that has assets but null cash (non-financial)."""
    rows = cur.execute(
        """
        SELECT c.id, c.ticker, c.name, c.symbol AS cmpy_id, c.sector, c.subsector,
               c.outstanding_shares, c.pe_ratio, c.pb_ratio, c.roe, c.market_cap,
               c.last_traded_price,
               SUM(CASE WHEN f.total_assets IS NOT NULL
                         AND f.cash_and_equivalents IS NULL THEN 1 ELSE 0 END) AS cash_gaps,
               MAX(f.fiscal_year) AS latest_year
        FROM companies c
        JOIN financials f ON f.company_id = c.id
        GROUP BY c.id
        HAVING cash_gaps > 0
        ORDER BY cash_gaps DESC, c.ticker
        """
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if is_financial_sector(d.get("sector"), d.get("subsector")):
            continue
        if tickers and (d.get("ticker") or "").upper() not in tickers:
            continue
        out.append(d)
    return out


def _to_db_row(metrics: dict) -> dict:
    row = {}
    for src, dst in _METRIC_TO_DB.items():
        if metrics.get(src) is not None:
            row[dst] = metrics[src]
    # PDF path already uses DB-ish keys for whitelist fields
    for key in (
        "cash_and_equivalents",
        "total_current_liabilities",
        "total_assets",
        "operating_income",
        "gross_profit",
        "ga_expense",
        "income_before_tax",
        "income_tax_expense",
        "total_loans",
        "total_deposits",
        "npl",
        "net_interest_income",
        "allowance_for_credit_losses",
        "statement_scope",
    ):
        if key not in row and metrics.get(key) is not None:
            row[key] = metrics[key]
    return row


def _extract_from_cached_pdfs(cmpy_id: str, *, max_pdfs: int = 6) -> dict[int, dict]:
    """Re-extract ranked local PDFs under data/filings/{EDGE cmpy_id}/."""
    base = os.path.join("data", "filings", str(cmpy_id))
    if not os.path.isdir(base):
        return {}
    pdfs: list[str] = []
    for root, _, files in os.walk(base):
        for name in files:
            if name.lower().endswith(".pdf"):
                pdfs.append(os.path.join(root, name))
    if not pdfs:
        return {}

    def _rank(path: str) -> tuple[int, float]:
        """Prefer AFS/FS packs; demote 17-L, SR-only, certifications."""
        name = os.path.basename(path).lower()
        try:
            mtime = -os.path.getmtime(path)
        except OSError:
            mtime = 0.0
        # Hard demotes (review often sampled these and got empty cash)
        if "17-l" in name or "17_l" in name or "form-17-l" in name:
            return (9, mtime)
        if any(
            s in name
            for s in (
                "certification",
                "mineral_resource",
                "annex_a_sr",
                "sustainability_report.pdf",
            )
        ) and not any(s in name for s in ("17-a", "17a", "afs", "audited")):
            return (8, mtime)
        if "sustainability" in name and not any(
            s in name for s in ("17-a", "17a", "afs", "audited", "financial")
        ):
            return (8, mtime)

        score = 5
        if any(
            s in name
            for s in (
                "afs",
                "audited_financial",
                "audited financial",
                "financial_statement",
                "financial statement",
                "_fs_",
                "-fs-",
                "separate_fs",
                "conso_fs",
                "parent_afs",
            )
        ):
            score = 0
        elif any(
            s in name
            for s in ("17-a", "17a", "sec_form_17", "sec form 17", "annual_report")
        ):
            score = 1
        # Prefer parent/separate/conso FS naming when present
        if any(s in name for s in ("parent", "separate", "conso", "consolidat")):
            score = max(0, score - 0)
        # Prefer filenames that mention recent fiscal years
        if re.search(r"202[4-6]", name):
            mtime -= 0.1  # slight tie-break toward dated packs
        return (score, mtime)

    pdfs.sort(key=_rank)
    candidates = []
    for path in pdfs[: max(1, max_pdfs)]:
        yearly = extract_roic_metrics_from_pdf_path(
            path, filename_hint=os.path.basename(path)
        )
        if yearly:
            sample = next(iter(yearly.values()))
            scope = sample.get("statement_scope") or "unknown"
            candidates.append((scope, yearly))
    if not candidates:
        return {}
    return prefer_scope_metrics(candidates)


def _extract_live(scraper: PSEScraper, cmpy_id: str, *, max_pdfs: int = 8) -> dict[int, dict]:
    yearly: dict[int, dict] = {}
    pdf_candidates = []
    disc_html = scraper.fetch_disclosures_search(cmpy_id, "Annual Report")
    edge_numbers = parser.parse_disclosure_edge_numbers(disc_html)
    for edge_no in edge_numbers:
        viewer_html = scraper.fetch_disclosure_viewer(edge_no)
        iframe_link = parser.parse_iframe_source(viewer_html)
        if iframe_link:
            referer = f"https://edge.pse.com.ph/openDiscViewer.do?edge_no={edge_no}"
            report_html = scraper.fetch_report_html(iframe_link, referer)
            disc_data = parser.parse_report_html(report_html)
            scale = disc_data.get("scale_factor", 1)
            metrics = parser.extract_all_years_metrics(
                disc_data.get("tables", []), scale_factor=scale
            )
            yearly.update(metrics)

        attachments = parser.parse_disclosure_attachments(viewer_html)
        to_fetch = select_attachments_to_download(attachments, max_files=max_pdfs)
        for att in to_fetch:
            try:
                referer = f"https://edge.pse.com.ph/openDiscViewer.do?edge_no={edge_no}"
                pdf_bytes = scraper.fetch_attachment_file(att["file_id"], referer=referer)
                cache_dir = os.path.join("data", "filings", str(cmpy_id), str(edge_no))
                safe_name = "".join(
                    c if c.isalnum() or c in "._-" else "_"
                    for c in (att.get("filename") or f"{att['file_id']}.pdf")
                )[:180]
                cache_path = os.path.join(cache_dir, safe_name)
                pdf_yearly = extract_roic_metrics_from_pdf_bytes(
                    pdf_bytes,
                    filename_hint=att.get("filename"),
                    cache_path=cache_path,
                )
                if pdf_yearly:
                    sample = next(iter(pdf_yearly.values()))
                    scope = sample.get("statement_scope") or "unknown"
                    pdf_candidates.append((scope, pdf_yearly))
                random_delay()
            except Exception as exc:
                logger.warning(
                    "Backfill PDF failed cmpy=%s file_id=%s: %s",
                    cmpy_id,
                    att.get("file_id"),
                    exc,
                )
    if pdf_candidates:
        pdf_merged = prefer_scope_metrics(pdf_candidates)
        yearly = fill_html_whitelist(yearly, pdf_merged)
    return yearly


def _rescreen(conn, company: dict) -> None:
    cur = conn.cursor()
    fins = cur.execute(
        """
        SELECT fiscal_year, revenue, net_income, eps, book_value,
               total_assets, total_liabilities, current_ratio, quick_ratio,
               outstanding_shares, cash_and_equivalents, total_current_liabilities,
               operating_income, gross_profit, ga_expense
        FROM financials WHERE company_id = ? ORDER BY fiscal_year
        """,
        (company["id"],),
    ).fetchall()
    divs = cur.execute(
        """
        SELECT ex_date, amount AS rate, type, security, is_common
        FROM dividends WHERE company_id = ?
        """,
        (company["id"],),
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
        company["id"],
        screening["check_pass_count"],
        screening["check_evaluable_total"],
        screening["info_incomplete"],
        div_yield=screening.get("div_yield"),
        roic=screening.get("roic"),
        debt_to_equity=screening.get("debt_to_equity"),
        check_struct_pass=screening.get("check_struct_pass"),
        check_struct_eval=screening.get("check_struct_eval"),
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="Max companies (0 = all)")
    ap.add_argument("--tickers", default="", help="Comma-separated tickers")
    ap.add_argument(
        "--cached-pdfs-only",
        action="store_true",
        help="Only re-extract local data/filings/{cmpy_id} PDFs (no EDGE fetch)",
    )
    ap.add_argument("--max-pdfs", type=int, default=8)
    args = ap.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()] or None

    db.init_db()
    conn = db.get_connection()
    cur = conn.cursor()
    targets = _companies_needing_cash(cur, tickers)
    if args.limit and args.limit > 0:
        targets = targets[: args.limit]

    print(
        f"Cash-gap companies: {len(targets)}"
        f"{' (cached PDFs only)' if args.cached_pdfs_only else ''}"
        f"{' [dry-run]' if args.dry_run else ''}"
    )

    scraper = None if args.cached_pdfs_only else PSEScraper()
    filled_cash_companies = 0
    filled_cash_rows = 0

    for co in targets:
        cmpy_id = str(co["cmpy_id"])
        ticker = co["ticker"]
        try:
            if args.cached_pdfs_only:
                pdf_yearly = _extract_from_cached_pdfs(
                    cmpy_id, max_pdfs=args.max_pdfs
                )
                # Seed HTML side from DB so fill-nulls keep asset anchors / non-nulls
                html_seed = {}
                for r in cur.execute(
                    """
                    SELECT fiscal_year, revenue, net_income, eps, book_value,
                           total_assets, total_liabilities, stockholders_equity,
                           total_current_liabilities, cash_and_equivalents,
                           operating_income, income_before_tax, income_tax_expense,
                           gross_profit, ga_expense,
                           total_loans, total_deposits, npl, net_interest_income,
                           outstanding_shares, statement_scope
                    FROM financials WHERE company_id=?
                    """,
                    (co["id"],),
                ).fetchall():
                    row = dict(r)
                    y = int(row.pop("fiscal_year"))
                    # Map DB revenue back to pipeline key for reconcile helpers
                    if row.get("revenue") is not None:
                        row["gross_revenue"] = row["revenue"]
                    html_seed[y] = row
                yearly = fill_html_whitelist(
                    html_seed,
                    pdf_yearly,
                    company={
                        "sector": co.get("sector"),
                        "subsector": co.get("subsector"),
                        "ticker": ticker,
                        "outstanding_shares": co.get("outstanding_shares"),
                    },
                )
            else:
                yearly = _extract_live(scraper, cmpy_id, max_pdfs=args.max_pdfs)

            yearly, scale_notes = repair_thousand_scale_jumps(
                yearly,
                shares_fallback=co.get("outstanding_shares"),
            )
            for note in scale_notes:
                logger.info("Scale guard %s: %s", ticker, note)

            company_cash_fills = 0
            all_fills: list[str] = []
            for year, metrics in sorted(yearly.items()):
                db_row = _to_db_row(metrics)
                if not db_row:
                    continue
                if args.dry_run:
                    existing = cur.execute(
                        """
                        SELECT cash_and_equivalents FROM financials
                        WHERE company_id=? AND fiscal_year=?
                        """,
                        (co["id"], year),
                    ).fetchone()
                    if (
                        existing
                        and existing["cash_and_equivalents"] is None
                        and db_row.get("cash_and_equivalents") is not None
                    ):
                        print(
                            f"  {ticker} FY{year}: would fill cash="
                            f"{db_row['cash_and_equivalents']:.6g}"
                        )
                        company_cash_fills += 1
                    continue

                lifted = db.overwrite_financial_scale_lift(
                    conn, co["id"], int(year), db_row, commit=False
                )
                # Attach field_sources so eps derived/pdf tags stick
                if metrics.get("_field_sources"):
                    db_row["_field_sources"] = metrics["_field_sources"]
                filled = db.fill_financial_nulls(
                    conn,
                    co["id"],
                    int(year),
                    db_row,
                    commit=False,
                    treat_zero_as_null=("eps",),
                )
                if "cash_and_equivalents" in filled:
                    company_cash_fills += 1
                    filled_cash_rows += 1
                note_parts = []
                if lifted:
                    note_parts.append(f"lift:{','.join(lifted)}")
                if filled:
                    note_parts.append(",".join(filled))
                if note_parts:
                    all_fills.append(f"FY{year}:{';'.join(note_parts)}")

            if args.dry_run:
                if company_cash_fills:
                    filled_cash_companies += 1
                elif not yearly:
                    print(f"  {ticker}: no extract")
                continue

            if all_fills:
                conn.commit()
                _rescreen(conn, co)
                print(f"{ticker}: filled {'; '.join(all_fills)}")
                if company_cash_fills:
                    filled_cash_companies += 1
            else:
                print(f"{ticker}: no nulls filled (gaps={co['cash_gaps']})")
        except Exception as exc:
            logger.exception("Backfill failed for %s: %s", ticker, exc)
            print(f"{ticker}: ERROR {exc}")

    if not args.dry_run:
        conn.commit()
    conn.close()
    print(
        f"Done. Companies with cash filled: {filled_cash_companies}; "
        f"cash row fills: {filled_cash_rows}"
    )


if __name__ == "__main__":
    main()
