import { useEffect, useMemo, useState } from 'react';
import {
  formatMarketCap,
  formatPct,
  formatPrice,
  marketCapTier,
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
import { API_BASE, jsonHeaders } from '../lib/api';

function formatRatio(v, digits = 2) {
  const n = Number(v);
  if (v == null || !Number.isFinite(n)) return '—';
  return n.toFixed(digits);
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

export default function WatchlistView({
  watchlist,
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
  /** Alert copy shown above the checklist when opened from an alert. */
  const [previewNotice, setPreviewNotice] = useState(null);

  const idsKey = watchlist.ids.join(',');
  const threshKey = JSON.stringify(appliedThresholds);
  const reportThresholds = useMemo(
    () => parseWatchlistSignalThresholds(appliedThresholds),
    [appliedThresholds],
  );

  useEffect(() => {
    setDraftThresholds(getWatchlistThresholds(watchlist));
  }, [watchlist.thresholds]);

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

  const compareAtCap = comparePicks.length >= maxCompare;
  const thresholdsPending =
    JSON.stringify(draftThresholds) !== JSON.stringify(appliedThresholds);

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
    setAppliedThresholds(next);
    onUpdateWatchlist?.({ thresholds: next });
  };

  const exportCsv = () => {
    if (!companies.length) return;
    const text = toCsv(companies, COMPANY_CSV_COLUMNS);
    downloadCsv(`pse-watchlist-${csvDateStamp()}.csv`, text);
  };

  const clearPreview = () => {
    setPreviewId(null);
    setPreviewNotice(null);
  };

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
  const colSpan = 16;

  return (
    <div className="watchlist-page animate-fade-in">
      <header className="nier-dashboard-header">
        <div className="flex items-center gap-3 flex-wrap">
          <button type="button" onClick={onBack} className="nier-btn nier-btn--compact">
            Back to list
          </button>
          <h1 className="nier-title text-sm tracking-[0.18em]">WATCHLIST_UNIT</h1>
        </div>
        <div className="text-xs tracking-widest uppercase font-medium text-right nier-ink-muted">
          [ WATCHING:{' '}
          <span className="text-nier-orange">{watchlist.ids.length}</span>
          {' / '}
          {WATCHLIST_MAX} ]
        </div>
      </header>

      <main id="main-content" className="nier-dashboard-stack nier-dashboard-stack--focus mx-auto">
        <div className="watchlist-toolbar">
          <p className="watchlist-copy">
            Companies you save here. Alerts appear when a signal changes since your last
            visit. Clearing this browser&apos;s site data clears the list.
          </p>
          <div className="flex gap-2 flex-wrap">
            {companies.length > 0 && (
              <button type="button" className="nier-btn nier-btn--compact" onClick={exportCsv}>
                Export CSV
              </button>
            )}
            {watchlist.ids.length > 0 && (
              <button type="button" className="nier-btn nier-btn--compact" onClick={onClearAll}>
                Clear watchlist
              </button>
            )}
          </div>
        </div>

        {watchlist.ids.length > 0 && (
          <div className="nier-filter-bar" role="group" aria-label="Watchlist thresholds">
            <ThresholdInput
              label="P/E MAX"
              hint="Leave blank for default 22"
              value={draftThresholds.peMax}
              onChange={(v) => setDraftThresholds((p) => ({ ...p, peMax: v }))}
            />
            <ThresholdInput
              label="P/B MAX"
              hint="Leave blank for default 1"
              value={draftThresholds.pbMax}
              onChange={(v) => setDraftThresholds((p) => ({ ...p, pbMax: v }))}
            />
            <ThresholdInput
              label="ROE MIN %"
              hint="Leave blank for default 10%"
              value={draftThresholds.roeMin}
              onChange={(v) => setDraftThresholds((p) => ({ ...p, roeMin: v }))}
            />
            <ThresholdInput
              label="YIELD MIN %"
              hint="Leave blank to skip yield alerts"
              value={draftThresholds.yieldMin}
              onChange={(v) => setDraftThresholds((p) => ({ ...p, yieldMin: v }))}
            />
            <ThresholdInput
              label="RETURN MIN %"
              hint="Leave blank for no minimum"
              value={draftThresholds.roicMin}
              onChange={(v) => setDraftThresholds((p) => ({ ...p, roicMin: v }))}
            />
            <ThresholdInput
              label="D/E MAX"
              hint="Leave blank for default 2"
              value={draftThresholds.deMax}
              onChange={(v) => setDraftThresholds((p) => ({ ...p, deMax: v }))}
            />
            <div className="nier-filter-actions">
              <button
                type="button"
                className={`nier-btn${thresholdsPending ? ' nier-btn--pressed' : ''}`}
                onClick={applyThresholds}
              >
                {thresholdsPending ? 'Apply alert limits · pending' : 'Apply alert limits'}
              </button>
            </div>
            {thresholdsPending && !thresholdError && (
              <p className="nier-filter-status nier-ink-muted nier-msg-plain" role="status">
                Alert limits are not applied yet.
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
                return (
                  <li key={alertKey}>
                    <button
                      type="button"
                      className={`watchlist-alert-btn${selected ? ' watchlist-alert-btn--active' : ''}`}
                      onClick={() => previewFromAlert(ev)}
                    >
                      {ev.text}
                    </button>
                  </li>
                );
              })}
            </ul>
            <p className="watchlist-alerts-hint nier-msg-plain">
              Open an alert to see that company&apos;s checklist — fails first.
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

        <div className="nier-dashboard-grid nier-dashboard-grid--focus">
          <div className="nier-table-column">
            {showPreview && (
              <RegistryPreview
                variant="bar"
                company={previewCompany}
                status={previewStatus}
                onOpen={onOpen}
                onClear={clearPreview}
                thresholds={reportThresholds}
                notice={previewNotice}
                emptyHint="Select a company — or open an alert — to see the checklist (fails first)."
                onPreviewFirst={
                  companies.length > 0 ? () => selectPreview(companies[0].id) : undefined
                }
              />
            )}

            <div className="nier-table-container">
              <table className="nier-table">
                <caption className="sr-only">
                  Watchlist companies. Select a row to preview the checklist. Enter or Space
                  previews; O opens the full report. Alerts open the same checklist.
                </caption>
                <thead>
                  <tr>
                    <th className="nier-check-col" scope="col">
                      <span className="sr-only">Compare</span>
                      <span aria-hidden="true">⊕</span>
                    </th>
                    <th scope="col">TICKER</th>
                    <th scope="col">NAME</th>
                    <th scope="col">PRICE</th>
                    <th scope="col">MCAP</th>
                    <th scope="col">YIELD</th>
                    <th scope="col">CHECKS</th>
                    <th scope="col">DILUTION</th>
                    <th scope="col">INCOMPLETE</th>
                    <th scope="col">P/E</th>
                    <th scope="col">P/B</th>
                    <th scope="col">ROE</th>
                    <th scope="col">ROIC</th>
                    <th scope="col">D/E</th>
                    <th scope="col" className="nier-col-sector">
                      SECTOR
                    </th>
                    <th scope="col">
                      <span className="sr-only">Remove</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="text-xs tracking-wider uppercase">
                  {status === 'empty' && (
                    <tr>
                      <td colSpan={colSpan} className="nier-empty-cell">
                        <div className="nier-empty-state">
                          <p className="nier-empty-title">No companies saved yet</p>
                          <p className="nier-empty-copy nier-msg-plain">
                            Save tickers from the company list to watch for signal changes on later
                            visits — checks, yield, dilution, and debt-to-equity flips show up here.
                          </p>
                          <button type="button" className="nier-btn" onClick={onBack}>
                            Back to company list
                          </button>
                        </div>
                      </td>
                    </tr>
                  )}
                  {status === 'loading' && (
                    <tr>
                      <td
                        colSpan={colSpan}
                        className="text-center nier-ink-muted py-12 nier-msg-plain"
                        role="status"
                      >
                        Loading watchlist…
                      </td>
                    </tr>
                  )}
                  {status === 'error' && (
                    <tr>
                      <td
                        colSpan={colSpan}
                        className="text-center py-12 text-nier-orange nier-msg-plain"
                        role="alert"
                      >
                        Couldn&apos;t load your watchlist. Make sure Edge is running, then try
                        again.
                        <div className="mt-4">
                          <button
                            type="button"
                            className="nier-btn nier-btn--compact"
                            onClick={() => setFetchRetry((n) => n + 1)}
                          >
                            Try again
                          </button>
                        </div>
                      </td>
                    </tr>
                  )}
                  {status === 'ready' &&
                    companies.map((company) => {
                      const ticker = company.ticker || company.symbol;
                      const tier = company.cap_tier || marketCapTier(company.market_cap);
                      const checksLabel =
                        company.check_pass_count != null &&
                        company.check_evaluable_total != null
                          ? `${company.check_pass_count}/${company.check_evaluable_total}`
                          : '—';
                      const inCompare = comparePicks.some((p) => p.id === company.id);
                      const checkboxDisabled = !inCompare && compareAtCap;
                      const dil =
                        company.dilution_pass === true
                          ? '✓'
                          : company.dilution_pass === false
                            ? '✗'
                            : '—';
                      const onRowKeyDown = (e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault();
                          if (e.ctrlKey || e.metaKey) onOpen(company.id);
                          else selectPreview(company.id);
                        } else if (e.key === ' ') {
                          e.preventDefault();
                          selectPreview(company.id);
                        } else if (e.key === 'o' && !e.ctrlKey && !e.metaKey && !e.altKey) {
                          e.preventDefault();
                          onOpen(company.id);
                        }
                      };
                      return (
                        <tr
                          key={company.id}
                          id={`watchlist-row-${company.id}`}
                          tabIndex={0}
                          aria-keyshortcuts="Enter Space o"
                          onClick={() => selectPreview(company.id)}
                          onDoubleClick={() => onOpen(company.id)}
                          onKeyDown={onRowKeyDown}
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
                                onChange={() => onToggleCompare?.(company)}
                                aria-label={
                                  checkboxDisabled
                                    ? `Compare full. Cannot add ${ticker}`
                                    : `Compare ${ticker}`
                                }
                              />
                            </label>
                          </td>
                          <td className="font-bold text-nier-orange">
                            <button
                              type="button"
                              className="watchlist-ticker-btn"
                              onClick={(e) => {
                                e.stopPropagation();
                                selectPreview(company.id);
                              }}
                              onDoubleClick={(e) => {
                                e.stopPropagation();
                                onOpen(company.id);
                              }}
                            >
                              {ticker}
                            </button>
                          </td>
                          <td className="nier-proper-name">{company.name}</td>
                          <td className="font-mono whitespace-nowrap">
                            {formatPrice(company.last_traded_price)}
                          </td>
                          <td className="whitespace-nowrap">
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
                          <td className="font-mono whitespace-nowrap">
                            {formatPct(company.div_yield)}
                          </td>
                          <td className="font-mono">{checksLabel}</td>
                          <td>{dil}</td>
                          <td>{company.info_incomplete ? 'YES' : '—'}</td>
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
                          <td className="nier-sentence nier-col-sector">
                            {company.sector || '—'}
                          </td>
                          <td
                            onClick={(e) => e.stopPropagation()}
                            onDoubleClick={(e) => e.stopPropagation()}
                            onKeyDown={(e) => e.stopPropagation()}
                          >
                            <button
                              type="button"
                              className="nier-btn nier-btn--compact"
                              onClick={() => handleRemove(company.id)}
                              aria-label={`Remove ${ticker} from watchlist`}
                            >
                              Remove
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
