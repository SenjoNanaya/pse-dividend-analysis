import { buildReport, checklistScore, evaluableChecklist, formatPct } from '../lib/metrics';

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
}) {
  const report = reportProp ?? (company ? buildReport(company) : null);
  if (!report) return null;

  const evaluable = evaluableChecklist(report.checklist);
  const score = checklistScore(report.checklist);
  const mid = Math.ceil(evaluable.length / 2);
  const leftChecks = evaluable.slice(0, mid);
  const rightChecks = evaluable.slice(mid);

  return (
    <div className={`report-checklist-preview${compact ? ' report-checklist-preview-compact' : ''}`}>
      {showScore && (
        <div className="report-score-row">
          <span className="report-score-badge">
            {score.pass}/{score.total} PASS
          </span>
          {showRatios && (
            <span className="report-ratio-strip">
              P/E {report.ratios.pe != null ? report.ratios.pe.toFixed(2) : '—'}
              {' · '}
              P/B {report.ratios.pb != null ? report.ratios.pb.toFixed(2) : '—'}
              {' · '}
              ROE {formatPct(report.ratios.roe)}
            </span>
          )}
        </div>
      )}
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
    </div>
  );
}
