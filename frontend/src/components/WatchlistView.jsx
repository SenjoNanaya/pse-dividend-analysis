import { useEffect, useMemo, useRef, useState } from 'react';
import {
  cellSignalClass,
  describeLiveScreeningRules,
  formatMarketCap,
  formatPct,
  formatPrice,
  marketCapTier,
  registryCellSignal,
  registryDataStatus,
  formatSectorSubsectorLine,
} from '../lib/metrics';
import {
  EMPTY_WATCHLIST_THRESHOLDS,
  WATCHLIST_MAX,
  getWatchlistThresholds,
  watchlistIdsParam,
} from '../lib/watchlist';
import {
  diffWatchlistAlerts,
  parseWatchlistSignalThresholds,
} from '../lib/watchlistAlerts';
import {
  COMPANY_CSV_COLUMNS,
  csvDateStamp,
  downloadCsv,
  toCsv,
} from '../lib/csvExport';
import RegistryPreview from './RegistryPreview';
import RowKeysLegend from './RowKeysLegend';
import TickerPreviewButton from './TickerPreviewButton';
import WatchToggle from './WatchToggle';
import WatchColumnHeader from './WatchColumnHeader';
import useMediaQuery from '../lib/useMediaQuery';
import useScrollLock from '../lib/useScrollLock';
import { focusTickerButton } from '../lib/tableRowKeys';
import { API_BASE, jsonHeaders } from '../lib/api';

function formatRatio(v, digits = 2) {
  const n = Number(v);
  if (v == null || !Number.isFinite(n)) return '—';
  return n.toFixed(digits);
}

function ThresholdInput({
  label,
  hint,
  title,
  value,
  onChange,
  ariaLabel,
  disabled = false,
}) {
  const tip = title || hint;
  const accessible = ariaLabel || label;
  return (
    <label className={`nier-filter-field nier-threshold-field${disabled ? ' is-disabled' : ''}`}>
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
        disabled={disabled}
      />
    </label>
  );
}

function buildWatchlistUrl(ids, thresholds) {
  const params = new URLSearchParams();
  params.set('ids', watchlistIdsParam(ids));
  const pe = String(thresholds.peMax ?? '').trim();
  const pb = String(thresholds.pbMax ?? '').trim();
  const roe = String(thresholds.roeMin ?? '').trim();
  const yld = String(thresholds.yieldMin ?? '').trim();
  const roic = String(thresholds.roicMin ?? '').trim();
  const de = String(thresholds.deMax ?? '').trim();
  if (pe !== '' && Number.isFinite(Number(pe))) params.set('pe_max', pe);
  if (pb !== '' && Number.isFinite(Number(pb))) params.set('pb_max', pb);
  if (roe !== '' && Number.isFinite(Number(roe))) {
    params.set('roe_min', String(Number(roe) / 100));
  }
  if (yld !== '' && Number.isFinite(Number(yld))) {
    params.set('yield_min', String(Number(yld) / 100));
  }
  if (roic !== '' && Number.isFinite(Number(roic))) {
    params.set('roic_min', String(Number(roic) / 100));
  }
  if (de !== '' && Number.isFinite(Number(de))) params.set('de_max', de);
  return `${API_BASE}/?${params.toString()}`;
}

async function fetchWatchlistCompanies(ids, thresholds) {
  if (!ids.length) return [];
  let url = buildWatchlistUrl(ids, thresholds);
  const rows = [];
  while (url) {
    const res = await fetch(url, { headers: jsonHeaders });
    if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
    const data = await res.json();
    rows.push(...(data.results || []));
    url = data.next || null;
  }
  return rows;
}

const ALERT_THRESHOLD_KEYS = ['peMax', 'pbMax', 'roeMin', 'yieldMin', 'roicMin', 'deMax'];

function pickAlertThresholds(src) {
  const out = { ...EMPTY_WATCHLIST_THRESHOLDS };
  for (const k of ALERT_THRESHOLD_KEYS) out[k] = String(src?.[k] ?? '');
  return out;
}

function alertThresholdsEqual(a, b) {
  return ALERT_THRESHOLD_KEYS.every(
    (k) => String(a?.[k] ?? '') === String(b?.[k] ?? ''),
  );
}

