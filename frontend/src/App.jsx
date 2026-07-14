import React, { useState, useEffect, useCallback } from 'react';
import CompanyReport from './components/CompanyReport';
import CompareView from './components/CompareView';
import NierSelect from './components/NierSelect';
import NierShell from './components/NierShell';
import RegistryPreview from './components/RegistryPreview';
import { formatMarketCap, formatPct, formatPrice, marketCapTier } from './lib/metrics';

const API_BASE = 'http://127.0.0.1:8000/api/companies';
const FACETS_URL = 'http://127.0.0.1:8000/api/companies/facets/';
const jsonHeaders = { Accept: 'application/json' };
const MAX_COMPARE = 4;
const CAP_TIERS = ['MICRO', 'SMALL', 'MID', 'LARGE'];

const SORT_FIELDS = {
  ticker: 'ticker',
  name: 'name',
  price: 'last_traded_price',
  mcap: 'market_cap',
  yield: 'div_yield',
  sector: 'sector',
  subsector: 'subsector',
  checks: 'check_pass_count',
  pass5: 'check_pass_count',
  incomplete: 'info_incomplete',
};

const EMPTY_FILTERS = {
  sector: '',
  capTier: '',
  qualified: '', // '' | 'true' | 'false'
  incomplete: '', // '' | 'true' | 'false'
};

function buildListUrl({
  search = '',
  ordering = '-check_pass_count',
  filters = EMPTY_FILTERS,
  pageUrl = null,
} = {}) {
  if (pageUrl) return pageUrl;
  const params = new URLSearchParams();
  if (search.trim()) params.set('search', search.trim());
  if (ordering) params.set('ordering', ordering);
  if (filters.sector) params.set('sector', filters.sector);
  if (filters.capTier) params.set('cap_tier', filters.capTier);
  if (filters.qualified === 'true' || filters.qualified === 'false') {
    params.set('qualified', filters.qualified);
  }
  if (filters.incomplete === 'true' || filters.incomplete === 'false') {
    params.set('incomplete', filters.incomplete);
  }
  const q = params.toString();
  return `${API_BASE}/${q ? `?${q}` : ''}`;
}

