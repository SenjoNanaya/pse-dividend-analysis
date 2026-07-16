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

# Longer PSE codes that are also everyday English — "rock Philippines" ≠ ROCK
_ENGLISH_WORD_TICKERS = frozenset(
    {
        "ROCK",
        "HOME",
        "FOOD",
        "PURE",
        "PRIME",
        "WORLD",
        "SUN",
        "STAR",
        "LAND",
        "WATER",
        "POWER",
        "GOLD",
        "SILVER",
        "METRO",
        "DELTA",
        "ALPHA",
        "CROWN",
        "UNION",
        "PACIFIC",
        "GLOBAL",
        "FIRST",
        "NATIONAL",
        "CENTRAL",
        "VISTA",
        "CREST",
        "EDGE",
        "PLUS",
        "MAX",
        "NEXT",
        "OPEN",
        "TECH",
        "DATA",
        "MEDIA",
        "HOUSE",
        "PLACE",
        "POINT",
        "PORT",
        "CITY",
        "TOWN",
        "GREEN",
        "BLUE",
        "WHITE",
        "BLACK",
        "LIGHT",
        "NICKEL",
        "COPPER",
        "IRON",
        "COAL",
        "OIL",
        "GAS",
        "ENERGY",
        "MINING",
        "BANK",
        "TRUST",
        "LIFE",
        "CARE",
        "HEALTH",
        "PHONE",
        "LINK",
        "NET",
        "WEB",
        "APP",
        "NOW",
        "ALL",
        "ONE",
        "TOP",
        "BEST",
        "NEW",
        "OLD",
        "BIG",
        "ACE",
        "AIM",
        "ASK",
        "ATM",
        "BBC",
        "CEO",
        "CPI",
        "GDP",
        "IPO",
        "SEC",
        "PSE",  # meta — never treat alone as issuer identity in prose
    }
)

_PH_MARKERS = (
    "pse",
    "philippines",
    "philippine",
    "manila",
    "edge.pse",
)

# Quote / chart / screener pages — not articles (TradingView, Yahoo quote, …)
_NON_NEWS_HOST_FRAGMENTS = (
    "tradingview.com",
    "finance.yahoo.com",
    "finance.yahoo",
    "stocktwits.com",
    "seekingalpha.com/symbol",
    "markets.businessinsider.com/stocks",
    "marketwatch.com/investing/stock",
    "investing.com/equities",
    "simplywall.st",
    "tipranks.com/stocks",
    "gurufocus.com/stock",
    "finviz.com",
    "barchart.com",
    "cnbc.com/quotes",
    "bloomberg.com/quote",
    "wsj.com/market-data",
    "pse.tools",  # quote widgets if they leak in
)

_NON_NEWS_SOURCE_NAMES = (
    "tradingview",
    "yahoo finance",
    "stocktwits",
    "finviz",
    "barchart",
    "simply wall",
    "tipranks",
    "gurufocus",
)

# Headlines that are clearly quote/chart landing pages, not reporting
_NON_NEWS_TITLE_PATTERNS = (
    re.compile(r"\bstock price and chart\b", re.I),
    re.compile(r"\bprice and chart\b", re.I),
    re.compile(r"\bstock quote\b", re.I),
    re.compile(r"\blive quote\b", re.I),
    re.compile(r"\btechnical (analysis|chart)\b", re.I),
    re.compile(r"\bchart\s*[—\-–:]\s*pse\s*:", re.I),
)

# Team/sports coverage that shares brand names (San Miguel Beermen, etc.)
_SPORTS_NOISE_PATTERNS = (
    re.compile(r"\bPBA\b"),
    re.compile(r"\bUAAP\b"),
    re.compile(r"\bNCAA\b"),
    re.compile(r"\bNBA\b"),
    re.compile(r"\bFIBA\b"),
    re.compile(r"\bFIFA\b"),
    re.compile(r"\bMPBL\b"),
    re.compile(r"\bbasketball\b", re.I),
    re.compile(r"\bvolleyball\b", re.I),
    re.compile(r"\bfootball\b", re.I),
    re.compile(r"\bsoccer\b", re.I),
    re.compile(r"\bboxing\b", re.I),
    re.compile(r"\bolympics?\b", re.I),
    re.compile(r"\bbeermen\b", re.I),
    re.compile(r"\bgin.?kings\b", re.I),
    re.compile(r"\bhotshots\b", re.I),
    re.compile(r"\belasto.?painters\b", re.I),
    re.compile(r"\btnt\s+ka?tropa\b", re.I),
    re.compile(r"\bchampionship\b", re.I),
    re.compile(r"\bplayoffs?\b", re.I),
    re.compile(r"\binning[s]?\b", re.I),
)

