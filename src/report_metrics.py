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


def map_shares_to_fiscal_years(historical_shares, fiscal_years, stock_shares=None):
    """
    Attach Form 17-C share counts to statement fiscal years.
    Prefers exact year, then year+1 (early next-year filings), then year-1.
    Falls back to stock-page shares for the latest fiscal year only.
    """
    historical_shares = historical_shares or {}
    mapped = {}
    for fy in sorted(fiscal_years or []):
        candidates = []
        for y in (fy, fy + 1, fy - 1):
            if y in historical_shares and historical_shares[y] is not None:
                candidates.append((abs(y - fy), -y, float(historical_shares[y])))
        if candidates:
            candidates.sort()
            mapped[fy] = candidates[0][2]
    if stock_shares is not None and fiscal_years:
        latest = max(fiscal_years)
        if latest not in mapped:
            mapped[latest] = float(stock_shares)
    return mapped


def no_share_dilution_pass(latest, prev):
    """
    Pass when share count did not increase YoY.
    Returns None when either year lacks share data.
    """
    if not latest or not prev:
        return None
    a = safe_float(latest.get("outstanding_shares"))
    b = safe_float(prev.get("outstanding_shares"))
    if a is None or b is None or b <= 0:
        return None
    # Treat tiny float noise as unchanged; dilution = clear increase
    return a <= b * 1.001


def build_checklist(company, financials):
    """
    company: dict with pe_ratio, pb_ratio, roe, market_cap, outstanding_shares, last_traded_price
    financials: list of dicts with fiscal_year, book_value, net_income, total_assets,
                current_ratio, quick_ratio, eps, outstanding_shares
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
    if shares is None and latest is not None:
        shares = safe_float(latest.get("outstanding_shares"))
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
        {"label": "NO Share Dilution", "pass": no_share_dilution_pass(latest, prev)},
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


def _is_common_dividend(d):
    is_common = d.get("is_common")
    if is_common is False or is_common == 0:
        return False
    if is_common is True or is_common == 1:
        return True
    security = str(d.get("security") or "").upper()
    if not security:
        return True
    return security == "COMMON" or security.startswith("COMMON ")


def _is_cash_dividend(d):
    dtype = str(d.get("type") or "cash").strip().lower()
    return dtype in ("", "cash")


def _dedupe_dividends(dividends):
    """Prefer flagged COMMON rows over legacy null-security duplicates."""
    stock_keys = set()
    for d in dividends or []:
        amt = safe_float(d.get("rate", d.get("amount")))
        if amt is None:
            continue
        dtype = str(d.get("type") or "cash").strip().lower() or "cash"
        if dtype == "stock":
            stock_keys.add((str(d.get("ex_date") or ""), round(amt, 8)))

    best = {}
    for d in dividends or []:
        amt = safe_float(d.get("rate", d.get("amount")))
        if amt is None:
            continue
        ex = str(d.get("ex_date") or "")
        dtype = str(d.get("type") or "cash").strip().lower() or "cash"
        # Drop cash rows that duplicate a stock dividend at the same date/amount
        if dtype == "cash" and (ex, round(amt, 8)) in stock_keys:
            continue
        key = (ex, round(amt, 8), dtype)
        flagged = d.get("is_common") in (1, True) or str(d.get("security") or "").upper().startswith("COMMON")
        prev = best.get(key)
        if prev is None:
            best[key] = d
            continue
        prev_flagged = prev.get("is_common") in (1, True) or str(prev.get("security") or "").upper().startswith("COMMON")
        if flagged and not prev_flagged:
            best[key] = d
    return list(best.values())


def compute_div_yield(price, dividends, latest_fiscal_year=None):
    """
    Common-share cash dividends in the latest fiscal year / price.
    dividends items: rate or amount, ex_date, type, is_common (optional).
    """
    price = safe_float(price)
    if not price or price <= 0:
        return None

    rows = [
        d for d in _dedupe_dividends(dividends)
        if _is_common_dividend(d) and _is_cash_dividend(d)
    ]
    year = None
    if latest_fiscal_year is not None:
        year = str(int(latest_fiscal_year))
    else:
        years = []
        for d in rows:
            ex = str(d.get("ex_date") or "")
            if len(ex) >= 4 and ex[:4].isdigit():
                years.append(int(ex[:4]))
        if not years:
            return None
        year = str(max(years))

    total = 0.0
    found = False
    for d in rows:
        ex = str(d.get("ex_date") or "")
        if not ex.startswith(year):
            continue
        amt = safe_float(d.get("rate", d.get("amount")))
        if amt is None:
            continue
        total += amt
        found = True
    if not found:
        return None
    return total / price


def compute_screening_summary(company, financials, dividends=None):
    checklist = build_checklist(company, financials)
    passed, total = checklist_score(checklist)
    incomplete = is_info_incomplete(company, financials)
    fin = _complete_financials(financials)
    latest_year = fin[-1]["fiscal_year"] if fin else None
    div_yield = compute_div_yield(
        company.get("last_traded_price"),
        dividends or [],
        latest_fiscal_year=latest_year,
    )
    return {
        "check_pass_count": passed,
        "check_evaluable_total": total,
        "info_incomplete": incomplete,
        "div_yield": div_yield,
    }
