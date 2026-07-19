import requests
from src.utils import DEFAULT_HEADERS, random_delay, logger

class PSEScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.base_url = "https://edge.pse.com.ph"
    
    def fetch_stock_data(self, cmpy_id, security_id):
        logger.info(f"Fetching stock data for company: {cmpy_id}")
        
        params = {
            'cmpy_id': cmpy_id, 
            'security_id': security_id
        }
        
        url = f"{self.base_url}/companyPage/stockData.do"
        response = self.session.get(url, params=params)
        return response.text
    
    def fetch_dividends(self, cmpy_id):
        logger.info(f"Fetching dividends for company: {cmpy_id}")
        
        headers = {
            **DEFAULT_HEADERS,
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'Origin': self.base_url,
            'Referer': f'{self.base_url}/companyPage/dividends_and_rights_form.do?cmpy_id={cmpy_id}'
        }
        
        params = {
            'DividendsOrRights': 'Dividends'
        }
        
        data = {'cmpy_id': cmpy_id}
        url = f"{self.base_url}/companyPage/dividends_and_rights_list.ax"
        response = self.session.post(url, params=params, headers=headers, data=data)
        return response.text
    
    def fetch_disclosures_search(self, cmpy_id, disclosure_type, *, page_no=None):
        logger.info(
            "Searching disclosures '%s' for company: %s%s",
            disclosure_type,
            cmpy_id,
            f" page={page_no}" if page_no is not None else "",
        )

        headers = {
            **DEFAULT_HEADERS,
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'Origin': self.base_url,
            'Referer': f"{self.base_url}/companyDisclosures/form.do?cmpy_id={cmpy_id}"
        }
        
        data = {
            'keyword': cmpy_id,
            'tmplNm': disclosure_type,
            'sortType': 'date',
            'dateSortType': 'DESC',
            'cmpySortType': 'ASC',
        }
        if page_no is not None:
            data['pageNo'] = str(page_no)
        
        url = f"{self.base_url}/companyDisclosures/search.ax"
        response = self.session.post(url, headers=headers, data=data)
        return response.text

    def fetch_all_disclosure_edge_numbers(
        self,
        cmpy_id,
        disclosure_type,
        *,
        max_pages: int = 20,
        parse_edge_numbers=None,
    ) -> list[str]:
        """
        Paginate ``search.ax`` (pageNo) and return unique edge_nos newest-first.
        """
        if parse_edge_numbers is None:
            from src.parser import parse_disclosure_edge_numbers

            parse_edge_numbers = parse_disclosure_edge_numbers

        import re

        seen: set[str] = set()
        ordered: list[str] = []
        total_pages = 1
        for page in range(1, max(1, max_pages) + 1):
            html = self.fetch_disclosures_search(
                cmpy_id, disclosure_type, page_no=page
            )
            m = re.search(
                r"\[\s*(\d+)\s*/\s*(\d+)\s*\]",
                html or "",
            )
            if m:
                total_pages = max(total_pages, int(m.group(2)))
            edges = parse_edge_numbers(html)
            if not edges:
                break
            for e in edges:
                if e in seen:
                    continue
                seen.add(e)
                ordered.append(e)
            if page >= total_pages:
                break
        return ordered

    def fetch_disclosure_viewer(self, edge_no):
        logger.info(f"Fetching disclosure viewer for edge_no: {edge_no}")
        
        params = {'edge_no': edge_no}
        
        url = f"{self.base_url}/openDiscViewer.do"
        response = self.session.get(url, params=params)
        return response.text
    
    def fetch_report_html(self, iframe_link, referer):
        logger.info(f"Downloading HTML report from path: {iframe_link}")
        headers = {**DEFAULT_HEADERS, 'Referer': referer, 'Upgrade-Insecure-Requests': '1'}
        
        if iframe_link.startswith("/"):
            url = f"{self.base_url}{iframe_link}"
            response = self.session.get(url, headers=headers)
        else:
            url = f"{self.base_url}/downloadHtml.do"
            params = {'file_id': iframe_link}
            response = self.session.get(url, params=params, headers=headers)
            
        return response.text
    
    def fetch_company_info(self, cmpy_id):
        logger.info(f"Fetching company info for cmpy_id: {cmpy_id}")
        url = f"{self.base_url}/companyInformation/form.do?cmpy_id={cmpy_id}"
        response = self.session.get(url)
        return response.text

    def fetch_attachment_file(self, file_id, referer=None):
        """
        Download a disclosure attachment (typically PDF) via downloadFile.do.
        Returns response content bytes.
        """
        logger.info(f"Downloading attachment file_id={file_id}")
        headers = {
            **DEFAULT_HEADERS,
            "Upgrade-Insecure-Requests": "1",
        }
        if referer:
            headers["Referer"] = referer
        url = f"{self.base_url}/downloadFile.do"
        # EDGE form uses GET or POST with file_id; try GET first then POST
        response = self.session.get(url, params={"file_id": file_id}, headers=headers)
        if response.status_code >= 400 or len(response.content) < 100:
            response = self.session.post(url, data={"file_id": file_id}, headers=headers)
        response.raise_for_status()
        return response.content