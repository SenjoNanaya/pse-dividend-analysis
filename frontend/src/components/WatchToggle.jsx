import { watchToggleCopy } from '../lib/watchToggle';

/**
 * Watchlist membership toggle.
 * Table cells: ★/☆ under the WATCH header. Sheet/rail: showLabel adds Watch/Unwatch.
 */
export default function WatchToggle({
  ticker,
  watched = false,
  disabled = false,
  max,
  onClick,
  className = '',
  showLabel = false,
}) {
  const { ariaLabel, title } = watchToggleCopy(ticker, { watched, disabled, max });
  const verb = watched ? 'Unwatch' : 'Watch';
  return (
    <button
      type="button"
      className={`nier-watch-btn${watched ? ' nier-watch-btn--on' : ''}${
        showLabel ? ' nier-watch-btn--labeled' : ''
      }${className ? ` ${className}` : ''}`}
      disabled={disabled}
      onClick={onClick}
      aria-pressed={watched}
      aria-label={ariaLabel}
      title={title}
    >
      <span aria-hidden="true">{watched ? '★' : '☆'}</span>
      {showLabel ? (
        <span className="nier-watch-btn-label" aria-hidden="true">
          {verb}
        </span>
      ) : null}
    </button>
  );
}
