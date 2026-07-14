import React, { useState, useEffect, useCallback } from 'react';
import CompanyReport from './components/CompanyReport';
import RegistryPreview from './components/RegistryPreview';

const API_BASE = 'http://127.0.0.1:8000/api/companies';
const jsonHeaders = { Accept: 'application/json' };

const SORT_FIELDS = {
  ticker: 'ticker',
  name: 'name',
  sector: 'sector',
  subsector: 'subsector',
  checks: 'check_pass_count',
  pass5: 'check_pass_count',
  incomplete: 'info_incomplete',
};

function buildListUrl({ search = '', ordering = '-check_pass_count', pageUrl = null } = {}) {
  if (pageUrl) return pageUrl;
  const params = new URLSearchParams();
  if (search.trim()) params.set('search', search.trim());
  if (ordering) params.set('ordering', ordering);
  const q = params.toString();
  return `${API_BASE}/${q ? `?${q}` : ''}`;
}

function SortHeader({ label, column, ordering, onSort }) {
  const field = SORT_FIELDS[column];
  const isActive = ordering === field || ordering === `-${field}`;
  const desc = ordering === `-${field}`;
  return (
    <th>
      <button type="button" className="nier-sort-btn" onClick={() => onSort(column)}>
        {label}
        {isActive && <span className="nier-sort-indicator">{desc ? ' ▼' : ' ▲'}</span>}
      </button>
    </th>
  );
}

