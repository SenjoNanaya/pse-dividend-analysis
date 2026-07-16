"""Google News RSS fetch/parse for PSE tickers (server-side proxy)."""
from __future__ import annotations

import base64
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (compatible; PSEAnalysisBot/1.0; +https://github.com/SenjoNanaya/pse-dividend-analysis)"
)
CACHE_TTL_SECONDS = 20 * 60
MAX_ITEMS = 10
FETCH_TIMEOUT = 12
UNWRAP_TIMEOUT = 4
# Tickers this short are common English words / noisy in Google News
AMBIGUOUS_TICKER_LEN = 3

_PH_MARKERS = (
    "pse",
    "philippines",
    "philippine",
    "manila",
    "edge.pse",
)


def _short_company_name(name: str | None) -> str:
    n = (name or "").strip()
    if not n:
        return ""
    short = re.sub(
        r"\b(Inc\.?|Corporation|Corp\.?|Company|Co\.?|Plc\.?|Holdings|Group|Limited|Ltd\.?)\b\.?",
        "",
        n,
        flags=re.I,
    )
    short = re.sub(r"\s+", " ", short).strip(" ,.-")
    return short or n


def _is_ambiguous_ticker(ticker: str | None) -> bool:
    t = (ticker or "").strip()
    return bool(t) and len(t) <= AMBIGUOUS_TICKER_LEN


def build_queries(ticker: str | None, name: str | None) -> list[str]:
    """
    Primary (+ optional secondary) Google News queries.

    Short tickers (SM, T, X, …) are constrained with company name and PSE/PH cues.
    """
    t = (ticker or "").strip().upper()
    short = _short_company_name(name)
    ambiguous = _is_ambiguous_ticker(t)
    queries: list[str] = []

    if ambiguous:
        if short:
            queries.append(
                f'("{t}" OR "{t}:PSE" OR "{t} PSE") "{short}" '
                f'(PSE OR Philippines OR "stock exchange" OR shares)'
            )
            queries.append(
                f'"{short}" (PSE OR Philippines) (stock OR shares OR dividend OR IPO)'
            )
        else:
            queries.append(
                f'("{t}:PSE" OR "{t} PSE") (Philippines OR PSE) (stock OR shares)'
            )
    else:
        parts: list[str] = []
        if t:
            parts.append(f'("{t}" OR "{t}:PSE" OR "{t} PSE")')
        if short and short.upper() != t:
            parts.append(f'"{short}"')
        elif name and (name or "").strip().upper() != t:
            parts.append(f'"{(name or "").strip()}"')
        core = " OR ".join(parts) if parts else '"Philippine Stock Exchange"'
        queries.append(f"({core}) (PSE OR Philippines OR Philippine)")

    # Deduplicate while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out or ['"Philippine Stock Exchange" stock']


def _source_from_title(title: str) -> tuple[str, str]:
    """Google often appends ' - Source' to titles."""
    if " - " in title:
        head, src = title.rsplit(" - ", 1)
        if 0 < len(src) <= 80:
            return head.strip(), src.strip()
    return title.strip(), ""


def _parse_published(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, IndexError):
        return raw


def _parse_rss(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    if channel is None:
        return []
    items: list[dict[str, Any]] = []
    for item in channel.findall("item"):
        title_raw = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title_raw or not link:
            continue
        title, source = _source_from_title(title_raw)
        source_el = item.find("source")
        if source_el is not None and (source_el.text or "").strip():
            source = source_el.text.strip()
        published = _parse_published(item.findtext("pubDate"))
        items.append(
            {
                "title": title,
                "link": link,
                "published": published,
                "source": source or urlparse(link).netloc or "News",
            }
        )
    return items


_BAD_UNWRAP_HOST_PARTS = (
    "news.google.",
    "google.com",
    "googleusercontent.com",
    "gstatic.com",
    "googleapis.com",
    "ggpht.com",
)


def _is_plausible_publisher_url(cand: str) -> bool:
    try:
        parsed = urlparse(cand)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.netloc or "").lower()
    if not host or "." not in host:
        return False
    if any(b in host for b in _BAD_UNWRAP_HOST_PARTS):
        return False
    # Prefer real article paths over bare CDN roots
    return True


