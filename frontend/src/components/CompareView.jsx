import { useEffect, useState } from 'react';
import CompareChart, { COMPARE_CHART_DEFS } from './CompareChart';
import {
  buildReport,
  formatMarketCap,
  formatPct,
  formatPrice,
  marketCapTier,
} from '../lib/metrics';
import { API_BASE, jsonHeaders } from '../lib/api';

function formatRatio(v, digits = 2) {
  if (v == null || !Number.isFinite(v)) return '—';
  return v.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function passMark(pass) {
  if (pass === true) return '✓';
  if (pass === false) return '✗';
  return '—';
}

function passLabel(pass) {
  if (pass === true) return 'Pass';
  if (pass === false) return 'Fail';
  return 'Not available';
}

function bestIndex(values, prefer = 'max') {
  let best = null;
  let bestIdx = -1;
  values.forEach((v, i) => {
    if (v == null || !Number.isFinite(v)) return;
    if (
      best == null
      || (prefer === 'max' ? v > best : v < best)
    ) {
      best = v;
      bestIdx = i;
    }
  });
  return bestIdx;
}

function CompareCell({ children, best = false }) {
  return (
    <td className={best ? 'compare-cell compare-cell--best' : 'compare-cell'}>
      {best && <span className="sr-only">Best: </span>}
      {children}
    </td>
  );
}

export default function CompareView({ picks, onBack, onRemove, onOpen, thresholds }) {
  const [reports, setReports] = useState([]);
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState(null);
  const [panel, setPanel] = useState('both'); // metrics | charts | both

  const pickKey = picks.map((p) => p.id).join(',');
  const thresholdKey = [
    thresholds?.peMax,
    thresholds?.pbMax,
    thresholds?.roeMin,
    thresholds?.deMax,
  ].join('|');

  useEffect(() => {
    if (!picks.length) {
      setReports([]);
      setStatus('idle');
      return undefined;
    }

    const ac = new AbortController();
    setStatus('loading');
    setError(null);

    Promise.all(
      picks.map((p) =>
        fetch(`${API_BASE}/${p.id}/`, { headers: jsonHeaders, signal: ac.signal }).then(async (res) => {
          if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
          return res.json();
        }),
      ),
    )
      .then((companies) => {
        setReports(companies.map((c) => buildReport(c, thresholds)));
        setStatus('ready');
      })
      .catch((err) => {
        if (err.name === 'AbortError') return;
        setError(err.message || 'Failed to load comparison');
        setStatus('error');
      });

    return () => ac.abort();
  }, [pickKey, thresholdKey]); // eslint-disable-line react-hooks/exhaustive-deps -- pick ids + thresholds

  if (status === 'loading' || status === 'idle') {
    return (
      <main id="main-content" className="compare-page compare-loading" role="status" aria-live="polite">
        Loading comparison…
      </main>
    );
  }

  if (status === 'error') {
    return (
      <main id="main-content" className="compare-page compare-loading" role="alert">
        <p className="nier-msg-plain">Couldn&apos;t load the comparison.</p>
        <p className="nier-ink-muted text-xs normal-case tracking-normal mt-2 max-w-md text-center">
          Make sure Edge is running, then go back and try again.
        </p>
        <button type="button" className="nier-btn mt-4" onClick={onBack}>
          Back to list
        </button>
      </main>
    );
  }

  const peBest = bestIndex(reports.map((r) => r.ratios.pe), 'min');
  const pbBest = bestIndex(reports.map((r) => r.ratios.pb), 'min');
  const roeBest = bestIndex(reports.map((r) => r.ratios.roe), 'max');
  // Proxy ROIC must not win "best" against proper NOPAT-based ROIC
  const roicBest = bestIndex(
    reports.map((r) =>
      r.roicMeta?.mode === 'proper' ? r.ratios.roic : null,
    ),
    'max',
  );
  const yieldBest = bestIndex(reports.map((r) => r.divYield), 'max');
  const checksBest = bestIndex(
    reports.map((r) => r.checklistScore?.pass ?? null),
    'max',
  );
  const bvCagrBest = bestIndex(reports.map((r) => r.growth.bookValue), 'max');
  const niCagrBest = bestIndex(reports.map((r) => r.growth.income), 'max');
  const asCagrBest = bestIndex(reports.map((r) => r.growth.assets), 'max');
  const liabCagrBest = bestIndex(reports.map((r) => r.growth.liabilities), 'min');

  const checkLabels = reports[0]?.checklist?.map((c) => c.label) || [];
  const showMetrics = panel === 'metrics' || panel === 'both';
  const showCharts = panel === 'charts' || panel === 'both';

  return (
    <main id="main-content" className="compare-page animate-fade-in">
      <header className="compare-topbar">
        <div className="flex items-center gap-3 flex-wrap">
          <button type="button" className="nier-btn" onClick={onBack}>
            Back to list
          </button>
          <h1 className="nier-title compare-heading">
            COMPARE_MATRIX
          </h1>
        </div>
        <div
          className="compare-panel-toggle"
          role="tablist"
          aria-label="Compare view mode"
          onKeyDown={(e) => {
            const order = ['metrics', 'charts', 'both'];
            const idx = order.indexOf(panel);
            let next = null;
            if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
              next = order[(idx + 1) % order.length];
            } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
              next = order[(idx - 1 + order.length) % order.length];
            } else if (e.key === 'Home') {
              next = order[0];
            } else if (e.key === 'End') {
              next = order[order.length - 1];
            }
            if (!next) return;
            e.preventDefault();
            setPanel(next);
            requestAnimationFrame(() => {
              document.getElementById(`compare-tab-${next}`)?.focus();
            });
          }}
        >
          {[
            { id: 'metrics', label: 'METRICS', controls: 'compare-panel-metrics' },
            { id: 'charts', label: 'CHARTS', controls: 'compare-panel-charts' },
            { id: 'both', label: 'BOTH', controls: 'compare-panel-metrics compare-panel-charts' },
          ].map((opt) => (
            <button
              key={opt.id}
              type="button"
              id={`compare-tab-${opt.id}`}
              role="tab"
              aria-selected={panel === opt.id}
              aria-controls={opt.controls}
              tabIndex={panel === opt.id ? 0 : -1}
              className={panel === opt.id ? 'nier-btn compare-tab-active' : 'nier-btn'}
              onClick={() => setPanel(opt.id)}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </header>

      <div className="nier-rail">
        <div className="compare-tickers">
          {reports.map((r) => (
            <div key={r.companyId} className="compare-ticker-card">
              <button
                type="button"
                className="compare-ticker-name"
                onClick={() => onOpen?.(r.companyId)}
              >
                {r.displayTicker}
              </button>
              <div className="compare-ticker-company">{r.companyName}</div>
              {onRemove && (
                <button
                  type="button"
                  className="compare-ticker-remove"
                  onClick={() => onRemove(r.companyId)}
                  aria-label={`Remove ${r.displayTicker}`}
                >
                  ×
                </button>
              )}
            </div>
          ))}
        </div>

        {showMetrics && (
          <div
            id="compare-panel-metrics"
            role="tabpanel"
            aria-labelledby={panel === 'both' ? 'compare-tab-both' : 'compare-tab-metrics'}
          >
            <div className="compare-section-label">Metric Matrix</div>
            <div className="compare-table-wrap">
              <table className="compare-table">
                <thead>
                  <tr>
                    <th scope="col">METRIC</th>
                    {reports.map((r) => (
                      <th scope="col" key={r.companyId}>{r.displayTicker}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <th scope="row">Price</th>
                    {reports.map((r) => (
                      <CompareCell key={r.companyId}>{formatPrice(r.price)}</CompareCell>
                    ))}
                  </tr>
                  <tr>
                    <th scope="row">Market Cap</th>
                    {reports.map((r) => {
                      const tier = r.capTier || marketCapTier(r.marketCap);
                      return (
                        <CompareCell key={r.companyId}>
                          <span>{formatMarketCap(r.marketCap)}</span>
                          {tier && (
                            <span className={`nier-cap-tier nier-cap-tier--${tier.toLowerCase()}`}>
                              {tier}
                            </span>
                          )}
                        </CompareCell>
                      );
                    })}
                  </tr>
                  <tr>
                    <th scope="row">Div Yield</th>
                    {reports.map((r, i) => (
                      <CompareCell key={r.companyId} best={i === yieldBest}>
                        {formatPct(r.divYield)}
                      </CompareCell>
                    ))}
                  </tr>
                  <tr>
                    <th scope="row">P/E</th>
                    {reports.map((r, i) => (
                      <CompareCell key={r.companyId} best={i === peBest}>
                        {formatRatio(r.ratios.pe)}
                      </CompareCell>
                    ))}
                  </tr>
                  <tr>
                    <th scope="row">P/B</th>
                    {reports.map((r, i) => (
                      <CompareCell key={r.companyId} best={i === pbBest}>
                        {formatRatio(r.ratios.pb)}
                      </CompareCell>
                    ))}
                  </tr>
                  <tr>
                    <th scope="row">ROE</th>
                    {reports.map((r, i) => (
                      <CompareCell key={r.companyId} best={i === roeBest}>
                        {formatPct(r.ratios.roe)}
                      </CompareCell>
                    ))}
                  </tr>
                  <tr>
                    <th scope="row">ROIC / Cap. return</th>
                    {reports.map((r, i) => (
                      <CompareCell key={r.companyId} best={i === roicBest}>
                        {formatPct(r.ratios.roic)}
                        {r.roicMeta?.mode === 'proxy' ? (
                          <span className="compare-roic-mode"> (proxy)</span>
                        ) : null}
                        {r.roicMeta?.mode === 'equity' ? (
                          <span className="compare-roic-mode"> (capital return)</span>
                        ) : null}
                        {r.roicMeta?.mode === 'na' ? (
                          <span className="compare-roic-mode"> (n/a)</span>
                        ) : null}
                      </CompareCell>
                    ))}
                  </tr>
                  <tr>
                    <th scope="row">Checks</th>
                    {reports.map((r, i) => {
                      const score = r.checklistScore;
                      const label =
                        score != null ? `${score.pass}/${score.total}` : '—';
                      return (
                        <CompareCell key={r.companyId} best={i === checksBest}>
                          {label}
                          {r.passesScreen ? ' ✓' : ''}
                        </CompareCell>
                      );
                    })}
                  </tr>
                  <tr>
                    <th scope="row">BV CAGR</th>
                    {reports.map((r, i) => (
                      <CompareCell key={r.companyId} best={i === bvCagrBest}>
                        {formatPct(r.growth.bookValue)}
                      </CompareCell>
                    ))}
                  </tr>
                  <tr>
                    <th scope="row">Income CAGR</th>
                    {reports.map((r, i) => (
                      <CompareCell key={r.companyId} best={i === niCagrBest}>
                        {formatPct(r.growth.income)}
                      </CompareCell>
                    ))}
                  </tr>
                  <tr>
                    <th scope="row">Assets CAGR</th>
                    {reports.map((r, i) => (
                      <CompareCell key={r.companyId} best={i === asCagrBest}>
                        {formatPct(r.growth.assets)}
                      </CompareCell>
                    ))}
                  </tr>
                  <tr>
                    <th scope="row">Liab. CAGR</th>
                    {reports.map((r, i) => (
                      <CompareCell key={r.companyId} best={i === liabCagrBest}>
                        {formatPct(r.growth.liabilities)}
                      </CompareCell>
                    ))}
                  </tr>
                  <tr>
                    <th scope="row">Sector</th>
                    {reports.map((r) => (
                      <CompareCell key={r.companyId}>{r.sector || '—'}</CompareCell>
                    ))}
                  </tr>
                  <tr>
                    <th scope="row">Subsector</th>
                    {reports.map((r) => (
                      <CompareCell key={r.companyId}>{r.subsector || '—'}</CompareCell>
                    ))}
                  </tr>

                  {checkLabels.map((label, rowIdx) => (
                    <tr key={label} className="compare-check-row">
                      <th scope="row">{label}</th>
                      {reports.map((r) => (
                        <CompareCell key={r.companyId}>
                          <span
                            className={
                              r.checklist[rowIdx]?.pass === true
                                ? 'compare-pass'
                                : r.checklist[rowIdx]?.pass === false
                                  ? 'compare-fail'
                                  : 'compare-na'
                            }
                            aria-label={passLabel(r.checklist[rowIdx]?.pass)}
                          >
                            {passMark(r.checklist[rowIdx]?.pass)}
                          </span>
                        </CompareCell>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="compare-note">
              Orange marks the best in each row (lowest P/E, P/B, and liabilities growth; highest yield, ROE, proper ROIC, checks, and other growth rates).
              Proxy ROIC and bank equity-capital returns are shown for context but cannot win the ROIC highlight.
              Click a ticker to open its full record.
            </p>
          </div>
        )}

        {showCharts && (
          <section
            id="compare-panel-charts"
            className="compare-charts-section"
            role="tabpanel"
            aria-label="Chart comparison"
            aria-labelledby={panel === 'both' ? 'compare-tab-both' : 'compare-tab-charts'}
          >
            <div className="compare-section-label">Chart Compare — YoY</div>
            <p className="compare-note compare-note--tight">
              Each graph overlays the selected tickers on a shared timeline (same scale per metric).
            </p>
            <div className="compare-charts-grid">
              {COMPARE_CHART_DEFS.filter((def) => {
                if (def.key !== 'outstandingShares' && def.key !== 'roic') return true;
                const visKey = def.key;
                return reports.some((r) => r?.chartVisibility?.[visKey]);
              }).map((def) => (
                <CompareChart
                  key={def.key}
                  title={def.title}
                  reports={reports}
                  chartKey={def.key}
                />
              ))}
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
