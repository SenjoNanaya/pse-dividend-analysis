import { buildReport, checklistScore, formatPct, isFinancialSector } from '../lib/metrics';

export function CheckCell({ item, compact = false }) {
  let mark = 'NA';
  let cls = 'report-check-na';
  let state = 'Not available';
  if (item.pass === true) {
    mark = '✓';
    cls = 'report-check-pass';
    state = 'Pass';
  } else if (item.pass === false) {
    mark = '✗';
    cls = 'report-check-fail';
    state = 'Fail';
  }
  return (
    <div className={`report-check-row${compact ? ' report-check-row-compact' : ''}`}>
      <span className={`report-check-box ${cls}`} aria-label={state}>{mark}</span>
      <span>{item.label}</span>
    </div>
  );
}

export default function ChecklistPreview({
  company,
  report: reportProp,
  compact = false,
  showScore = true,
  showRatios = false,
  /** Score + fails first; full checklist behind disclosure. */
  failsFirst = false,
}) {
  const report = reportProp ?? (company ? buildReport(company) : null);
  if (!report) return null;

  // Show every slot (including NA) so the badge denominator matches the list.
  const checks = report.checklist || [];
  const score = checklistScore(checks);
  const naCount = checks.filter((item) => item.pass === null).length;
  const fails = checks.filter((item) => item.pass === false);
  const mid = Math.ceil(checks.length / 2);
  const leftChecks = checks.slice(0, mid);
  const rightChecks = checks.slice(mid);
  const bank = isFinancialSector({
    sector: report.sector,
    subsector: report.subsector,
  });

  const scoreRow = showScore && (
    <div className="report-score-row">
      <span className="report-score-badge">
        {score.pass}/{score.total} PASS
        {naCount > 0 ? ` · ${naCount} NA` : ''}
      </span>
      {showRatios && (
        <span className="report-ratio-strip">
          P/E {report.ratios.pe != null ? report.ratios.pe.toFixed(2) : '—'}
          {' · '}
          P/B {report.ratios.pb != null ? report.ratios.pb.toFixed(2) : '—'}
          {' · '}
          {bank ? (
            <>Cap. ret. {formatPct(report.ratios.roic)}</>
          ) : (
            <>
              D/E{' '}
              {report.ratios.debtEquity != null
                ? report.ratios.debtEquity.toFixed(2)
                : '—'}
            </>
          )}
          {' · '}
          ROE {formatPct(report.ratios.roe)}
        </span>
      )}
    </div>
  );

  const fullCols = (
    <div className="report-check-cols report-check-cols-preview">
      <div>
        {leftChecks.map((item) => (
          <CheckCell key={item.label} item={item} compact={compact} />
        ))}
      </div>
      <div>
        {rightChecks.map((item) => (
          <CheckCell key={item.label} item={item} compact={compact} />
        ))}
      </div>
    </div>
  );

  if (failsFirst) {
    return (
      <div className={`report-checklist-preview${compact ? ' report-checklist-preview-compact' : ''}`}>
        {scoreRow}
        {fails.length > 0 ? (
          <div className="report-check-fails">
            {fails.map((item) => (
              <CheckCell key={item.label} item={item} compact={compact} />
            ))}
          </div>
        ) : (
          <p className="report-check-all-pass nier-ink-muted nier-msg-plain">All evaluable checks passed</p>
        )}
        <details className="report-check-all">
          <summary>All checks</summary>
          {fullCols}
        </details>
      </div>
    );
  }

  return (
    <div className={`report-checklist-preview${compact ? ' report-checklist-preview-compact' : ''}`}>
      {scoreRow}
      {fullCols}
    </div>
  );
}