export default function WatchlistView({
  watchlist,
  /** Applied registry Limit field strings (same shape as watchlist thresholds). */
  listThresholds = EMPTY_WATCHLIST_THRESHOLDS,
  onBack,
  onOpen,
  onRemove,
  onClearAll,
  onToggleCompare,
  onUpdateWatchlist,
  onOpenCompare,
  onClearCompare,
  onRemoveCompare,
  comparePicks = [],
  maxCompare = 4,
}) {
  const [companies, setCompanies] = useState([]);
  const [status, setStatus] = useState('idle');
  const [error, setError] = useState(null);
  const [draftThresholds, setDraftThresholds] = useState(() =>
    getWatchlistThresholds(watchlist),
  );
  const [appliedThresholds, setAppliedThresholds] = useState(() =>
    getWatchlistThresholds(watchlist),
  );
  const [thresholdError, setThresholdError] = useState(null);
  const [alertEvents, setAlertEvents] = useState([]);
  const [alertsDismissed, setAlertsDismissed] = useState(false);
  const [fetchRetry, setFetchRetry] = useState(0);
  const [previewId, setPreviewId] = useState(null);
  const [previewCompany, setPreviewCompany] = useState(null);
  const [previewStatus, setPreviewStatus] = useState('idle');
  const scrollLockRestoreYRef = useRef(null);
  /** Alert copy shown above the checklist when opened from an alert. */
  const [previewNotice, setPreviewNotice] = useState(null);
  const [clearConfirm, setClearConfirm] = useState(false);
  const [compareMode, setCompareMode] = useState(false);
  const [alertLimitsOpen, setAlertLimitsOpen] = useState(false);
  /** Narrow: Export / Clear / unarmed Pick live behind Tools. */
  const [toolsOpen, setToolsOpen] = useState(false);
  const isNarrow = useMediaQuery('(max-width: 767px)');

  const idsKey = watchlist.ids.join(',');
  const threshKey = JSON.stringify(appliedThresholds);
  const reportThresholds = useMemo(
    () => parseWatchlistSignalThresholds(appliedThresholds),
    [appliedThresholds],
  );

  useEffect(() => {
    const t = getWatchlistThresholds(watchlist);
    setDraftThresholds(t);
    setAppliedThresholds(t);
  }, [watchlist.thresholds]);

  useEffect(() => {
    if (!watchlist.ids.length) setClearConfirm(false);
  }, [watchlist.ids.length]);

  useEffect(() => {
    if (!watchlist.ids.length) {
      setCompanies([]);
      setStatus('empty');
      setError(null);
      setAlertEvents([]);
      setPreviewId(null);
      setPreviewCompany(null);
      setPreviewStatus('idle');
      setPreviewNotice(null);
      return undefined;
    }

    let cancelled = false;
    setStatus('loading');
    setError(null);
    setAlertsDismissed(false);

    fetchWatchlistCompanies(watchlist.ids, appliedThresholds)
      .then((rows) => {
        if (cancelled) return;
        const order = new Map(watchlist.ids.map((id, i) => [id, i]));
        rows.sort((a, b) => (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0));
        setCompanies(rows);
        setStatus('ready');

        const foundIds = rows.map((r) => r.id);
        if (foundIds.length !== watchlist.ids.length && onUpdateWatchlist) {
          onUpdateWatchlist({ pruneIds: foundIds });
        }

        const { events } = diffWatchlistAlerts(rows, appliedThresholds);
        setAlertEvents(events);
      })
      .catch((err) => {
        if (cancelled) return;
        console.error('Watchlist fetch error:', err);
        setCompanies([]);
        setError(err.message || 'Failed to reach API');
        setStatus('error');
      });

    return () => {
      cancelled = true;
    };
  }, [idsKey, threshKey, fetchRetry]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!previewId) {
      setPreviewCompany(null);
      setPreviewStatus('idle');
      return undefined;
    }
    if (!watchlist.ids.includes(previewId)) {
      setPreviewId(null);
      setPreviewCompany(null);
      setPreviewStatus('idle');
      setPreviewNotice(null);
      return undefined;
    }

    const ac = new AbortController();
    setPreviewCompany(null);
    setPreviewStatus('loading');

    fetch(`${API_BASE}/${previewId}/`, { headers: jsonHeaders, signal: ac.signal })
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
        console.error('Watchlist preview fetch error:', err);
        setPreviewStatus('error');
      });

    return () => ac.abort();
  }, [previewId, watchlist.ids]);

  const missingIds = useMemo(() => {
    if (status !== 'ready') return [];
    const found = new Set(companies.map((c) => c.id));
    return watchlist.ids.filter((id) => !found.has(id));
  }, [status, companies, watchlist.ids]);

  const showCompareCol = compareMode || comparePicks.length > 0;
  const compareAtCap = comparePicks.length >= maxCompare;
  // ticker name price mcap yield checks data pe pb roe roic de sector remove [+compare]
  const showWatchlistTable = status === 'ready' && companies.length > 0;
  const thresholdsPending =
    JSON.stringify(draftThresholds) !== JSON.stringify(appliedThresholds);
  const liveRules = useMemo(
    () => describeLiveScreeningRules(appliedThresholds),
    [appliedThresholds],
  );

  const listThresholdNorm = useMemo(
    () => pickAlertThresholds(listThresholds),
    [listThresholds],
  );
  const followListLimits = watchlist.alertsFollowList !== false;
  const matchesListLimits = alertThresholdsEqual(
    appliedThresholds,
    listThresholdNorm,
  );
  /** Hard-sync: while following, adopt company list Limits whenever they change. */
  useEffect(() => {
    if (!followListLimits) return;
    const next = pickAlertThresholds(listThresholdNorm);
    if (alertThresholdsEqual(appliedThresholds, next)) return;
    setThresholdError(null);
    setDraftThresholds(next);
    setAppliedThresholds(next);
    onUpdateWatchlist?.({ thresholds: next, alertsFollowList: true });
  }, [
    followListLimits,
    listThresholdNorm,
    appliedThresholds,
    onUpdateWatchlist,
  ]);

  const applyThresholds = () => {
    const labelFor = {
      peMax: 'P/E max',
      pbMax: 'P/B max',
      roeMin: 'ROE min',
      yieldMin: 'Yield min',
      roicMin: 'ROIC min',
      deMax: 'D/E max',
    };
    const next = { ...EMPTY_WATCHLIST_THRESHOLDS, ...draftThresholds };
    for (const [k, v] of Object.entries(next)) {
      const s = String(v ?? '').trim();
      const label = labelFor[k] || k;
      if (s !== '' && !Number.isFinite(Number(s))) {
        setThresholdError(`${label} needs a number of 0 or more.`);
        return;
      }
      if (s !== '' && Number(s) < 0) {
        setThresholdError(`${label} needs a number of 0 or more.`);
        return;
      }
    }
    setThresholdError(null);
    const follow = alertThresholdsEqual(next, listThresholdNorm);
    setAppliedThresholds(next);
    onUpdateWatchlist?.({ thresholds: next, alertsFollowList: follow });
    // Collapse after Apply so the watchlist table owns the viewport again.
    setAlertLimitsOpen(false);
  };

  const followCompanyListLimits = () => {
    const next = pickAlertThresholds(listThresholdNorm);
    setDraftThresholds(next);
    setThresholdError(null);
    setAppliedThresholds(next);
    onUpdateWatchlist?.({ thresholds: next, alertsFollowList: true });
    setAlertLimitsOpen(false);
  };

  const detachAlertLimits = () => {
    setThresholdError(null);
    onUpdateWatchlist?.({ alertsFollowList: false });
  };

  const exportCsv = () => {
    if (!companies.length) return;
    const text = toCsv(companies, COMPANY_CSV_COLUMNS);
    downloadCsv(`pse-watchlist-${csvDateStamp()}.csv`, text);
  };

  const clearPreview = () => {
    setPreviewId(null);
    setPreviewCompany(null);
    setPreviewNotice(null);
  };

  useEffect(() => {
    if (!isNarrow || previewId == null) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') clearPreview();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isNarrow, previewId]);

  /** Narrow sheet owns the viewport — close Alert limits / Tools so the shortlist can peek. */
  useEffect(() => {
    if (!isNarrow || previewId == null) return;
    setAlertLimitsOpen(false);
    setToolsOpen(false);
  }, [isNarrow, previewId]);

  useEffect(() => {
    if (!isNarrow) setToolsOpen(false);
  }, [isNarrow]);

  const selectPreview = (id, notice = null) => {
    setPreviewId(id);
    setPreviewNotice(notice);
    requestAnimationFrame(() => {
      const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      document.getElementById(`watchlist-row-${id}`)?.scrollIntoView({
        block: 'nearest',
        behavior: reduceMotion ? 'auto' : 'smooth',
      });
    });
  };

  const previewFromAlert = (ev) => {
    selectPreview(ev.id, ev.text);
  };

  const handleRemove = (id) => {
    if (previewId === id) clearPreview();
    onRemove(id);
  };

  const showPreview = status === 'ready' && companies.length > 0;
  const showNarrowSheet = isNarrow && Boolean(previewCompany);
  // Narrow: sheet is the preview — don't park an empty tip bar above the shortlist.
  const showBarPreview = showPreview && !isNarrow;
  useScrollLock(showNarrowSheet, { restoreYRef: scrollLockRestoreYRef });
  const openFromSheet = (id) => {
    scrollLockRestoreYRef.current = 0;
    onOpen(id);
  };
  const previewProps = {
    company: previewCompany,
    status: previewStatus,
    onOpen: openFromSheet,
    onClear: clearPreview,
    watched: Boolean(previewCompany),
    onToggleWatch: previewCompany
      ? (company) => handleRemove(company.id)
      : undefined,
    thresholds: reportThresholds,
    notice: previewNotice,
    emptyHint: isNarrow
      ? 'Tap a row or an alert for the checklist.'
      : 'Select a company — or open an alert — for the checklist.',
  };

  return (
    <div
      className={`watchlist-page nier-view-settle${
        showNarrowSheet ? ' watchlist-page--sheet-open' : ''
      }${isNarrow ? ' watchlist-page--narrow' : ''}${
        watchlist.ids.length === 0 ? ' watchlist-page--empty' : ''
      }`}
    >
      <div className="nier-sheet-background" inert={showNarrowSheet || undefined}>
      <header className="nier-dashboard-header">
        <div className="flex items-center gap-3 flex-wrap">
          <button type="button" onClick={onBack} className="nier-btn nier-btn--compact">
            Back to list
          </button>
          <h1 className="nier-chrome-title">Watchlist</h1>
        </div>
        <div className="nier-chrome-meta watchlist-header-meta">
          <span>
            <span className="nier-chrome-meta-value">{watchlist.ids.length}</span>
            {' / '}
            {WATCHLIST_MAX} watched
          </span>
          {isNarrow && watchlist.ids.length > 0 && (
            <>
              {showCompareCol && companies.length > 0 && (
                <button
                  type="button"
                  className="nier-btn nier-btn--compact nier-btn--pressed"
                  onClick={() => setCompareMode(false)}
                  aria-pressed
                  title="Hide compare checkboxes"
                >
                  Compare
                </button>
              )}
              <button
                type="button"
                className={`nier-btn nier-btn--compact${toolsOpen || clearConfirm ? ' nier-btn--pressed' : ''}`}
                onClick={() => {
                  setToolsOpen((o) => !o);
                  if (clearConfirm) setClearConfirm(false);
                }}
                aria-expanded={toolsOpen || clearConfirm}
                aria-controls="watchlist-tools"
                title="Export CSV, clear list, and pick to compare"
              >
                Tools
                {clearConfirm ? ' · clear' : ''}
              </button>
            </>
          )}
        </div>
      </header>

      <main id="main-content" className="nier-dashboard-stack nier-dashboard-stack--focus mx-auto">
        {isNarrow && watchlist.ids.length > 0 && (toolsOpen || clearConfirm) && (
          <div
            id="watchlist-tools"
            className="watchlist-tools-panel"
            role="group"
            aria-label="Watchlist tools"
          >
            {!showCompareCol && companies.length > 0 && (
              <button
                type="button"
                className="nier-btn nier-btn--compact"
                onClick={() => {
                  setCompareMode(true);
                  setToolsOpen(false);
                }}
                aria-pressed={false}
                title="Show checkboxes to pick companies for comparison"
              >
                Pick to compare
              </button>
            )}
            {companies.length > 0 && (
              <button type="button" className="nier-btn nier-btn--compact" onClick={exportCsv}>
                Export CSV
              </button>
            )}
            {!clearConfirm && (
              <button
                type="button"
                className="nier-btn nier-btn--compact"
                onClick={() => setClearConfirm(true)}
              >
                Clear watchlist
              </button>
            )}
            {clearConfirm && (
              <div
                className="watchlist-clear-confirm"
                role="group"
                aria-label="Confirm clear watchlist"
              >
                <p className="watchlist-clear-confirm-copy nier-msg-plain" role="status">
                  Remove all {watchlist.ids.length} saved{' '}
                  {watchlist.ids.length === 1 ? 'ticker' : 'tickers'}? This cannot be undone.
                </p>
                <button
                  type="button"
                  className="nier-btn nier-btn--compact"
                  onClick={() => {
                    onClearAll();
                    setClearConfirm(false);
                    setToolsOpen(false);
                    setPreviewId(null);
                    setPreviewCompany(null);
                    setPreviewNotice(null);
                    setAlertEvents([]);
                  }}
                >
                  Yes, clear all
                </button>
                <button
                  type="button"
                  className="nier-btn nier-btn--compact"
                  onClick={() => setClearConfirm(false)}
                >
                  Keep list
                </button>
              </div>
            )}
          </div>
        )}

        {!isNarrow && watchlist.ids.length > 0 && (
          <div className="watchlist-toolbar">
            <p className="watchlist-copy">
              Companies you watch here. Alerts appear when a signal changes since your last
              visit. Clearing this browser&apos;s site data clears the list.
            </p>
            <div className="watchlist-toolbar-actions">
              {companies.length > 0 && (
                <button
                  type="button"
                  className={`nier-btn nier-btn--compact${showCompareCol ? ' nier-btn--pressed' : ''}`}
                  onClick={() => setCompareMode((o) => !o)}
                  aria-pressed={showCompareCol}
                  title="Show checkboxes to pick companies for comparison"
                >
                  Pick to compare
                </button>
              )}
              {companies.length > 0 && (
                <button type="button" className="nier-btn nier-btn--compact" onClick={exportCsv}>
                  Export CSV
                </button>
              )}
              {!clearConfirm && (
                <button
                  type="button"
                  className="nier-btn nier-btn--compact"
                  onClick={() => setClearConfirm(true)}
                >
                  Clear watchlist
                </button>
              )}
              {clearConfirm && (
                <div
                  className="watchlist-clear-confirm"
                  role="group"
                  aria-label="Confirm clear watchlist"
                >
                  <p className="watchlist-clear-confirm-copy nier-msg-plain" role="status">
                    Remove all {watchlist.ids.length} saved{' '}
                    {watchlist.ids.length === 1 ? 'ticker' : 'tickers'}? This cannot be undone.
                  </p>
                  <button
                    type="button"
                    className="nier-btn nier-btn--compact"
                    onClick={() => {
                      onClearAll();
                      setClearConfirm(false);
                      setPreviewId(null);
                      setPreviewCompany(null);
                      setPreviewNotice(null);
                      setAlertEvents([]);
                    }}
                  >
                    Yes, clear all
                  </button>
                  <button
                    type="button"
                    className="nier-btn nier-btn--compact"
                    onClick={() => setClearConfirm(false)}
                  >
                    Keep list
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {watchlist.ids.length > 0 && (
          <div className="nier-live-rules-row">
            <p
              className="nier-live-rules nier-msg-plain"
              role="status"
              title={
                followListLimits
                  ? 'Alert flips follow company list Limits. When you change list Limits, alerts update too.'
                  : `${liveRules.title} Detached from list Limits — Follow list Limits to re-link.`
              }
            >
              <span className="nier-live-rules-line">
                {isNarrow ? liveRules.compactLine : liveRules.line}
              </span>
              {followListLimits ? (
                <span className="nier-live-rules-tag">
                  {isNarrow ? ' list' : ' following list'}
                </span>
              ) : liveRules.usingDefaults ? (
                <span className="nier-live-rules-tag">
                  {isNarrow ? ' detached' : ' detached · defaults'}
                </span>
              ) : (
                <span className="nier-live-rules-tag"> detached</span>
              )}
              <span className="nier-live-rules-edit"> · Alert flips only</span>
            </p>
            <button
              type="button"
              className={`nier-btn nier-btn--compact${alertLimitsOpen ? ' nier-btn--pressed' : ''}`}
              onClick={() => setAlertLimitsOpen((o) => !o)}
              aria-expanded={alertLimitsOpen}
              aria-controls="watchlist-alert-limits"
              title={
                followListLimits
                  ? 'Alert flips follow list Limits. Open to detach or confirm the shared numbers.'
                  : 'Edit detached alert floors (does not change company list screening)'
              }
            >
              Alert limits
              {!followListLimits ? ' · on' : ''}
              {thresholdsPending && !alertLimitsOpen ? ' · pending' : ''}
            </button>
          </div>
        )}

        {watchlist.ids.length > 0 && alertLimitsOpen && (
          <div
            id="watchlist-alert-limits"
            className="nier-filter-bar"
            role="group"
            aria-label="Watchlist alert limits"
          >
            <p className="nier-threshold-bridge nier-msg-plain">
              {followListLimits
                ? 'Following company list Limits — alert flips use the same numbers as screening. Detach to set different alert floors.'
                : 'Detached — alert flips ignore list Limits until you Follow list Limits again.'}
              {!followListLimits && matchesListLimits
                ? ' Numbers currently match the list, but will not auto-update when list Limits change.'
                : ''}
            </p>
            <ThresholdInput
              label="P/E MAX"
              hint="Blank = default 22"
              value={draftThresholds.peMax}
              onChange={(v) => setDraftThresholds((p) => ({ ...p, peMax: v }))}
              ariaLabel="P/E maximum"
              disabled={followListLimits}
            />
            <ThresholdInput
              label="P/B MAX"
              hint="Blank = default 1"
              value={draftThresholds.pbMax}
              onChange={(v) => setDraftThresholds((p) => ({ ...p, pbMax: v }))}
              ariaLabel="P/B maximum"
              disabled={followListLimits}
            />
            <ThresholdInput
              label="ROE MIN %"
              hint="Blank = default 10%"
              value={draftThresholds.roeMin}
              onChange={(v) => setDraftThresholds((p) => ({ ...p, roeMin: v }))}
              ariaLabel="ROE minimum percent"
              disabled={followListLimits}
            />
            <ThresholdInput
              label="YIELD MIN %"
              hint="Blank = no floor"
              title="Blank = no yield alert floor"
              value={draftThresholds.yieldMin}
              onChange={(v) => setDraftThresholds((p) => ({ ...p, yieldMin: v }))}
              ariaLabel="Dividend yield minimum percent"
              disabled={followListLimits}
            />
            <ThresholdInput
              label="ROIC MIN %"
              hint="Blank = no floor"
              title="Blank = no ROIC alert floor"
              value={draftThresholds.roicMin}
              onChange={(v) => setDraftThresholds((p) => ({ ...p, roicMin: v }))}
              ariaLabel="ROIC or capital return minimum percent"
              disabled={followListLimits}
            />
            <ThresholdInput
              label="D/E MAX"
              hint="Blank = default 2"
              value={draftThresholds.deMax}
              onChange={(v) => setDraftThresholds((p) => ({ ...p, deMax: v }))}
              ariaLabel="Debt to equity maximum"
              disabled={followListLimits}
            />
            <div className="nier-filter-actions">
              {followListLimits ? (
                <button
                  type="button"
                  className="nier-btn"
                  onClick={detachAlertLimits}
                  title="Stop following list Limits so you can set different alert floors"
                >
                  Detach
                </button>
              ) : (
                <button
                  type="button"
                  className="nier-btn"
                  onClick={followCompanyListLimits}
                  title="Copy company list Limits into alerts and keep them linked"
                >
                  Follow list Limits
                </button>
              )}
              {!followListLimits && (
                <button
                  type="button"
                  className={`nier-btn${thresholdsPending ? ' nier-btn--pressed' : ''}`}
                  onClick={applyThresholds}
                >
                  {thresholdsPending ? 'Apply · pending' : 'Apply'}
                </button>
              )}
              <button
                type="button"
                className="nier-btn"
                onClick={() => {
                  setDraftThresholds(appliedThresholds);
                  setThresholdError(null);
                  setAlertLimitsOpen(false);
                }}
              >
                Close
              </button>
            </div>
            {thresholdsPending && !thresholdError && !followListLimits && (
              <p className="nier-filter-status nier-ink-muted nier-msg-plain" role="status">
                Draft limits are not live yet. Press Apply.
              </p>
            )}
            {thresholdError && (
              <p className="nier-filter-error nier-msg-plain" role="alert">
                {thresholdError}
              </p>
            )}
          </div>
        )}

        {comparePicks.length > 0 && (
          <div className="nier-compare-tray" role="region" aria-label="Compare selection">
            <div className="nier-compare-tray-picks">
              <span className="nier-compare-tray-label">COMPARE</span>
              {comparePicks.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className="nier-compare-chip"
                  onClick={() => onRemoveCompare?.(p.id)}
                  aria-label={`Remove ${p.ticker} from compare`}
                >
                  {p.ticker} ×
                </button>
              ))}
              <span className="nier-compare-tray-count" aria-live="polite">
                {comparePicks.length}/{maxCompare}
              </span>
            </div>
            <div className="nier-compare-tray-actions">
              <button
                type="button"
                className="nier-btn nier-btn--compact"
                disabled={comparePicks.length < 2}
                onClick={onOpenCompare}
              >
                Compare selected
              </button>
              <button type="button" className="nier-btn nier-btn--compact" onClick={onClearCompare}>
                Clear selection
              </button>
            </div>
          </div>
        )}

        {!alertsDismissed && alertEvents.length > 0 && (
          <div className="watchlist-alerts" role="status">
            <div className="watchlist-alerts-head">
              <span className="watchlist-alerts-title">
                {alertEvents.length} watchlist alert
                {alertEvents.length === 1 ? '' : 's'}
              </span>
              <button
                type="button"
                className="nier-btn nier-btn--compact"
                onClick={() => setAlertsDismissed(true)}
              >
                Dismiss
              </button>
            </div>
            <ul className="watchlist-alerts-list">
              {alertEvents.map((ev) => {
                const alertKey = `${ev.id}-${ev.kind}-${ev.from}-${ev.to}`;
                const selected = previewId === ev.id && previewNotice === ev.text;
                const ticker = ev.ticker || 'company';
                return (
                  <li key={alertKey}>
                    <button
                      type="button"
                      className={`watchlist-alert-btn${selected ? ' watchlist-alert-btn--active' : ''}`}
                      onClick={() => previewFromAlert(ev)}
                      aria-label={`Open checklist for ${ticker}: ${ev.text}`}
                      aria-pressed={selected || undefined}
                    >
                      {ev.text}
                    </button>
                  </li>
                );
              })}
            </ul>
            <p className="watchlist-alerts-hint nier-msg-plain">
              {isNarrow
                ? 'Tap an alert for that checklist — fails first.'
                : "Open an alert to see that company's checklist — fails first."}
            </p>
          </div>
        )}

        {missingIds.length > 0 && (
          <p className="watchlist-warn nier-msg-plain" role="status">
            {missingIds.length} saved ticker
            {missingIds.length === 1 ? '' : 's'}{' '}
            {missingIds.length === 1 ? 'is' : 'are'} no longer in the registry and
            {missingIds.length === 1 ? ' was' : ' were'} removed from this list.
          </p>
        )}

        <div
          className={`nier-dashboard-grid nier-dashboard-grid--focus${
            isNarrow ? ' nier-dashboard-grid--narrow' : ''
          }`}
        >
          <div className="nier-table-column">
            {showBarPreview && (
              <RegistryPreview variant="bar" {...previewProps} />
            )}

            <div className="nier-table-container">
              {!isNarrow && showWatchlistTable && (
                <RowKeysLegend id="watchlist-row-keys" />
              )}
              {!showWatchlistTable ? (
                <div className="nier-table-status">
                  {status === 'loading' ? (
                    <p className="nier-table-status-msg nier-ink-muted nier-msg-plain" role="status">
                      Loading watchlist…
                    </p>
                  ) : status === 'error' ? (
                    <div className="nier-table-status-panel" role="alert">
                      <p className="nier-table-status-msg text-nier-orange nier-msg-plain">
                        Couldn&apos;t load your watchlist. Make sure Edge is running, then try
                        again.
                      </p>
                      <button
                        type="button"
                        className="nier-btn"
                        onClick={() => setFetchRetry((n) => n + 1)}
                      >
                        Try again
                      </button>
                    </div>
                  ) : (
                    <div
                      className="nier-empty-state nier-table-status-panel watchlist-empty"
                      role="status"
                    >
                      <p className="nier-empty-title">Nothing watched yet</p>
                      <p className="nier-empty-copy nier-msg-plain">
                        On the company list, tap ★ under WATCH to save a name. Alerts for check
                        and ratio flips show up here on later visits.
                      </p>
                      <button type="button" className="nier-btn" onClick={onBack}>
                        Back to company list
                      </button>
                    </div>
                  )}
                </div>
              ) : (
              <table
                className="nier-table"
                aria-describedby={isNarrow ? undefined : 'watchlist-row-keys'}
              >
                <caption className="sr-only">
                  Watchlist companies. Alerts open the same checklist as a row preview.
                </caption>
                <thead>
                  <tr>
                    {showCompareCol && (
                      <th className="nier-check-col" scope="col">
                        <span className="sr-only">Compare</span>
                        <span aria-hidden="true">⊕</span>
                      </th>
                    )}
                    <WatchColumnHeader />
                    <th scope="col" className="nier-col-ticker">
                      TICKER
                    </th>
                    <th scope="col" className="nier-col-wide">
                      NAME
                    </th>
                    <th scope="col" className="nier-col-wide">
                      PRICE
                    </th>
                    <th scope="col" className="nier-col-wide">
                      MCAP
                    </th>
                    <th scope="col" className="nier-col-yield" title="YIELD">
                      <span className="nier-sort-label">
                        <span className="nier-sort-label--full">YIELD</span>
                        <span className="nier-sort-label--short" aria-hidden="true">
                          YLD
                        </span>
                      </span>
                    </th>
                    <th scope="col" className="nier-col-trust nier-col-checks" title="CHECKS">
                      <span className="nier-sort-label">
                        <span className="nier-sort-label--full">CHECKS</span>
                        <span className="nier-sort-label--short" aria-hidden="true">
                          CHK
                        </span>
                      </span>
                    </th>
                    <th
                      scope="col"
                      className="nier-col-trust nier-col-data"
                      title="Filing data quality: OK, WARN, or INCOMPLETE"
                    >
                      DATA
                    </th>
                    <th scope="col" className="nier-col-ratio">
                      P/E
                    </th>
                    <th scope="col" className="nier-col-ratio">
                      P/B
                    </th>
                    <th scope="col" className="nier-col-ratio">
                      ROE
                    </th>
                    <th scope="col" className="nier-col-ratio">
                      ROIC
                    </th>
                    <th scope="col" className="nier-col-ratio">
                      D/E
                    </th>
                    <th scope="col" className="nier-col-sector nier-col-wide">
                      SECTOR
                    </th>
                  </tr>
                </thead>
                <tbody className="text-xs tracking-wider uppercase">
                  {companies.map((company) => {
                      const ticker = company.ticker || company.symbol;
                      const sectorLine = formatSectorSubsectorLine(company);
                      const tier = company.cap_tier || marketCapTier(company.market_cap);
                      const checksLabel =
                        company.check_pass_count != null &&
                        company.check_evaluable_total != null
                          ? `${company.check_pass_count}/${company.check_evaluable_total}`
                          : '—';
                      const inCompare = comparePicks.some((p) => p.id === company.id);
                      const checkboxDisabled = !inCompare && compareAtCap;
                      const dq = registryDataStatus(company);
                      const signalExtras = {
                        yieldMin: reportThresholds.yieldMin,
                        roicMin: reportThresholds.roicMin,
                      };
                      const checksSignal = registryCellSignal('checks', null, reportThresholds, {
                        qualified: company.passes_screen,
                        passCount: company.check_pass_count,
                        total: company.check_evaluable_total,
                      });
                      const yieldSignal = registryCellSignal(
                        'yield',
                        company.div_yield,
                        reportThresholds,
                        signalExtras,
                      );
                      const peSignal = registryCellSignal('pe', company.pe_ratio, reportThresholds);
                      const pbSignal = registryCellSignal('pb', company.pb_ratio, reportThresholds);
                      const roeSignal = registryCellSignal('roe', company.roe, reportThresholds);
                      const roicSignal = registryCellSignal(
                        'roic',
                        company.roic,
                        reportThresholds,
                        signalExtras,
                      );
                      const deSignal = registryCellSignal(
                        'de',
                        company.debt_to_equity,
                        reportThresholds,
                      );
                      const tickerBtnId = `watchlist-ticker-${company.id}`;
                      const previewRow = () => {
                        focusTickerButton(tickerBtnId);
                        selectPreview(company.id);
                      };
                      return (
                        <tr
                          key={company.id}
                          id={`watchlist-row-${company.id}`}
                          aria-selected={previewId === company.id}
                          onClick={previewRow}
                          onDoubleClick={() => onOpen(company.id)}
                          className={[
                            'transition-colors duration-150 hover:bg-nier-dark/10',
                            previewId === company.id
                              ? 'bg-nier-dark/15 ring-1 ring-inset ring-nier-dark/30'
                              : '',
                            company.passes_screen ? 'nier-row-qualified' : '',
                            inCompare ? 'nier-row-compare' : '',
                          ]
                            .filter(Boolean)
                            .join(' ')}
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
                                  onChange={() => onToggleCompare?.(company)}
                                  aria-label={
                                    checkboxDisabled
                                      ? `Compare full (max ${maxCompare}). Cannot add ${ticker}`
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
                              watched
                              onClick={() => handleRemove(company.id)}
                            />
                          </td>
                          <td className="nier-col-ticker font-bold text-nier-orange">
                            <div className="nier-ticker-stack">
                              <TickerPreviewButton
                                id={tickerBtnId}
                                ticker={ticker}
                                companyName={company.name}
                                onPreview={previewRow}
                                onOpen={() => onOpen(company.id)}
                                describedBy={isNarrow ? undefined : 'watchlist-row-keys'}
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
                            <span className="font-mono">
                              {formatMarketCap(company.market_cap)}
                            </span>
                            {tier && (
                              <span
                                className={`nier-cap-tier nier-cap-tier--${tier.toLowerCase()}`}
                              >
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
          </div>
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
    </div>
  );
}