_SPORTS_URL_FRAGMENTS = (
    "/sports/",
    "/sport/",
    "/pba/",
    "/basketball/",
    "/uaap/",
    "sports.",
)

# Corporate / markets cues — required to keep a sports-branded name hit
_BUSINESS_CUE_PATTERNS = (
    re.compile(r"\bdividend", re.I),
    re.compile(r"\bearnings?\b", re.I),
    re.compile(r"\brevenue\b", re.I),
    re.compile(r"\bprofit", re.I),
    re.compile(r"\bnet\s+income\b", re.I),
    re.compile(r"\bIPO\b"),
    re.compile(r"\bPSE\b"),
    re.compile(r"\bstock\s+exchange\b", re.I),
    re.compile(r"\bshares?\b", re.I),
    re.compile(r"\binvestor", re.I),
    re.compile(r"\bSEC\b"),
    re.compile(r"\b17-?[AC]\b", re.I),
    re.compile(r"\bcorporation\b", re.I),
    re.compile(r"\bconglomerate\b", re.I),
    re.compile(r"\bmarket\s+cap", re.I),
    re.compile(r"\bbuyback\b", re.I),
    re.compile(r"\bguidance\b", re.I),
    re.compile(r"\bquarter(?:ly)?\s+results?\b", re.I),
    re.compile(r"\bpeso", re.I),
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


# Trailing sector / legal qualifiers stripped when forming a brand stem
# (Filinvest Land → Filinvest; East West Banking → East West).
_TRAILING_NAME_NOISE = frozenset(
    {
        "land",
        "development",
        "banking",
        "bank",
        "power",
        "energy",
        "mining",
        "realty",
        "properties",
        "property",
        "reit",
        "resources",
        "ventures",
        "finance",
        "financial",
        "insurance",
        "investments",
        "investment",
        "international",
        "philippines",
        "philippine",
        "industrial",
        "industries",
        "manufacturing",
        "foods",
        "food",
        "petroleum",
        "water",
        "telecom",
        "telecommunications",
        "communications",
        "express",
        "airways",
        "shipping",
        "ports",
        "terminal",
        "terminals",
        "hotel",
        "hotels",
        "resort",
        "resorts",
        "entertainment",
        "and",
        "the",
        "of",
    }
)


def _alnum_key(s: str) -> str:
    """Lowercase letters+digits only — EastWest ≡ East West."""
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _brand_core_words(name: str | None) -> list[str]:
    """Short-name words with trailing sector qualifiers removed."""
    short = _short_company_name(name)
    words = short.split() if short else []
    core = list(words)
    while len(core) > 1 and core[-1].lower().rstrip(".") in _TRAILING_NAME_NOISE:
        core.pop()
    return core


def _brand_stem(name: str | None) -> str:
    """Compact brand for queries/matching (Filinvest, East West). Empty if weak."""
    core = _brand_core_words(name)
    if not core:
        return ""
    brand = " ".join(core)
    if len(_alnum_key(brand)) < 5:
        return ""
    short = _short_company_name(name)
    if short and _alnum_key(brand) == _alnum_key(short):
        return ""
    return brand


def _brand_phrases(name: str | None) -> list[str]:
    """
    Issuer phrases for headline matching (longest / most specific first).

    Handles EastWest vs 'East West Banking', and Filinvest vs 'Filinvest Land'.
    """
    short = _short_company_name(name)
    full = (name or "").strip()
    phrases: list[str] = []
    if short:
        phrases.append(short)
    if full and full.lower() != (short or "").lower():
        phrases.append(full)

    core = _brand_core_words(name)
    if core:
        brand = " ".join(core)
        phrases.append(brand)
        if len(core) >= 2:
            phrases.append("".join(core))
        lead = re.sub(r"[^A-Za-z0-9]+", "", core[0])
        if len(lead) >= 6:
            phrases.append(lead)
        # Short first word + second (East West → EastWest)
        if len(core) >= 2 and len(lead) <= 5:
            phrases.append(f"{core[0]} {core[1]}")
            phrases.append(f"{core[0]}{core[1]}")

    seen: set[str] = set()
    out: list[str] = []
    for p in phrases:
        key = _alnum_key(p)
        if len(key) < 5 or key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _is_ambiguous_ticker(ticker: str | None) -> bool:
    t = (ticker or "").strip().upper()
    if not t:
        return False
    if len(t) <= AMBIGUOUS_TICKER_LEN:
        return True
    return t in _ENGLISH_WORD_TICKERS


def _ticker_pse_qualified(ticker: str, text: str) -> bool:
    """True when ticker appears as a PSE symbol, not bare English prose."""
    if not ticker or not text:
        return False
    t = re.escape(ticker.strip().upper())
    return bool(
        re.search(
            rf"(?i)(?<![A-Za-z0-9]){t}\s*:?\s*PSE|PSE\s*:?\s*{t}"
            rf"|(?<![A-Za-z0-9]){t}\.(?:PS|PSE)\b",
            text,
        )
    )


def _ticker_in_text(ticker: str, text: str, *, strict: bool = False) -> bool:
    """
    Match ticker as a token. English-word / short tickers only count when
    PSE-qualified or as an ALL-CAPS token (avoids 'rock Philippines').
    """
    if not ticker or not text:
        return False
    t = ticker.strip().upper()
    if not t:
        return False
    if _ticker_pse_qualified(t, text):
        return True
    ambiguous = _is_ambiguous_ticker(t)
    if ambiguous or strict:
        # Require uppercase ticker token (headlines rarely shout the verb ROCK)
        return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(t)}(?![A-Za-z0-9])", text))
    return bool(
        re.search(rf"(?<![A-Za-z0-9]){re.escape(t)}(?![A-Za-z0-9])", text, flags=re.I)
    )


