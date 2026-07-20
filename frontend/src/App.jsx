import React, {
  Suspense,
  lazy,
  useState,
  useEffect,
  useLayoutEffect,
  useCallback,
  useMemo,
  useRef,
} from 'react';
import NierSelect from './components/NierSelect';
import NierShell from './components/NierShell';
import RegistryPreview from './components/RegistryPreview';
import RowKeysLegend from './components/RowKeysLegend';
import TickerPreviewButton from './components/TickerPreviewButton';
import { focusTickerButton } from './lib/tableRowKeys';
import WatchToggle from './components/WatchToggle';
import WatchColumnHeader from './components/WatchColumnHeader';

/** Heavy / chart views — kept out of the registry landing bundle. */
const CompanyReport = lazy(() => import('./components/CompanyReport'));
const CompareView = lazy(() => import('./components/CompareView'));
const WatchlistView = lazy(() => import('./components/WatchlistView'));

import {
  cellSignalClass,
  describeLiveScreeningRules,
  formatMarketCap,
  formatPct,
  formatPrice,
  marketCapTier,
  normalizeThresholds,
  registryCellSignal,
  registryDataStatus,
  formatSectorSubsectorLine,
} from './lib/metrics';
import {
  EMPTY_WATCHLIST_THRESHOLDS,
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
import useMediaQuery from './lib/useMediaQuery';
import useScrollLock from './lib/useScrollLock';
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

const FOCUS_STORAGE_KEY = 'edge-registry-focus-v3';

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

/**
 * Wide table (ratio columns + preview bar) is opt-in.
 * Default is browse-first: side preview rail, identity + trust columns only.
 */
function loadFocusMode() {
  try {
    const v = sessionStorage.getItem(FOCUS_STORAGE_KEY);
    if (v === null) return false;
    return v === '1';
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

function hasFacetFilters(f) {
  return Boolean(f?.sector || f?.subsector || f?.capTier || f?.incomplete);
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

function ThresholdInput({ label, hint, title, value, onChange, ariaLabel }) {
  const tip = title || hint;
  const accessible = ariaLabel || label;
  return (
    <label className="nier-filter-field nier-threshold-field">
      <span>{label}</span>
      <input
        type="number"
        inputMode="decimal"
        step="any"
        min="0"
        placeholder={hint}
        title={tip}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="nier-input nier-threshold-input"
        aria-label={tip ? `${accessible}. ${tip}` : accessible}
      />
    </label>
  );
}

function SortHeader({
  label,
  shortLabel,
  column,
  ordering,
  onSort,
  className = '',
  title,
}) {
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
        aria-label={title ? `${sortHint}. ${title}` : sortHint}
        title={title || label}
      >
        <span className="nier-sort-label">
          <span className="nier-sort-label--full">{label}</span>
          {shortLabel ? (
            <span className="nier-sort-label--short" aria-hidden="true">
              {shortLabel}
            </span>
          ) : null}
        </span>
        {isActive && (
          <span className="nier-sort-indicator" aria-hidden="true">
            {desc ? ' ▼' : ' ▲'}
          </span>
        )}
      </button>
    </th>
  );
}


function shouldSkipLanding() {
  if (isOnboardingDismissed(ONBOARD.skipLanding)) return true;
  try {
    const skip = new URLSearchParams(window.location.search).get('skip');
    if (skip === '1' || skip === 'true') {
      dismissOnboarding(ONBOARD.skipLanding);
      return true;
    }
  } catch {
    /* ignore */
  }
  return false;
}

export default function App() {
  const [view, setView] = useState(() => (shouldSkipLanding() ? 'dashboard' : 'landing'));

  const [companies, setCompanies] = useState([]);
  const [search, setSearch] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [ordering, setOrdering] = useState('-live_check_pass');
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState(EMPTY_FILTERS);
  const [filterError, setFilterError] = useState(null);
  const appliedThresholds = screeningThresholds(appliedFilters);
  const thresholdExtras = useMemo(() => {
    const parsed = parseThresholdFilters(appliedFilters);
    if (!parsed.ok) return { yieldMin: null, roicMin: null };
    return {
      yieldMin: parsed.yieldMinFrac,
      roicMin: parsed.roicMinFrac,
    };
  }, [appliedFilters]);
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
  /** When leaving a sheet into report/compare, force unlock scroll restore to this Y. */
  const scrollLockRestoreYRef = useRef(null);

  const [selectedCompanyId, setSelectedCompanyId] = useState(null);
  const [companyDetails, setCompanyDetails] = useState(null);
  const [detailStatus, setDetailStatus] = useState('idle');
  const [detailRetry, setDetailRetry] = useState(0);
  const [detailError, setDetailError] = useState(null);

  const [comparePicks, setComparePicks] = useState([]);
  const [watchlist, setWatchlist] = useState(() => loadWatchlist());
  const [returnView, setReturnView] = useState('dashboard');
  const [focusMode, setFocusMode] = useState(() => loadFocusMode());
  const [compareMode, setCompareMode] = useState(false);
  /** Exclusive chrome: only one of facets | limits | tools at a time. */
  const [filterPanel, setFilterPanel] = useState(null);
  /** Sector / Limits / Tools live behind Filters until opened */
  const [filtersMenuOpen, setFiltersMenuOpen] = useState(false);
  /** Phone / narrow: sheet preview + shortlist columns (not side rail). */
  const isNarrow = useMediaQuery('(max-width: 767px)');
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

  const commitFilters = (nextFilters, { collapseChrome = true } = {}) => {
    const parsed = parseThresholdFilters(nextFilters);
    if (!parsed.ok) {
      setFilterError(parsed.error);
      return false;
    }
    setFilterError(null);
    setSearchQuery(search);
    setAppliedFilters(nextFilters);
    // Collapse filter chrome after Apply so the shortlist owns the viewport
    // (especially on narrow screens). Passed live-commit keeps chrome open.
    if (collapseChrome) {
      setFilterPanel(null);
      setFiltersMenuOpen(false);
    }
    setPageUrl(null);
    setPreviewCompanyId(null);
    return true;
  };

  const handleSearch = (e) => {
    e.preventDefault();
    // Search also applies any filter drafts — one commit path for Enter.
    commitFilters(filters);
  };

  const handleFilterChange = (key, value) => {
    setFilterError(null);
    setFilters((prev) => {
      let next;
      if (key !== 'sector') {
        next = { ...prev, [key]: value };
      } else {
        // Drop a subsector that does not belong to the newly selected sector.
        const allowed = value && sectorSubsectors[value]
          ? sectorSubsectors[value]
          : null;
        const subOk =
          !prev.subsector
          || !allowed
          || allowed.some((s) => s === prev.subsector);
        next = {
          ...prev,
          sector: value,
          subsector: subOk ? prev.subsector : '',
        };
      }
      // Passed screen is live — only that field commits (Limits drafts stay pending).
      if (key === 'qualified') {
        queueMicrotask(() => {
          setAppliedFilters((applied) => ({ ...applied, qualified: value }));
          setPageUrl(null);
          setPreviewCompanyId(null);
        });
      }
      return next;
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
    // Sheet unlock would otherwise restore list scrollY and clip report Back.
    scrollLockRestoreYRef.current = 0;
    setPreviewCompanyId(null);
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

  useEffect(() => {
    if (!isNarrow || previewCompanyId == null) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') clearPreview();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isNarrow, previewCompanyId]);

  /** Narrow sheet owns the viewport — collapse Filters peers/panels so the list can peek. */
  useEffect(() => {
    if (!isNarrow || previewCompanyId == null) return;
    setFiltersMenuOpen(false);
    setFilterPanel(null);
  }, [isNarrow, previewCompanyId]);

  /** Tools (wide table / export) stays closed when crossing into narrow — reclaim chrome. */
  useEffect(() => {
    if (!isNarrow) return;
    setFilterPanel((cur) => (cur === 'tools' ? null : cur));
  }, [isNarrow]);

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

  // Teach through action: first row preview clears the getting-started line.
  useEffect(() => {
    if (previewCompanyId == null || !showRegistryTip) return;
    dismissOnboarding(ONBOARD.tipRegistry);
    setShowRegistryTip(false);
  }, [previewCompanyId, showRegistryTip]);

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
      if (patch?.thresholds != null || typeof patch?.alertsFollowList === 'boolean') {
        return setWatchlistThresholds(
          prev,
          patch.thresholds != null ? patch.thresholds : null,
          { followList: patch.alertsFollowList },
        );
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

  const liveRules = useMemo(
    () => describeLiveScreeningRules(appliedFilters),
    [appliedFilters],
  );
  const listThresholdUi = useMemo(() => {
    const out = { ...EMPTY_WATCHLIST_THRESHOLDS };
    for (const k of THRESHOLD_KEYS) out[k] = String(appliedFilters[k] ?? '');
    return out;
  }, [appliedFilters]);
  const thresholdDraftPending = THRESHOLD_KEYS.some(
    (k) => String(filters[k] ?? '') !== String(appliedFilters[k] ?? ''),
  );
  const searchDraftPending = search !== searchQuery;
  const otherFiltersDraftPending = ['qualified', 'sector', 'subsector', 'capTier', 'incomplete']
    .some((k) => String(filters[k] ?? '') !== String(appliedFilters[k] ?? ''));
  const pendingShortlistMessage = (() => {
    if (thresholdDraftPending && searchDraftPending) {
      return isNarrow
        ? 'Limits + search draft — Apply.'
        : 'Limits and search not on the shortlist yet — press Apply (Search also applies).';
    }
    if (thresholdDraftPending) {
      return isNarrow
        ? 'Limits draft — Apply.'
        : 'Limits not on the shortlist yet — press Apply.';
    }
    if (searchDraftPending) {
      return isNarrow
        ? 'Search draft — Search or Apply.'
        : 'Search not run — press Search or Apply.';
    }
    if (otherFiltersDraftPending) {
      return isNarrow
        ? 'Filters draft — Apply.'
        : 'Sector filters not on the shortlist yet — press Apply.';
    }
    return isNarrow
      ? 'Draft — Apply.'
      : 'Shortlist not updated yet — press Apply.';
  })();
  const facetsActive = hasFacetFilters(filters) || hasFacetFilters(appliedFilters);
  const limitsActive =
    hasThresholdValues(filters) || hasThresholdValues(appliedFilters);
  const facetsOpen = filterPanel === 'facets';
  const limitsOpen = filterPanel === 'limits';
  const toolsOpen = filterPanel === 'tools';
  const moreFiltersVisible = filtersMenuOpen || filterPanel != null;
  const toggleFilterPanel = (panel) => {
    setFiltersMenuOpen(true);
    setFilterPanel((cur) => (cur === panel ? null : panel));
  };
  const toggleFiltersMenu = () => {
    if (filtersMenuOpen || filterPanel != null) {
      setFiltersMenuOpen(false);
      setFilterPanel(null);
      return;
    }
    setFiltersMenuOpen(true);
  };
  /** Collapse filter disclosure when entering compare pick mode (less chrome noise). */
  const toggleComparePickMode = () => {
    setCompareMode((prev) => {
      const next = !prev;
      if (next) {
        setFiltersMenuOpen(false);
        setFilterPanel(null);
      }
      return next;
    });
  };

  // Must run before view early-returns (Rules of Hooks).
  useScrollLock(view === 'dashboard' && isNarrow && Boolean(previewCompany), {
    restoreYRef: scrollLockRestoreYRef,
  });

  useLayoutEffect(() => {
    if (view !== 'report' && view !== 'compare') return;
    window.scrollTo(0, 0);
  }, [view, selectedCompanyId]);

  if (view === 'landing') {
    return (
      <NierShell landing>
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
              Screen PSE companies from filing-backed numbers. Open the list, click a row to
              see why it passed, then watch names you want alerts on.
            </p>
            <div className="nier-landing-cta">
              <button
                type="button"
                className="nier-btn nier-btn--ink"
                onClick={() => openCompanyList(false)}
              >
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
            watched={isWatched(watchlist, companyDetails.id)}
            watchDisabled={
              !isWatched(watchlist, companyDetails.id)
              && watchlist.ids.length >= WATCHLIST_MAX
            }
            onToggleWatch={toggleWatchlistPick}
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
            listThresholds={listThresholdUi}
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
  /** Wide ratio columns are desktop-only; narrow always uses the shortlist. */
  const wideTable = focusMode && !isNarrow;
  /** Tools · on = layout/export only — Compare lives in primary chrome. */
  const toolsActive = wideTable;
  /** Filters · on = screening only (Sector / Limits), never Tools or Compare. */
  const screeningFiltersOn = facetsActive || limitsActive;
  // ⊕? ★ ticker name price mcap yield checks data sector [+5 wide]
  // Narrow shortlist hides name/price/mcap/sector (+ ratios) via CSS.
  /** Data rows only — status panels stay out of the table (fixed-layout + colspan collapsed thead on SE). */
  const showRegistryTable = listStatus === 'ready' && companies.length > 0;
  const compareAtCap = comparePicks.length >= MAX_COMPARE;
  const watchAtCap = watchlist.ids.length >= WATCHLIST_MAX;
  const previewProps = {
    company: previewCompany,
    status: previewStatus,
    onOpen: openCompany,
    onClear: clearPreview,
    thresholds: appliedThresholds,
    watched: previewCompany ? isWatched(watchlist, previewCompany.id) : false,
    watchDisabled: previewCompany
      ? !isWatched(watchlist, previewCompany.id) && watchAtCap
      : false,
    onToggleWatch: toggleWatchlistPick,
    emptyHint: showRegistryTip
      ? (isNarrow
        ? 'Tap a row for why it passed. ★ saves alerts.'
        : 'Click a row for why it passed. ★ in WATCH saves alerts.')
      : (isNarrow
        ? 'Tap a row for why it passed.'
        : 'Click a row for why it passed.'),
    onDismissEmptyHint: showRegistryTip ? dismissRegistryTip : undefined,
  };
  const showDesktopRail = !wideTable && !isNarrow;
  const showNarrowSheet = isNarrow && Boolean(previewCompany);
  const showNarrowEmptyTip = isNarrow && !previewCompany;

  return (
    <NierShell className={`select-text${showNarrowSheet ? ' nier-shell--sheet-open' : ''}`}>
      <div className="nier-sheet-background" inert={showNarrowSheet || undefined}>
      <header className="nier-dashboard-header">
        <div className="nier-dashboard-header-lead">
          <button type="button" onClick={goHome} className="nier-btn nier-btn--compact">
            Home
          </button>
          <button type="button" onClick={() => setView('watchlist')} className="nier-btn nier-btn--compact">
            {isNarrow ? `Watch (${watchlist.ids.length})` : `Watchlist (${watchlist.ids.length})`}
          </button>
        </div>
        <div className="nier-dashboard-header-title">
          <h1 className="nier-chrome-title">Company list</h1>
          <div className="nier-chrome-meta">
            <span className="nier-chrome-meta-value">{totalCount}</span> companies
          </div>
        </div>
      </header>

      <main
        id="main-content"
        className={`nier-dashboard-stack mx-auto${
          wideTable ? ' nier-dashboard-stack--focus' : ' max-w-[90rem]'
        }`}
      >
        <div className="nier-controls">
          <form onSubmit={handleSearch} className="nier-search-form" role="search">
            <input
              type="text"
              placeholder={isNarrow ? 'Ticker or name' : 'Search by ticker, symbol, or name…'}
              aria-label="Search by ticker, symbol, or name"
              title="Search by ticker, symbol, or name"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="grow nier-input"
              autoComplete="off"
              enterKeyHint="search"
            />
            <button
              type="submit"
              className={`nier-btn${searchDraftPending || filtersPending ? ' nier-btn--pressed' : ''}`}
              title={
                filtersPending && !searchDraftPending
                  ? 'Search and apply pending filters to the shortlist'
                  : 'Search the shortlist'
              }
            >
              Search
            </button>
          </form>

          <div
            className="nier-filter-bar nier-filter-bar--primary"
            role="group"
            aria-label="Screen shortlist"
          >
            <NierSelect
              label={isNarrow ? 'PASSED' : 'PASSED SCREEN'}
              value={filters.qualified}
              onChange={(v) => handleFilterChange('qualified', v)}
              options={[
                { value: '', label: 'All' },
                { value: 'true', label: 'Yes (>5 checks)' },
                { value: 'false', label: 'No' },
              ]}
            />
            <div className="nier-filter-actions nier-filter-actions--primary">
              <button
                type="button"
                className={`nier-btn${filtersPending ? ' nier-btn--pressed' : ''}`}
                onClick={applyFilters}
                aria-describedby={filtersPending ? 'registry-filters-pending' : undefined}
                title={
                  filtersPending
                    ? 'Apply drafts to the shortlist (Passed already applies live)'
                    : 'Shortlist already matches these controls'
                }
              >
                {filtersPending ? 'Apply · pending' : 'Apply'}
              </button>
              <button
                type="button"
                className="nier-btn"
                onClick={clearFilters}
                disabled={!filtersActive
                  && !Object.values(filters).some(Boolean)
                  && !search}
              >
                Clear
              </button>
              <button
                type="button"
                className={`nier-btn${moreFiltersVisible ? ' nier-btn--pressed' : ''}`}
                onClick={toggleFiltersMenu}
                aria-expanded={moreFiltersVisible}
                aria-controls="registry-filter-peers"
                title="Sector and ratio limits (Tools for wide table / export)"
              >
                Filters
                {screeningFiltersOn ? ' · on' : ''}
              </button>
              <button
                type="button"
                className={`nier-btn${showCompareCol ? ' nier-btn--pressed' : ''}`}
                onClick={toggleComparePickMode}
                aria-pressed={showCompareCol}
                title="Show checkboxes to pick companies for comparison"
              >
                {isNarrow ? 'Compare' : 'Pick to compare'}
              </button>
            </div>
            <p
              className="nier-live-rules nier-msg-plain"
              role="status"
              title={
                filtersPending
                  ? `${liveRules.title} Showing the last applied shortlist — drafts need Apply.`
                  : liveRules.title
              }
            >
              <span className="nier-live-rules-line">
                {isNarrow ? liveRules.compactLine : liveRules.line}
              </span>
              {liveRules.usingDefaults ? (
                <span className="nier-live-rules-tag"> defaults</span>
              ) : null}
              {filtersPending ? (
                <span className="nier-live-rules-tag"> last applied</span>
              ) : null}
            </p>
            {filtersPending && !filterError && (
              <p
                id="registry-filters-pending"
                className="nier-filter-status nier-ink-muted nier-msg-plain"
                role="status"
                aria-live="polite"
              >
                {pendingShortlistMessage}
              </p>
            )}
            {filterError && (
              <p className="nier-filter-error nier-msg-plain" role="alert">
                {filterError}
              </p>
            )}
          </div>


          {moreFiltersVisible && (
            <div
              id="registry-filter-peers"
              className="nier-filter-peers"
              role="group"
              aria-label="More filters"
            >
              <button
                type="button"
                className={`nier-btn${facetsOpen ? ' nier-btn--pressed' : ''}`}
                onClick={() => toggleFilterPanel('facets')}
                aria-expanded={facetsOpen}
                aria-controls="registry-more-filters"
              >
                Sector{facetsActive ? ' · on' : ''}
              </button>
              <button
                type="button"
                className={`nier-btn${limitsOpen ? ' nier-btn--pressed' : ''}`}
                onClick={() => toggleFilterPanel('limits')}
                aria-expanded={limitsOpen}
                aria-controls="registry-thresholds"
              >
                Limits{limitsActive ? ' · on' : ''}
              </button>
              <button
                type="button"
                className={`nier-btn${toolsOpen ? ' nier-btn--pressed' : ''}`}
                onClick={() => toggleFilterPanel('tools')}
                aria-expanded={toolsOpen}
                aria-controls="registry-filter-tools"
              >
                Tools{toolsActive ? ' · on' : ''}
              </button>
            </div>
          )}

          {facetsOpen && (
            <div
              id="registry-more-filters"
              className="nier-filter-bar nier-filter-bar--secondary"
              role="group"
              aria-label="Sector and data filters"
            >
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
                label="MISSING DATA"
                value={filters.incomplete}
                onChange={(v) => handleFilterChange('incomplete', v)}
                options={[
                  { value: '', label: 'All' },
                  { value: 'true', label: 'Yes' },
                  { value: 'false', label: 'No' },
                ]}
              />
            </div>
          )}

          {toolsOpen && (
            <div
              id="registry-filter-tools"
              className="nier-filter-tools nier-filter-tools--panel"
              role="group"
              aria-label="Layout and export"
            >
              {!isNarrow && (
                <button
                  type="button"
                  className={`nier-btn nier-btn--compact${focusMode ? ' nier-btn--pressed' : ''}`}
                  onClick={toggleFocusMode}
                  aria-pressed={focusMode}
                  aria-label={
                    focusMode
                      ? 'Wide table on. Switch to side preview: checklist in a panel, hide ratio columns'
                      : 'Switch to wide table: ratio columns with checklist above the table'
                  }
                  title={
                    focusMode
                      ? 'Wide table on — click for side preview (hide P/E–D/E columns)'
                      : 'Wide table — show P/E–D/E columns; checklist above the table'
                  }
                >
                  Wide table
                </button>
              )}
              <button
                type="button"
                className="nier-btn nier-btn--compact"
                onClick={exportRegistryCsv}
                disabled={listStatus === 'loading' || csvStatus === 'loading'}
              >
                {csvStatus === 'loading' ? 'Exporting…' : 'Export CSV'}
              </button>
              {csvStatus && csvStatus !== 'loading' && (
                <p className="nier-filter-status nier-ink-muted nier-msg-plain" role="status">
                  {csvStatus}
                </p>
              )}
              <p className="nier-filter-tools-hint nier-ink-muted nier-msg-plain">
                Compare sits next to Filters — turn it on, pick rows, then Compare selected.
              </p>
            </div>
          )}

          {limitsOpen && (
            <div
              id="registry-thresholds"
              className="nier-filter-bar nier-filter-bar--thresholds"
              role="group"
              aria-label="Screening thresholds"
            >
              <ThresholdInput
                label="P/E MAX"
                hint="Blank = default 22"
                value={filters.peMax}
                onChange={(v) => handleFilterChange('peMax', v)}
                ariaLabel="P/E maximum"
              />
              <ThresholdInput
                label="P/B MAX"
                hint="Blank = default 1"
                value={filters.pbMax}
                onChange={(v) => handleFilterChange('pbMax', v)}
                ariaLabel="P/B maximum"
              />
              <ThresholdInput
                label="ROE MIN %"
                hint="Blank = default 10%"
                value={filters.roeMin}
                onChange={(v) => handleFilterChange('roeMin', v)}
                ariaLabel="ROE minimum percent"
              />
              <ThresholdInput
                label="YIELD MIN %"
                hint="Blank = no floor"
                title="Blank = no dividend yield floor"
                value={filters.yieldMin}
                onChange={(v) => handleFilterChange('yieldMin', v)}
                ariaLabel="Dividend yield minimum percent"
              />
              <ThresholdInput
                label="ROIC MIN %"
                hint="Blank = no floor"
                title="Blank = no ROIC / capital-return floor"
                value={filters.roicMin}
                onChange={(v) => handleFilterChange('roicMin', v)}
                ariaLabel="ROIC or capital return minimum percent"
              />
              <ThresholdInput
                label="D/E MAX"
                hint="Blank = default 2"
                value={filters.deMax}
                onChange={(v) => handleFilterChange('deMax', v)}
                ariaLabel="Debt to equity maximum"
              />
              <p className="nier-threshold-bridge nier-msg-plain">
                Screens the company list only. Watchlist alerts follow these Limits until you
                Detach on the watchlist.
              </p>
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

        {showWatchTip && (
          <div className="nier-coach-stack">
            <div
              className="nier-coach-strip nier-coach-strip--watch nier-coach-strip--inline"
              role="region"
              aria-label="Watchlist tip"
            >
              <p className="nier-coach-copy nier-msg-plain">
                Watching (★). Open Watchlist next time to see if checks or ratios flip.
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
                <button
                  type="button"
                  className="nier-btn nier-btn--compact"
                  onClick={dismissWatchTip}
                >
                  Got it
                </button>
              </div>
            </div>
          </div>
        )}

        <div
          className={`nier-dashboard-grid${wideTable ? ' nier-dashboard-grid--focus' : ''}${
            isNarrow ? ' nier-dashboard-grid--narrow' : ''
          }`}
        >
          <div className="nier-table-column">
          {wideTable && (
            <RegistryPreview variant="bar" {...previewProps} />
          )}
          {showNarrowEmptyTip && (
            <RegistryPreview variant="bar" {...previewProps} />
          )}

          <div className="nier-table-container">
            {!isNarrow && <RowKeysLegend id="registry-row-keys" />}
            {!showRegistryTable ? (
              <div className="nier-table-status">
                {listStatus === 'loading' ? (
                  <p className="nier-table-status-msg nier-ink-muted nier-msg-plain" role="status">
                    Loading companies…
                  </p>
                ) : listStatus === 'error' ? (
                  <div className="nier-table-status-panel" role="alert">
                    <p className="nier-table-status-msg text-nier-orange nier-msg-plain">
                      {listError || serviceUnavailableMessage('list')}
                    </p>
                    <p className="nier-table-status-hint nier-ink-muted nier-msg-plain">
                      Start Edge&apos;s data service, then try again.
                    </p>
                    <button
                      type="button"
                      className="nier-btn"
                      onClick={() => setListRetry((n) => n + 1)}
                    >
                      Try again
                    </button>
                  </div>
                ) : (
                  <div className="nier-table-status-panel" role="status">
                    <p className="nier-empty-title">No companies match these filters.</p>
                    <p className="nier-empty-copy nier-msg-plain">
                      Clear filters or widen the limits, then search again.
                    </p>
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
                  </div>
                )}
              </div>
            ) : (
            <table
              className="nier-table"
              aria-describedby={isNarrow ? undefined : 'registry-row-keys'}
            >
              <caption className="sr-only">Company registry</caption>
              <thead>
                <tr>
                  {showCompareCol && (
                    <th className="nier-check-col" scope="col">
                      <span className="sr-only">Compare</span>
                      <span aria-hidden="true">⊕</span>
                    </th>
                  )}
                  <WatchColumnHeader />
                  <SortHeader
                    label="TICKER"
                    column="ticker"
                    ordering={ordering}
                    onSort={handleSort}
                    className="nier-col-ticker"
                  />
                  <SortHeader
                    label="NAME"
                    column="name"
                    ordering={ordering}
                    onSort={handleSort}
                    className="nier-col-wide"
                  />
                  <SortHeader
                    label="PRICE"
                    column="price"
                    ordering={ordering}
                    onSort={handleSort}
                    className="nier-col-wide"
                  />
                  <SortHeader
                    label="MCAP"
                    column="mcap"
                    ordering={ordering}
                    onSort={handleSort}
                    className="nier-col-wide"
                  />
                  <SortHeader
                    label="YIELD"
                    shortLabel="YLD"
                    column="yield"
                    ordering={ordering}
                    onSort={handleSort}
                    className="nier-col-yield"
                  />
                  <SortHeader
                    label="CHECKS"
                    shortLabel="CHK"
                    column="checks"
                    ordering={ordering}
                    onSort={handleSort}
                    className="nier-col-trust nier-col-checks"
                  />
                  <SortHeader
                    label="DATA"
                    column="incomplete"
                    ordering={ordering}
                    onSort={handleSort}
                    className="nier-col-trust nier-col-data"
                    title="Filing data quality: OK, WARN, or INCOMPLETE"
                  />
                  {wideTable && (
                    <>
                      <SortHeader label="P/E" column="pe" ordering={ordering} onSort={handleSort} className="nier-col-ratio" />
                      <SortHeader label="P/B" column="pb" ordering={ordering} onSort={handleSort} className="nier-col-ratio" />
                      <SortHeader label="ROE" column="roe" ordering={ordering} onSort={handleSort} className="nier-col-ratio" />
                      <SortHeader label="ROIC" column="roic" ordering={ordering} onSort={handleSort} className="nier-col-ratio" />
                      <SortHeader label="D/E" column="de" ordering={ordering} onSort={handleSort} className="nier-col-ratio" />
                    </>
                  )}
                  <SortHeader
                    label="SECTOR"
                    column="sector"
                    ordering={ordering}
                    onSort={handleSort}
                    className="nier-col-sector nier-col-wide"
                  />
                </tr>
              </thead>
              <tbody className="text-xs tracking-wider uppercase">
                  {companies.map((company) => {
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
                    const sectorLine = formatSectorSubsectorLine(company);
                    const dq = registryDataStatus(company);
                    const checksSignal = registryCellSignal('checks', null, appliedThresholds, {
                      qualified: company.passes_screen,
                      passCount: company.check_pass_count,
                      total: company.check_evaluable_total,
                    });
                    const yieldSignal = registryCellSignal(
                      'yield',
                      company.div_yield,
                      appliedThresholds,
                      thresholdExtras,
                    );
                    const peSignal = registryCellSignal('pe', company.pe_ratio, appliedThresholds);
                    const pbSignal = registryCellSignal('pb', company.pb_ratio, appliedThresholds);
                    const roeSignal = registryCellSignal('roe', company.roe, appliedThresholds);
                    const roicSignal = registryCellSignal(
                      'roic',
                      company.roic,
                      appliedThresholds,
                      thresholdExtras,
                    );
                    const deSignal = registryCellSignal(
                      'de',
                      company.debt_to_equity,
                      appliedThresholds,
                    );
                    const tickerBtnId = `registry-ticker-${company.id}`;
                    const previewRow = () => {
                      focusTickerButton(tickerBtnId);
                      selectCompanyPreview(company.id);
                    };
                    return (
                      <tr
                        key={company.id}
                        id={`registry-row-${company.id}`}
                        aria-selected={previewCompanyId === company.id}
                        onClick={previewRow}
                        onDoubleClick={() => openCompany(company.id)}
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
                        >
                          <WatchToggle
                            ticker={ticker}
                            watched={watched}
                            disabled={watchDisabled}
                            max={WATCHLIST_MAX}
                            onClick={() => toggleWatchlistPick(company)}
                          />
                        </td>
                        <td className="nier-col-ticker font-bold text-nier-orange">
                          <div className="nier-ticker-stack">
                            <TickerPreviewButton
                              id={tickerBtnId}
                              ticker={ticker}
                              companyName={company.name}
                              onPreview={previewRow}
                              onOpen={() => openCompany(company.id)}
                              describedBy={isNarrow ? undefined : 'registry-row-keys'}
                              openOnDoubleClick={!isNarrow}
                            />
                            {sectorLine ? (
                              <span
                                className="nier-ticker-sector nier-sentence nier-ink-muted"
                                title={sectorLine}
                              >
                                {sectorLine}
                              </span>
                            ) : null}
                          </div>
                        </td>
                        <td className="nier-proper-name nier-col-wide">{company.name}</td>
                        <td className="font-mono whitespace-nowrap nier-col-wide">
                          {formatPrice(company.last_traded_price)}
                        </td>
                        <td className="whitespace-nowrap nier-col-wide">
                          <span className="font-mono">{formatMarketCap(company.market_cap)}</span>
                          {tier && (
                            <span className={`nier-cap-tier nier-cap-tier--${tier.toLowerCase()}`}>
                              {tier}
                            </span>
                          )}
                        </td>
                        <td
                          className={`nier-col-yield font-mono whitespace-nowrap ${cellSignalClass(yieldSignal.signal)}`}
                          title={yieldSignal.title}
                        >
                          {formatPct(company.div_yield)}
                        </td>
                        <td
                          className={`font-mono nier-col-trust nier-col-checks ${cellSignalClass(checksSignal.signal)}`}
                          title={checksSignal.title}
                        >
                          {checksLabel}
                          {company.passes_screen ? (
                            <span className="nier-checks-qualified" aria-label="Qualified">
                              {' '}✓
                            </span>
                          ) : null}
                        </td>
                        <td className="nier-col-trust nier-col-data">
                          <span
                            className={`nier-dq-chip nier-dq-chip--${dq.level}`}
                            title={dq.title}
                            aria-label={`Data ${dq.label}: ${dq.title}`}
                          >
                            <span className="nier-dq-chip-label--full">{dq.label}</span>
                            <span className="nier-dq-chip-label--short" aria-hidden="true">
                              {dq.shortLabel || dq.label}
                            </span>
                          </span>
                        </td>
                        {wideTable && (
                          <>
                            <td
                              className={`font-mono whitespace-nowrap nier-col-ratio ${cellSignalClass(peSignal.signal)}`}
                              title={peSignal.title}
                            >
                              {formatRatio(company.pe_ratio)}
                            </td>
                            <td
                              className={`font-mono whitespace-nowrap nier-col-ratio ${cellSignalClass(pbSignal.signal)}`}
                              title={pbSignal.title}
                            >
                              {formatRatio(company.pb_ratio)}
                            </td>
                            <td
                              className={`font-mono whitespace-nowrap nier-col-ratio ${cellSignalClass(roeSignal.signal)}`}
                              title={roeSignal.title}
                            >
                              {formatPct(company.roe)}
                            </td>
                            <td
                              className={`font-mono whitespace-nowrap nier-col-ratio ${cellSignalClass(roicSignal.signal)}`}
                              title={roicSignal.title}
                            >
                              {formatPct(company.roic)}
                            </td>
                            <td
                              className={`font-mono whitespace-nowrap nier-col-ratio ${cellSignalClass(deSignal.signal)}`}
                              title={deSignal.title}
                            >
                              {formatRatio(company.debt_to_equity)}
                            </td>
                          </>
                        )}
                        <td className="nier-sentence nier-col-sector nier-col-wide">
                          <span>{company.sector || '—'}</span>
                          {company.subsector
                            && company.sector
                            && company.subsector.toLowerCase()
                              !== company.sector.toLowerCase() ? (
                            <span className="nier-subsector-inline nier-ink-muted">
                              {' '}· {company.subsector}
                            </span>
                          ) : null}
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
            )}
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

          {showDesktopRail && (
            <aside className="nier-detail-column">
              <RegistryPreview {...previewProps} />
            </aside>
          )}
        </div>
      </main>
      </div>

      {showNarrowSheet && (
        <>
          <button
            type="button"
            className="nier-preview-sheet-backdrop"
            tabIndex={-1}
            aria-hidden="true"
            onClick={clearPreview}
          />
          <RegistryPreview variant="sheet" {...previewProps} />
        </>
      )}
    </NierShell>
  );
}
