import { useEffect, useState } from 'react';
import { API_BASE, jsonHeaders } from '../lib/api';

function formatNewsDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export default function TickerNews({
  companyId,
  ticker,
  /** Nested under a report disclosure — skip the duplicate section heading. */
  embedded = false,
}) {
  const [status, setStatus] = useState(companyId == null ? 'idle' : 'loading');
  const [items, setItems] = useState([]);
  const [error, setError] = useState(null);
  const [hiddenCount, setHiddenCount] = useState(0);
  const [showAll, setShowAll] = useState(false);
  const [ambiguous, setAmbiguous] = useState(false);
  const [retryTick, setRetryTick] = useState(0);

  useEffect(() => {
    setShowAll(false);
  }, [companyId]);

  useEffect(() => {
    if (companyId == null) {
      setStatus('idle');
      setItems([]);
      setError(null);
      setHiddenCount(0);
      setAmbiguous(false);
      return undefined;
    }

    let cancelled = false;
    setStatus('loading');
    setError(null);

    const qs = showAll ? '?all=1' : '';
    fetch(`${API_BASE}/${companyId}/news/${qs}`, { headers: jsonHeaders })
      .then(async (res) => {
        if (!res.ok) {
          throw new Error(
            res.status === 404
              ? "News isn't available right now. If Edge was just updated, restart it and open this company again."
              : "Couldn't load news for this ticker. Try again in a moment.",
          );
        }
        return res.json();
      })
      .then((data) => {
        if (cancelled) return;
        setItems(Array.isArray(data.items) ? data.items : []);
        setHiddenCount(Number(data.hidden_count) || 0);
        setAmbiguous(Boolean(data.ambiguous_ticker));
        if (data.error && !(data.items && data.items.length)) {
          setError(data.error);
          setStatus('error');
        } else {
          setStatus('ready');
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.message || "Couldn't load news for this ticker. Try again in a moment.");
        setItems([]);
        setHiddenCount(0);
        setStatus('error');
      });

    return () => { cancelled = true; };
  }, [companyId, showAll, retryTick]);

  return (
    <section className="report-news" aria-label={`News for ${ticker || 'selected ticker'}`}>
      {!embedded && <h2 className="report-section-label">News</h2>}
      <p className="report-note report-news-note">
        Optional depth after you shortlist — not a live feed. Headlines from Google News
        (Philippines); ones that don&apos;t clearly match this ticker are hidden
        {ambiguous ? ' (short tickers use a stricter match)' : ''}. Filings remain the source of
        truth. Links open in a new tab.
      </p>

      {status === 'idle' && (
        <div className="report-news-status nier-msg-plain" role="status">
          Select a company to see news.
        </div>
      )}

      {status === 'loading' && (
        <div className="report-news-status nier-msg-plain" role="status" aria-live="polite">
          Loading news…
        </div>
      )}

      {status === 'error' && (
        <div className="report-news-status nier-msg-plain" role="alert">
          <p className="report-news-error-detail">
            {error || "Couldn't load news for this ticker. Try again in a moment."}
          </p>
          <button
            type="button"
            className="nier-btn nier-btn--compact"
            onClick={() => setRetryTick((n) => n + 1)}
          >
            Retry
          </button>
        </div>
      )}

      {status === 'ready' && items.length === 0 && (
        <div className="report-news-status nier-msg-plain" role="status">
          {showAll || hiddenCount === 0
            ? 'No recent headlines found.'
            : `No closely matching headlines (${hiddenCount} less relevant hidden).`}
        </div>
      )}

      {status === 'ready' && items.length > 0 && (
        <ul className="report-news-list">
          {items.map((item) => (
            <li key={item.link} className="report-news-item">
              <a
                href={item.link}
                target="_blank"
                rel="noopener noreferrer"
                className="report-news-link"
              >
                {item.title}
              </a>
              <div className="report-news-meta">
                <span>{item.source || 'News'}</span>
                {item.published ? (
                  <>
                    <span aria-hidden="true"> · </span>
                    <time dateTime={item.published}>{formatNewsDate(item.published)}</time>
                  </>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}

      {status === 'ready' && !showAll && hiddenCount > 0 && (
        <button
          type="button"
          className="report-news-show-all"
          onClick={() => setShowAll(true)}
        >
          Show {hiddenCount} less relevant
        </button>
      )}

      {status === 'ready' && showAll && (
        <button
          type="button"
          className="report-news-show-all"
          onClick={() => setShowAll(false)}
        >
          Show relevant only
        </button>
      )}
    </section>
  );
}
