import { useEffect, useState } from 'react';
import {
  buildReport,
  formatMarketCap,
  formatPct,
  formatPrice,
  marketCapTier,
} from '../lib/metrics';

const API_BASE = 'http://127.0.0.1:8000/api/companies';
const jsonHeaders = { Accept: 'application/json' };

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
      {children}
    </td>
  );
}

export default function CompareView({ picks, onBack, onRemove, onOpen }) {
  const [reports, setReports] = useState([]);
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState(null);

  const pickKey = picks.map((p) => p.id).join(',');

  useEffect(() => {
    if (!picks.length) {
      setReports([]);
      setStatus('idle');
      return undefined;
    }

    let cancelled = false;
    setStatus('loading');
    setError(null);

    Promise.all(
      picks.map((p) =>
        fetch(`${API_BASE}/${p.id}/`, { headers: jsonHeaders }).then(async (res) => {
          if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
          return res.json();
        }),
      ),
    )
      .then((companies) => {
        if (cancelled) return;
        setReports(companies.map((c) => buildReport(c)));
        setStatus('ready');
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.message || 'Failed to load comparison');
        setStatus('error');
      });

    return () => { cancelled = true; };
  }, [pickKey]); // eslint-disable-line react-hooks/exhaustive-deps -- pick ids only

  if (status === 'loading' || status === 'idle') {
    return (
      <div className="compare-page compare-loading">
        LOADING_COMPARE_MATRIX...
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="compare-page compare-loading">
        <p>COMPARE_RETRIEVAL_FAILURE: {error}</p>
        <button type="button" className="nier-btn mt-4" onClick={onBack}>
          &lt; REGISTRY
        </button>
      </div>
    );
  }

  const peBest = bestIndex(reports.map((r) => r.ratios.pe), 'min');
  const pbBest = bestIndex(reports.map((r) => r.ratios.pb), 'min');
  const roeBest = bestIndex(reports.map((r) => r.ratios.roe), 'max');
  const yieldBest = bestIndex(reports.map((r) => r.divYield), 'max');
  const checksBest = bestIndex(
    reports.map((r) => r.checklistScore?.pass ?? null),
    'max',
  );
  const bvCagrBest = bestIndex(reports.map((r) => r.growth.bookValue), 'max');
  const niCagrBest = bestIndex(reports.map((r) => r.growth.income), 'max');
  const asCagrBest = bestIndex(reports.map((r) => r.growth.assets), 'max');

  const checkLabels = reports[0]?.checklist?.map((c) => c.label) || [];

  return (
    <div className="compare-page animate-fade-in">
      <header className="compare-topbar">
        <div className="flex items-center gap-3">
          <button type="button" className="nier-btn px-3 py-1 text-xs" onClick={onBack}>
            &lt; REGISTRY
          </button>
          <h1 className="nier-title text-sm tracking-[0.18em]">
            COMPARE_MATRIX
          </h1>
        </div>
        <div className="text-xs tracking-widest uppercase font-medium opacity-70">
          [ {reports.length} UNITS ]
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

        <div className="compare-table-wrap">
          <table className="compare-table">
            <thead>
              <tr>
                <th>METRIC</th>
                {reports.map((r) => (
                  <th key={r.companyId}>{r.displayTicker}</th>
                ))}
              </tr>
            </thead>
            <tbody>
            <tr>
              <td>Price</td>
              {reports.map((r) => (
                <CompareCell key={r.companyId}>{formatPrice(r.price)}</CompareCell>
              ))}
            </tr>
            <tr>
              <td>Market Cap</td>
              {reports.map((r) => {
                const tier = r.capTier || marketCapTier(r.marketCap);
                return (
                  <CompareCell key={r.companyId}>
                    <span className="font-mono">{formatMarketCap(r.marketCap)}</span>
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
              <td>Div Yield</td>
              {reports.map((r, i) => (
                <CompareCell key={r.companyId} best={i === yieldBest}>
                  {formatPct(r.divYield)}
                </CompareCell>
              ))}
            </tr>
            <tr>
              <td>P/E</td>
              {reports.map((r, i) => (
                <CompareCell key={r.companyId} best={i === peBest}>
                  {formatRatio(r.ratios.pe)}
                </CompareCell>
              ))}
            </tr>
            <tr>
              <td>P/B</td>
              {reports.map((r, i) => (
                <CompareCell key={r.companyId} best={i === pbBest}>
                  {formatRatio(r.ratios.pb)}
                </CompareCell>
              ))}
            </tr>
            <tr>
              <td>ROE</td>
              {reports.map((r, i) => (
                <CompareCell key={r.companyId} best={i === roeBest}>
                  {formatPct(r.ratios.roe)}
                </CompareCell>
              ))}
            </tr>
            <tr>
              <td>Checks</td>
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
              <td>BV CAGR</td>
              {reports.map((r, i) => (
                <CompareCell key={r.companyId} best={i === bvCagrBest}>
                  {formatPct(r.growth.bookValue)}
                </CompareCell>
              ))}
            </tr>
            <tr>
              <td>Income CAGR</td>
              {reports.map((r, i) => (
                <CompareCell key={r.companyId} best={i === niCagrBest}>
                  {formatPct(r.growth.income)}
                </CompareCell>
              ))}
            </tr>
            <tr>
              <td>Assets CAGR</td>
              {reports.map((r, i) => (
                <CompareCell key={r.companyId} best={i === asCagrBest}>
                  {formatPct(r.growth.assets)}
                </CompareCell>
              ))}
            </tr>
            <tr>
              <td>Sector</td>
              {reports.map((r) => (
                <CompareCell key={r.companyId}>{r.sector || '—'}</CompareCell>
              ))}
            </tr>
            <tr>
              <td>Subsector</td>
              {reports.map((r) => (
                <CompareCell key={r.companyId}>{r.subsector || '—'}</CompareCell>
              ))}
            </tr>

            {checkLabels.map((label, rowIdx) => (
              <tr key={label} className="compare-check-row">
                <td>{label}</td>
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
        Orange highlight = best among the set (lowest P/E &amp; P/B; highest yield, ROE, checks, CAGRs).
        Click a ticker to open its full record.
      </p>
      </div>
    </div>
  );
}