def _name_in_text(name: str | None, text: str) -> bool:
    """
    Company / brand hit in headline or metadata.

    Accepts spaced vs compacted forms (East West ↔ EastWest) and brand stems
    after dropping sector qualifiers (Filinvest Land → Filinvest). Requires a
    ≥5-character alphanumeric key so short tokens like SM alone never match.
    """
    blob = text or ""
    blob_l = blob.lower()
    blob_key = _alnum_key(blob)
    for phrase in _brand_phrases(name):
        if phrase.lower() in blob_l:
            return True
        key = _alnum_key(phrase)
        if key and key in blob_key:
            return True
    return False


def build_queries(ticker: str | None, name: str | None) -> list[str]:
    """
    Primary (+ optional secondary) Google News queries.

    Prefer the corporation name; never rely on bare Philippines + English-word ticker.
    """
    t = (ticker or "").strip().upper()
    short = _short_company_name(name)
    full = (name or "").strip()
    ambiguous = _is_ambiguous_ticker(t)
    queries: list[str] = []

    # Exclude common sports hijacks of conglomerate brand names (PBA teams, etc.)
    sports_excl = "-PBA -basketball -UAAP -Beermen -volleyball -FIFA -NBA"

    # Issuer-first query (always prefer legal / short name when available)
    stem = _brand_stem(name)
    if short and len(short) >= 4:
        queries.append(
            f'"{short}" (PSE OR "Philippine Stock Exchange" OR dividend OR earnings OR shares) '
            f"{sports_excl}"
        )
        # Brand stem when shorter than legal short name (Filinvest, East West)
        if stem:
            queries.append(
                f'"{stem}" (PSE OR dividend OR earnings OR shares OR bank OR property) '
                f"{sports_excl}"
            )
        if full and full.lower() != short.lower() and len(full) >= 8:
            queries.append(
                f'"{full}" (PSE OR dividend OR earnings OR "stock exchange") {sports_excl}'
            )
    elif full and len(full) >= 6:
        queries.append(
            f'"{full}" (PSE OR "Philippine Stock Exchange" OR dividend OR earnings) '
            f"{sports_excl}"
        )
    elif stem:
        queries.append(
            f'"{stem}" (PSE OR dividend OR earnings OR shares) {sports_excl}'
        )

    if ambiguous:
        # Only PSE-qualified ticker forms — never bare word + Philippines
        if t:
            queries.append(
                f'("{t}:PSE" OR "{t} PSE" OR "{t}.PS") '
                f'(stock OR shares OR dividend OR earnings OR corporation)'
            )
    else:
        if t:
            if short and short.upper() != t:
                queries.append(
                    f'("{t}:PSE" OR "{t} PSE" OR "{t}") "{short}" '
                    f'(stock OR shares OR dividend OR earnings)'
                )
            else:
                queries.append(
                    f'("{t}:PSE" OR "{t} PSE" OR "{t}") '
                    f'(PSE OR "stock exchange") (stock OR shares OR dividend)'
                )

    # Deduplicate while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out or ['"Philippine Stock Exchange" listed company']


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


