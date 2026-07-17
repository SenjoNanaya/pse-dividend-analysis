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
import { diffWatchlistAlerts } from '../lib/watchlistAlerts';
import {
  COMPANY_CSV_COLUMNS,
  csvDateStamp,
  downloadCsv,
  toCsv,
} from '../lib/csvExport';

const API_BASE = 'http://127.0.0.1:8000/api/companies';
const jsonHeaders = { Accept: 'application/json' };

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

  const idsKey = watchlist.ids.join(',');
  const threshKey = JSON.stringify(appliedThresholds);

  useEffect(() => {
    setDraftThresholds(getWatchlistThresholds(watchlist));
  }, [watchlist.thresholds]);

  useEffect(() => {
    if (!watchlist.ids.length) {
      setCompanies([]);
      setStatus('empty');
      setError(null);
      setAlertEvents([]);
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
  }, [idsKey, threshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const missingIds = useMemo(() => {
    if (status !== 'ready') return [];
    const found = new Set(companies.map((c) => c.id));
    return watchlist.ids.filter((id) => !found.has(id));
  }, [status, companies, watchlist.ids]);

  const compareAtCap = comparePicks.length >= maxCompare;

  const applyThresholds = () => {
    const next = { ...EMPTY_WATCHLIST_THRESHOLDS, ...draftThresholds };
    for (const [k, v] of Object.entries(next)) {
      const s = String(v ?? '').trim();
      if (s !== '' && !Number.isFinite(Number(s))) {
        setThresholdError(`${k} must be a non-negative number.`);
        return;
      }
      if (s !== '' && Number(s) < 0) {
        setThresholdError(`${k} must be a non-negative number.`);
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

  return (
    <div className="watchlist-page animate-fade-in">
      <header className="nier-dashboard-header">
        <div className="flex items-center gap-3 flex-wrap">
          <button type="button" onClick={onBack} className="nier-btn px-3 py-1 text-xs">
            &lt; REGISTRY
          </button>
          <div className="w-2.5 h-2.5 bg-nier-dark hidden lg:block" />
          <h1 className="nier-title text-sm tracking-[0.18em]">WATCHLIST_UNIT</h1>
        </div>
        <div className="text-xs tracking-widest uppercase font-medium text-right opacity-80">
          [ WATCHING:{' '}
          <span className="text-nier-orange">{watchlist.ids.length}</span>
          {' / '}
          {WATCHLIST_MAX} ]
        </div>
      </header>

      <div className="nier-dashboard-stack max-w-[90rem] mx-auto">
        <div className="watchlist-toolbar">
          <p className="watchlist-copy">
            Local browser list with shared screening thresholds. Alerts fire when a
            signal flips vs the last visit. Cleared if you wipe site data.
          </p>
          <div className="flex gap-2 flex-wrap">
            {companies.length > 0 && (
              <button type="button" className="nier-btn text-xs" onClick={exportCsv}>
                EXPORT CSV
              </button>
            )}
            {watchlist.ids.length > 0 && (
              <button type="button" className="nier-btn text-xs" onClick={onClearAll}>
                CLEAR WATCHLIST
              </button>
            )}
          </div>
        </div>

        <div className="nier-filter-bar" role="group" aria-label="Watchlist thresholds">
          <ThresholdInput
            label="P/E MAX"
            hint="blank = 22"
            value={draftThresholds.peMax}
            onChange={(v) => setDraftThresholds((p) => ({ ...p, peMax: v }))}
          />
          <ThresholdInput
            label="P/B MAX"
            hint="blank = 1"
            value={draftThresholds.pbMax}
            onChange={(v) => setDraftThresholds((p) => ({ ...p, pbMax: v }))}
          />
          <ThresholdInput
            label="ROE MIN %"
            hint="blank = 10"
            value={draftThresholds.roeMin}
            onChange={(v) => setDraftThresholds((p) => ({ ...p, roeMin: v }))}
          />
          <ThresholdInput
            label="YIELD MIN %"
            hint="blank = no yield alert"
            value={draftThresholds.yieldMin}
            onChange={(v) => setDraftThresholds((p) => ({ ...p, yieldMin: v }))}
          />
          <ThresholdInput
            label="ROIC MIN %"
            hint="blank = any"
            value={draftThresholds.roicMin}
            onChange={(v) => setDraftThresholds((p) => ({ ...p, roicMin: v }))}
          />
          <ThresholdInput
            label="D/E MAX"
            hint="blank = 2"
            value={draftThresholds.deMax}
            onChange={(v) => setDraftThresholds((p) => ({ ...p, deMax: v }))}
          />
          <div className="nier-filter-actions">
            <button type="button" className="nier-btn" onClick={applyThresholds}>
              APPLY
            </button>
          </div>
          {thresholdError && (
            <p className="nier-filter-error" role="alert">
              {thresholdError}
            </p>
          )}
        </div>

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
                className="nier-btn text-xs"
                disabled={comparePicks.length < 2}
                onClick={onOpenCompare}
              >
                OPEN COMPARE
              </button>
              <button type="button" className="nier-btn text-xs" onClick={onClearCompare}>
                CLEAR
              </button>
            </div>
          </div>
        )}

        {!alertsDismissed && alertEvents.length > 0 && (
          <div className="watchlist-alerts" role="status">
            <div className="watchlist-alerts-head">
              <span className="watchlist-alerts-title">
                {alertEvents.length} WATCHLIST ALERT
                {alertEvents.length === 1 ? '' : 'S'}
              </span>
              <button
                type="button"
                className="nier-btn px-2 py-0.5 text-[10px]"
                onClick={() => setAlertsDismissed(true)}
              >
                DISMISS
              </button>
            </div>
            <ul className="watchlist-alerts-list">
              {alertEvents.map((ev) => (
                <li key={`${ev.id}-${ev.kind}-${ev.from}-${ev.to}`}>{ev.text}</li>
              ))}
            </ul>
          </div>
        )}

        {missingIds.length > 0 && (
          <p className="watchlist-warn" role="status">
            {missingIds.length} watched id(s) not in the database; pruned from the list
            when possible.
          </p>
        )}

        <div className="nier-table-container">
          <table className="nier-table">
            <caption className="sr-only">
              Watchlist companies. Open a row for the full report.
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
                <th scope="col">D/E</th>
                <th scope="col">SECTOR</th>
                <th scope="col">CHECKS</th>
                <th scope="col">DILUTION</th>
                <th scope="col">INCOMPLETE</th>
                <th scope="col">
                  <span className="sr-only">Remove</span>
                </th>
              </tr>
            </thead>
            <tbody className="text-xs tracking-wider uppercase">
              {status === 'empty' && (
                <tr>
                  <td colSpan={12} className="text-center opacity-50 py-12 tracking-widest">
                    WATCHLIST_EMPTY. Star a ticker in the registry to pin it here.
                  </td>
                </tr>
              )}
              {status === 'loading' && (
                <tr>
                  <td
                    colSpan={12}
                    className="text-center opacity-50 py-12 tracking-widest"
                    role="status"
                  >
                    LOADING_WATCHLIST...
                  </td>
                </tr>
              )}
              {status === 'error' && (
                <tr>
                  <td
                    colSpan={12}
                    className="text-center py-12 tracking-widest text-nier-orange"
                    role="alert"
                  >
                    LINK_FAILURE: {error || 'UNABLE_TO_REACH_API'}
                  </td>
                </tr>
              )}
              {status === 'ready' &&
                companies.map((company) => {
                  const ticker = company.ticker || company.symbol;
                  const tier = company.cap_tier || marketCapTier(company.market_cap);
                  const checksLabel =
                    company.check_pass_count != null && company.check_evaluable_total != null
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
                  return (
                    <tr
                      key={company.id}
                      className={[
                        'transition-colors duration-150 hover:bg-nier-dark/10',
                        company.passes_screen ? 'nier-row-qualified' : '',
                        inCompare ? 'nier-row-compare' : '',
                      ]
                        .filter(Boolean)
                        .join(' ')}
                    >
                      <td className="nier-check-col">
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
                          onClick={() => onOpen(company.id)}
                        >
                          {ticker}
                        </button>
                      </td>
                      <td>{company.name}</td>
                      <td className="font-mono whitespace-nowrap">
                        {formatPrice(company.last_traded_price)}
                      </td>
                      <td className="whitespace-nowrap">
                        <span className="font-mono">{formatMarketCap(company.market_cap)}</span>
                        {tier && (
                          <span className={`nier-cap-tier nier-cap-tier--${tier.toLowerCase()}`}>
                            {tier}
                          </span>
                        )}
                      </td>
                      <td className="font-mono whitespace-nowrap">
                        {formatPct(company.div_yield)}
                      </td>
                      <td className="font-mono whitespace-nowrap">
                        {company.debt_to_equity != null
                          ? Number(company.debt_to_equity).toFixed(2)
                          : '—'}
                      </td>
                      <td>{company.sector || '—'}</td>
                      <td className="font-mono">{checksLabel}</td>
                      <td>{dil}</td>
                      <td>{company.info_incomplete ? 'YES' : '—'}</td>
                      <td>
                        <button
                          type="button"
                          className="nier-btn px-2 py-0.5 text-[10px]"
                          onClick={() => onRemove(company.id)}
                          aria-label={`Remove ${ticker} from watchlist`}
                        >
                          DROP
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
  );
}