def _decode_google_article_id(url: str) -> str | None:
    """Best-effort extract publisher URL embedded in /articles/BASE64 ids."""
    m = re.search(r"/articles/([A-Za-z0-9_\-:]+)", url)
    if not m:
        return None
    raw = m.group(1)
    pad = "=" * ((4 - len(raw) % 4) % 4)
    try:
        decoded = base64.urlsafe_b64decode(raw + pad)
    except Exception:
        return None
    text = decoded.decode("latin-1", errors="ignore")
    found = re.findall(r"https?://[^\x00-\x08\x0b\x0c\x0e-\x1f]+", text)
    candidates: list[str] = []
    for cand in found:
        cand = cand.rstrip("\\").rstrip()
        cand = re.split(r"[\x00-\x1f]", cand, maxsplit=1)[0]
        # Truncate at common binary/trailer markers
        cand = re.split(r"[\"'<>\s]", cand, maxsplit=1)[0]
        if _is_plausible_publisher_url(cand):
            candidates.append(cand)
    if not candidates:
        return None
    # Prefer longer paths (article URLs over bare domains)
    candidates.sort(key=lambda u: (len(urlparse(u).path), len(u)), reverse=True)
    return candidates[0]


def unwrap_google_news_url(link: str, *, allow_http: bool = False) -> str:
    """
    Resolve news.google.com RSS/article redirects to publisher URLs when possible.

    Fast path: query-param + article-id decode (no network).
    Optional HTTP follow is slow — used sparingly by the batch unwraper.
    """
    if not link or "news.google.com" not in link.lower():
        return link

    qs = parse_qs(urlparse(link).query)
    for key in ("url", "q", "continue"):
        vals = qs.get(key) or []
        if vals and str(vals[0]).startswith("http"):
            return unquote(str(vals[0]))

    decoded = _decode_google_article_id(link)
    if decoded:
        return decoded

    if not allow_http:
        return link

    try:
        resp = requests.get(
            link,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"},
            timeout=UNWRAP_TIMEOUT,
            allow_redirects=True,
        )
        final = resp.url or link
        if final and "news.google.com" not in final.lower():
            return final
        m = re.search(
            r'href=["\'](https?://(?!news\.google\.com)[^"\']+)["\']',
            resp.text or "",
            flags=re.I,
        )
        if m:
            return unquote(m.group(1))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Google News unwrap failed for %s: %s", link[:80], exc)

    return link


def _normalize_title(title: str) -> str:
    t = re.sub(r"\s+", " ", (title or "").lower()).strip()
    t = re.sub(r"[^\w\s]", "", t)
    return t


def _ticker_in_text(ticker: str, text: str) -> bool:
    if not ticker:
        return False
    return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(ticker)}(?![A-Za-z0-9])", text, flags=re.I))


def relevance_score(
    item: dict[str, Any],
    *,
    ticker: str | None,
    name: str | None,
) -> int:
    """Higher = more likely about this PSE issuer."""
    blob = f"{item.get('title') or ''} {item.get('source') or ''} {item.get('link') or ''}"
    score = 0
    t = (ticker or "").strip()
    short = _short_company_name(name)
    if t and _ticker_in_text(t, blob):
        score += 3
        if re.search(rf"{re.escape(t)}\s*:?\s*PSE|{re.escape(t)}\s+PSE", blob, flags=re.I):
            score += 2
    if short and len(short) >= 4 and short.lower() in blob.lower():
        score += 4
    elif name and len((name or "").strip()) >= 6 and (name or "").strip().lower() in blob.lower():
        score += 3
    low = blob.lower()
    if any(m in low for m in _PH_MARKERS):
        score += 1
    return score


def item_is_relevant(
    item: dict[str, Any],
    *,
    ticker: str | None,
    name: str | None,
) -> bool:
    """
    Drop obvious off-ticker noise. Ambiguous short tickers require an identity hit
    (ticker or company name) in the headline/source/link.
    """
    t = (ticker or "").strip()
    short = _short_company_name(name)
    blob = f"{item.get('title') or ''} {item.get('source') or ''} {item.get('link') or ''}"
    has_ticker = bool(t) and _ticker_in_text(t, blob)
    has_name = bool(short) and len(short) >= 4 and short.lower() in blob.lower()
    score = relevance_score(item, ticker=ticker, name=name)

    if _is_ambiguous_ticker(t):
        return (has_ticker or has_name) and score >= 3
    # Longer tickers: keep identity hits; also keep strong PH+name-less PSE hits with ticker
    if has_ticker or has_name:
        return True
    return score >= 4


def _fetch_rss_query(query: str) -> list[dict[str, Any]]:
    url = (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl=en-PH&gl=PH&ceid=PH:en"
    )
    resp = requests.get(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
        timeout=FETCH_TIMEOUT,
    )
    resp.raise_for_status()
    return _parse_rss(resp.text)


