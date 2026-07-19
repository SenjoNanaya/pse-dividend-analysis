import argparse
import os

import pandas as pd

from src.scraper import PSEScraper
from src import report_generator
from src.utils import logger, random_delay
from src import db
from src.db import get_connection, init_db
from src import parser
from src.field_sources import (
    init_sources_from_metrics,
    remap_sources_for_db,
    set_source,
)
from src.report_metrics import (
    compute_screening_summary,
    incomplete_reasons,
    map_shares_to_fiscal_years,
)
from src.filing_triage import is_financial_sector, select_attachments_to_download
from src.pdf_roic_extract import (
    extract_roic_metrics_from_pdf_bytes,
    fill_html_whitelist,
    prefer_scope_metrics,
    plausible_fiscal_years,
)
from src.scale_guard import harmonize_yearly_pl_scale, repair_thousand_scale_jumps


def _enforce_pe_roic_invariants(conn, company_id, *, ticker, pe, roic):
    """Log and null any PE/ROIC that slipped past resolve/sanitize."""
    from src.parser import (
        NON_OPERATING_PE_TICKERS,
        PE_COMPUTE_ABS_MAX,
        SECONDARY_LISTING_TICKERS,
    )
    from src.utils import safe_float

    t = (ticker or "").strip().upper()
    pe_v = safe_float(pe)
    roic_v = safe_float(roic)
    issues = []
    clear_pe = False
    clear_roic = False

    if pe_v is not None:
        if pe_v == 0 or abs(pe_v) > PE_COMPUTE_ABS_MAX:
            issues.append(f"pe={pe_v}")
            clear_pe = True
        if t in SECONDARY_LISTING_TICKERS or t in NON_OPERATING_PE_TICKERS:
            issues.append(f"pe_on_special_ticker={pe_v}")
            clear_pe = True
    if roic_v is not None and abs(roic_v) > 1.0:
        issues.append(f"roic={roic_v}")
        clear_roic = True

    if not issues:
        return
    logger.warning("PE/ROIC invariant fail %s: %s", t or company_id, "; ".join(issues))
    if clear_pe:
        conn.execute(
            "UPDATE companies SET pe_ratio = NULL WHERE id = ?", (company_id,)
        )
    if clear_roic:
        conn.execute(
            "UPDATE companies SET roic = NULL WHERE id = ?", (company_id,)
        )
    conn.commit()


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="PSE EDGE scrape pipeline (full or incremental).",
    )
    p.add_argument(
        "--skip-recent",
        type=float,
        default=24,
        metavar="HOURS",
        help="Skip companies successfully processed within HOURS (0 = never skip). Default: 24",
    )
    p.add_argument(
        "--tickers",
        type=str,
        default="",
        help="Comma-separated tickers to process (CSV intersection).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        metavar="N",
        help="Process at most N companies after filters (0 = no limit).",
    )
    p.add_argument(
        "--incomplete-only",
        action="store_true",
        help="Only process companies marked info_incomplete in the DB.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Log the work queue without scraping.",
    )
    return p.parse_args(argv)


def _parse_ticker_filter(raw):
    if not raw or not str(raw).strip():
        return None
    return {t.strip().upper() for t in str(raw).split(",") if t.strip()}


def _load_db_index(conn):
    """Map EDGE cmpy_id (companies.symbol) -> row metadata."""
    cur = conn.cursor()
    index = {}
    for row in cur.execute(
        """
        SELECT id, symbol, ticker, info_incomplete, last_updated
        FROM companies
        """
    ):
        index[str(row["symbol"])] = {
            "id": row["id"],
            "ticker": (row["ticker"] or "").upper(),
            "incomplete": bool(row["info_incomplete"]),
            "last_updated": row["last_updated"],
        }
    return index


def build_work_queue(companies_df, conn, tickers=None, incomplete_only=False):
    """
    Order: incomplete first, then oldest last_updated, then never-scraped CSV rows.
    """
    db_index = _load_db_index(conn)
    items = []
    for _, row in companies_df.iterrows():
        cmpy_id = str(row["cmpy_id"])
        csv_ticker = str(row.get("ticker") or "").strip().upper()
        meta = db_index.get(cmpy_id)
        db_id = meta["id"] if meta else None
        incomplete = bool(meta["incomplete"]) if meta else False
        last_updated = meta["last_updated"] if meta else None
        ticker = (meta["ticker"] if meta and meta["ticker"] else csv_ticker) or ""

        if tickers is not None and ticker not in tickers and csv_ticker not in tickers:
            continue
        if incomplete_only and not incomplete:
            continue

        if incomplete:
            tier = 0
        elif db_id is None:
            tier = 2
        else:
            tier = 1

        items.append(
            {
                "row": row,
                "cmpy_id": cmpy_id,
                "security_id": str(row["security_id"]),
                "ticker": ticker or csv_ticker or cmpy_id,
                "db_id": db_id,
                "incomplete": incomplete,
                "last_updated": last_updated,
                "tier": tier,
            }
        )

    items.sort(
        key=lambda it: (
            it["tier"],
            it["last_updated"] or "",
            it["ticker"] or it["cmpy_id"],
        )
    )
    return items


