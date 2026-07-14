import React, { useState, useEffect } from 'react';
import CompanyReport from './components/CompanyReport';

export default function App() {
  const [view, setView] = useState('landing');

  const [companies, setCompanies] = useState([]);
  const [apiUrl, setApiUrl] = useState('http://127.0.0.1:8000/api/companies/');
  const [nextPage, setNextPage] = useState(null);
  const [prevPage, setPrevPage] = useState(null);
  const [search, setSearch] = useState('');
  const [totalCount, setTotalCount] = useState(0);
  const [listStatus, setListStatus] = useState('loading');
  const [listError, setListError] = useState(null);

  const [selectedCompanyId, setSelectedCompanyId] = useState(null);
  const [companyDetails, setCompanyDetails] = useState(null);
  const [detailStatus, setDetailStatus] = useState('idle');

  const jsonHeaders = { Accept: 'application/json' };

  useEffect(() => {
    let cancelled = false;
    setListStatus('loading');
    setListError(null);

    fetch(apiUrl, { headers: jsonHeaders })
      .then(async (res) => {
        if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
        return res.json();
      })
      .then((data) => {
        if (cancelled) return;
        setCompanies(data.results || []);
        setNextPage(data.next);
        setPrevPage(data.previous);
        setTotalCount(data.count || 0);
        setListStatus('ready');
      })
      .catch((err) => {
        if (cancelled) return;
        console.error('Fetch error:', err);
        setCompanies([]);
        setListError(err.message || 'Failed to reach API');
        setListStatus('error');
      });

    return () => { cancelled = true; };
  }, [apiUrl]);

  useEffect(() => {
    if (!selectedCompanyId) return;
    let cancelled = false;
    setCompanyDetails(null);
    setDetailStatus('loading');

    fetch(`http://127.0.0.1:8000/api/companies/${selectedCompanyId}/`, {
      headers: jsonHeaders,
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
        return res.json();
      })
      .then((data) => {
        if (cancelled) return;
        setCompanyDetails(data);
        setDetailStatus('ready');
      })
      .catch((err) => {
        if (cancelled) return;
        console.error('Network error fetching detail record:', err);
        setDetailStatus('error');
      });

    return () => { cancelled = true; };
  }, [selectedCompanyId]);

  const handleSearch = (e) => {
    e.preventDefault();
    setApiUrl(`http://127.0.0.1:8000/api/companies/?search=${encodeURIComponent(search)}`);
  };

  const openCompany = (id) => {
    setSelectedCompanyId(id);
    setView('report');
  };

  const backToDirectory = () => {
    setView('dashboard');
    setSelectedCompanyId(null);
    setCompanyDetails(null);
    setDetailStatus('idle');
  };

  if (view === 'landing') {
    return (
      <div className="min-h-screen bg-nier-bg font-nier text-nier-dark flex flex-col justify-between p-8 lg:p-16 select-none animate-fade-in">
        <div className="w-full flex justify-between items-center border-b border-nier-dark pb-3 text-xs tracking-widest font-bold">
          <div>[ GLORY_TO_MANKIND ]</div>
          <div>SYS_STATUS: READY</div>
        </div>

        <div className="max-w-2xl mx-auto flex flex-col gap-6 text-center lg:text-left my-auto">
          <div className="flex justify-center lg:justify-start items-center gap-4">
            <div className="w-8 h-8 bg-nier-dark"></div>
            <span className="text-xs uppercase tracking-widest font-mono opacity-60">PROTOTYPE_V.2.0.6</span>
          </div>

          <h1 className="text-4xl lg:text-6xl font-bold tracking-tighter uppercase border-b-4 border-nier-dark pb-4">
            PSE_ANALYSIS <br />
            <span className="text-nier-orange font-normal">DATA_REGISTRY</span>
          </h1>

          <p className="text-xs tracking-widest uppercase leading-relaxed opacity-80 max-w-md">
            Automated monitoring client for tracking stock indexes, financial statements, and systemic multi-sector business evaluation records.
          </p>

          <div className="pt-4">
            <button
              onClick={() => setView('dashboard')}
              className="group relative border-2 border-nier-dark bg-transparent text-nier-dark px-10 py-4 uppercase tracking-widest text-sm font-bold rounded-none hover:bg-nier-dark hover:text-nier-bg transition-colors duration-300 w-full lg:w-auto"
            >
              Initialize Dashboard Sequence
              <span className="absolute -bottom-2 -right-2 w-3 h-3 bg-nier-dark group-hover:bg-nier-orange transition-colors"></span>
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (view === 'report') {
    if (detailStatus === 'loading' || detailStatus === 'idle') {
      return (
        <div className="report-page report-loading">
          LOADING_FUNDAMENTAL_RECORD...
        </div>
      );
    }
    if (detailStatus === 'error' || !companyDetails) {
      return (
        <div className="report-page report-loading">
          <p>RECORD_RETRIEVAL_FAILURE</p>
          <button type="button" className="report-back" onClick={backToDirectory}>
            &lt; REGISTRY
          </button>
        </div>
      );
    }
    return <CompanyReport company={companyDetails} onBack={backToDirectory} />;
  }

  return (
    <div className="min-h-screen bg-nier-bg font-nier text-nier-dark p-4 lg:p-10 select-text">
      <header className="nier-dashboard-header">
        <div className="flex items-center gap-3">
          <button onClick={() => setView('landing')} className="nier-btn px-3 py-1 text-xs">
            &lt; DISCONNECT
          </button>
          <div className="w-3 h-3 bg-nier-dark hidden lg:block"></div>
          <h1 className="uppercase tracking-widest text-sm font-bold">CENTRAL_REGISTRY_UNIT</h1>
        </div>
        <div className="text-xs tracking-widest uppercase font-bold text-right">
          [ ONLINE_RECORDS: <span className="text-nier-orange">{totalCount}</span> ]
        </div>
      </header>

      <div className="nier-table-column max-w-5xl">
        <form onSubmit={handleSearch} className="nier-search-form">
          <input
            type="text"
            placeholder="FILTER BY TICKER, SYMBOL OR NAME..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="grow nier-input"
          />
          <button type="submit" className="nier-btn">QUERY</button>
        </form>

        <div className="nier-table-container">
          <table className="nier-table">
            <thead>
              <tr>
                <th>TICKER</th>
                <th>NAME</th>
                <th>SECTOR</th>
              </tr>
            </thead>
            <tbody className="text-xs tracking-wider uppercase">
              {listStatus === 'loading' ? (
                <tr>
                  <td colSpan="3" className="text-center opacity-50 py-12 tracking-widest">
                    AWAITING_DATABASE_STREAM_INTEGRITY...
                  </td>
                </tr>
              ) : listStatus === 'error' ? (
                <tr>
                  <td colSpan="3" className="text-center py-12 tracking-widest text-nier-orange">
                    LINK_FAILURE: {listError || 'UNABLE_TO_REACH_API'}
                    <div className="mt-2 opacity-60 text-[10px] normal-case tracking-normal">
                      Is Django running on http://127.0.0.1:8000 ?
                    </div>
                  </td>
                </tr>
              ) : companies.length === 0 ? (
                <tr>
                  <td colSpan="3" className="text-center opacity-50 py-12 tracking-widest">
                    NO_RECORDS_MATCH_QUERY
                  </td>
                </tr>
              ) : (
                companies.map((company) => (
                  <tr
                    key={company.id}
                    onClick={() => openCompany(company.id)}
                    className="transition-colors duration-150 hover:bg-nier-dark/10"
                  >
                    <td className="font-bold text-nier-orange">
                      {company.ticker || company.symbol}
                    </td>
                    <td>{company.name}</td>
                    <td>{company.sector || 'N/A'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="nier-pagination-bar">
          <button onClick={() => setApiUrl(prevPage)} disabled={!prevPage} className="nier-btn">
            &lt; REWIND_PAGE
          </button>
          <div className="grow border-t border-dotted border-nier-gray mx-4 hidden sm:block"></div>
          <button onClick={() => setApiUrl(nextPage)} disabled={!nextPage} className="nier-btn">
            ADVANCE_PAGE &gt;
          </button>
        </div>
      </div>
    </div>
  );
}
