import { useRef } from 'react';
import ChecklistPreview from './ChecklistPreview';
import DataQualityPanel from './DataQualityPanel';
import WatchToggle from './WatchToggle';
import { buildReport, registryDataStatus } from '../lib/metrics';
import { WATCHLIST_MAX } from '../lib/watchlist';
import useFocusTrap from '../lib/useFocusTrap';

function PreviewActions({
  company,
  onOpen,
  onClear,
  watched,
  watchDisabled,
  onToggleWatch,
  compact = false,
  /** Sheet foot: primary Open report + secondary watch/clear. */
  sheet = false,
  initialFocus = false,
}) {
  const ticker = company?.ticker || company?.symbol || 'company';
  return (
    <div
      className={[
        'nier-preview-actions',
        sheet ? 'nier-preview-actions--sheet' : 'flex gap-2 flex-wrap',
        !sheet && compact ? 'shrink-0' : null,
        !sheet && !compact ? 'mt-auto pt-2' : null,
      ].filter(Boolean).join(' ')}
    >
      <button
        type="button"
        className={sheet ? 'nier-btn nier-btn--ink' : `nier-btn nier-btn--compact${compact ? '' : ' grow'}`}
        onClick={() => onOpen(company.id)}
        data-sheet-initial-focus={initialFocus ? '' : undefined}
      >
        Open report
      </button>
      {(onToggleWatch || onClear) && (
        <div className={sheet ? 'nier-preview-actions-secondary' : 'contents'}>
          {onToggleWatch && (
            <WatchToggle
              ticker={ticker}
              watched={watched}
              disabled={watchDisabled}
              max={WATCHLIST_MAX}
              showLabel={sheet}
              onClick={() => onToggleWatch(company)}
            />
          )}
          {onClear && (
            <button
              type="button"
              className="nier-btn nier-btn--compact"
              onClick={onClear}
              aria-label="Close preview"
              title="Close preview"
            >
              ×
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/** Modal bottom sheet: focus trap + restore on dismiss. */
function PreviewSheetShell({ label, onClear, children, live }) {
  const sheetRef = useRef(null);
  useFocusTrap(sheetRef, { active: true, onEscape: onClear });

  return (
    <aside
      ref={sheetRef}
      className="nier-preview-sheet"
      role="dialog"
      aria-modal="true"
      aria-label={label}
      aria-live={live}
    >
      <div className="nier-preview-sheet-handle" aria-hidden="true" />
      {children}
    </aside>
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
  /** Optional dismiss for the empty-state tip (Got it). */
  onDismissEmptyHint,
  /** Optional strip above the checklist (e.g. watchlist alert text). */
  notice = null,
  emptyHint = 'Click a row for why it passed.',
  variant = 'panel',
}) {
  const isBar = variant === 'bar';
  const isSheet = variant === 'sheet';
  const shellClass = isSheet
    ? 'nier-preview-sheet'
    : isBar
      ? 'nier-preview-bar'
      : 'nier-outer-box h-full';
  const innerClass = isSheet
    ? 'nier-preview-sheet-inner'
    : isBar
      ? 'nier-preview-bar-inner'
      : 'nier-inner-box p-4';

  if (status === 'loading') {
    if (isSheet) {
      return (
        <PreviewSheetShell label="Loading preview" onClear={onClear} live="polite">
          <div className={innerClass}>
            <p className="text-xs nier-ink-muted py-2 text-center nier-msg-plain">
              Loading preview…
            </p>
            {onClear && (
              <div className="nier-preview-sheet-actions">
                <button
                  type="button"
                  className="nier-btn nier-btn--compact"
                  onClick={onClear}
                  data-sheet-initial-focus=""
                >
                  Close
                </button>
              </div>
            )}
          </div>
        </PreviewSheetShell>
      );
    }
    return (
      <div className={shellClass} role="status" aria-live="polite">
        <div className={isBar ? 'nier-preview-bar-inner' : innerClass}>
          <p className="text-xs nier-ink-muted py-2 text-center nier-msg-plain">
            Loading preview…
          </p>
        </div>
      </div>
    );
  }

  if (status === 'error') {
    if (isSheet) {
      return (
        <PreviewSheetShell label="Preview unavailable" onClear={onClear}>
          <div className={innerClass}>
            <p className="text-xs text-nier-orange py-2 text-center nier-msg-plain" role="alert">
              Couldn&apos;t load this preview. Select the row again, or open the full report.
            </p>
            {onClear && (
              <div className="nier-preview-sheet-actions">
                <button
                  type="button"
                  className="nier-btn nier-btn--compact"
                  onClick={onClear}
                  data-sheet-initial-focus=""
                >
                  Close
                </button>
              </div>
            )}
          </div>
        </PreviewSheetShell>
      );
    }
    return (
      <div className={shellClass} role="alert">
        <div className={isBar ? 'nier-preview-bar-inner' : innerClass}>
          <p className="text-xs text-nier-orange py-2 text-center nier-msg-plain">
            Couldn&apos;t load this preview. Select the row again, or open the full report.
          </p>
        </div>
      </div>
    );
  }

  if (!company) {
    if (isSheet) return null;
    return (
      <div className={isBar ? 'nier-preview-bar' : 'nier-outer-box h-full'}>
        <div
          className={
            isBar
              ? 'nier-preview-bar-inner nier-preview-bar-empty'
              : 'nier-inner-box p-4 flex flex-col justify-center items-center text-center min-h-32'
          }
        >
          <div className="nier-preview-empty-row">
            <p className="nier-preview-empty-copy nier-msg-plain">
              {emptyHint}
            </p>
            {onDismissEmptyHint && (
              <button
                type="button"
                className="nier-btn nier-btn--compact nier-btn--quiet"
                onClick={onDismissEmptyHint}
              >
                Got it
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  const report = buildReport(company, thresholds);
  const dq = registryDataStatus(company);
  /** Sheet: only surface DQ when something needs attention (chip + disclosure). */
  const dqNeedsAttention = dq.level !== 'ok';
  const noticeEl = notice ? (
    <p className="nier-preview-notice nier-msg-plain" role="status">
      {notice}
    </p>
  ) : null;
  const dqChip = (extraClass = '') =>
    dqNeedsAttention ? (
      <span
        className={`nier-dq-chip nier-dq-chip--${dq.level}${extraClass ? ` ${extraClass}` : ''}`}
        title={dq.title}
        aria-label={`Data ${dq.label}: ${dq.title}`}
      >
        {dq.label}
      </span>
    ) : null;

  if (isSheet) {
    return (
      <PreviewSheetShell
        label={`Preview ${report.displayTicker}`}
        onClear={onClear}
      >
        <div className="nier-preview-sheet-inner">
          <div className="nier-preview-sheet-head">
            <div className="nier-preview-sheet-id">
              <div className="nier-preview-sheet-ticker">{report.displayTicker}</div>
              <div className="nier-preview-sheet-name" title={report.companyName}>
                {report.companyName}
              </div>
            </div>
            <div className="nier-preview-sheet-mcap">
              <span className="nier-meta">Mcap</span>
              <span className="font-bold">{report.marketCapLabel}</span>
              {dqChip()}
            </div>
          </div>
          {noticeEl}
          <div className="nier-preview-sheet-checks">
            <div className="nier-data-block-title">Why it passed</div>
            <ChecklistPreview report={report} compact showRatios={false} failsFirst />
          </div>
          {dqNeedsAttention ? (
            <details className="nier-preview-sheet-dq">
              <summary>
                Data quality
                <span className="nier-preview-sheet-dq-tag">{dq.label}</span>
              </summary>
              <DataQualityPanel quality={report.dataQuality} compact sheet />
            </details>
          ) : null}
        </div>
        <div className="nier-preview-sheet-actions">
          <PreviewActions
            company={company}
            onOpen={onOpen}
            onClear={onClear}
            watched={watched}
            watchDisabled={watchDisabled}
            onToggleWatch={onToggleWatch}
            sheet
            initialFocus
          />
        </div>
      </PreviewSheetShell>
    );
  }

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
              {dqChip('nier-preview-bar-dq')}
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
