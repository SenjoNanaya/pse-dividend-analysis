import React, { Suspense, lazy, useState, useEffect, useCallback } from 'react';
import NierSelect from './components/NierSelect';
import NierShell from './components/NierShell';
import RegistryPreview from './components/RegistryPreview';
import TickerNews from './components/TickerNews';

/** Heavy / chart views — kept out of the registry landing bundle. */
const CompanyReport = lazy(() => import('./components/CompanyReport'));
const CompareView = lazy(() => import('./components/CompareView'));
const WatchlistView = lazy(() => import('./components/WatchlistView'));

import {
  formatMarketCap,
  formatPct,
  formatPrice,
  marketCapTier,
  normalizeThresholds,
  registryDataStatus,
} from './lib/metrics';
import {
  WATCHLIST_MAX,
  clearWatchlist,
  isWatched,
  loadWatchlist,
  pruneWatchlistIds,
  removeWatch,
  setWatchlistThresholds,
  toggleWatch,
} from './lib/watchlist';
import {
  COMPANY_CSV_COLUMNS,
  csvDateStamp,
  downloadCsv,
  fetchAllListPages,
  toCsv,
} from './lib/csvExport';
import {
  ONBOARD,
  dismissOnboarding,
  isOnboardingDismissed,
} from './lib/onboarding';
import { API_BASE, FACETS_URL, jsonHeaders } from './lib/api';

function ViewFallback({ label = 'Loading…' }) {
  return (
    <main id="main-content" className="report-page report-loading" role="status" aria-live="polite">
      {label}
    </main>
  );
}

/** User-facing fetch failure — technical detail stays in the console. */
function serviceUnavailableMessage(kind = 'list') {
  if (kind === 'report') return "Couldn't open this company report.";
  if (kind === 'preview') return "Couldn't load this preview.";
  if (kind === 'export') return "Couldn't export the list. Try again.";
  return "Couldn't load the company list. Make sure Edge is running, then try again.";
}
const MAX_COMPARE = 4;
const CAP_TIERS = ['MICRO', 'SMALL', 'MID', 'LARGE'];

const FOCUS_STORAGE_KEY = 'edge-registry-focus';

const SORT_FIELDS = {
  ticker: 'ticker',
  name: 'name',
  price: 'last_traded_price',
  mcap: 'market_cap',
  yield: 'div_yield',
  sector: 'sector',
  subsector: 'subsector',
  pe: 'pe_ratio',
  pb: 'pb_ratio',
  roe: 'roe',
  roic: 'roic',
  de: 'debt_to_equity',
  checks: 'live_check_pass',
  pass5: 'live_check_pass',
  incomplete: 'info_incomplete',
};

function formatRatio(v, digits = 2) {
  const n = Number(v);
  if (v == null || !Number.isFinite(n)) return '—';
  return n.toFixed(digits);
}

