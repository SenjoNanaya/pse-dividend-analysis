import ChecklistPreview from './ChecklistPreview';
import DataQualityPanel from './DataQualityPanel';
import { buildReport, registryDataStatus } from '../lib/metrics';

function PreviewActions({
  company,
  onOpen,
  onClear,
  watched,
  watchDisabled,
  onToggleWatch,
  compact = false,
}) {
  return (
    <div className={`flex gap-2 flex-wrap${compact ? ' shrink-0' : ' mt-auto pt-2'}`}>
      <button
        type="button"
        className={`nier-btn nier-btn--compact${compact ? '' : ' grow'}`}
        onClick={() => onOpen(company.id)}
      >
        Open report
      </button>
      {onToggleWatch && (
        <button
          type="button"
          className={`nier-btn nier-btn--compact${watched ? ' nier-watch-btn--on' : ''}`}
          disabled={watchDisabled}
          onClick={() => onToggleWatch(company)}
          aria-pressed={watched}
          aria-label={watched ? 'Remove from watchlist' : 'Add to watchlist'}
          title={watched ? 'On watchlist' : 'Add to watchlist'}
        >
          {watched ? '★' : '☆'}
        </button>
      )}
      {onClear && (
        <button
          type="button"
          className="nier-btn nier-btn--compact"
          onClick={onClear}
          aria-label="Clear preview"
          title="Clear preview"
        >
          ×
        </button>
      )}
    </div>
  );
}

export default function RegistryPreview({
  company,
  status,
  onOpen,
  onClear,
  thresholds,
  watched = false,
  watchDisabled = false,
  onToggleWatch,
  onPreviewFirst,
  /** Optional strip above the checklist (e.g. watchlist alert text). */
  notice = null,
  emptyHint = 'Select a company to see why it passed screening.',
  variant = 'panel',
}) {
  const isBar = variant === 'bar';

  if (status === 'loading') {
    return (
      <div className={isBar ? 'nier-preview-bar' : 'nier-outer-box h-full'}>
        <div className={isBar ? 'nier-preview-bar-inner' : 'nier-inner-box p-4'}>
          <p className="text-xs nier-ink-muted py-2 text-center nier-msg-plain" role="status" aria-live="polite">
            Loading preview…
          </p>
        </div>
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className={isBar ? 'nier-preview-bar' : 'nier-outer-box h-full'}>
        <div className={isBar ? 'nier-preview-bar-inner' : 'nier-inner-box p-4'}>
          <p className="text-xs text-nier-orange py-2 text-center nier-msg-plain" role="alert">
            Couldn&apos;t load this preview. Select the row again, or open the full report.
          </p>
        </div>
      </div>
    );
  }

  if (!company) {
    return (
      <div className={isBar ? 'nier-preview-bar' : 'nier-outer-box h-full'}>
        <div
          className={
            isBar
              ? 'nier-preview-bar-inner nier-preview-bar-empty'
              : 'nier-inner-box p-4 flex flex-col justify-center items-center text-center min-h-48'
          }
        >
          <p className="text-xs nier-ink-muted mb-0 nier-msg-plain">
            {emptyHint}
          </p>
          {onPreviewFirst && (
            <button
              type="button"
              className="nier-btn nier-btn--compact mt-3"
              onClick={onPreviewFirst}
            >
              Preview first company
            </button>
          )}
        </div>
      </div>
    );
  }

  const report = buildReport(company, thresholds);
  const dq = registryDataStatus(company);
  const noticeEl = notice ? (
    <p className="nier-preview-notice nier-msg-plain" role="status">
      {notice}
    </p>
  ) : null;

  if (isBar) {
    return (
      <aside
        className="nier-preview-bar"
        aria-label={`Preview ${report.displayTicker}`}
      >
        <div className="nier-preview-bar-inner">
          <div className="nier-preview-bar-id">
            <div className="nier-preview-bar-ticker">{report.displayTicker}</div>
            <div className="nier-preview-bar-name" title={report.companyName}>
              {report.companyName}
            </div>
            <div className="nier-preview-bar-mcap">
              {report.marketCapLabel}
              {dq.level !== 'ok' && (
                <span
                  className={`nier-dq-chip nier-dq-chip--${dq.level} nier-preview-bar-dq`}
                  title={dq.title}
                >
                  {dq.label}
                </span>
              )}
            </div>
          </div>
          {noticeEl}
          <div className="nier-preview-bar-checks">
            <ChecklistPreview report={report} compact showRatios failsFirst />
          </div>
          <div className="nier-preview-bar-dq-panel">
            <DataQualityPanel quality={report.dataQuality} compact />
          </div>
          <PreviewActions
            company={company}
            onOpen={onOpen}
            onClear={onClear}
            watched={watched}
            watchDisabled={watchDisabled}
            onToggleWatch={onToggleWatch}
            compact
          />
        </div>
      </aside>
    );
  }

  return (
    <aside className="nier-outer-box h-full" aria-label={`Preview ${report.displayTicker}`}>
      <div className="nier-inner-box p-4 flex flex-col gap-4">
        <div className="flex justify-between items-start gap-2 border-b border-nier-dark/30 pb-3">
          <div className="min-w-0">
            <h2 className="text-2xl font-bold text-nier-orange tracking-wide m-0">
              {report.displayTicker}
            </h2>
            <div className="nier-proper-name text-xs nier-ink-muted mt-1 leading-snug">
              {report.companyName}
            </div>
          </div>
          <div className="text-right shrink-0">
            <div className="nier-meta tracking-widest">
              Market Cap
            </div>
            <div className="text-lg font-bold">{report.marketCapLabel}</div>
          </div>
        </div>

        {noticeEl}

        <div>
          <div className="nier-data-block-title">Why it passed</div>
          <ChecklistPreview report={report} compact showRatios failsFirst />
        </div>

        <DataQualityPanel quality={report.dataQuality} compact />

        <PreviewActions
          company={company}
          onOpen={onOpen}
          onClear={onClear}
          watched={watched}
          watchDisabled={watchDisabled}
          onToggleWatch={onToggleWatch}
        />
      </div>
    </aside>
  );
}
