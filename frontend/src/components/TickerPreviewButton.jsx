import { handleTickerRowKeyDown } from '../lib/tableRowKeys';

/**
 * Named primary control for shortlist rows (preview / open).
 * Keeps Watch / Compare as sibling tab stops — not nested inside a focusable row.
 */
export default function TickerPreviewButton({
  id,
  ticker,
  companyName,
  onPreview,
  onOpen,
  describedBy,
  /** Desktop: double-click opens report. Off on narrow (use sheet Open report). */
  openOnDoubleClick = true,
}) {
  const label = companyName
    ? `Preview ${ticker}, ${companyName}`
    : `Preview ${ticker}`;
  const title = openOnDoubleClick
    ? `${label}. Double-click or O to open report.`
    : `${label}. Open report from the preview.`;

  return (
    <button
      type="button"
      id={id}
      className="nier-ticker-btn"
      aria-label={label}
      title={title}
      aria-keyshortcuts={openOnDoubleClick ? 'Enter Space o' : 'Enter Space'}
      aria-describedby={describedBy}
      onClick={(e) => {
        e.stopPropagation();
        onPreview();
      }}
      onDoubleClick={(e) => {
        if (!openOnDoubleClick) return;
        e.stopPropagation();
        onOpen();
      }}
      onKeyDown={(e) => handleTickerRowKeyDown(e, { onPreview, onOpen })}
    >
      {ticker}
    </button>
  );
}