def _has_business_cue(text: str) -> bool:
    return any(p.search(text or "") for p in _BUSINESS_CUE_PATTERNS)


def _is_sports_noise(item: dict[str, Any]) -> bool:
    """
    True for team/sports coverage that hijacks corporate brand names
    (e.g. PBA 'San Miguel sinks Macau' ≠ San Miguel Corporation finance).
    Kept only if a clear business/markets cue is also present.
    """
    title = item.get("title") or ""
    source = item.get("source") or ""
    link = (item.get("link") or "").lower()
    google = (item.get("google_link") or "").lower()
    blob = f"{title} {source}"
    url_blob = f"{link} {google}"

    sports_hit = any(p.search(blob) for p in _SPORTS_NOISE_PATTERNS)
    sports_hit = sports_hit or any(frag in url_blob for frag in _SPORTS_URL_FRAGMENTS)
    if not sports_hit:
        return False
    if _has_business_cue(blob) or _has_business_cue(url_blob):
        return False
    return True


def item_is_news_like(item: dict[str, Any]) -> bool:
    """
    False for quote/chart/screener landing pages (TradingView, Yahoo Finance
    quote URLs, 'Stock Price and Chart — PSE:ANS', etc.) and for sports/team
    pages that are not corporate finance coverage.
    """
    title = item.get("title") or ""
    source = (item.get("source") or "").strip().lower()
    link = (item.get("link") or "").strip().lower()
    google = (item.get("google_link") or "").strip().lower()
    host_blob = f"{link} {google}"

    for frag in _NON_NEWS_HOST_FRAGMENTS:
        if frag in host_blob:
            return False

    for name in _NON_NEWS_SOURCE_NAMES:
        if name in source:
            return False

    for pat in _NON_NEWS_TITLE_PATTERNS:
        if pat.search(title):
            return False

    if _is_sports_noise(item):
        return False

    return True


def relevance_score(
    item: dict[str, Any],
    *,
    ticker: str | None,
    name: str | None,
) -> int:
    """Higher = more likely about this PSE issuer. PH geography alone does not score."""
    if not item_is_news_like(item):
        return -100
    title = item.get("title") or ""
    blob = f"{title} {item.get('source') or ''} {item.get('link') or ''}"
    score = 0
    t = (ticker or "").strip().upper()
    short = _short_company_name(name)

    if t and _ticker_pse_qualified(t, blob):
        score += 5
    elif t and _ticker_in_text(t, blob, strict=_is_ambiguous_ticker(t)):
        # Bare ticker token — weak unless non-ambiguous
        score += 1 if _is_ambiguous_ticker(t) else 3

    if _name_in_text(name, blob):
        score += 5
    elif short and len(_alnum_key(short)) >= 5 and _alnum_key(short) in _alnum_key(title):
        score += 4

    # PH markers only reinforce an existing issuer identity hit
    if score > 0 and any(m in blob.lower() for m in _PH_MARKERS):
        score += 1
    return score


def item_is_relevant(
    item: dict[str, Any],
    *,
    ticker: str | None,
    name: str | None,
) -> bool:
    """
    Keep only items about this corporation.

    Requires issuer identity: company name, or PSE-qualified ticker, or (for
    non-English-word tickers) an ALL-CAPS / clear ticker token — never
    Philippines + verb collisions like 'rock Philippine politics'.
    """
    if not item_is_news_like(item):
        return False
    t = (ticker or "").strip().upper()
    title = item.get("title") or ""
    blob = f"{title} {item.get('source') or ''} {item.get('link') or ''}"

    has_name = _name_in_text(name, blob)
    has_pse_ticker = bool(t) and _ticker_pse_qualified(t, blob)
    has_ticker_token = bool(t) and _ticker_in_text(
        t, blob, strict=_is_ambiguous_ticker(t)
    )

    if _is_ambiguous_ticker(t):
        # English-word / short codes: name or PSE-qualified ticker only
        if has_name or has_pse_ticker:
            return relevance_score(item, ticker=ticker, name=name) >= 4
        return False

    # Distinct tickers (JFC, DNL, …): name, PSE form, or clear ticker token
    if has_name or has_pse_ticker or has_ticker_token:
        return relevance_score(item, ticker=ticker, name=name) >= 3
    return False


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

    cache_key = f"company_news:v5:{company_id}"
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

    items_all: list[dict[str, Any]] = [
        it for it in (raw.get("items_all") or []) if item_is_news_like(it)
    ]
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
