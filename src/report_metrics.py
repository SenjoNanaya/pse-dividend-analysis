"""Checklist scoring and completeness checks (mirrors frontend/src/lib/metrics.js)."""

from src.utils import safe_float


def _liquidity_ratio_pass(current_ratio, quick_ratio):
    cr = safe_float(current_ratio)
    qr = safe_float(quick_ratio)
    if cr is None and qr is None:
        return None
    if (cr is not None and cr > 1) or (qr is not None and qr > 1):
        return True
    return False


def _sanitize_price(price, market_cap, shares):
    p = safe_float(price)
    cap = safe_float(market_cap)
    sh = safe_float(shares)
    if p is not None and p > 100_000:
        p = None
    if p is not None and sh and abs(p - sh) / sh < 0.05:
        p = None
    if cap and sh:
        implied = cap / sh
        if implied > 0:
            if p is None:
                return implied
            if abs(p - implied) / implied > 10:
                return implied
    return p


def _sorted_financials(financials):
    rows = [f for f in (financials or []) if f.get("fiscal_year") is not None]
    return sorted(rows, key=lambda f: f["fiscal_year"])


def _has_core_metrics(row):
    for key in ("book_value", "net_income", "total_assets", "revenue", "eps"):
        if safe_float(row.get(key)) is not None:
            return True
    return False


def _complete_financials(financials):
    return [f for f in _sorted_financials(financials) if _has_core_metrics(f)]


def build_checklist(company, financials):
    """
    company: dict with pe_ratio, pb_ratio, roe, market_cap, outstanding_shares, last_traded_price
    financials: list of dicts with fiscal_year, book_value, net_income, total_assets,
                current_ratio, quick_ratio, eps
    """
    fin = _complete_financials(financials)
    latest = fin[-1] if fin else None
    prev = fin[-2] if len(fin) >= 2 else None

    price = _sanitize_price(
        company.get("last_traded_price"),
        company.get("market_cap"),
        company.get("outstanding_shares"),
    )
    shares = safe_float(company.get("outstanding_shares"))
    eps = safe_float(latest.get("eps")) if latest else None
    book_value = safe_float(latest.get("book_value")) if latest else None
    net_income = safe_float(latest.get("net_income")) if latest else None
    equity = book_value * shares if book_value is not None and shares is not None else None

    pe_scraped = safe_float(company.get("pe_ratio"))
    pb_scraped = safe_float(company.get("pb_ratio"))
    roe_scraped = safe_float(company.get("roe"))
    pe_computed = price / eps if price is not None and eps else None
    pb_computed = price / book_value if price is not None and book_value else None
    pe = pe_scraped if pe_scraped is not None and abs(pe_scraped) <= 1000 else None
    if pe is None:
        pe = pe_computed
    pb = pb_scraped if pb_scraped is not None and abs(pb_scraped) <= 1000 else None
    if pb is None:
        pb = pb_computed
    roe_computed = net_income / equity if equity and net_income is not None else None
    roe = roe_scraped if roe_scraped is not None else roe_computed

    current_ratio = latest.get("current_ratio") if latest else None
    quick_ratio = latest.get("quick_ratio") if latest else None

    def _inc(key):
        if not prev or not latest:
            return None
        a = safe_float(latest.get(key))
        b = safe_float(prev.get(key))
        if a is None or b is None:
            return None
        return a > b

    return [
        {"label": "P/E Ratio < 22", "pass": pe < 22 if pe is not None else None},
        {"label": "P/B < 1", "pass": pb < 1 if pb is not None else None},
        {"label": "Increasing BV", "pass": _inc("book_value")},
        {"label": "Increasing Income", "pass": _inc("net_income")},
        {"label": "Increasing Assets", "pass": _inc("total_assets")},
        {"label": "NO Share Dilution", "pass": True if shares is not None else None},
        {"label": "Quick/Current R > 1", "pass": _liquidity_ratio_pass(current_ratio, quick_ratio)},
        {"label": "ROE > 10%", "pass": roe > 0.1 if roe is not None else None},
    ]


def checklist_score(checklist):
    evaluable = [item for item in checklist if item.get("pass") is not None]
    passed = sum(1 for item in evaluable if item.get("pass") is True)
    return passed, len(evaluable)


def is_info_incomplete(company, financials):
    """True when core company or latest-year filing data is missing."""
    if not company.get("name") and not company.get("ticker"):
        return True
    fin = _complete_financials(financials)
    if not fin:
        return True
    latest = fin[-1]
    required = ("revenue", "net_income", "total_assets", "eps", "book_value")
    for key in required:
        if safe_float(latest.get(key)) is None:
            return True
    return False


def compute_screening_summary(company, financials):
    checklist = build_checklist(company, financials)
    passed, total = checklist_score(checklist)
    incomplete = is_info_incomplete(company, financials)
    return {
        "check_pass_count": passed,
        "check_evaluable_total": total,
        "info_incomplete": incomplete,
    }
