"""
Backfill OI / GA / cash for non-financials, and bank FS fields for financials.

Non-financials: years needing PDF OI or missing/tiny cash.
Banks: years missing loans / deposits / NPL / NII / credit-loss allowance.
Uses cached PDFs under data/filings/{cmpy_id} by default; optional live EDGE fetch.

Usage (from repo root):
  python scripts/backfill_roic_whitelist.py --dry-run
  python scripts/backfill_roic_whitelist.py --cached-pdfs-only --tickers ALI,FCG,JFC
  python scripts/backfill_roic_whitelist.py --limit 20
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from src import db
from src import parser
from src.filing_triage import (
    is_banks_subsector,
    is_financial_sector,
    select_attachments_to_download,
)
from src.pdf_roic_extract import (
    extract_roic_metrics_from_pdf_bytes,
    extract_roic_metrics_from_pdf_path,
    fill_html_whitelist,
    prefer_scope_metrics,
)
from src.report_metrics import (
    compute_screening_summary,
    needs_pdf_cash,
    needs_pdf_eps,
    needs_pdf_oi,
)
from src.field_sources import (
    merge_source_tags,
    sources_from_json,
    sources_to_json,
)
from src.scale_guard import harmonize_yearly_pl_scale, repair_thousand_scale_jumps
from src.scraper import PSEScraper
from src.utils import logger, random_delay

_UPDATE_COLS = (
    "operating_income",
    "ga_expense",
    "cash_and_equivalents",
    "gross_profit",
    "cost_of_sales",
    "interest_expense",
    "other_expenses",
    "income_before_tax",
    "income_tax_expense",
    "eps",
    "total_loans",
    "total_deposits",
    "npl",
    "net_interest_income",
    "allowance_for_credit_losses",
    "statement_scope",
)


def _load_html_seed(cur, company_id: int) -> dict[int, dict]:
    html_seed = {}
    for r in cur.execute(
        """
        SELECT fiscal_year, revenue, net_income, eps, book_value,
               total_assets, total_liabilities, stockholders_equity,
               total_current_liabilities, cash_and_equivalents,
               operating_income, income_before_tax, income_tax_expense,
               gross_profit, ga_expense, cost_of_sales, interest_expense,
               other_expenses, total_loans, total_deposits, npl,
               net_interest_income, allowance_for_credit_losses,
               outstanding_shares, statement_scope, field_sources
        FROM financials WHERE company_id=?
        """,
        (company_id,),
    ).fetchall():
        row = dict(r)
        y = int(row.pop("fiscal_year"))
        if row.get("revenue") is not None:
            row["gross_revenue"] = row["revenue"]
        src = sources_from_json(row.pop("field_sources", None))
        if src:
            row["_field_sources"] = src
        html_seed[y] = row
    return html_seed


_BANK_FILL_COLS = (
    "total_loans",
    "total_deposits",
    "npl",
    "net_interest_income",
    "allowance_for_credit_losses",
)


def _needs_bank_fields(fins: list[dict]) -> bool:
    """True when any year is missing a bank field or pdf provenance tag."""
    for f in fins:
        src = sources_from_json(f.get("field_sources"))
        for col in _BANK_FILL_COLS:
            if f.get(col) is None:
                return True
            if src.get(col) != "pdf":
                return True
    return False


def _companies_needing_oi_or_cash(cur, tickers: list[str] | None) -> list[dict]:
    """
    Non-financials with OI/cash gaps, plus banks missing loans/deposits/NPL/NII.
    Explicit --tickers still respects sector rules (banks only for bank fields).
    """
    rows = cur.execute(
        """
        SELECT c.id, c.ticker, c.name, c.symbol AS cmpy_id, c.sector, c.subsector,
               c.outstanding_shares, c.pe_ratio, c.pb_ratio, c.roe, c.market_cap,
               c.last_traded_price
        FROM companies c
        ORDER BY c.ticker
        """
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if tickers and (d.get("ticker") or "").upper() not in tickers:
            continue
        financial = is_financial_sector(d.get("sector"), d.get("subsector"))
        deposit_bank = is_banks_subsector(d.get("sector"), d.get("subsector"))
        fins = [
            dict(x)
            for x in cur.execute(
                """
                SELECT fiscal_year, revenue, net_income, operating_income,
                       income_before_tax, gross_profit, ga_expense, eps,
                       total_assets, cash_and_equivalents, outstanding_shares,
                       total_loans, total_deposits, npl, net_interest_income,
                       allowance_for_credit_losses, field_sources
                FROM financials WHERE company_id=? ORDER BY fiscal_year
                """,
                (d["id"],),
            ).fetchall()
        ]
        if not fins:
            continue
        if deposit_bank:
            if _needs_bank_fields(fins):
                out.append(d)
            continue
        if financial:
            # Brokers / other FI: equity ROIC path; no bank-field backfill
            continue
        if any(
            needs_pdf_oi(f) or needs_pdf_cash(f) or needs_pdf_eps(f) for f in fins
        ):
            out.append(d)
    return out


def _extract_from_cached_pdfs(cmpy_id: str) -> dict[int, dict]:
    base = os.path.join("data", "filings", str(cmpy_id))
    if not os.path.isdir(base):
        return {}
    candidates = []
    for root, _, files in os.walk(base):
        for name in files:
            if not name.lower().endswith(".pdf"):
                continue
            path = os.path.join(root, name)
            yearly = extract_roic_metrics_from_pdf_path(path, filename_hint=name)
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
        # company filled by caller via second merge with seed — here yearly is HTML
        return yearly, pdf_merged
    return yearly, {}


def _rescreen(conn, company: dict) -> None:
    cur = conn.cursor()
    fins = cur.execute(
        """
        SELECT fiscal_year, revenue, net_income, eps, book_value,
               total_assets, total_liabilities, stockholders_equity,
               outstanding_shares, current_ratio, quick_ratio,
               cash_and_equivalents, total_current_liabilities,
               operating_income, income_before_tax, income_tax_expense,
               gross_profit, ga_expense, statement_scope
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
            "sector": company.get("sector"),
            "subsector": company.get("subsector"),
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
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--tickers", default="", help="Comma-separated tickers")
    ap.add_argument(
        "--cached-pdfs-only",
        action="store_true",
        help="Only re-extract local data/filings/{cmpy_id} PDFs",
    )
    ap.add_argument(
        "--derive-eps-only",
        action="store_true",
        help="Skip PDF OCR; fill zero/null EPS from NI/shares only",
    )
    ap.add_argument("--max-pdfs", type=int, default=8)
    args = ap.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()] or None

    db.init_db()
    conn = db.get_connection()
    cur = conn.cursor()
    targets = _companies_needing_oi_or_cash(cur, tickers)
    if args.derive_eps_only:
        filtered = []
        for co in targets:
            fins = [
                dict(x)
                for x in cur.execute(
                    """
                    SELECT net_income, eps, outstanding_shares
                    FROM financials WHERE company_id=?
                    """,
                    (co["id"],),
                ).fetchall()
            ]
            if any(needs_pdf_eps(f) for f in fins):
                filtered.append(co)
        targets = filtered
    if args.limit and args.limit > 0:
        targets = targets[: args.limit]

    n_bank = sum(
        1
        for co in targets
        if is_banks_subsector(co.get("sector"), co.get("subsector"))
    )
    print(
        f"Whitelist targets: {len(targets)}"
        f" (banks needing loans/NII/etc: {n_bank})"
        f"{' (cached PDFs only)' if args.cached_pdfs_only else ''}"
        f"{' [derive-eps-only]' if args.derive_eps_only else ''}"
        f"{' [dry-run]' if args.dry_run else ''}"
    )

    scraper = None if (args.cached_pdfs_only or args.derive_eps_only) else PSEScraper()
    touched = 0
    field_updates = 0

    for co in targets:
        cmpy_id = str(co["cmpy_id"])
        ticker = co["ticker"]
        company_meta = {
            "sector": co.get("sector"),
            "subsector": co.get("subsector"),
            "ticker": ticker,
            "outstanding_shares": co.get("outstanding_shares"),
        }
        try:
            html_seed = _load_html_seed(cur, co["id"])
            if args.derive_eps_only:
                yearly = fill_html_whitelist(html_seed, {}, company=company_meta)
            elif args.cached_pdfs_only:
                pdf_yearly = _extract_from_cached_pdfs(cmpy_id)
                yearly = fill_html_whitelist(html_seed, pdf_yearly, company=company_meta)
            else:
                html_live, pdf_merged = _extract_live(
                    scraper, cmpy_id, max_pdfs=args.max_pdfs
                )
                # Prefer live HTML when present; else DB seed
                base = html_live if html_live else html_seed
                yearly = fill_html_whitelist(base, pdf_merged, company=company_meta)

            yearly, scale_notes = repair_thousand_scale_jumps(
                yearly,
                shares_fallback=co.get("outstanding_shares"),
            )
            yearly, pl_notes = harmonize_yearly_pl_scale(yearly)
            for note in scale_notes + pl_notes:
                logger.info("%s: %s", ticker, note)

            company_hits = 0
            for year, metrics in sorted(yearly.items()):
                existing = cur.execute(
                    """
                    SELECT operating_income, ga_expense, cash_and_equivalents,
                           gross_profit, cost_of_sales, interest_expense,
                           other_expenses, total_loans, total_deposits, npl,
                           net_interest_income, allowance_for_credit_losses,
                           eps, field_sources
                    FROM financials WHERE company_id=? AND fiscal_year=?
                    """,
                    (co["id"], year),
                ).fetchone()
                if not existing:
                    continue
                replaceable = (
                    "operating_income",
                    "ga_expense",
                    "cash_and_equivalents",
                    "gross_profit",
                    "cost_of_sales",
                    "interest_expense",
                    "other_expenses",
                    "eps",
                    # Bank BS/IS lines: allow overwrite when re-extract corrects
                    # interest-income / note false positives (e.g. BPI loans).
                    "total_loans",
                    "total_deposits",
                    "npl",
                    "net_interest_income",
                    "allowance_for_credit_losses",
                )
                updates = {}
                for col in _UPDATE_COLS:
                    new = metrics.get(col)
                    if new is None:
                        continue
                    old = existing[col] if col in existing.keys() else None
                    replace_ok = old is None or (
                        col in replaceable and old != new
                    )
                    if col == "eps" and old is not None:
                        try:
                            # EDGE placeholder zeros are replaceable
                            if float(old) == 0.0:
                                replace_ok = True
                        except (TypeError, ValueError):
                            pass
                    if not replace_ok:
                        continue
                    if old is None or col in replaceable or (
                        col == "eps" and replace_ok
                    ):
                        try:
                            if old is not None and abs(float(old) - float(new)) < 1e-9:
                                continue
                        except (TypeError, ValueError):
                            pass
                        updates[col] = new
                metric_sources = metrics.get("_field_sources") or {}
                existing_sources = sources_from_json(existing["field_sources"])
                # Stamp pdf provenance for bank fields already equal to PDF extract
                # (earlier runs filled values without field_sources).
                src_updates = [
                    col for col in updates if col != "statement_scope"
                ]
                for col in _BANK_FILL_COLS:
                    new = metrics.get(col)
                    if new is None or col in src_updates:
                        continue
                    old = existing[col] if col in existing.keys() else None
                    if old is None:
                        continue
                    try:
                        if abs(float(old) - float(new)) >= 1e-3:
                            continue
                    except (TypeError, ValueError):
                        continue
                    if existing_sources.get(col) != "pdf":
                        src_updates.append(col)
                if not updates and not src_updates:
                    continue
                company_hits += 1
                field_updates += len(updates)
                if updates:
                    bits = ", ".join(
                        f"{k}={updates[k]:.6g}"
                        if isinstance(updates[k], float)
                        else f"{k}={updates[k]}"
                        for k in updates
                    )
                    print(f"  {ticker} FY{year}: {bits}")
                elif src_updates:
                    print(f"  {ticker} FY{year}: sources {','.join(src_updates)}")
                if args.dry_run:
                    continue
                sources = merge_source_tags(existing_sources, src_updates, "pdf")
                for col in src_updates:
                    tag = metric_sources.get(col)
                    if tag:
                        sources[col] = tag
                updates_with_src = dict(updates)
                updates_with_src["field_sources"] = sources_to_json(sources)
                sets = ", ".join(f"{c}=?" for c in updates_with_src)
                cur.execute(
                    f"UPDATE financials SET {sets} WHERE company_id=? AND fiscal_year=?",
                    (*updates_with_src.values(), co["id"], year),
                )

            if company_hits:
                touched += 1
                if not args.dry_run:
                    _rescreen(conn, co)
        except Exception as exc:
            logger.warning("Backfill failed %s: %s", ticker, exc)

    if not args.dry_run:
        conn.commit()
    conn.close()
    print(
        f"{'[dry-run] ' if args.dry_run else ''}"
        f"companies touched: {touched}; field updates: {field_updates}"
    )


if __name__ == "__main__":
    main()
