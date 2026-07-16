"""Checklist scoring and completeness checks (mirrors frontend/src/lib/metrics.js)."""

from datetime import date, datetime, timedelta

from src.utils import safe_float

# Shared screening defaults — keep in sync with frontend/src/lib/metrics.js
DEFAULT_THRESHOLDS = {
    "pe_max": 22.0,
    "pb_max": 1.0,
    "roe_min": 0.10,
}

# Checklist order: 0 PE, 1 PB, 2–6 structural, 7 ROE
STRUCT_CHECK_INDEXES = (2, 3, 4, 5, 6)

# P&L growth only meaningful when both periods are profitable (skip sign flips / zeros)
PL_GROWTH_KEYS = frozenset({
    "net_income",
    "gross_revenue",
    "revenue",
    "eps",
})
# Exact zero is a placeholder, not a real revenue/EPS print
ZERO_AS_MISSING_KEYS = frozenset({"revenue", "gross_revenue", "eps"})
# Ignore YoY off a microscopically small profitable base (AB-style %)
PL_MIN_ABS_PREV = {
    "net_income": 1_000_000.0,
    "gross_revenue": 1_000_000.0,
    "revenue": 1_000_000.0,
    "eps": 0.05,
}


def normalize_thresholds(thresholds=None):
    """Merge partial thresholds with defaults (snake_case keys)."""
    out = dict(DEFAULT_THRESHOLDS)
    if not thresholds:
        return out
    if thresholds.get("pe_max") is not None:
        out["pe_max"] = float(thresholds["pe_max"])
    if thresholds.get("pb_max") is not None:
        out["pb_max"] = float(thresholds["pb_max"])
    if thresholds.get("roe_min") is not None:
        out["roe_min"] = float(thresholds["roe_min"])
    return out


def metric_value(value, key=None):
    """safe_float with zero-revenue / zero-EPS treated as missing."""
    v = safe_float(value)
    if v is None:
        return None
    if key in ZERO_AS_MISSING_KEYS and v == 0:
        return None
    return v


def growth_rate(prev, curr, *, key=None):
    """
    (curr - prev) / prev, or None when the % would be meaningless.

    For P&L keys: both periods must be > 0 and |prev| above a floor.
    Otherwise: skip zero prev and sign changes.
    """
    prev = safe_float(prev)
    curr = safe_float(curr)
    if prev is None or curr is None or prev == 0:
        return None
    if key in PL_GROWTH_KEYS:
        if prev <= 0 or curr <= 0:
            return None
        floor = PL_MIN_ABS_PREV.get(key, 0.0)
        if abs(prev) < floor:
            return None
    elif (prev > 0) != (curr > 0):
        return None
    rate = (curr - prev) / prev
    # Exact flat prints as 0.0% and confuses the report — treat as N/A
    if abs(rate) < 1e-6:
        return None
    return rate


def cagr_rate(first, last, periods, *, key=None):
    """CAGR over `periods` steps; P&L requires sustained positive values."""
    first = safe_float(first)
    last = safe_float(last)
    if first is None or last is None or periods < 1 or first == 0:
        return None
    if key in PL_GROWTH_KEYS:
        if first <= 0 or last <= 0:
            return None
        floor = PL_MIN_ABS_PREV.get(key, 0.0)
        if abs(first) < floor:
            return None
    elif first <= 0 or last <= 0:
        return None
    ratio = last / first
    if ratio <= 0:
        return None
    return ratio ** (1 / periods) - 1


def pe_check_pass(pe, pe_max):
    """Value screen: positive earnings multiple under the cap (negative P/E fails)."""
    pe = safe_float(pe)
    pe_max = safe_float(pe_max)
    if pe is None or pe_max is None:
        return None
    return pe > 0 and pe < pe_max


def earnings_usable_for_valuation(eps, net_income=None):
    """EPS-based DCF / computed P/E only when earnings are actually positive."""
    eps = safe_float(eps)
    if eps is None or eps <= 0:
        return False
    if net_income is not None:
        ni = safe_float(net_income)
        if ni is not None and ni <= 0:
            return False
    return True


def sanitize_pe_display(pe):
    """Hide non-earning / absurd multiples from ratio tables."""
    pe = safe_float(pe)
    if pe is None or pe <= 0 or abs(pe) > 1000:
        return None
    return pe


