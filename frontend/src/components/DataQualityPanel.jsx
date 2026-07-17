function roicModeLabel(mode) {
  if (mode === 'proper') return 'ROIC proper';
  if (mode === 'proxy') return 'ROIC proxy';
  if (mode === 'equity') return 'Bank capital return';
  if (mode === 'na') return 'ROIC n/a';
  return 'ROIC unknown';
}

function Mark({ ok }) {
  return (
    <span
      className={`dq-mark ${ok ? 'report-check-pass' : 'report-check-na'}`}
      aria-label={ok ? 'Present' : 'Missing'}
    >
      {ok ? '✓' : '—'}
    </span>
  );
}

const GRID_COLS = [
  { key: 'core', label: 'Core' },
  { key: 'cash', label: 'Cash' },
  { key: 'cl', label: 'CL' },
  { key: 'oi', label: 'OI' },
  { key: 'equity', label: 'Equity' },
  { key: 'shares', label: 'Shares' },
];

export default function DataQualityPanel({ quality, compact = false }) {
  if (!quality) return null;

  const { summary, yearCount } = quality;
  const status = quality.incomplete ? 'INCOMPLETE' : 'COMPLETE';
  const statusCls = quality.incomplete ? 'dq-status-bad' : 'dq-status-ok';

  const missing =
    Array.isArray(quality.incompleteReasons) && quality.incompleteReasons.length > 0
      ? quality.incompleteReasons.join(', ')
      : null;

  if (compact) {
    return (
      <div className="dq-panel dq-panel-compact" aria-label="Data quality">
        <div className="nier-data-block-title">Data quality</div>
        <div className="dq-compact-row">
          <span className={`dq-status ${statusCls}`}>{status}</span>
          <span className="dq-meta">{roicModeLabel(quality.roicMode)}</span>
        </div>
        {missing && (
          <div className="dq-compact-counts dq-missing">MISSING: {missing}</div>
        )}
        <div className="dq-compact-counts">
          CORE {summary.coreYears}/{yearCount} yrs
          {' · '}
          CASH {summary.withCash}
          {' · '}
          SHARES {summary.withShares}
          {' · '}
          CHECK NA {quality.checklistNa}/{quality.checklistNa + quality.checklistEval}
        </div>
        {quality.cashDivYears > 0 && (
          <div className="dq-compact-counts dq-muted">
            CASH DIV YEARS {quality.cashDivYears}
          </div>
        )}
      </div>
    );
  }

  return (
    <section className="dq-panel" aria-label="Data quality">
      <h2 className="report-section-label">Data quality</h2>
      <div className="dq-full-header">
        <span className={`dq-status ${statusCls}`}>{status}</span>
        <span className="dq-meta">
          {roicModeLabel(quality.roicMode)}
          {quality.statementScope ? ` (${quality.statementScope})` : ''}
        </span>
        <span className="dq-meta">
          CHECK NA {quality.checklistNa}/{quality.checklistNa + quality.checklistEval}
        </span>
        <span className="dq-meta">CASH DIV YRS {quality.cashDivYears}</span>
      </div>
      {missing && (
        <p className="dq-missing-line" role="status">
          MISSING: {missing}
        </p>
      )}

      {quality.coverage.length === 0 ? (
        <div className="dq-empty">No fiscal-year financials stored.</div>
      ) : (
        <div className="dq-table-wrap">
          <table className="dq-table">
            <thead>
              <tr>
                <th scope="col">Year</th>
                {GRID_COLS.map((c) => (
                  <th key={c.key} scope="col">{c.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...quality.coverage].reverse().map((row) => (
                <tr key={row.year}>
                  <th scope="row">{row.year}</th>
                  {GRID_COLS.map((c) => (
                    <td key={c.key}>
                      <Mark ok={Boolean(row[c.key])} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="dq-footnote report-note--section">
        Coverage is from stored financials. PDF fill-nulls are already merged into
        those rows; field provenance is not tracked.
      </p>
    </section>
  );
}