def process_company(conn, scraper, item):
    """Scrape and upsert one CSV company. Returns 'ok' | 'skip_empty' | 'failed'."""
    cmpy_id = item["cmpy_id"]
    security_id = item["security_id"]
    company_db_id = item["db_id"]
    row = item["row"]
    sector = row.get("sector", None)

    logger.info("Processing %s (%s)...", cmpy_id, item["ticker"])

    try:
        stock_html = scraper.fetch_stock_data(cmpy_id, security_id)
        stock_info = parser.parse_stock_data(stock_html)

        company_info_html = scraper.fetch_company_info(cmpy_id)
        company_info = parser.parse_company_info(company_info_html)

        stock_info["sector"] = company_info.get("sector")
        subsector = company_info.get("subsector")

        div_html = scraper.fetch_dividends(cmpy_id)
        dividends = parser.parse_dividends(div_html)

        yearly_metrics = {}
        filing_prices = []
        disclosure_ratios = {}
        pdf_metric_candidates = []
        disc_search_html = scraper.fetch_disclosures_search(cmpy_id, "Annual Report")
        edge_numbers = parser.parse_disclosure_edge_numbers(disc_search_html)

        for edge_no in edge_numbers:
            viewer_html = scraper.fetch_disclosure_viewer(edge_no)
            iframe_link = parser.parse_iframe_source(viewer_html)
            if iframe_link:
                referer = f"https://edge.pse.com.ph/openDiscViewer.do?edge_no={edge_no}"
                report_html = scraper.fetch_report_html(iframe_link, referer)
                disc_data = parser.parse_report_html(report_html)
                scale_factor = disc_data.get("scale_factor", 1)
                all_metrics = parser.extract_all_years_metrics(
                    disc_data.get("tables", []), scale_factor=scale_factor
                )
                yearly_metrics.update(all_metrics)

                filing_price = disc_data.get("filing_price")
                disc_year = disc_data.get("year")
                if filing_price is not None and disc_year:
                    filing_prices.append((disc_year, filing_price))
                elif filing_price is not None and all_metrics:
                    filing_prices.append((max(all_metrics.keys()), filing_price))

                for year, ratios in (disc_data.get("financial_ratios") or {}).items():
                    disclosure_ratios.setdefault(year, {}).update(ratios)

            attachments = parser.parse_disclosure_attachments(viewer_html)
            max_pdfs = (
                6
                if is_financial_sector(stock_info.get("sector"), subsector)
                else 8
            )
            to_fetch = select_attachments_to_download(attachments, max_files=max_pdfs)
            for att in to_fetch:
                try:
                    referer = f"https://edge.pse.com.ph/openDiscViewer.do?edge_no={edge_no}"
                    pdf_bytes = scraper.fetch_attachment_file(
                        att["file_id"], referer=referer
                    )
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
                        pdf_metric_candidates.append((scope, pdf_yearly))
                    random_delay()
                except Exception as pdf_err:
                    logger.warning(
                        "PDF attachment extract failed for %s file_id=%s: %s",
                        cmpy_id,
                        att.get("file_id"),
                        pdf_err,
                    )

        if pdf_metric_candidates:
            pdf_merged = prefer_scope_metrics(pdf_metric_candidates)
            yearly_metrics = fill_html_whitelist(
                yearly_metrics,
                pdf_merged,
                company={
                    "sector": stock_info.get("sector"),
                    "subsector": subsector,
                    "ticker": stock_info.get("ticker"),
                },
            )
        else:
            for _y, _row in yearly_metrics.items():
                if "_field_sources" not in _row:
                    init_sources_from_metrics(_row, "html")

        historical_shares = parser.collect_historical_shares(
            scraper, cmpy_id
        )

        fiscal_years = plausible_fiscal_years(list(yearly_metrics.keys()))
        for y in list(yearly_metrics.keys()):
            if y not in fiscal_years:
                logger.warning(
                    "Dropping non-plausible fiscal year %s for %s", y, cmpy_id
                )
                yearly_metrics.pop(y, None)

        share_by_year = map_shares_to_fiscal_years(
            historical_shares,
            fiscal_years,
            stock_shares=stock_info.get("outstanding_shares"),
        )
        for year, shares in share_by_year.items():
            if year in yearly_metrics:
                yearly_metrics[year]["outstanding_shares"] = shares
                # Tag disclosure history (17-C / 17-12-A) even when mapped via FY±1
                src = "html"
                for y in (year, year + 1, year - 1):
                    if y in historical_shares and historical_shares[y] is not None:
                        try:
                            if abs(float(historical_shares[y]) - float(shares)) < 1.0:
                                src = "form17c"
                                break
                        except (TypeError, ValueError):
                            pass
                set_source(yearly_metrics[year], "outstanding_shares", src)

        yearly_metrics, scale_actions = repair_thousand_scale_jumps(
            yearly_metrics,
            shares_fallback=stock_info.get("outstanding_shares"),
        )
        for note in scale_actions:
            logger.warning("Scale guard %s: %s", cmpy_id, note)
        yearly_metrics, pl_actions = harmonize_yearly_pl_scale(yearly_metrics)
        for note in pl_actions:
            logger.warning("P&L scale %s: %s", cmpy_id, note)

        stock_info = parser.resolve_valuation_fallbacks(
            stock_info,
            yearly_metrics,
            filing_prices=filing_prices,
            disclosure_ratios=disclosure_ratios,
        )

        company_data = {
            "stock_data": stock_info,
            "years": yearly_metrics,
            "dividends": dividends,
            "historical_outstanding_shares": historical_shares,
        }

        if not yearly_metrics:
            logger.warning(
                "No financial data for %s, skipping report and storage.", cmpy_id
            )
            if company_db_id:
                db.log_processing(conn, company_db_id, "failed", "No financial data found")
            return "skip_empty"

        company_name = stock_info.get("company_name", "Unknown")
        company_id = db.get_or_create_company(
            conn,
            cmpy_id,
            company_name,
            stock_info.get("sector"),
            subsector=subsector,
            snapshot={
                "ticker": stock_info.get("ticker"),
                "market_cap": stock_info.get("market_cap"),
                "outstanding_shares": stock_info.get("outstanding_shares"),
                "last_traded_price": stock_info.get("last_traded_price"),
                "pe_ratio": stock_info.get("pe_ratio"),
                "pb_ratio": stock_info.get("pb_ratio"),
                "roe": stock_info.get("roe"),
            },
        )

        financial_rows = []
        for year, metrics in yearly_metrics.items():
            year_ratios = disclosure_ratios.get(year, {})
            if year_ratios.get("current_ratio") is not None:
                set_source(metrics, "current_ratio", "disclosure")
            if year_ratios.get("quick_ratio") is not None:
                set_source(metrics, "quick_ratio", "disclosure")
            sources = remap_sources_for_db(metrics.get("_field_sources"))
            financial_data = {
                "revenue": metrics.get("gross_revenue"),
                "net_income": metrics.get("net_income"),
                "eps": metrics.get("eps"),
                "book_value": metrics.get("book_value_per_share"),
                "total_assets": metrics.get("total_assets"),
                "total_liabilities": metrics.get("total_liabilities"),
                "stockholders_equity": metrics.get("stockholders_equity"),
                "total_current_liabilities": metrics.get("total_current_liabilities"),
                "cash_and_equivalents": metrics.get("cash_and_equivalents"),
                "operating_income": metrics.get("operating_income"),
                "income_before_tax": metrics.get("income_before_tax"),
                "income_tax_expense": metrics.get("income_tax_expense"),
                "gross_profit": metrics.get("gross_profit"),
                "ga_expense": metrics.get("ga_expense"),
                "cost_of_sales": metrics.get("cost_of_sales"),
                "interest_expense": metrics.get("interest_expense"),
                "other_expenses": metrics.get("other_expenses"),
                "total_loans": metrics.get("total_loans"),
                "total_deposits": metrics.get("total_deposits"),
                "npl": metrics.get("npl"),
                "net_interest_income": metrics.get("net_interest_income"),
                "allowance_for_credit_losses": metrics.get(
                    "allowance_for_credit_losses"
                ),
                "statement_scope": metrics.get("statement_scope"),
                "current_ratio": year_ratios.get("current_ratio"),
                "quick_ratio": year_ratios.get("quick_ratio"),
                "outstanding_shares": metrics.get("outstanding_shares"),
                "field_sources": sources,
            }
            has_core = any(
                financial_data.get(k) is not None
                for k in (
                    "revenue",
                    "net_income",
                    "eps",
                    "book_value",
                    "total_assets",
                    "total_liabilities",
                    "stockholders_equity",
                )
            )
            if not has_core:
                continue
            if not plausible_fiscal_years([year]):
                continue
            assets = financial_data.get("total_assets")
            if (
                assets is not None
                and abs(float(assets)) < 1_000
                and financial_data.get("net_income") is None
                and financial_data.get("book_value") is None
            ):
                continue
            db.insert_financials(conn, company_id, year, financial_data)
            financial_rows.append({"fiscal_year": year, **financial_data})

        pruned = db.delete_out_of_range_financials(conn, company_id=company_id)
        if pruned:
            logger.info(
                "Pruned %s out-of-range fiscal year row(s) for %s",
                pruned,
                cmpy_id,
            )

        company_for_screen = {
            "name": company_name,
            "ticker": stock_info.get("ticker"),
            "sector": stock_info.get("sector"),
            "subsector": subsector,
            "pe_ratio": stock_info.get("pe_ratio"),
            "pb_ratio": stock_info.get("pb_ratio"),
            "roe": stock_info.get("roe"),
            "market_cap": stock_info.get("market_cap"),
            "outstanding_shares": stock_info.get("outstanding_shares"),
            "last_traded_price": stock_info.get("last_traded_price"),
        }
        screening = compute_screening_summary(
            company_for_screen,
            financial_rows,
            dividends=dividends,
        )
        db.update_company_screening(
            conn,
            company_id,
            screening["check_pass_count"],
            screening["check_evaluable_total"],
            screening["info_incomplete"],
            div_yield=screening.get("div_yield"),
            roic=screening.get("roic"),
            debt_to_equity=screening.get("debt_to_equity"),
            check_struct_pass=screening.get("check_struct_pass"),
            check_struct_eval=screening.get("check_struct_eval"),
        )

        _enforce_pe_roic_invariants(
            conn,
            company_id,
            ticker=stock_info.get("ticker") or item.get("ticker"),
            pe=stock_info.get("pe_ratio"),
            roic=screening.get("roic"),
        )

        reasons = incomplete_reasons(company_for_screen, financial_rows)
        if reasons:
            logger.info(
                "Incomplete %s (%s): %s",
                item["ticker"],
                cmpy_id,
                ", ".join(reasons),
            )

        for div in dividends:
            dividend_data = {
                "ex_date": div.get("ex_date"),
                "record_date": div.get("record_date"),
                "payment_date": div.get("payment_date"),
                "amount": div.get("rate"),
                "type": div.get("type", "cash"),
                "security": div.get("security"),
                "is_common": div.get("is_common", True),
            }
            db.insert_dividend(conn, company_id, dividend_data)

        db.log_processing(conn, company_id, "success")
        logger.info("Successfully stored %s in database", cmpy_id)

        report_generator.generate_report(company_data)
        return "ok"

    except Exception as e:
        error_msg = str(e)
        logger.error("Failed for %s: %s", cmpy_id, error_msg)
        if company_db_id:
            db.log_processing(conn, company_db_id, "failed", error_msg)
        return "failed"


