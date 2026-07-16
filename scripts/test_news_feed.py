"""Unit tests for ticker news query / unwrap / relevance (no network)."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from api.news import (
    build_queries,
    item_is_relevant,
    relevance_score,
    unwrap_google_news_url,
    _decode_google_article_id,
)


def test_short_ticker_queries_are_constrained():
    qs = build_queries("SM", "SM Investments Corporation")
    assert qs
    assert any("SM Investments" in q or "SM Investment" in q for q in qs)
    assert any("PSE" in q or "Philippines" in q for q in qs)
    # Should not be a bare OR of ticker alone
    assert not any(q.strip() == '("SM") stock Philippines' for q in qs)


def test_long_ticker_query():
    qs = build_queries("JFC", "Jollibee Foods Corporation")
    assert len(qs) >= 1
    assert "JFC" in qs[0]
    assert "Philippines" in qs[0] or "PSE" in qs[0]


def test_relevance_filters_ambiguous_noise():
    ticker, name = "SM", "SM Investments Corporation"
    good = {
        "title": "SM Investments posts higher profit",
        "source": "BusinessWorld",
        "link": "https://www.bworldonline.com/sm-investments",
    }
    noise = {
        "title": "Why SMEs struggle with inventory in Texas",
        "source": "Some Blog",
        "link": "https://example.com/sme",
    }
    assert item_is_relevant(good, ticker=ticker, name=name)
    assert not item_is_relevant(noise, ticker=ticker, name=name)
    assert relevance_score(good, ticker=ticker, name=name) > relevance_score(
        noise, ticker=ticker, name=name
    )


def test_unwrap_query_param_and_passthrough():
    publisher = "https://www.philstar.com/business/2025/01/01/foo"
    wrapped = f"https://news.google.com/url?url={publisher}&sa=t"
    assert unwrap_google_news_url(wrapped) == publisher
    assert unwrap_google_news_url(publisher) == publisher


def test_decode_article_id_when_url_embedded():
    # Synthetic payload: base64 urlsafe of bytes containing a publisher URL
    import base64

    raw = (
        b"\x08\x13https://lh3.googleusercontent.com/img\x00"
        b"https://www.example.com/article/123\x00junk"
    )
    token = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    link = f"https://news.google.com/rss/articles/{token}?oc=5"
    decoded = _decode_google_article_id(link)
    assert decoded is not None
    assert decoded.startswith("https://www.example.com/")
    assert "googleusercontent" not in decoded


if __name__ == "__main__":
    test_short_ticker_queries_are_constrained()
    test_long_ticker_query()
    test_relevance_filters_ambiguous_noise()
    test_unwrap_query_param_and_passthrough()
    test_decode_article_id_when_url_embedded()
    print("ok")
