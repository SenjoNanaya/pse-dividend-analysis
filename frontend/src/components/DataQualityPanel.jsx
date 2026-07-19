import { formatDataWarning } from '../lib/metrics';

function roicModeLabel(mode) {
  if (mode === 'proper') return 'ROIC proper';
  if (mode === 'proxy') return 'ROIC proxy';
  if (mode === 'equity') return 'Capital return';
  if (mode === 'na') return 'Capital return n/a';
  return 'Return unknown';
}

function Mark({ ok, source, sourceLetter }) {
  const letter = source && sourceLetter ? sourceLetter[source] : null;
  const title = source ? `Source: ${source}` : ok ? 'Present' : 'Missing';
  return (
    <span
      className={`dq-mark ${ok ? 'report-check-pass' : 'report-check-na'}`}
      aria-label={title}
      title={title}
    >
      {ok ? (letter || '✓') : '—'}
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

const GRID_COLS_BANK = [
  { key: 'core', label: 'Core' },
  { key: 'loans', label: 'Loans' },
  { key: 'deposits', label: 'Dep' },
  { key: 'nii', label: 'NII' },
  { key: 'npl', label: 'NPL' },
  { key: 'allowance', label: 'ACL' },
  { key: 'equity', label: 'Equity' },
  { key: 'shares', label: 'Shares' },
];

export default function DataQualityPanel({ quality, compact = false }) {
  if (!quality) return null;

  const { summary, yearCount } = quality;
  const bankMode = Boolean(quality.bankMode || quality.roicMode === 'equity');
  const gridCols = bankMode ? GRID_COLS_BANK : GRID_COLS;
  const status = quality.incomplete ? 'INCOMPLETE' : 'COMPLETE';
  const statusCls = quality.incomplete ? 'dq-status-bad' : 'dq-status-ok';

  const missing =
    Array.isArray(quality.incompleteReasons) && quality.incompleteReasons.length > 0
      ? quality.incompleteReasons.join(', ')
      : null;
  const warn =
    Array.isArray(quality.dataWarnings) && quality.dataWarnings.length > 0
      ? quality.dataWarnings.map(formatDataWarning).join('; ')
      : null;
  const letters = quality.sourceLetter || {};

  if (compact) {
    return (
      <div className="dq-panel dq-panel-compact" aria-label="Data quality">
        <div className="dq-compact-row">
          <span className={`dq-status ${statusCls}`}>{status}</span>
          <span className="dq-meta">{roicModeLabel(quality.roicMode)}</span>
        </div>
        {missing && (
          <div className="dq-compact-counts dq-missing nier-msg-plain">Missing: {missing}</div>
        )}
        {warn && (
          <div className="dq-compact-counts dq-warn nier-msg-plain">Warning: {warn}</div>
        )}
        <details className="dq-compact-detail">
          <summary>Data detail</summary>
          <div className="dq-compact-counts">
            CORE {summary.coreYears}/{yearCount} yrs
            {' · '}
            {bankMode ? (
              <>
                LOANS {summary.withLoans ?? 0}
                {' · '}
                NII {summary.withNii ?? 0}
                {' · '}
                NPL {summary.withNpl ?? 0}
              </>
            ) : (
              <>CASH {summary.withCash}</>
            )}
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
        </details>
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
        <p className="dq-missing-line nier-msg-plain" role="status">
          Missing: {missing}
        </p>
      )}
      {warn && (
        <p className="dq-warn-line nier-msg-plain" role="status">
          Warning: {warn}
        </p>
      )}

      {quality.coverage.length === 0 ? (
        <div className="dq-empty nier-msg-plain">No yearly financial figures on file for this company.</div>
      ) : (
        <details className="dq-grid-disclosure" open={quality.incomplete || undefined}>
          <summary>Year coverage</summary>
          <div className="dq-table-wrap">
            <table className="dq-table">
              <thead>
                <tr>
                  <th scope="col">Year</th>
                  {gridCols.map((c) => (
                    <th key={c.key} scope="col">{c.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[...quality.coverage].reverse().map((row) => (
                  <tr key={row.year}>
                    <th scope="row">{row.year}</th>
                    {gridCols.map((c) => (
                      <td key={c.key}>
                        <Mark
                          ok={Boolean(row[c.key])}
                          source={row.sources?.[c.key]}
                          sourceLetter={letters}
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {Array.isArray(quality.provenanceHints) && quality.provenanceHints.length > 0 && (
            <p className="dq-provenance-line dq-muted">
              {quality.provenanceHints.join(' · ')}
            </p>
          )}
          <p className="dq-footnote report-note--section">
            Coverage from stored financials. Cell letters: H html, P pdf, B backfill,
            D derived, F Form 17-C, R disclosure ratios. Hover a mark for the full tag.
          </p>
        </details>
      )}
    </section>
  );
}
