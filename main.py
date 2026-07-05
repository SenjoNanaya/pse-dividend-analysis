import pandas as pd
from src.scraper import PSEScraper
from src import parser
from src import database
from src.utils import logger

def run_pipeline(row_index=45):
    try:
        companies = pd.read_csv("./data/companies.csv")
        cmpy_id = companies.at[row_index, "cmpy_id"]
        security_id = companies.at[row_index, "security_id"]
    except Exception as e:
        logger.error(f"Failed to read data/companies.csv: {e}")
        return

    scraper = PSEScraper()

    # fetch and parse stocks
    stock_html = scraper.fetch_stock_data(cmpy_id, security_id)
    stock_info = parser.parse_stock_data(stock_html)

    # fetch and parse divs
    div_html = scraper.fetch_dividends(cmpy_id)
    dividends = parser.parse_dividends(div_html)

    # fetch & parse disclosures
    yearly_metrics = {}
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
            for yr, mets in all_metrics.items():
                yearly_metrics[yr] = mets  # updates with newest restated items if duplicate

    # fetch & parse share dilution disclosures
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

    for year, shares in historical_shares.items():
        if year in yearly_metrics:
            yearly_metrics[year]['outstanding_shares'] = shares
        else:
            yearly_metrics[year] = {'outstanding_shares': shares}

    # company_data proper
    company_data = {
        "stock_data": stock_info,
        "years": yearly_metrics,
        "dividends": dividends,
        "historical_outstanding_shares": historical_shares
    }

    database.generate_report(company_data)

if __name__ == "__main__":
    logger.info("Starting pipeline processing execution.")
    run_pipeline(row_index=45)
    logger.info("Pipeline execution completed successfully.")