def sanitize_roe_display(roe, net_income=None):
    """Hide loss-period or ~0% ROE that round to noise."""
    roe = safe_float(roe)
    if roe is None:
        return None
    ni = safe_float(net_income)
    if ni is not None and ni <= 0:
        return None
    if abs(roe) < 0.0005:  # < 0.05 ppt → prints as 0.0%
        return None
    return roe


def compute_growth(metric_key, years, company_data):
    """
    YoY and CAGR for a metric across fiscal years.
    company_data: {"years": {year: {metric_key: value, ...}}}
    """
    values = []
    for y in years:
        if y in company_data["years"] and metric_key in company_data["years"][y]:
            raw = company_data["years"][y][metric_key]
            val = metric_value(raw, metric_key)
            if val is None and metric_key not in ZERO_AS_MISSING_KEYS:
                val = safe_float(raw)
            if val is not None:
                values.append((y, val))
    if len(values) < 2:
        return {"yoy": {}, "cagr": None}

    yoy = {}
    for i in range(len(values) - 1):
        rate = growth_rate(values[i][1], values[i + 1][1], key=metric_key)
        if rate is not None:
            yoy[values[i + 1][0]] = rate

    cagr = cagr_rate(
        values[0][1],
        values[-1][1],
        len(values) - 1,
        key=metric_key,
    )
    return {"yoy": yoy, "cagr": cagr}


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
        if key in ZERO_AS_MISSING_KEYS:
            if metric_value(row.get(key), key) is not None:
                return True
        elif safe_float(row.get(key)) is not None:
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


def sanitize_ratio(scraped):
    """Drop absurd scraped PE/PB outliers (same rule as frontend)."""
    v = safe_float(scraped)
    if v is None or abs(v) > 1000:
        return None
    return v


def ratio_pass_from_columns(pe_ratio, pb_ratio, roe, thresholds=None):
    """
    Evaluate PE/PB/ROE checks from persisted company columns only
    (list API / hybrid rescore — no filing fallbacks).
    Returns (pe_pass, pb_pass, roe_pass) each True/False/None.
    """
    t = normalize_thresholds(thresholds)
    pe = sanitize_ratio(pe_ratio)
    pb = sanitize_ratio(pb_ratio)
    roe_v = safe_float(roe)
    pe_pass = pe_check_pass(pe, t["pe_max"])
    pb_pass = pb < t["pb_max"] if pb is not None else None
    roe_pass = roe_v > t["roe_min"] if roe_v is not None else None
    return pe_pass, pb_pass, roe_pass


def merge_live_score(struct_pass, struct_eval, pe_pass, pb_pass, roe_pass):
    """Combine stored structural scores with live ratio passes."""
    passed = int(struct_pass or 0)
    total = int(struct_eval or 0)
    for p in (pe_pass, pb_pass, roe_pass):
        if p is None:
            continue
        total += 1
        if p is True:
            passed += 1
    return passed, total


def structural_checklist_score(checklist):
    """Pass/evaluable counts for structural checks only (indexes 2–6)."""
    passed = 0
    total = 0
    for i in STRUCT_CHECK_INDEXES:
        if i >= len(checklist):
            break
        p = checklist[i].get("pass")
        if p is None:
            continue
        total += 1
        if p is True:
            passed += 1
    return passed, total


