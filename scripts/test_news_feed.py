"""Unit tests for ticker news query / unwrap / relevance (no network)."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from api.news import (
    build_queries,
    item_is_news_like,
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
    # Issuer name leads; ticker appears in a PSE-qualified follow-up
    assert any("Jollibee" in q for q in qs)
    assert any("JFC" in q for q in qs)
    assert any("PSE" in q or "stock exchange" in q.lower() for q in qs)


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


def test_rejects_english_verb_ticker_collisions():
    """ROCK must not match 'rock Philippine politics' style headlines."""
    ticker, name = "ROCK", "Rockwell Land Corporation"
    politics = {
        "title": "Impeachment and a failed arrest rock Philippine politics",
        "source": "GZERO Media",
        "link": "https://www.gzeromedia.com/philippines-politics",
    }
    graft = {
        "title": "Protests over graft in flood control projects rock Philippines",
        "source": "ucanews.com",
        "link": "https://www.ucanews.com/news/philippines-graft",
    }
    sports = {
        "title": "Major player transfers continue to rock Philippine college basketball world",
        "source": "Sun.Star Cebu",
        "link": "https://www.sunstar.com.ph/cebu/basketball",
    }
    good = {
        "title": "Rockwell Land Corporation books higher rental income",
        "source": "BusinessWorld",
        "link": "https://www.bworldonline.com/rockwell-land",
    }
    good_pse = {
        "title": "ROCK:PSE rises on property sales",
        "source": "Philstar",
        "link": "https://www.philstar.com/business/rock-pse",
    }
    for bad in (politics, graft, sports):
        assert not item_is_relevant(bad, ticker=ticker, name=name), bad["title"]
    assert item_is_relevant(good, ticker=ticker, name=name)
    assert item_is_relevant(good_pse, ticker=ticker, name=name)


def test_short_ticker_queries_prefer_company_name():
    qs = build_queries("ROCK", "Rockwell Land Corporation")
    assert any("Rockwell Land" in q for q in qs)
    # Must not be a bare Philippines + ROCK word query
    assert not any(
        "Philippines" in q and "Rockwell" not in q and "ROCK:PSE" not in q
        for q in qs
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


def test_filters_tradingview_and_quote_pages():
    ticker, name = "ANS", "A. Soriano Corporation"
    tv = {
        "title": "ANS Stock Price and Chart — PSE:ANS",
        "source": "TradingView",
        "link": "https://www.tradingview.com/symbols/PSE-ANS/",
    }
    yahoo = {
        "title": "ANS.PS Stock Quote",
        "source": "Yahoo Finance",
        "link": "https://finance.yahoo.com/quote/ANS.PS/",
    }
    real = {
        "title": "A. Soriano Corporation declares cash dividend",
        "source": "BusinessWorld",
        "link": "https://www.bworldonline.com/ans-dividend",
    }
    assert not item_is_news_like(tv)
    assert not item_is_news_like(yahoo)
    assert item_is_news_like(real)
    assert not item_is_relevant(tv, ticker=ticker, name=name)
    assert item_is_relevant(real, ticker=ticker, name=name)


def test_matches_compacted_and_brand_stems():
    """EastWest ≡ East West; Filinvest alone matches Filinvest Land / FDC."""
    ew = {
        "title": (
            "EastWest Banking Corporation: Connecting Further "
            "in Philippine Consumer Finance"
        ),
        "source": "CFI.CO — CAPITAL FINANCE INTERNATIONAL",
        "link": "https://cfi.co/eastwest-banking",
    }
    fli_earn = {
        "title": "Filinvest first-quarter earnings rose 8%",
        "source": "INQUIRER.NET",
        "link": "https://business.inquirer.net/filinvest-earnings",
    }
    simply = {
        "title": "Global's Undervalued Small Caps With Insider Actions For May 2026",
        "source": "SIMPLYWALL.ST",
        "link": "https://simplywall.st/screener/global-undervalued",
    }
    assert item_is_relevant(
        ew, ticker="EW", name="East West Banking Corporation"
    )
    assert item_is_relevant(
        fli_earn, ticker="FLI", name="Filinvest Land, Inc."
    )
    assert item_is_relevant(
        fli_earn, ticker="FDC", name="Filinvest Development Corporation"
    )
    # Still not issuer-identity for an unrelated ticker
    assert not item_is_relevant(
        ew, ticker="SMC", name="San Miguel Corporation"
    )
    assert not item_is_news_like(simply)
    assert not item_is_relevant(
        simply, ticker="EW", name="East West Banking Corporation"
    )


def test_rejects_sports_brand_hijacks():
    """San Miguel Beermen / PBA coverage is not SMC corporate news."""
    ticker, name = "SMC", "San Miguel Corporation"
    pba = {
        "title": (
            "PBA: Rodney Brondial steps up in June Mar's absence "
            "as San Miguel sinks Macau"
        ),
        "source": "GMA Network",
        "link": "https://www.gmanetwork.com/news/sports/pba/san-miguel",
    }
    basketball = {
        "title": "San Miguel Beermen clinch PBA finals berth",
        "source": "Philstar",
        "link": "https://www.philstar.com/sports/pba/san-miguel-beermen",
    }
    corporate = {
        "title": "San Miguel Corporation posts higher first-half profit",
        "source": "BusinessWorld",
        "link": "https://www.bworldonline.com/corporate/san-miguel-corporation",
    }
    assert not item_is_news_like(pba)
    assert not item_is_news_like(basketball)
    assert item_is_news_like(corporate)
    assert not item_is_relevant(pba, ticker=ticker, name=name)
    assert item_is_relevant(corporate, ticker=ticker, name=name)
    qs = build_queries(ticker, name)
    assert any("-PBA" in q for q in qs)


if __name__ == "__main__":
    test_short_ticker_queries_are_constrained()
    test_long_ticker_query()
    test_relevance_filters_ambiguous_noise()
    test_rejects_english_verb_ticker_collisions()
    test_short_ticker_queries_prefer_company_name()
    test_unwrap_query_param_and_passthrough()
    test_decode_article_id_when_url_embedded()
    test_filters_tradingview_and_quote_pages()
    test_matches_compacted_and_brand_stems()
    test_rejects_sports_brand_hijacks()
    print("ok")
