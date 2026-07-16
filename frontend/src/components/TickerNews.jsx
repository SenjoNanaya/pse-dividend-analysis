import { useEffect, useState } from 'react';

const API_BASE = 'http://127.0.0.1:8000/api/companies';
const jsonHeaders = { Accept: 'application/json' };

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

export default function TickerNews({ companyId, ticker, compact = false }) {
  const [status, setStatus] = useState(companyId == null ? 'idle' : 'loading');
  const [items, setItems] = useState([]);
  const [error, setError] = useState(null);
  const [hiddenCount, setHiddenCount] = useState(0);
  const [showAll, setShowAll] = useState(false);
  const [ambiguous, setAmbiguous] = useState(false);

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
          const hint =
            res.status === 404
              ? 'News 404 — restart Django so /api/companies/<id>/news/ is loaded'
              : `News ${res.status}`;
          throw new Error(hint);
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
        setError(err.message || 'Failed to load news');
        setItems([]);
        setHiddenCount(0);
        setStatus('error');
      });

    return () => { cancelled = true; };
  }, [companyId, showAll]);

  const sectionClass = compact ? 'report-news report-news--compact' : 'report-news';
  const heading = compact ? 'h3' : 'h2';
  const HeadingTag = heading;
  const visible = compact ? items.slice(0, 6) : items;

  return (
    <section className={sectionClass} aria-label={`News for ${ticker || 'selected ticker'}`}>
      <HeadingTag className="report-section-label">News Feed</HeadingTag>
      {!compact && (
        <p className="report-note report-news-note">
          Aggregated headlines via Google News RSS (Philippines). Off-ticker noise is
          filtered{ambiguous ? ' (short ticker — stricter match)' : ''}. External links open
          in a new tab.
        </p>
      )}

      {status === 'idle' && (
        <div className="report-news-status" role="status">
          SELECT_A_ROW_TO_LOAD_NEWS
        </div>
      )}

      {status === 'loading' && (
        <div className="report-news-status" role="status" aria-live="polite">
          RETRIEVING_COVERAGE_STREAM...
        </div>
      )}

      {status === 'error' && (
        <div className="report-news-status" role="alert">
          NEWS_FEED_UNAVAILABLE
          {error ? <span className="report-news-error-detail"> — {error}</span> : null}
        </div>
      )}

      {status === 'ready' && items.length === 0 && (
        <div className="report-news-status" role="status">
          {showAll || hiddenCount === 0
            ? 'NO_RECENT_HEADLINES_FOR_QUERY'
            : `NO_RELEVANT_HEADLINES (${hiddenCount} hidden)`}
        </div>
      )}

      {status === 'ready' && items.length > 0 && (
        <ul className="report-news-list">
          {visible.map((item) => (
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