export default function App() {
  const [view, setView] = useState('landing');

  const [companies, setCompanies] = useState([]);
  const [search, setSearch] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [ordering, setOrdering] = useState('-check_pass_count');
  const [pageUrl, setPageUrl] = useState(null);
  const [nextPage, setNextPage] = useState(null);
  const [prevPage, setPrevPage] = useState(null);
  const [totalCount, setTotalCount] = useState(0);
  const [listStatus, setListStatus] = useState('loading');
  const [listError, setListError] = useState(null);

  const [previewCompanyId, setPreviewCompanyId] = useState(null);
  const [previewCompany, setPreviewCompany] = useState(null);
  const [previewStatus, setPreviewStatus] = useState('idle');

  const [selectedCompanyId, setSelectedCompanyId] = useState(null);
  const [companyDetails, setCompanyDetails] = useState(null);
  const [detailStatus, setDetailStatus] = useState('idle');

  const listFetchUrl = pageUrl || buildListUrl({ search: searchQuery, ordering });

  useEffect(() => {
    let cancelled = false;
    setListStatus('loading');
    setListError(null);

    fetch(listFetchUrl, { headers: jsonHeaders })
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
  }, [listFetchUrl]);

  useEffect(() => {
    if (!previewCompanyId) {
      setPreviewCompany(null);
      setPreviewStatus('idle');
      return undefined;
    }

    let cancelled = false;
    setPreviewCompany(null);
    setPreviewStatus('loading');

    fetch(`${API_BASE}/${previewCompanyId}/`, { headers: jsonHeaders })
      .then(async (res) => {
        if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
        return res.json();
      })
      .then((data) => {
        if (cancelled) return;
        setPreviewCompany(data);
        setPreviewStatus('ready');
      })
      .catch((err) => {
        if (cancelled) return;
        console.error('Preview fetch error:', err);
        setPreviewStatus('error');
      });

    return () => { cancelled = true; };
  }, [previewCompanyId]);

  useEffect(() => {
    if (!selectedCompanyId) return undefined;
    let cancelled = false;
    setCompanyDetails(null);
    setDetailStatus('loading');

    fetch(`${API_BASE}/${selectedCompanyId}/`, { headers: jsonHeaders })
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
    setSearchQuery(search);
    setPageUrl(null);
    setPreviewCompanyId(null);
  };

  const handleSort = useCallback((column) => {
    const field = SORT_FIELDS[column];
    setOrdering((prev) => {
      if (prev === `-${field}`) return field;
      return `-${field}`;
    });
    setPageUrl(null);
  }, []);

  const selectCompanyPreview = (id) => {
    setPreviewCompanyId(id);
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

  const clearPreview = () => {
    setPreviewCompanyId(null);
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

  const colSpan = 7;

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

      <div className="nier-dashboard-grid max-w-7xl mx-auto">
        <div className="nier-table-column">
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
                  <SortHeader label="TICKER" column="ticker" ordering={ordering} onSort={handleSort} />
                  <SortHeader label="NAME" column="name" ordering={ordering} onSort={handleSort} />
                  <SortHeader label="SECTOR" column="sector" ordering={ordering} onSort={handleSort} />
                  <SortHeader label="SUBSECTOR" column="subsector" ordering={ordering} onSort={handleSort} />
                  <SortHeader label="CHECKS" column="checks" ordering={ordering} onSort={handleSort} />
                  <SortHeader label=">5 PASS" column="pass5" ordering={ordering} onSort={handleSort} />
                  <SortHeader label="INCOMPLETE" column="incomplete" ordering={ordering} onSort={handleSort} />
                </tr>
              </thead>
              <tbody className="text-xs tracking-wider uppercase">
                {listStatus === 'loading' ? (
                  <tr>
                    <td colSpan={colSpan} className="text-center opacity-50 py-12 tracking-widest">
                      AWAITING_DATABASE_STREAM_INTEGRITY...
                    </td>
                  </tr>
                ) : listStatus === 'error' ? (
                  <tr>
                    <td colSpan={colSpan} className="text-center py-12 tracking-widest text-nier-orange">
                      LINK_FAILURE: {listError || 'UNABLE_TO_REACH_API'}
                      <div className="mt-2 opacity-60 text-[10px] normal-case tracking-normal">
                        Is Django running on http://127.0.0.1:8000 ?
                      </div>
                    </td>
                  </tr>
                ) : companies.length === 0 ? (
                  <tr>
                    <td colSpan={colSpan} className="text-center opacity-50 py-12 tracking-widest">
                      NO_RECORDS_MATCH_QUERY
                    </td>
                  </tr>
                ) : (
                  companies.map((company) => {
                    const qualified = company.passes_screen;
                    const checksLabel =
                      company.check_pass_count != null && company.check_evaluable_total != null
                        ? `${company.check_pass_count}/${company.check_evaluable_total}`
                        : '—';
                    return (
                      <tr
                        key={company.id}
                        onClick={() => selectCompanyPreview(company.id)}
                        onDoubleClick={() => openCompany(company.id)}
                        className={[
                          'transition-colors duration-150 hover:bg-nier-dark/10',
                          previewCompanyId === company.id ? 'bg-nier-dark/15 ring-1 ring-inset ring-nier-dark/30' : '',
                          qualified ? 'nier-row-qualified' : '',
                        ].filter(Boolean).join(' ')}
                      >
                        <td className="font-bold text-nier-orange">
                          {company.ticker || company.symbol}
                        </td>
                        <td>{company.name}</td>
                        <td>{company.sector || '—'}</td>
                        <td>{company.subsector || '—'}</td>
                        <td className="font-mono">{checksLabel}</td>
                        <td>{company.passes_screen ? '✓' : '—'}</td>
                        <td>{company.info_incomplete ? 'YES' : '—'}</td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          <div className="nier-pagination-bar">
            <button
              onClick={() => setPageUrl(prevPage)}
              disabled={!prevPage}
              className="nier-btn"
            >
              &lt; REWIND_PAGE
            </button>
            <div className="grow border-t border-dotted border-nier-gray mx-4 hidden sm:block"></div>
            <button
              onClick={() => setPageUrl(nextPage)}
              disabled={!nextPage}
              className="nier-btn"
            >
              ADVANCE_PAGE &gt;
            </button>
          </div>
        </div>

        <div className="nier-detail-column">
          <RegistryPreview
            company={previewCompany}
            status={previewStatus}
            onOpen={openCompany}
            onClear={clearPreview}
          />
        </div>
      </div>
    </div>
  );
}
