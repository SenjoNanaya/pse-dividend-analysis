import pandas as pd
from src.scraper import PSEScraper
from src import report_generator
from src.utils import logger, random_delay
from src import db 
from src.db import get_connection, init_db
from src import parser
from src.report_metrics import compute_screening_summary, map_shares_to_fiscal_years
from src.filing_triage import select_attachments_to_download
from src.pdf_roic_extract import (
    extract_roic_metrics_from_pdf_bytes,
    fill_html_whitelist,
    prefer_scope_metrics,
    plausible_fiscal_years,
)
from src.scale_guard import repair_thousand_scale_jumps
import os


def run_pipeline():
    # 1. Initialize database
    init_db()
    conn = get_connection()
    
    try:
        companies_df = pd.read_csv("./data/companies.csv")
    except Exception as e:
        logger.error(f"Failed to read companies.csv: {e}")
        return

    scraper = PSEScraper()

    for index, row in companies_df.iterrows():
        cmpy_id = str(row['cmpy_id'])  # Ensure it's a string
        security_id = str(row['security_id'])
        sector = row.get('sector', None)  # If your CSV has a sector column
        
        # 2. Skip if already processed recently (e.g., last 24 hours)
        # First, check if company exists in DB and was processed successfully
        # We'll check by trying to fetch its ID
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM companies WHERE symbol = ?", (cmpy_id,))
        company_row = cursor.fetchone()
        company_db_id = company_row[0] if company_row else None
        
        # if company_db_id and db.is_company_processed_recently(conn, company_db_id, hours=24):
        #     logger.info(f"✅ Skipping {cmpy_id} (processed within last 24 hours)")
        #     continue
        
        logger.info(f"🔄 Processing {cmpy_id}...")
        
        try:
            # 3. Scrape data (your existing logic)
            stock_html = scraper.fetch_stock_data(cmpy_id, security_id)
            stock_info = parser.parse_stock_data(stock_html)
            
            company_info_html = scraper.fetch_company_info(cmpy_id)
            company_info = parser.parse_company_info(company_info_html)
            
            stock_info['sector'] = company_info.get('sector')
            subsector = company_info.get('subsector')

            div_html = scraper.fetch_dividends(cmpy_id)
            dividends = parser.parse_dividends(div_html)
            
            # Annual Reports
            yearly_metrics = {}
            filing_prices = []
            disclosure_ratios = {}
            pdf_metric_candidates = []  # (scope, yearly_dict)
            disc_search_html = scraper.fetch_disclosures_search(cmpy_id, "Annual Report")
            edge_numbers = parser.parse_disclosure_edge_numbers(disc_search_html)
            
            for edge_no in edge_numbers:
                viewer_html = scraper.fetch_disclosure_viewer(edge_no)
                iframe_link = parser.parse_iframe_source(viewer_html)
                if iframe_link:
                    referer = f"https://edge.pse.com.ph/openDiscViewer.do?edge_no={edge_no}"
                    report_html = scraper.fetch_report_html(iframe_link, referer)
                    disc_data = parser.parse_report_html(report_html)
                    scale_factor = disc_data.get('scale_factor', 1)
                    all_metrics = parser.extract_all_years_metrics(disc_data.get('tables', []), scale_factor=scale_factor)
                    yearly_metrics.update(all_metrics)

                    filing_price = disc_data.get('filing_price')
                    disc_year = disc_data.get('year')
                    if filing_price is not None and disc_year:
                        filing_prices.append((disc_year, filing_price))
                    elif filing_price is not None and all_metrics:
                        filing_prices.append((max(all_metrics.keys()), filing_price))

                    for year, ratios in (disc_data.get('financial_ratios') or {}).items():
                        disclosure_ratios.setdefault(year, {}).update(ratios)

                # PDF attachments (ROIC whitelist); OCR runs automatically on sparse/image-only AFS
                attachments = parser.parse_disclosure_attachments(viewer_html)
                to_fetch = select_attachments_to_download(attachments, max_files=6)
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
                            # Infer scope from first year meta
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
                yearly_metrics = fill_html_whitelist(yearly_metrics, pdf_merged)

            # Shares (Form 17-C)
            historical_shares = {}
            share_search_html = scraper.fetch_disclosures_search(cmpy_id, "Shares")
            share_edges = parser.parse_disclosure_edge_numbers(share_search_html)
            
            for edge_no in share_edges:
                viewer_html = scraper.fetch_disclosure_viewer(edge_no)
                iframe_link = parser.parse_iframe_source(viewer_html)
                if iframe_link:
                    referer = f"https://edge.pse.com.ph/openDiscViewer.do?edge_no={edge_no}"
                    report_html = scraper.fetch_report_html(iframe_link, referer)
                    disc_data = parser.parse_report_html(report_html)
                    if disc_data.get('type') == 'form17c':
                        year = disc_data.get('year')
                        shares = disc_data.get('common_shares_outstanding')
                        if year and shares:
                            historical_shares[year] = shares
            
            # Merge Form 17-C shares onto real statement fiscal years only
            fiscal_years = plausible_fiscal_years(list(yearly_metrics.keys()))
            # Drop accidental PDF/HTML junk year keys before persistence
            for y in list(yearly_metrics.keys()):
                if y not in fiscal_years:
                    logger.warning(
                        "Dropping non-plausible fiscal year %s for %s", y, cmpy_id
                    )
                    yearly_metrics.pop(y, None)

            share_by_year = map_shares_to_fiscal_years(
                historical_shares,
                fiscal_years,
                stock_shares=stock_info.get('outstanding_shares'),
            )
            for year, shares in share_by_year.items():
                if year in yearly_metrics:
                    yearly_metrics[year]['outstanding_shares'] = shares

            # Insert-time guard: repair ~1000× cross-year HTML scale misses
            # (after shares merge so equity ≈ BV×shares can anchor the fix)
            yearly_metrics, scale_actions = repair_thousand_scale_jumps(
                yearly_metrics,
                shares_fallback=stock_info.get("outstanding_shares"),
            )
            for note in scale_actions:
                logger.warning("Scale guard %s: %s", cmpy_id, note)

            # Fill blank stock-page P/E, P/B, price, ROE from disclosures
            stock_info = parser.resolve_valuation_fallbacks(
                stock_info,
                yearly_metrics,
                filing_prices=filing_prices,
                disclosure_ratios=disclosure_ratios,
            )

            # 4. Build company_data (same as before)
            company_data = {
                "stock_data": stock_info,
                "years": yearly_metrics,
                "dividends": dividends,
                "historical_outstanding_shares": historical_shares
            }
            
            # 5. Check if we have any data before storing
            if not yearly_metrics:
                logger.warning(f"No financial data for {cmpy_id}, skipping report and storage.")
                # Log failure but don't store anything
                if company_db_id:
                    db.log_processing(conn, company_db_id, 'failed', 'No financial data found')
                continue
            
            # 6. Insert into database
            # 6a. Get or create company
            company_name = stock_info.get('company_name', 'Unknown')
            company_id = db.get_or_create_company(
                conn,
                cmpy_id,
                company_name,
                stock_info.get('sector'),
                subsector=subsector,
                snapshot={
                    'ticker': stock_info.get('ticker'),
                    'market_cap': stock_info.get('market_cap'),
                    'outstanding_shares': stock_info.get('outstanding_shares'),
                    'last_traded_price': stock_info.get('last_traded_price'),
                    'pe_ratio': stock_info.get('pe_ratio'),
                    'pb_ratio': stock_info.get('pb_ratio'),
                    'roe': stock_info.get('roe'),
                },
            )
            
            # 6b. Insert financials for each year (skip share-only / empty shells)
            financial_rows = []
            for year, metrics in yearly_metrics.items():
                year_ratios = disclosure_ratios.get(year, {})
                financial_data = {
                    'revenue': metrics.get('gross_revenue'),
                    'net_income': metrics.get('net_income'),
                    'eps': metrics.get('eps'),
                    'book_value': metrics.get('book_value_per_share'),
                    'total_assets': metrics.get('total_assets'),
                    'total_liabilities': metrics.get('total_liabilities'),
                    'stockholders_equity': metrics.get('stockholders_equity'),
                    'total_current_liabilities': metrics.get('total_current_liabilities'),
                    'cash_and_equivalents': metrics.get('cash_and_equivalents'),
                    'operating_income': metrics.get('operating_income'),
                    'income_before_tax': metrics.get('income_before_tax'),
                    'income_tax_expense': metrics.get('income_tax_expense'),
                    'gross_profit': metrics.get('gross_profit'),
                    'ga_expense': metrics.get('ga_expense'),
                    'statement_scope': metrics.get('statement_scope'),
                    'current_ratio': year_ratios.get('current_ratio'),
                    'quick_ratio': year_ratios.get('quick_ratio'),
                    'outstanding_shares': metrics.get('outstanding_shares'),
                }
                has_core = any(
                    financial_data.get(k) is not None
                    for k in (
                        'revenue', 'net_income', 'eps', 'book_value',
                        'total_assets', 'total_liabilities', 'stockholders_equity',
                    )
                )
                if not has_core:
                    continue
                if not plausible_fiscal_years([year]):
                    continue
                # Guard against note/year misfires stored as "assets"
                assets = financial_data.get('total_assets')
                if (
                    assets is not None
                    and abs(float(assets)) < 1_000
                    and financial_data.get('net_income') is None
                    and financial_data.get('book_value') is None
                ):
                    continue
                db.insert_financials(conn, company_id, year, financial_data)
                financial_rows.append({'fiscal_year': year, **financial_data})

            screening = compute_screening_summary(
                {
                    'name': company_name,
                    'ticker': stock_info.get('ticker'),
                    'pe_ratio': stock_info.get('pe_ratio'),
                    'pb_ratio': stock_info.get('pb_ratio'),
                    'roe': stock_info.get('roe'),
                    'market_cap': stock_info.get('market_cap'),
                    'outstanding_shares': stock_info.get('outstanding_shares'),
                    'last_traded_price': stock_info.get('last_traded_price'),
                },
                financial_rows,
                dividends=dividends,
            )
            db.update_company_screening(
                conn,
                company_id,
                screening['check_pass_count'],
                screening['check_evaluable_total'],
                screening['info_incomplete'],
                div_yield=screening.get('div_yield'),
                check_struct_pass=screening.get('check_struct_pass'),
                check_struct_eval=screening.get('check_struct_eval'),
            )
            
            # 6c. Insert dividends (common + preferred; yield uses is_common)
            for div in dividends:
                dividend_data = {
                    'ex_date': div.get('ex_date'),
                    'record_date': div.get('record_date'),
                    'payment_date': div.get('payment_date'),
                    'amount': div.get('rate'),
                    'type': div.get('type', 'cash'),
                    'security': div.get('security'),
                    'is_common': div.get('is_common', True),
                }
                db.insert_dividend(conn, company_id, dividend_data)
            
            # 6d. Log success
            db.log_processing(conn, company_id, 'success')
            logger.info(f"✅ Successfully stored {cmpy_id} in database")
            
            # 7. Optional: Generate report (comment out if you want DB-only)
            report_generator.generate_report(company_data)
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed for {cmpy_id}: {error_msg}")
            # Log failure if company exists in DB
            if company_db_id:
                db.log_processing(conn, company_db_id, 'failed', error_msg)
            # Don't stop the pipeline
            continue
        finally:
            # Polite delay between companies
            random_delay()
    
    # Close connection when done
    conn.close()
    logger.info("Pipeline execution completed successfully.")

if __name__ == "__main__":
    logger.info("Starting pipeline processing execution.")
    run_pipeline()