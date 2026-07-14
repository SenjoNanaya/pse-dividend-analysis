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
    
    def fetch_disclosures_search(self, cmpy_id, disclosure_type):
        logger.info(f"Searching disclosures '{disclosure_type}' for company: {cmpy_id}")

        headers = {
            **DEFAULT_HEADERS,
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'Origin': self.base_url,
            'Referer': f"{self.base_url}/companyDisclosures/form.do?cmpy_id={cmpy_id}"
        }
        
        data = {
            'keyword': cmpy_id,
            'tmplNm': disclosure_type
        }
        
        url = f"{self.base_url}/companyDisclosures/search.ax"
        response = self.session.post(url, headers=headers, data=data)
        return response.text
    
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