function loadFocusMode() {
  try {
    return sessionStorage.getItem(FOCUS_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

const EMPTY_FILTERS = {
  sector: '',
  subsector: '',
  capTier: '',
  qualified: '', // '' | 'true' | 'false'
  incomplete: '', // '' | 'true' | 'false'
  peMax: '', // absolute ratio
  pbMax: '', // absolute ratio
  roeMin: '', // percent in UI (20 = 20%)
  yieldMin: '', // percent in UI (4 = 4%)
  roicMin: '', // percent in UI (8 = 8%); bank capital return uses same field
  deMax: '', // absolute D/E (liabilities ÷ equity)
};

const THRESHOLD_KEYS = ['peMax', 'pbMax', 'roeMin', 'yieldMin', 'roicMin', 'deMax'];

function hasThresholdValues(f) {
  return THRESHOLD_KEYS.some((k) => Boolean(String(f?.[k] ?? '').trim()));
}

function filtersEqual(a, b) {
  return Object.keys(EMPTY_FILTERS).every(
    (k) => String(a?.[k] ?? '') === String(b?.[k] ?? ''),
  );
}

const PE_PB_MAX = 1000;

/** Parse a non-negative finite number; empty string → null. */
function parseNonNeg(raw) {
  const s = String(raw ?? '').trim();
  if (s === '') return { ok: true, value: null };
  const n = Number(s);
  if (!Number.isFinite(n) || n < 0) {
    return { ok: false, value: null };
  }
  return { ok: true, value: n };
}

/**
 * Validate threshold draft fields.
 * Returns { ok, error, peMax, pbMax, roeMinFrac, yieldMinFrac, roicMinFrac, deMax }.
 */
function parseThresholdFilters(filters) {
  const pe = parseNonNeg(filters.peMax);
  const pb = parseNonNeg(filters.pbMax);
  const roePct = parseNonNeg(filters.roeMin);
  const yieldPct = parseNonNeg(filters.yieldMin);
  const roicPct = parseNonNeg(filters.roicMin);
  const de = parseNonNeg(filters.deMax);

  if (!pe.ok) return { ok: false, error: 'P/E max needs a number of 0 or more.' };
  if (!pb.ok) return { ok: false, error: 'P/B max needs a number of 0 or more.' };
  if (!roePct.ok) return { ok: false, error: 'ROE min needs a percent of 0 or more.' };
  if (!yieldPct.ok) return { ok: false, error: 'Yield min needs a percent of 0 or more.' };
  if (!roicPct.ok) return { ok: false, error: 'Return min needs a percent of 0 or more.' };
  if (!de.ok) return { ok: false, error: 'D/E max needs a number of 0 or more.' };

  if (pe.value != null && pe.value > PE_PB_MAX) {
    return { ok: false, error: `P/E max cannot be above ${PE_PB_MAX}.` };
  }
  if (pb.value != null && pb.value > PE_PB_MAX) {
    return { ok: false, error: `P/B max cannot be above ${PE_PB_MAX}.` };
  }
  if (roePct.value != null && roePct.value > 1000) {
    return { ok: false, error: 'ROE min looks too high — use 20 for 20%, not 0.20.' };
  }
  if (yieldPct.value != null && yieldPct.value > 1000) {
    return { ok: false, error: 'Yield min looks too high — use 4 for 4%, not 0.04.' };
  }
  if (roicPct.value != null && roicPct.value > 1000) {
    return { ok: false, error: 'Return min looks too high — use 8 for 8%, not 0.08.' };
  }
  if (de.value != null && de.value > PE_PB_MAX) {
    return { ok: false, error: `D/E max cannot be above ${PE_PB_MAX}.` };
  }

  return {
    ok: true,
    error: null,
    peMax: pe.value,
    pbMax: pb.value,
    roeMinFrac: roePct.value != null ? roePct.value / 100 : null,
    yieldMinFrac: yieldPct.value != null ? yieldPct.value / 100 : null,
    roicMinFrac: roicPct.value != null ? roicPct.value / 100 : null,
    deMax: de.value,
  };
}

/** Thresholds for checklist / report (defaults when field is empty). */
function screeningThresholds(filters) {
  const parsed = parseThresholdFilters(filters);
  if (!parsed.ok) {
    return normalizeThresholds({});
  }
  return normalizeThresholds({
    peMax: parsed.peMax ?? undefined,
    pbMax: parsed.pbMax ?? undefined,
    roeMin: parsed.roeMinFrac ?? undefined,
    deMax: parsed.deMax ?? undefined,
  });
}

function buildListUrl({
  search = '',
  ordering = '-live_check_pass',
  filters = EMPTY_FILTERS,
  pageUrl = null,
} = {}) {
  if (pageUrl) return pageUrl;
  const params = new URLSearchParams();
  if (search.trim()) params.set('search', search.trim());
  if (ordering) params.set('ordering', ordering);
  if (filters.sector) params.set('sector', filters.sector);
  if (filters.subsector) params.set('subsector', filters.subsector);
  if (filters.capTier) params.set('cap_tier', filters.capTier);
  if (filters.qualified === 'true' || filters.qualified === 'false') {
    params.set('qualified', filters.qualified);
  }
  if (filters.incomplete === 'true' || filters.incomplete === 'false') {
    params.set('incomplete', filters.incomplete);
  }
  const parsed = parseThresholdFilters(filters);
  if (parsed.ok) {
    if (parsed.peMax != null) params.set('pe_max', String(parsed.peMax));
    if (parsed.pbMax != null) params.set('pb_max', String(parsed.pbMax));
    if (parsed.roeMinFrac != null) params.set('roe_min', String(parsed.roeMinFrac));
    if (parsed.yieldMinFrac != null) params.set('yield_min', String(parsed.yieldMinFrac));
    if (parsed.roicMinFrac != null) params.set('roic_min', String(parsed.roicMinFrac));
    if (parsed.deMax != null) params.set('de_max', String(parsed.deMax));
  }
  const q = params.toString();
  return `${API_BASE}/${q ? `?${q}` : ''}`;
}

function ThresholdInput({ label, hint, value, onChange, ariaLabel }) {
  return (
    <label className="nier-filter-field nier-threshold-field">
      <span>{label}</span>
      <input
        type="number"
        inputMode="decimal"
        step="any"
        min="0"
        placeholder={hint}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="nier-input nier-threshold-input"
        aria-label={ariaLabel || label}
      />
    </label>
  );
}

function SortHeader({ label, column, ordering, onSort, className = '' }) {
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
    <th scope="col" aria-sort={ariaSort} className={className || undefined}>
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
  const [view, setView] = useState(() =>
    (isOnboardingDismissed(ONBOARD.skipLanding) ? 'dashboard' : 'landing'),
  );

  const [companies, setCompanies] = useState([]);
  const [search, setSearch] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [ordering, setOrdering] = useState('-live_check_pass');
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState(EMPTY_FILTERS);
  const [filterError, setFilterError] = useState(null);
  const appliedThresholds = screeningThresholds(appliedFilters);
  const [sectors, setSectors] = useState([]);
  const [subsectors, setSubsectors] = useState([]);
  const [sectorSubsectors, setSectorSubsectors] = useState({});
  const [pageUrl, setPageUrl] = useState(null);
  const [nextPage, setNextPage] = useState(null);
  const [prevPage, setPrevPage] = useState(null);
  const [totalCount, setTotalCount] = useState(0);
  const [listStatus, setListStatus] = useState('loading');
  const [listError, setListError] = useState(null);
  const [listRetry, setListRetry] = useState(0);

  const [previewCompanyId, setPreviewCompanyId] = useState(null);
  const [previewCompany, setPreviewCompany] = useState(null);
  const [previewStatus, setPreviewStatus] = useState('idle');

  const [selectedCompanyId, setSelectedCompanyId] = useState(null);
  const [companyDetails, setCompanyDetails] = useState(null);
  const [detailStatus, setDetailStatus] = useState('idle');
  const [detailRetry, setDetailRetry] = useState(0);
  const [detailError, setDetailError] = useState(null);

  const [comparePicks, setComparePicks] = useState([]);
  const [watchlist, setWatchlist] = useState(() => loadWatchlist());
  const [returnView, setReturnView] = useState('dashboard');
  const [focusMode, setFocusMode] = useState(() => loadFocusMode());
  const [thresholdsOpen, setThresholdsOpen] = useState(() => hasThresholdValues(EMPTY_FILTERS));
  const [compareMode, setCompareMode] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [showRegistryTip, setShowRegistryTip] = useState(
    () => !isOnboardingDismissed(ONBOARD.tipRegistry),
  );
  const [showWatchTip, setShowWatchTip] = useState(false);

  const toggleFocusMode = () => {
    setFocusMode((prev) => {
      const next = !prev;
      try {
        sessionStorage.setItem(FOCUS_STORAGE_KEY, next ? '1' : '0');
      } catch {
        /* ignore quota / private mode */
      }
      return next;
    });
  };

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
        setSubsectors(data.subsectors || []);
        setSectorSubsectors(data.sector_subsectors || {});
      })
      .catch((err) => {
        console.error('Facets fetch error:', err);
      });
    return () => { cancelled = true; };
  }, []);

  // Subsectors for the selected sector only (avoids Financials + Casinos, etc.).
  const subsectorOptions = (() => {
    const sector = filters.sector || '';
    const scoped = sector && sectorSubsectors[sector]
      ? sectorSubsectors[sector]
      : subsectors;
    const options = scoped.map((s) => ({ value: s, label: s }));
    if (sector.toLowerCase() !== 'financials') {
      return options;
    }
    const prefer = ['Banks', 'Insurance', 'Other Financial Institutions'];
    const rank = (label) => {
      const i = prefer.findIndex((p) => p.toLowerCase() === label.toLowerCase());
      return i === -1 ? prefer.length : i;
    };
    return [...options].sort(
      (a, b) => rank(a.label) - rank(b.label) || a.label.localeCompare(b.label),
    );
  })();

  useEffect(() => {
    const ac = new AbortController();
    setListStatus('loading');
    setListError(null);

    fetch(listFetchUrl, { headers: jsonHeaders, signal: ac.signal })
      .then(async (res) => {
        if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
        return res.json();
      })
      .then((data) => {
        setCompanies(data.results || []);
        setNextPage(data.next);
        setPrevPage(data.previous);
        setTotalCount(data.count || 0);
        setListStatus('ready');
      })
      .catch((err) => {
        if (err.name === 'AbortError') return;
        console.error('Fetch error:', err);
        setCompanies([]);
        setListError(serviceUnavailableMessage('list'));
        setListStatus('error');
      });

    return () => ac.abort();
  }, [listFetchUrl, listRetry]);

  useEffect(() => {
    if (!previewCompanyId) {
      setPreviewCompany(null);
      setPreviewStatus('idle');
      return undefined;
    }

    const ac = new AbortController();
    setPreviewCompany(null);
    setPreviewStatus('loading');

    fetch(`${API_BASE}/${previewCompanyId}/`, { headers: jsonHeaders, signal: ac.signal })
      .then(async (res) => {
        if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
        return res.json();
      })
      .then((data) => {
        setPreviewCompany(data);
        setPreviewStatus('ready');
      })
      .catch((err) => {
        if (err.name === 'AbortError') return;
        console.error('Preview fetch error:', err);
        setPreviewStatus('error');
      });

    return () => ac.abort();
  }, [previewCompanyId]);

  useEffect(() => {
    if (!selectedCompanyId) return undefined;
    const ac = new AbortController();
    setCompanyDetails(null);
    setDetailError(null);
    setDetailStatus('loading');

    fetch(`${API_BASE}/${selectedCompanyId}/`, { headers: jsonHeaders, signal: ac.signal })
      .then(async (res) => {
        if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
        return res.json();
      })
      .then((data) => {
        setCompanyDetails(data);
        setDetailStatus('ready');
      })
      .catch((err) => {
        if (err.name === 'AbortError') return;
        console.error('Network error fetching detail record:', err);
        setDetailError(serviceUnavailableMessage('report'));
        setDetailStatus('error');
      });

    return () => ac.abort();
  }, [selectedCompanyId, detailRetry]);

  const commitFilters = (nextFilters) => {
    const parsed = parseThresholdFilters(nextFilters);
    if (!parsed.ok) {
      setFilterError(parsed.error);
      return false;
    }
    setFilterError(null);
    setSearchQuery(search);
    setAppliedFilters(nextFilters);
    if (hasThresholdValues(nextFilters)) setThresholdsOpen(true);
    setPageUrl(null);
    setPreviewCompanyId(null);
    return true;
  };

  const handleSearch = (e) => {
    e.preventDefault();
    commitFilters(filters);
  };

  const handleFilterChange = (key, value) => {
    setFilterError(null);
    setFilters((prev) => {
      if (key !== 'sector') {
        return { ...prev, [key]: value };
      }
      // Drop a subsector that does not belong to the newly selected sector.
      const allowed = value && sectorSubsectors[value]
        ? sectorSubsectors[value]
        : null;
      const subOk =
        !prev.subsector
        || !allowed
        || allowed.some((s) => s === prev.subsector);
      return {
        ...prev,
        sector: value,
        subsector: subOk ? prev.subsector : '',
      };
    });
  };

  const applyFilters = () => {
    commitFilters(filters);
  };

  const clearFilters = () => {
    setFilters(EMPTY_FILTERS);
    setAppliedFilters(EMPTY_FILTERS);
    setFilterError(null);
    setSearch('');
    setSearchQuery('');
    setPageUrl(null);
    setPreviewCompanyId(null);
  };

  const filtersActive = Object.values(appliedFilters).some(Boolean) || Boolean(searchQuery);
  const filtersPending =
    !filtersEqual(filters, appliedFilters) || search !== searchQuery;

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
      setView(returnView === 'watchlist' ? 'watchlist' : 'dashboard');
    }
  }, [view, comparePicks.length, returnView]);

  const openCompare = () => {
    if (comparePicks.length < 2) return;
    setReturnView(view === 'watchlist' ? 'watchlist' : 'dashboard');
    setView('compare');
  };

  const openCompany = (id, fromView) => {
    setSelectedCompanyId(id);
    setReturnView(fromView || (view === 'watchlist' ? 'watchlist' : 'dashboard'));
    setView('report');
  };

  const backToDirectory = () => {
    setView(returnView === 'watchlist' ? 'watchlist' : 'dashboard');
    setSelectedCompanyId(null);
    setCompanyDetails(null);
    setDetailStatus('idle');
  };

  const backFromWatchlist = () => {
    setReturnView('dashboard');
    setView('dashboard');
  };

  const clearPreview = () => {
    setPreviewCompanyId(null);
  };

  const toggleWatchlistPick = useCallback((company) => {
    setWatchlist((prev) => {
      const wasWatched = isWatched(prev, company.id);
      const next = toggleWatch(prev, company);
      if (
        !wasWatched
        && isWatched(next, company.id)
        && !isOnboardingDismissed(ONBOARD.tipWatch)
      ) {
        setShowWatchTip(true);
      }
      return next;
    });
  }, []);

  const openCompanyList = (skipLanding = false) => {
    if (skipLanding) dismissOnboarding(ONBOARD.skipLanding);
    setView('dashboard');
  };

  const goHome = () => {
    // After “skip this screen next time”, Home returns to the list — not the landing.
    if (isOnboardingDismissed(ONBOARD.skipLanding)) setView('dashboard');
    else setView('landing');
  };

  const dismissRegistryTip = () => {
    dismissOnboarding(ONBOARD.tipRegistry);
    setShowRegistryTip(false);
  };

  const dismissWatchTip = () => {
    dismissOnboarding(ONBOARD.tipWatch);
    setShowWatchTip(false);
  };

  const showPassedOnly = () => {
    const next = { ...filters, qualified: 'true' };
    setFilters(next);
    commitFilters(next);
    dismissRegistryTip();
  };

  const previewFirstCompany = () => {
    const first = companies[0];
    if (first) selectCompanyPreview(first.id);
  };

  const removeWatchlistPick = useCallback((id) => {
    setWatchlist((prev) => removeWatch(prev, id));
  }, []);

  const clearWatchlistAll = useCallback(() => {
    setWatchlist(clearWatchlist());
  }, []);

  const updateWatchlist = useCallback((patch) => {
    setWatchlist((prev) => {
      if (patch?.pruneIds) {
        return pruneWatchlistIds(prev, patch.pruneIds);
      }
      if (patch?.thresholds) {
        return setWatchlistThresholds(prev, patch.thresholds);
      }
      return prev;
    });
  }, []);

  const [csvStatus, setCsvStatus] = useState(null);

  const exportRegistryCsv = useCallback(async () => {
    setCsvStatus('loading');
    try {
      // Always start from page 1 of the applied query (ignore pagination cursor).
      const startUrl = buildListUrl({
        search: searchQuery,
        ordering,
        filters: appliedFilters,
      });
      const { rows, count } = await fetchAllListPages(startUrl, {
        headers: jsonHeaders,
      });
      downloadCsv(
        `pse-registry-${csvDateStamp()}.csv`,
        toCsv(rows, COMPANY_CSV_COLUMNS),
      );
      setCsvStatus(
        count != null
          ? `Exported ${rows.length} of ${count} companies`
          : `Exported ${rows.length} companies`,
      );
    } catch (err) {
      console.error('Registry CSV export failed:', err);
      setCsvStatus(serviceUnavailableMessage('export'));
    }
  }, [searchQuery, ordering, appliedFilters]);

  if (view === 'landing') {
    return (
      <NierShell landing className="animate-fade-in">
        <main id="main-content" className="nier-landing-main">
          <div className="nier-rail w-full nier-landing-panel">
            <div className="nier-landing-brand-wrap">
              <h1
                className="nier-title nier-landing-brand nier-title-ghost"
                data-text="PSE_ANALYSIS"
              >
                PSE_ANALYSIS
                <span className="nier-landing-sub">DATA_REGISTRY</span>
              </h1>
            </div>
            <p className="nier-landing-copy">
              Screen PSE companies from filing-backed numbers. Build a shortlist, keep a
              watchlist, and notice when signals change.
            </p>
            <p className="nier-landing-steps nier-msg-plain">
              Start with the company list: click a row to see why it passed, then star names
              you want to watch.
            </p>
            <div className="nier-landing-cta">
              <button type="button" className="nier-btn" onClick={() => openCompanyList(false)}>
                Open company list
              </button>
              <button type="button" className="nier-btn" onClick={() => setView('watchlist')}>
                Open watchlist
              </button>
            </div>
            <button
              type="button"
              className="nier-landing-skip"
              onClick={() => openCompanyList(true)}
            >
              Open list and skip this screen next time
            </button>
          </div>
        </main>
      </NierShell>
    );
  }

  if (view === 'report') {
    if (detailStatus === 'loading' || detailStatus === 'idle') {
      return (
        <NierShell>
          <main id="main-content" className="report-page report-loading" role="status" aria-live="polite">
            Loading company report…
          </main>
        </NierShell>
      );
    }
    if (detailStatus === 'error' || !companyDetails) {
      return (
        <NierShell>
          <main id="main-content" className="report-page report-loading" role="alert">
            <p className="nier-msg-plain">
              {detailError || serviceUnavailableMessage('report')}
            </p>
            <p className="nier-ink-muted text-xs normal-case tracking-normal mt-2 max-w-md text-center">
              Make sure Edge is running, then try again.
            </p>
            <div className="flex flex-wrap gap-2 mt-4 justify-center">
              <button
                type="button"
                className="nier-btn"
                onClick={() => setDetailRetry((n) => n + 1)}
              >
                Try again
              </button>
              <button type="button" className="nier-btn" onClick={backToDirectory}>
                Back to list
              </button>
            </div>
          </main>
        </NierShell>
      );
    }
    return (
      <NierShell>
        <Suspense fallback={<ViewFallback label="Loading company report…" />}>
          <CompanyReport
            company={companyDetails}
            onBack={backToDirectory}
            thresholds={appliedThresholds}
          />
        </Suspense>
      </NierShell>
    );
  }

  if (view === 'compare') {
    return (
      <NierShell>
        <Suspense fallback={<ViewFallback label="Loading comparison…" />}>
          <CompareView
            picks={comparePicks}
            onBack={backToDirectory}
            onRemove={removeComparePick}
            onOpen={openCompany}
            thresholds={appliedThresholds}
          />
        </Suspense>
      </NierShell>
    );
  }

  if (view === 'watchlist') {
    return (
      <NierShell className="select-text">
        <Suspense fallback={<ViewFallback label="Loading watchlist…" />}>
          <WatchlistView
            watchlist={watchlist}
            onBack={backFromWatchlist}
            onOpen={openCompany}
            onRemove={removeWatchlistPick}
            onClearAll={clearWatchlistAll}
            onUpdateWatchlist={updateWatchlist}
            onToggleCompare={toggleComparePick}
            onOpenCompare={openCompare}
            onClearCompare={clearComparePicks}
            onRemoveCompare={removeComparePick}
            comparePicks={comparePicks}
            maxCompare={MAX_COMPARE}
          />
        </Suspense>
      </NierShell>
    );
  }

  const showCompareCol = compareMode || comparePicks.length > 0;
  // ⊕? ★ ticker name price mcap yield checks data sector [+5 focus]
  const colSpan = (showCompareCol ? 1 : 0) + (focusMode ? 14 : 9);
  const compareAtCap = comparePicks.length >= MAX_COMPARE;
  const watchAtCap = watchlist.ids.length >= WATCHLIST_MAX;

  return (
    <NierShell className="select-text">
      <header className="nier-dashboard-header">
        <div className="flex items-center gap-3 flex-wrap">
          <button type="button" onClick={goHome} className="nier-btn nier-btn--compact">
            Home
          </button>
          <button type="button" onClick={() => setView('watchlist')} className="nier-btn nier-btn--compact">
            WATCHLIST ({watchlist.ids.length})
          </button>
          <h1 className="nier-title text-sm tracking-[0.18em]">CENTRAL_REGISTRY_UNIT</h1>
        </div>
        <div className="text-xs tracking-widest uppercase font-medium text-right nier-ink-muted">
          [ ONLINE_RECORDS: <span className="text-nier-orange">{totalCount}</span> ]
        </div>
      </header>

      <main
        id="main-content"
        className={`nier-dashboard-stack mx-auto${
          focusMode ? ' nier-dashboard-stack--focus' : ' max-w-[90rem]'
        }`}
      >
        <div className="nier-controls">
          <form onSubmit={handleSearch} className="nier-search-form" role="search">
            <input
              type="text"
              placeholder="Search by ticker, symbol, or name…"
              aria-label="Search by ticker, symbol, or name"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="grow nier-input"
            />
            <button type="submit" className="nier-btn">Search</button>
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
              label="SUBSECTOR"
              value={filters.subsector}
              onChange={(v) => handleFilterChange('subsector', v)}
              options={[
                { value: '', label: 'All' },
                ...subsectorOptions,
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
              label="PASSED SCREEN"
              value={filters.qualified}
              onChange={(v) => handleFilterChange('qualified', v)}
              options={[
                { value: '', label: 'All' },
                { value: 'true', label: 'Yes (more than 5 checks)' },
                { value: 'false', label: 'No' },
              ]}
            />
            <NierSelect
              label="MISSING DATA"
              value={filters.incomplete}
              onChange={(v) => handleFilterChange('incomplete', v)}
              options={[
                { value: '', label: 'All' },
                { value: 'true', label: 'Yes' },
                { value: 'false', label: 'No' },
              ]}
            />
            <div className="nier-filter-actions">
              <button
                type="button"
                className={`nier-btn${thresholdsOpen ? ' nier-btn--pressed' : ''}`}
                onClick={() => setThresholdsOpen((o) => !o)}
                aria-expanded={thresholdsOpen}
                aria-controls="registry-thresholds"
              >
                Limits{hasThresholdValues(appliedFilters) ? ' · on' : ''}
              </button>
              <button
                type="button"
                className={`nier-btn${filtersPending ? ' nier-btn--pressed' : ''}`}
                onClick={applyFilters}
                aria-describedby={filtersPending ? 'registry-filters-pending' : undefined}
              >
                {filtersPending ? 'Apply filters · pending' : 'Apply filters'}
              </button>
              <button
                type="button"
                className="nier-btn"
                onClick={clearFilters}
                disabled={!filtersActive
                  && !Object.values(filters).some(Boolean)
                  && !search}
              >
                Clear filters
              </button>
              <button
                type="button"
                className={`nier-btn${focusMode ? ' nier-btn--pressed' : ''}`}
                onClick={toggleFocusMode}
                aria-pressed={focusMode}
                title="Hide preview and show ratio columns in the table"
              >
                Show ratios
              </button>
              <button
                type="button"
                className={`nier-btn${showCompareCol ? ' nier-btn--pressed' : ''}`}
                onClick={() => setCompareMode((o) => !o)}
                aria-pressed={showCompareCol}
                title="Show checkboxes to pick companies for comparison"
              >
                Pick to compare
              </button>
              <button
                type="button"
                className={`nier-btn${moreOpen ? ' nier-btn--pressed' : ''}`}
                onClick={() => setMoreOpen((o) => !o)}
                aria-expanded={moreOpen}
                aria-controls="registry-more-actions"
              >
                More
              </button>
              {moreOpen && (
                <button
                  type="button"
                  id="registry-more-actions"
                  className="nier-btn"
                  onClick={exportRegistryCsv}
                  disabled={listStatus === 'loading' || csvStatus === 'loading'}
                >
                  {csvStatus === 'loading' ? 'Exporting…' : 'Export CSV'}
                </button>
              )}
            </div>
            {filtersPending && !filterError && (
              <p
                id="registry-filters-pending"
                className="nier-filter-status nier-ink-muted nier-msg-plain"
                role="status"
              >
                Changes are not applied yet. Press Apply filters or Search.
              </p>
            )}
            {filterError && (
              <p className="nier-filter-error nier-msg-plain" role="alert">
                {filterError}
              </p>
            )}
            {csvStatus && csvStatus !== 'loading' && (
              <p className="nier-filter-status nier-ink-muted nier-msg-plain" role="status">
                {csvStatus}
              </p>
            )}
          </div>

          {thresholdsOpen && (
            <div
              id="registry-thresholds"
              className="nier-filter-bar nier-filter-bar--thresholds"
              role="group"
              aria-label="Screening thresholds"
            >
              <ThresholdInput
                label="P/E MAX"
                hint="e.g. 10 — blank = default 22"
                value={filters.peMax}
                onChange={(v) => handleFilterChange('peMax', v)}
                ariaLabel="P/E maximum"
              />
              <ThresholdInput
                label="P/B MAX"
                hint="e.g. 0.5 — blank = default 1"
                value={filters.pbMax}
                onChange={(v) => handleFilterChange('pbMax', v)}
                ariaLabel="P/B maximum"
              />
              <ThresholdInput
                label="ROE MIN %"
                hint="e.g. 20 — blank = default 10%"
                value={filters.roeMin}
                onChange={(v) => handleFilterChange('roeMin', v)}
                ariaLabel="ROE minimum percent"
              />
              <ThresholdInput
                label="YIELD MIN %"
                hint="e.g. 4 — blank = any"
                value={filters.yieldMin}
                onChange={(v) => handleFilterChange('yieldMin', v)}
                ariaLabel="Dividend yield minimum percent"
              />
              <ThresholdInput
                label="RETURN MIN %"
                hint="ROIC or bank capital return; e.g. 8"
                value={filters.roicMin}
                onChange={(v) => handleFilterChange('roicMin', v)}
                ariaLabel="ROIC or capital return minimum percent"
              />
              <ThresholdInput
                label="D/E MAX"
                hint="e.g. 1.5 — blank = default 2"
                value={filters.deMax}
                onChange={(v) => handleFilterChange('deMax', v)}
                ariaLabel="Debt to equity maximum"
              />
            </div>
          )}

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
                  className="nier-btn nier-btn--compact"
                  disabled={comparePicks.length < 2}
                  onClick={openCompare}
                >
                  Compare selected
                </button>
                <button type="button" className="nier-btn nier-btn--compact" onClick={clearComparePicks}>
                  Clear selection
                </button>
              </div>
            </div>
          )}
        </div>

        {(showRegistryTip || showWatchTip) && (
          <div className="nier-coach-stack">
            {showRegistryTip && (
              <div className="nier-coach-strip" role="region" aria-label="Getting started">
                <p className="nier-coach-copy nier-msg-plain">
                  Click a row to see why it passed. Star names you want alerts on.
                </p>
                <div className="nier-coach-actions">
                  <button type="button" className="nier-btn nier-btn--compact" onClick={showPassedOnly}>
                    Show passed only
                  </button>
                  <button type="button" className="nier-btn nier-btn--compact" onClick={dismissRegistryTip}>
                    Got it
                  </button>
                </div>
              </div>
            )}
            {showWatchTip && (
              <div
                className="nier-coach-strip nier-coach-strip--watch"
                role="region"
                aria-label="Watchlist tip"
              >
                <p className="nier-coach-copy nier-msg-plain">
                  Saved. Open Watchlist next time to see if checks or ratios flip.
                </p>
                <div className="nier-coach-actions">
                  <button
                    type="button"
                    className="nier-btn nier-btn--compact"
                    onClick={() => {
                      dismissWatchTip();
                      setView('watchlist');
                    }}
                  >
                    Open watchlist
                  </button>
                  <button type="button" className="nier-btn nier-btn--compact" onClick={dismissWatchTip}>
                    Got it
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        <div className={`nier-dashboard-grid${focusMode ? ' nier-dashboard-grid--focus' : ''}`}>
          <div className="nier-table-column">
          {focusMode && (
            <RegistryPreview
              variant="bar"
              company={previewCompany}
              status={previewStatus}
              onOpen={openCompany}
              onClear={clearPreview}
              thresholds={appliedThresholds}
              watched={previewCompany ? isWatched(watchlist, previewCompany.id) : false}
              watchDisabled={
                previewCompany
                  ? !isWatched(watchlist, previewCompany.id) && watchAtCap
                  : false
              }
              onToggleWatch={toggleWatchlistPick}
              onPreviewFirst={
                listStatus === 'ready' && companies.length > 0 ? previewFirstCompany : undefined
              }
            />
          )}

          <div className="nier-table-container">
            <table className="nier-table">
              <caption className="sr-only">
                Company registry. Focus a row, then Enter or Space to preview, O to open the full report.
              </caption>
              <thead>
                <tr>
                  {showCompareCol && (
                    <th className="nier-check-col" scope="col">
                      <span className="sr-only">Add to compare</span>
                      <span aria-hidden="true">⊕</span>
                    </th>
                  )}
                  <th className="nier-check-col" scope="col">
                    <span className="sr-only">Add to watchlist</span>
                    <span aria-hidden="true">★</span>
                  </th>
                  <SortHeader label="TICKER" column="ticker" ordering={ordering} onSort={handleSort} />
                  <SortHeader label="NAME" column="name" ordering={ordering} onSort={handleSort} />
                  <SortHeader label="PRICE" column="price" ordering={ordering} onSort={handleSort} />
                  <SortHeader label="MCAP" column="mcap" ordering={ordering} onSort={handleSort} />
                  <SortHeader label="YIELD" column="yield" ordering={ordering} onSort={handleSort} />
                  <SortHeader
                    label="CHECKS"
                    column="checks"
                    ordering={ordering}
                    onSort={handleSort}
                    className="nier-col-trust"
                  />
                  <SortHeader
                    label="DATA"
                    column="incomplete"
                    ordering={ordering}
                    onSort={handleSort}
                    className="nier-col-trust"
                  />
                  {focusMode && (
                    <>
                      <SortHeader label="P/E" column="pe" ordering={ordering} onSort={handleSort} />
                      <SortHeader label="P/B" column="pb" ordering={ordering} onSort={handleSort} />
                      <SortHeader label="ROE" column="roe" ordering={ordering} onSort={handleSort} />
                      <SortHeader label="ROIC" column="roic" ordering={ordering} onSort={handleSort} />
                      <SortHeader label="D/E" column="de" ordering={ordering} onSort={handleSort} />
                    </>
                  )}
                  <SortHeader
                    label="SECTOR"
                    column="sector"
                    ordering={ordering}
                    onSort={handleSort}
                    className="nier-col-sector"
                  />
                </tr>
              </thead>
              <tbody className="text-xs tracking-wider uppercase">
                {listStatus === 'loading' ? (
                  <tr>
                    <td colSpan={colSpan} className="text-center nier-ink-muted py-12 nier-msg-plain" role="status">
                      Loading companies…
                    </td>
                  </tr>
                ) : listStatus === 'error' ? (
                  <tr>
                    <td colSpan={colSpan} className="text-center py-12 text-nier-orange nier-msg-plain" role="alert">
                      {listError || serviceUnavailableMessage('list')}
                      <div className="mt-2 nier-ink-muted text-xs leading-snug">
                        Start Edge&apos;s data service, then try again.
                      </div>
                      <button
                        type="button"
                        className="nier-btn mt-4 text-xs"
                        onClick={() => setListRetry((n) => n + 1)}
                      >
                        Try again
                      </button>
                    </td>
                  </tr>
                ) : companies.length === 0 ? (
                  <tr>
                    <td colSpan={colSpan} className="text-center nier-ink-muted py-12 nier-msg-plain" role="status">
                      <p className="mb-0">No companies match these filters.</p>
                      <p className="mt-2 mb-0 nier-ink-muted">
                        Clear filters or widen the limits, then search again.
                      </p>
                      <button
                        type="button"
                        className="nier-btn mt-4"
                        onClick={clearFilters}
                        disabled={!filtersActive
                          && !Object.values(filters).some(Boolean)
                          && !search}
                      >
                        Clear filters
                      </button>
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
                    const watched = isWatched(watchlist, company.id);
                    const watchDisabled = !watched && watchAtCap;
                    const ticker = company.ticker || company.symbol;
                    const dq = registryDataStatus(company);
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
                          previewCompanyId === company.id
                            ? 'bg-nier-dark/15 ring-1 ring-inset ring-nier-dark/30'
                            : '',
                          qualified ? 'nier-row-qualified' : '',
                          inCompare ? 'nier-row-compare' : '',
                        ].filter(Boolean).join(' ')}
                      >
                        {showCompareCol && (
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
                        )}
                        <td
                          className="nier-check-col"
                          onClick={(e) => e.stopPropagation()}
                          onDoubleClick={(e) => e.stopPropagation()}
                          onKeyDown={(e) => e.stopPropagation()}
                        >
                          <button
                            type="button"
                            className={`nier-watch-btn${watched ? ' nier-watch-btn--on' : ''}`}
                            disabled={watchDisabled}
                            onClick={() => toggleWatchlistPick(company)}
                            aria-pressed={watched}
                            aria-label={
                              watchDisabled
                                ? `Watchlist full (max ${WATCHLIST_MAX}). Cannot add ${ticker}`
                                : watched
                                  ? `Remove ${ticker} from watchlist`
                                  : `Add ${ticker} to watchlist`
                            }
                            title={watched ? 'On watchlist' : 'Add to watchlist'}
                          >
                            {watched ? '★' : '☆'}
                          </button>
                        </td>
                        <td className="font-bold text-nier-orange">
                          {ticker}
                        </td>
                        <td className="nier-proper-name">{company.name}</td>
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
                        <td
                          className="font-mono nier-col-trust"
                          title={company.passes_screen ? 'Qualified (>5 pass)' : 'Not qualified'}
                        >
                          {checksLabel}
                          {company.passes_screen ? (
                            <span className="nier-checks-qualified" aria-label="Qualified">
                              {' '}✓
                            </span>
                          ) : null}
                        </td>
                        <td className="nier-col-trust">
                          {dq.level === 'ok' ? (
                            <span className="nier-dq-chip nier-dq-chip--ok" title={dq.title}>
                              {dq.label}
                            </span>
                          ) : (
                            <span
                              className={`nier-dq-chip nier-dq-chip--${dq.level}`}
                              title={dq.title}
                              aria-label={`${dq.label}: ${dq.title}`}
                            >
                              {dq.label}
                            </span>
                          )}
                        </td>
                        {focusMode && (
                          <>
                            <td className="font-mono whitespace-nowrap">
                              {formatRatio(company.pe_ratio)}
                            </td>
                            <td className="font-mono whitespace-nowrap">
                              {formatRatio(company.pb_ratio)}
                            </td>
                            <td className="font-mono whitespace-nowrap">
                              {formatPct(company.roe)}
                            </td>
                            <td className="font-mono whitespace-nowrap">
                              {formatPct(company.roic)}
                            </td>
                            <td className="font-mono whitespace-nowrap">
                              {formatRatio(company.debt_to_equity)}
                            </td>
                          </>
                        )}
                        <td className="nier-sentence nier-col-sector">
                          <span>{company.sector || '—'}</span>
                          {company.subsector ? (
                            <span className="nier-subsector-inline nier-ink-muted">
                              {' '}· {company.subsector}
                            </span>
                          ) : null}
                        </td>
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
              Previous
            </button>
            <div className="grow border-t border-dotted border-nier-gray mx-4 hidden sm:block" aria-hidden="true"></div>
            <button
              type="button"
              onClick={() => setPageUrl(nextPage)}
              disabled={!nextPage}
              className="nier-btn"
              aria-label="Next page"
            >
              Next
            </button>
          </nav>
        </div>

          {!focusMode && (
            <aside className="nier-detail-column">
              <RegistryPreview
                company={previewCompany}
                status={previewStatus}
                onOpen={openCompany}
                onClear={clearPreview}
                thresholds={appliedThresholds}
                watched={previewCompany ? isWatched(watchlist, previewCompany.id) : false}
                watchDisabled={
                  previewCompany
                    ? !isWatched(watchlist, previewCompany.id) && watchAtCap
                    : false
                }
                onToggleWatch={toggleWatchlistPick}
                onPreviewFirst={
                  listStatus === 'ready' && companies.length > 0 ? previewFirstCompany : undefined
                }
              />
              <details className="nier-news-drawer">
                <summary className="nier-news-drawer-summary">News</summary>
                <TickerNews
                  companyId={previewCompanyId}
                  ticker={previewCompany?.ticker || previewCompany?.symbol}
                  compact
                />
              </details>
            </aside>
          )}
        </div>
      </main>
    </NierShell>
  );
}