def build_checklist(company, financials, thresholds=None):
    """
    company: dict with pe_ratio, pb_ratio, roe, market_cap, outstanding_shares, last_traded_price
    financials: list of dicts with fiscal_year, book_value, net_income, total_assets,
                current_ratio, quick_ratio, eps, outstanding_shares
    thresholds: optional {pe_max, pb_max, roe_min}
    """
    t = normalize_thresholds(thresholds)
    pe_max = t["pe_max"]
    pb_max = t["pb_max"]
    roe_min = t["roe_min"]

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
    eps = metric_value(latest.get("eps"), "eps") if latest else None
    book_value = safe_float(latest.get("book_value")) if latest else None
    net_income = safe_float(latest.get("net_income")) if latest else None
    equity = book_value * shares if book_value is not None and shares is not None else None

    pe_scraped = safe_float(company.get("pe_ratio"))
    pb_scraped = safe_float(company.get("pb_ratio"))
    roe_scraped = safe_float(company.get("roe"))
    pe_computed = (
        price / eps
        if price is not None and earnings_usable_for_valuation(eps, net_income)
        else None
    )
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

    roe_pct = int(round(roe_min * 100))
    return [
        {
            "label": f"P/E Ratio < {pe_max:g}",
            "pass": pe_check_pass(pe, pe_max),
        },
        {
            "label": f"P/B < {pb_max:g}",
            "pass": pb < pb_max if pb is not None else None,
        },
        {"label": "Increasing BV", "pass": _inc("book_value")},
        {"label": "Increasing Income", "pass": _inc("net_income")},
        {"label": "Increasing Assets", "pass": _inc("total_assets")},
        {"label": "NO Share Dilution", "pass": no_share_dilution_pass(latest, prev)},
        {"label": "Quick/Current R > 1", "pass": _liquidity_ratio_pass(current_ratio, quick_ratio)},
        {
            "label": f"ROE > {roe_pct}%",
            "pass": roe > roe_min if roe is not None else None,
        },
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
        if key in ZERO_AS_MISSING_KEYS:
            if metric_value(latest.get(key), key) is None:
                return True
        elif safe_float(latest.get(key)) is None:
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


def _parse_ex_date(value):
    """Return datetime.date or None from EDGE date strings / dates."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if len(text) < 10:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def common_cash_dividends(dividends):
    """Deduped common-share cash dividend rows."""
    return [
        d for d in _dedupe_dividends(dividends)
        if _is_common_dividend(d) and _is_cash_dividend(d)
    ]


def annual_dividend_by_calendar_year(dividends):
    """
    Sum quarterly (and other) cash common dividends into calendar-year DPS.
    Returns {year_int: total_amount}.
    """
    totals = {}
    for d in common_cash_dividends(dividends):
        ex = _parse_ex_date(d.get("ex_date"))
        amt = safe_float(d.get("rate", d.get("amount")))
        if ex is None or amt is None:
            continue
        totals[ex.year] = totals.get(ex.year, 0.0) + amt
    return totals


def trailing_annual_dividend(dividends, as_of=None, window_days=365):
    """
    Trailing-twelve-month common cash DPS only.

    Sums each quarterly (and other) cash payment with ex-date in
    (as_of - window_days, as_of]. as_of defaults to today — never to the
    latest historical ex-date, so stale unpaid years cannot inflate yield.
    Returns None when nothing cash/common falls in the window.
    """
    rows = []
    for d in common_cash_dividends(dividends):
        ex = _parse_ex_date(d.get("ex_date"))
        amt = safe_float(d.get("rate", d.get("amount")))
        if ex is None or amt is None:
            continue
        rows.append((ex, amt))
    if not rows:
        return None

    if as_of is None:
        as_of = date.today()
    elif hasattr(as_of, "date") and not isinstance(as_of, date):
        as_of = as_of.date()

    start = as_of - timedelta(days=window_days)
    ttm = sum(amt for ex, amt in rows if start < ex <= as_of)
    if ttm <= 0:
        return None
    return ttm


def compute_div_yield(price, dividends, latest_fiscal_year=None, as_of=None):
    """
    Dividend yield = trailing-12-month common cash DPS / price.

    No fiscal-year or older-calendar-year fallback: if the company has no
    cash dividends in the last year, yield is None.
    """
    del latest_fiscal_year  # unused — yield is strictly TTM
    price = safe_float(price)
    if not price or price <= 0:
        return None
    annual_dps = trailing_annual_dividend(dividends, as_of=as_of)
    if annual_dps is None or annual_dps <= 0:
        return None
    return annual_dps / price


def compute_screening_summary(company, financials, dividends=None, thresholds=None):
    checklist = build_checklist(company, financials, thresholds=thresholds)
    passed, total = checklist_score(checklist)
    struct_pass, struct_eval = structural_checklist_score(checklist)
    incomplete = is_info_incomplete(company, financials)
    div_yield = compute_div_yield(
        company.get("last_traded_price"),
        dividends or [],
    )
    return {
        "check_pass_count": passed,
        "check_evaluable_total": total,
        "check_struct_pass": struct_pass,
        "check_struct_eval": struct_eval,
        "info_incomplete": incomplete,
        "div_yield": div_yield,
    }