def run_pipeline(args=None):
    if args is None:
        args = parse_args([])

    init_db()
    conn = get_connection()

    try:
        companies_df = pd.read_csv("./data/companies.csv")
    except Exception as e:
        logger.error("Failed to read companies.csv: %s", e)
        conn.close()
        return

    tickers = _parse_ticker_filter(args.tickers)
    queue = build_work_queue(
        companies_df,
        conn,
        tickers=tickers,
        incomplete_only=args.incomplete_only,
    )

    skip_recent = float(args.skip_recent or 0)
    skipped_recent = 0
    work = []
    for item in queue:
        if (
            skip_recent > 0
            and item["db_id"]
            and db.is_company_processed_recently(conn, item["db_id"], hours=skip_recent)
        ):
            skipped_recent += 1
            logger.info(
                "Skipping %s (%s) — processed within last %s hours",
                item["cmpy_id"],
                item["ticker"],
                skip_recent,
            )
            continue
        work.append(item)

    if args.limit and args.limit > 0:
        work = work[: args.limit]

    logger.info(
        "Queue: %s to process, %s skipped (recent), %s CSV rows after filters",
        len(work),
        skipped_recent,
        len(queue),
    )

    if args.dry_run:
        for item in work:
            logger.info(
                "DRY-RUN would scrape %s ticker=%s incomplete=%s last_updated=%s tier=%s",
                item["cmpy_id"],
                item["ticker"],
                item["incomplete"],
                item["last_updated"],
                item["tier"],
            )
        conn.close()
        logger.info(
            "Dry-run done. would_scrape=%s skipped_recent=%s",
            len(work),
            skipped_recent,
        )
        return

    scraper = PSEScraper()
    ok = failed = empty = 0
    for item in work:
        try:
            result = process_company(conn, scraper, item)
            if result == "ok":
                ok += 1
            elif result == "skip_empty":
                empty += 1
            else:
                failed += 1
        finally:
            random_delay()

    conn.close()
    logger.info(
        "Pipeline done. ok=%s failed=%s empty=%s skipped_recent=%s",
        ok,
        failed,
        empty,
        skipped_recent,
    )


if __name__ == "__main__":
    cli = parse_args()
    logger.info("Starting pipeline processing execution.")
    run_pipeline(cli)