def _merge_items(batches: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    seen_links: set[str] = set()
    for batch in batches:
        for item in batch:
            key = _normalize_title(item.get("title") or "")
            link = (item.get("link") or "").strip()
            if key and key in seen_titles:
                continue
            if link and link in seen_links:
                continue
            if key:
                seen_titles.add(key)
            if link:
                seen_links.add(link)
            merged.append(item)
    return merged


def _apply_resolved_link(item: dict[str, Any], raw_link: str, resolved: str) -> dict[str, Any]:
    row = dict(item)
    row["link"] = resolved
    if resolved != raw_link:
        row["google_link"] = raw_link
        host = urlparse(resolved).netloc
        if host and (not row.get("source") or row["source"] == "News"):
            row["source"] = host.removeprefix("www.")
    return row


def _unwrap_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Local unwrap for all items; HTTP follow for at most a few unresolved links."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    out: list[dict[str, Any] | None] = [None] * len(items)
    need_http: list[tuple[int, str]] = []

    for i, item in enumerate(items):
        raw_link = item.get("link") or ""
        resolved = unwrap_google_news_url(raw_link, allow_http=False)
        if resolved != raw_link or "news.google.com" not in raw_link.lower():
            out[i] = _apply_resolved_link(item, raw_link, resolved)
        else:
            need_http.append((i, raw_link))

    # Bound latency: only a few HTTP follows, in parallel
    for i, raw_link in need_http[3:]:
        out[i] = _apply_resolved_link(items[i], raw_link, raw_link)
    need_http = need_http[:3]

    if need_http:
        with ThreadPoolExecutor(max_workers=3) as pool:
            futs = {
                pool.submit(unwrap_google_news_url, link, allow_http=True): (idx, link)
                for idx, link in need_http
            }
            for fut in as_completed(futs):
                idx, raw_link = futs[fut]
                try:
                    resolved = fut.result()
                except Exception:
                    resolved = raw_link
                out[idx] = _apply_resolved_link(items[idx], raw_link, resolved)

    return [row for row in out if row is not None]


def fetch_company_news(
    ticker: str | None,
    name: str | None,
    company_id: int,
    *,
    show_all: bool = False,
) -> dict[str, Any]:
    """
    Returns { query, queries, items, cached, filtered, hidden_count, ambiguous_ticker, error? }.

    Soft-fails: empty items + error message on failure.
    Cache stores the unfiltered unwrapped list; filtering is applied per request.
    """
    from django.core.cache import cache

    cache_key = f"company_news:v2:{company_id}"
    cached = cache.get(cache_key)

    queries = build_queries(ticker, name)
    ambiguous = _is_ambiguous_ticker(ticker)

    if cached is None:
        payload: dict[str, Any] = {
            "query": queries[0],
            "queries": queries,
            "items_all": [],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "ambiguous_ticker": ambiguous,
        }
        batches: list[list[dict[str, Any]]] = []
        errors: list[str] = []
        for q in queries:
            try:
                batches.append(_fetch_rss_query(q))
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc) or type(exc).__name__)
        merged = _merge_items(batches)
        # Cap before unwrap to bound latency
        merged = merged[: MAX_ITEMS * 2]
        try:
            merged = _unwrap_items(merged)
        except Exception as exc:  # noqa: BLE001
            logger.warning("News unwrap batch failed: %s", exc)
        # Rank by relevance then recency (published iso sorts lexicographically)
        merged.sort(
            key=lambda it: (
                relevance_score(it, ticker=ticker, name=name),
                it.get("published") or "",
            ),
            reverse=True,
        )
        payload["items_all"] = merged[: MAX_ITEMS * 2]
        if errors and not merged:
            payload["error"] = errors[0]
        cache.set(cache_key, payload, CACHE_TTL_SECONDS)
        raw = payload
        from_cache = False
    else:
        raw = cached
        from_cache = True

    items_all: list[dict[str, Any]] = list(raw.get("items_all") or [])
    if show_all:
        items = items_all[:MAX_ITEMS]
        hidden = 0
        filtered = False
    else:
        relevant = [
            it
            for it in items_all
            if item_is_relevant(it, ticker=ticker, name=name)
        ]
        items = relevant[:MAX_ITEMS]
        hidden = max(0, len(items_all) - len(relevant))
        filtered = True

    return {
        "query": raw.get("query") or (queries[0] if queries else ""),
        "queries": raw.get("queries") or queries,
        "items": items,
        "cached": from_cache,
        "fetched_at": raw.get("fetched_at"),
        "filtered": filtered,
        "hidden_count": hidden,
        "ambiguous_ticker": bool(raw.get("ambiguous_ticker", ambiguous)),
        **({"error": raw["error"]} if raw.get("error") else {}),
    }