function SortHeader({ label, column, ordering, onSort }) {
  const field = SORT_FIELDS[column];
  const isActive = ordering === field || ordering === `-${field}`;
  const desc = ordering === `-${field}`;
  let ariaSort = 'none';
  if (isActive) ariaSort = desc ? 'descending' : 'ascending';
  const sortHint = !isActive
    ? `Sort by ${label}`
    : desc
      ? `${label}, descending. Activate to sort ascending`
      : `${label}, ascending. Activate to sort descending`;
  return (
    <th scope="col" aria-sort={ariaSort}>
      <button
        type="button"
        className="nier-sort-btn"
        onClick={() => onSort(column)}
        aria-label={sortHint}
      >
        {label}
        {isActive && (
          <span className="nier-sort-indicator" aria-hidden="true">
            {desc ? ' ▼' : ' ▲'}
          </span>
        )}
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
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState(EMPTY_FILTERS);
  const [sectors, setSectors] = useState([]);
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

  const [comparePicks, setComparePicks] = useState([]);

  const listFetchUrl = pageUrl || buildListUrl({
    search: searchQuery,
    ordering,
    filters: appliedFilters,
  });

  useEffect(() => {
    let cancelled = false;
    fetch(FACETS_URL, { headers: jsonHeaders })
      .then(async (res) => {
        if (!res.ok) throw new Error(`Facets ${res.status}`);
        return res.json();
      })
      .then((data) => {
        if (cancelled) return;
        setSectors(data.sectors || []);
      })
      .catch((err) => {
        console.error('Facets fetch error:', err);
      });
    return () => { cancelled = true; };
  }, []);

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
    setAppliedFilters(filters);
    setPageUrl(null);
    setPreviewCompanyId(null);
  };

  const handleFilterChange = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  const applyFilters = () => {
    setSearchQuery(search);
    setAppliedFilters(filters);
    setPageUrl(null);
    setPreviewCompanyId(null);
  };

  const clearFilters = () => {
    setFilters(EMPTY_FILTERS);
    setAppliedFilters(EMPTY_FILTERS);
    setSearch('');
    setSearchQuery('');
    setPageUrl(null);
    setPreviewCompanyId(null);
  };

  const filtersActive = Object.values(appliedFilters).some(Boolean) || Boolean(searchQuery);

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

  const toggleComparePick = useCallback((company) => {
    setComparePicks((prev) => {
      const exists = prev.some((p) => p.id === company.id);
      if (exists) return prev.filter((p) => p.id !== company.id);
      if (prev.length >= MAX_COMPARE) return prev;
      return [
        ...prev,
        {
          id: company.id,
          ticker: company.ticker || company.symbol,
          name: company.name,
        },
      ];
    });
  }, []);

  const clearComparePicks = () => setComparePicks([]);

  const removeComparePick = (id) => {
    setComparePicks((prev) => prev.filter((p) => p.id !== id));
  };

  useEffect(() => {
    if (view === 'compare' && comparePicks.length < 2) {
      setView('dashboard');
    }
  }, [view, comparePicks.length]);

  const openCompare = () => {
    if (comparePicks.length < 2) return;
    setView('compare');
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
      <NierShell landing className="animate-fade-in">
        <div className="nier-landing-meta">
          <div>[ GLORY_TO_MANKIND ]</div>
          <div>SYS_STATUS: READY</div>
        </div>

        <div className="nier-landing-main">
          <div className="nier-rail w-full animate-wipe-in">
            <p className="text-[10px] uppercase tracking-[0.2em] opacity-60 mb-4 font-normal">
              PROTOTYPE_V.2.0.6
            </p>
            <h1
              className="nier-title nier-landing-brand nier-title-ghost"
              data-text="PSE_ANALYSIS"
            >
              PSE_ANALYSIS
              <span className="nier-landing-sub">DATA_REGISTRY</span>
            </h1>
            <p className="nier-landing-copy">
              Automated monitoring client for tracking stock indexes, financial statements,
              and systemic multi-sector business evaluation records.
            </p>
            <div className="nier-landing-cta">
              <button type="button" className="nier-btn" onClick={() => setView('dashboard')}>
                Initialize Dashboard Sequence
              </button>
            </div>
          </div>
        </div>
      </NierShell>
    );
  }

  if (view === 'report') {
    if (detailStatus === 'loading' || detailStatus === 'idle') {
      return (
        <NierShell>
          <div className="report-page report-loading">
            LOADING_FUNDAMENTAL_RECORD...
          </div>
        </NierShell>
      );
    }
    if (detailStatus === 'error' || !companyDetails) {
      return (
        <NierShell>
          <div className="report-page report-loading">
            <p>RECORD_RETRIEVAL_FAILURE</p>
            <button type="button" className="nier-btn mt-4" onClick={backToDirectory}>
              &lt; REGISTRY
            </button>
          </div>
        </NierShell>
      );
    }
    return (
      <NierShell>
        <CompanyReport company={companyDetails} onBack={backToDirectory} />
      </NierShell>
    );
  }

  if (view === 'compare') {
    return (
      <NierShell>
        <CompareView
          picks={comparePicks}
          onBack={backToDirectory}
          onRemove={removeComparePick}
          onOpen={openCompany}
        />
      </NierShell>
    );
  }

  const colSpan = 11;
  const compareAtCap = comparePicks.length >= MAX_COMPARE;

  return (
    <NierShell className="select-text">
      <header className="nier-dashboard-header">
        <div className="flex items-center gap-3">
          <button type="button" onClick={() => setView('landing')} className="nier-btn px-3 py-1 text-xs">
            &lt; DISCONNECT
          </button>
          <div className="w-2.5 h-2.5 bg-nier-dark hidden lg:block" />
          <h1 className="nier-title text-sm tracking-[0.18em]">CENTRAL_REGISTRY_UNIT</h1>
        </div>
        <div className="text-xs tracking-widest uppercase font-medium text-right opacity-80">
          [ ONLINE_RECORDS: <span className="text-nier-orange">{totalCount}</span> ]
        </div>
      </header>

      <div className="nier-dashboard-grid max-w-[90rem] mx-auto">
        <div className="nier-table-column">
          <form onSubmit={handleSearch} className="nier-search-form" role="search">
            <input
              type="text"
              placeholder="FILTER BY TICKER, SYMBOL OR NAME..."
              aria-label="Filter by ticker, symbol, or name"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="grow nier-input"
            />
            <button type="submit" className="nier-btn">QUERY</button>
          </form>

          <div className="nier-filter-bar" role="group" aria-label="Directory filters">
            <NierSelect
              label="SECTOR"
              value={filters.sector}
              onChange={(v) => handleFilterChange('sector', v)}
              options={[
                { value: '', label: 'All' },
                ...sectors.map((s) => ({ value: s, label: s })),
              ]}
            />
            <NierSelect
              label="CAP TIER"
              value={filters.capTier}
              onChange={(v) => handleFilterChange('capTier', v)}
              options={[
                { value: '', label: 'All' },
                ...CAP_TIERS.map((t) => ({ value: t, label: t })),
              ]}
            />
            <NierSelect
              label="QUALIFIED"
              value={filters.qualified}
              onChange={(v) => handleFilterChange('qualified', v)}
              options={[
                { value: '', label: 'All' },
                { value: 'true', label: 'Yes (>5 pass)' },
                { value: 'false', label: 'No' },
              ]}
            />
            <NierSelect
              label="INCOMPLETE"
              value={filters.incomplete}
              onChange={(v) => handleFilterChange('incomplete', v)}
              options={[
                { value: '', label: 'All' },
                { value: 'true', label: 'Yes' },
                { value: 'false', label: 'No' },
              ]}
            />
            <div className="nier-filter-actions">
              <button type="button" className="nier-btn" onClick={applyFilters}>
                APPLY
              </button>
              <button
                type="button"
                className="nier-btn"
                onClick={clearFilters}
                disabled={!filtersActive
                  && !Object.values(filters).some(Boolean)
                  && !search}
              >
                CLEAR
              </button>
            </div>
          </div>

          {comparePicks.length > 0 && (
            <div
              className="nier-compare-tray"
              role="region"
              aria-label="Compare selection"
            >
              <div className="nier-compare-tray-picks">
                <span className="nier-compare-tray-label">COMPARE</span>
                {comparePicks.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    className="nier-compare-chip"
                    onClick={() => removeComparePick(p.id)}
                    aria-label={`Remove ${p.ticker} from compare`}
                  >
                    {p.ticker} ×
                  </button>
                ))}
                <span className="nier-compare-tray-count" aria-live="polite">
                  {comparePicks.length}/{MAX_COMPARE}
                </span>
              </div>
              <div className="nier-compare-tray-actions">
                <button
                  type="button"
                  className="nier-btn text-xs"
                  disabled={comparePicks.length < 2}
                  onClick={openCompare}
                >
                  OPEN COMPARE
                </button>
                <button type="button" className="nier-btn text-xs" onClick={clearComparePicks}>
                  CLEAR
                </button>
              </div>
            </div>
          )}

          <p className="nier-row-hint" aria-hidden="true">
            Row keys: Enter / Space = preview · O = open report · double-click = open
          </p>

          <div className="nier-table-container">
            <table className="nier-table">
              <caption className="sr-only">
                Company registry. Focus a row, then Enter or Space to preview, O to open the full report.
              </caption>
              <thead>
                <tr>
                  <th className="nier-check-col" scope="col">
                    <span className="sr-only">Add to compare</span>
                    <span aria-hidden="true">⊕</span>
                  </th>
                  <SortHeader label="TICKER" column="ticker" ordering={ordering} onSort={handleSort} />
                  <SortHeader label="NAME" column="name" ordering={ordering} onSort={handleSort} />
                  <SortHeader label="PRICE" column="price" ordering={ordering} onSort={handleSort} />
                  <SortHeader label="MCAP" column="mcap" ordering={ordering} onSort={handleSort} />
                  <SortHeader label="YIELD" column="yield" ordering={ordering} onSort={handleSort} />
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
                    <td colSpan={colSpan} className="text-center opacity-50 py-12 tracking-widest" role="status">
                      AWAITING_DATABASE_STREAM_INTEGRITY...
                    </td>
                  </tr>
                ) : listStatus === 'error' ? (
                  <tr>
                    <td colSpan={colSpan} className="text-center py-12 tracking-widest text-nier-orange" role="alert">
                      LINK_FAILURE: {listError || 'UNABLE_TO_REACH_API'}
                      <div className="mt-2 opacity-60 text-[10px] normal-case tracking-normal">
                        Is Django running on http://127.0.0.1:8000 ?
                      </div>
                    </td>
                  </tr>
                ) : companies.length === 0 ? (
                  <tr>
                    <td colSpan={colSpan} className="text-center opacity-50 py-12 tracking-widest" role="status">
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
                    const tier = company.cap_tier || marketCapTier(company.market_cap);
                    const inCompare = comparePicks.some((p) => p.id === company.id);
                    const checkboxDisabled = !inCompare && compareAtCap;
                    const ticker = company.ticker || company.symbol;
                    const onRowKeyDown = (e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        if (e.ctrlKey || e.metaKey) openCompany(company.id);
                        else selectCompanyPreview(company.id);
                      } else if (e.key === ' ') {
                        e.preventDefault();
                        selectCompanyPreview(company.id);
                      } else if (e.key === 'o' && !e.ctrlKey && !e.metaKey && !e.altKey) {
                        e.preventDefault();
                        openCompany(company.id);
                      }
                    };
                    return (
                      <tr
                        key={company.id}
                        tabIndex={0}
                        aria-keyshortcuts="Enter Space o"
                        onClick={() => selectCompanyPreview(company.id)}
                        onDoubleClick={() => openCompany(company.id)}
                        onKeyDown={onRowKeyDown}
                        className={[
                          'transition-colors duration-150 hover:bg-nier-dark/10',
                          previewCompanyId === company.id ? 'bg-nier-dark/15 ring-1 ring-inset ring-nier-dark/30' : '',
                          qualified ? 'nier-row-qualified' : '',
                          inCompare ? 'nier-row-compare' : '',
                        ].filter(Boolean).join(' ')}
                      >
                        <td
                          className="nier-check-col"
                          onClick={(e) => e.stopPropagation()}
                          onDoubleClick={(e) => e.stopPropagation()}
                          onKeyDown={(e) => e.stopPropagation()}
                        >
                          <label className="nier-compare-check-wrap">
                            <input
                              type="checkbox"
                              className="nier-compare-check"
                              checked={inCompare}
                              disabled={checkboxDisabled}
                              onChange={() => toggleComparePick(company)}
                              aria-label={
                                checkboxDisabled
                                  ? `Compare full (max ${MAX_COMPARE}). Cannot add ${ticker}`
                                  : `Compare ${ticker}`
                              }
                            />
                          </label>
                        </td>
                        <td className="font-bold text-nier-orange">
                          {ticker}
                        </td>
                        <td>{company.name}</td>
                        <td className="font-mono whitespace-nowrap">{formatPrice(company.last_traded_price)}</td>
                        <td className="whitespace-nowrap">
                          <span className="font-mono">{formatMarketCap(company.market_cap)}</span>
                          {tier && (
                            <span className={`nier-cap-tier nier-cap-tier--${tier.toLowerCase()}`}>
                              {tier}
                            </span>
                          )}
                        </td>
                        <td className="font-mono whitespace-nowrap">{formatPct(company.div_yield)}</td>
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

          <nav className="nier-pagination-bar" aria-label="Results pages">
            <button
              type="button"
              onClick={() => setPageUrl(prevPage)}
              disabled={!prevPage}
              className="nier-btn"
              aria-label="Previous page"
            >
              &lt; REWIND_PAGE
            </button>
            <div className="grow border-t border-dotted border-nier-gray mx-4 hidden sm:block" aria-hidden="true"></div>
            <button
              type="button"
              onClick={() => setPageUrl(nextPage)}
              disabled={!nextPage}
              className="nier-btn"
              aria-label="Next page"
            >
              ADVANCE_PAGE &gt;
            </button>
          </nav>
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
    </NierShell>
  );
}
