"""Checklist scoring and completeness checks (mirrors frontend/src/lib/metrics.js)."""

from datetime import date, datetime, timedelta

from src.utils import safe_float

# Shared screening defaults — keep in sync with frontend/src/lib/metrics.js
DEFAULT_THRESHOLDS = {
    "pe_max": 22.0,
    "pb_max": 1.0,
    "roe_min": 0.10,
    "de_max": 2.0,
}

# Checklist order: 0 PE, 1 PB, 2–6 structural, 7 D/E (live), 8 ROE (live)
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
    if thresholds.get("de_max") is not None:
        out["de_max"] = float(thresholds["de_max"])
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


def debt_to_equity_ratio(row, company=None):
    """
    Total liabilities ÷ equity. NA for financials (extreme leverage by design).
    Equity prefers stockholders_equity, else assets − liabilities.
    """
    if not row:
        return None
    from src.filing_triage import is_financial_sector

    company = company or {}
    if is_financial_sector(company.get("sector"), company.get("subsector")):
        return None
    liab = safe_float(row.get("total_liabilities"))
    if liab is None:
        return None
    eq = safe_float(row.get("stockholders_equity"))
    if eq is None or abs(eq) < 1e-9:
        assets = safe_float(row.get("total_assets"))
        if assets is None:
            return None
        eq = assets - liab
    if eq is None or eq <= 0:
        return None
    return liab / eq


def debt_to_equity_pass(de, de_max):
    """Pass when 0 ≤ D/E < de_max."""
    d = safe_float(de)
    cap = safe_float(de_max)
    if d is None or cap is None:
        return None
    if d < 0:
        return None
    return d < cap


def latest_debt_to_equity(company, financials):
    """Latest-year D/E fraction for companies.debt_to_equity persistence."""
    fin = _complete_financials(financials)
    if not fin:
        return None
    return debt_to_equity_ratio(fin[-1], company)


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


def prefer_roe(scraped, computed):
    """
    Choose ROE when disclosure FR and NI/equity disagree.

    Double-/100 on already-fraction FR values yields ~0.19% while NI/E is ~19%.
    Prefer computed only for that pattern, and never when |computed| > 200%
    (usually bad equity scale).
    """
    s = safe_float(scraped)
    c = safe_float(computed)
    if c is not None and abs(c) > 2.0:
        c = None  # absurd NI/E — ignore
    if s is None:
        return c
    if c is None:
        return s
    # SPC-style: scraped ~0.xx% after erroneous /100, computed ~xx%
    if abs(s) < 0.01 and abs(c) > 0.05:
        return c
    return s


def normalize_ga_expense(ga):
    """G&A is always a positive expense magnitude."""
    v = safe_float(ga)
    if v is None:
        return None
    return abs(v)


# Material peso floor for undersize OI checks (ignore micro rounding rows).
_OI_ANCHOR_MIN = 1_000_000.0
# False mid-size OI (ALI-shaped): must be ≥ this share of IBT when IBT is material.
_OI_IBT_MIN_RATIO = 0.40


def gross_profit_sane(
    gp,
    *,
    revenue=None,
    total_assets=None,
    net_income=None,
):
    """Reject GP that cannot be a statement gross profit."""
    v = safe_float(gp)
    if v is None:
        return False
    rev = safe_float(revenue)
    if rev is not None and abs(rev) >= _OI_ANCHOR_MIN and abs(v) > abs(rev) * 1.05:
        return False
    assets = safe_float(total_assets)
    if assets is not None and abs(assets) >= _OI_ANCHOR_MIN and abs(v) > abs(assets):
        return False
    ni = safe_float(net_income)
    if ni is not None and abs(ni) >= _OI_ANCHOR_MIN and abs(v) > 50.0 * abs(ni):
        return False
    return True


def operating_income_sane(
    oi,
    *,
    revenue=None,
    gross_profit=None,
    net_income=None,
    income_before_tax=None,
    allow_below_ibt=False,
):
    """
    Reject OI that cannot be core ops:
    - |OI| > revenue (when rev is a believable anchor), or |OI| ≫ GP
    - |OI| ≪ GP (misparsed subline, FCG-shaped)
    - |OI| ≪ NI when GP is missing or also scale-broken vs NI (JFC-shaped)
    - |OI| < 0.4× |IBT| when both material and same sign (ALI false mid-size OI)
    - |OI| ≫ NI (AEV-shaped GP−GA)

    When ``allow_below_ibt`` (GP−GA derived), skip the IBT floor — other income
    can make IBT ≫ core OI on parent statements.

    Missing anchors do not fail the check.
    """
    v = safe_float(oi)
    if v is None:
        return False
    rev = safe_float(revenue)
    gp = safe_float(gross_profit)

    # Too large vs revenue — skip when GP shows revenue is the broken field
    if rev is not None and abs(v) > abs(rev) * 1.05:
        rev_believable = gp is None or abs(gp) <= abs(rev) * 1.05
        if rev_believable:
            return False
    if gp is not None and abs(gp) > 0 and abs(v) > 3.0 * abs(gp):
        return False

    # Undersized vs gross profit (e.g. OI ≈ 1% of GP)
    if gp is not None and abs(gp) >= _OI_ANCHOR_MIN and abs(v) < 0.03 * abs(gp):
        return False

    ni = safe_float(net_income)
    ibt = safe_float(income_before_tax)

    # False mid-size OI vs IBT (ALI-shaped misparse)
    if (
        not allow_below_ibt
        and ibt is not None
        and abs(ibt) >= _OI_ANCHOR_MIN
        and ((v > 0 and ibt > 0) or (v < 0 and ibt < 0))
        and abs(v) < _OI_IBT_MIN_RATIO * abs(ibt)
    ):
        return False

    # Undersized vs NI only when GP cannot vouch for scale (missing or ≪ NI)
    earn = ni if ni is not None else ibt
    if earn is not None and abs(earn) >= _OI_ANCHOR_MIN and abs(v) < 0.05 * abs(earn):
        gp_ok = (
            gp is not None
            and abs(gp) >= _OI_ANCHOR_MIN
            and abs(gp) >= 0.10 * abs(earn)
        )
        if not gp_ok:
            return False

    # Oversized vs NI — blocks GP−GA when GP/NI are on different scales (AEV)
    if earn is not None and abs(earn) >= _OI_ANCHOR_MIN and abs(v) > 5.0 * abs(earn):
        return False

    return True


def normalize_expense_magnitude(raw):
    """Expense lines as positive magnitudes (GA / interest / other)."""
    v = safe_float(raw)
    if v is None:
        return None
    return abs(v)


def derived_gross_profit(row):
    """revenue − cost_of_sales when both present and result is sane."""
    if not row:
        return None
    rev = safe_float(row.get("revenue"))
    if rev is None:
        rev = safe_float(row.get("gross_revenue"))
    cogs = normalize_expense_magnitude(row.get("cost_of_sales"))
    if rev is None or cogs is None:
        return None
    gp = rev - cogs
    if not gross_profit_sane(
        gp,
        revenue=rev,
        total_assets=row.get("total_assets"),
        net_income=row.get("net_income"),
    ):
        return None
    return gp


def constructed_operating_income(row):
    """
    Build EBIT when the statement has no OI line (ALI-class).

    Prefer IBT + interest/financing when interest is material vs IBT;
    else GP − |GA| − other expenses.
    """
    if not row:
        return None
    ibt = safe_float(row.get("income_before_tax"))
    interest = normalize_expense_magnitude(row.get("interest_expense"))
    # Ignore note-scale interest crumbs (SPC parent ~₱0.4M vs ₱2B IBT)
    if (
        ibt is not None
        and interest is not None
        and abs(ibt) >= _OI_ANCHOR_MIN
        and abs(interest) >= max(_OI_ANCHOR_MIN, 0.02 * abs(ibt))
    ):
        return ibt + interest

    gp = safe_float(row.get("gross_profit"))
    ga = normalize_ga_expense(row.get("ga_expense"))
    other = normalize_expense_magnitude(row.get("other_expenses"))
    if gp is None or ga is None or other is None:
        return None
    rev = safe_float(row.get("revenue"))
    if rev is None:
        rev = safe_float(row.get("gross_revenue"))
    if not gross_profit_sane(
        gp,
        revenue=rev,
        total_assets=row.get("total_assets"),
        net_income=row.get("net_income"),
    ):
        return None
    return gp - ga - other


def derived_operating_income(row):
    """GP − |GA| when both present and GP is sane."""
    if not row:
        return None
    gp = safe_float(row.get("gross_profit"))
    ga = normalize_ga_expense(row.get("ga_expense"))
    if gp is None or ga is None:
        return None
    rev = safe_float(row.get("revenue"))
    if rev is None:
        rev = safe_float(row.get("gross_revenue"))
    if not gross_profit_sane(
        gp,
        revenue=rev,
        total_assets=row.get("total_assets"),
        net_income=row.get("net_income"),
    ):
        return None
    return gp - ga


def prefer_operating_income(row):
    """
    Prefer scraped OI when sane; else IBT+interest / GP−GA−other / GP−|GA|.
    """
    if not row:
        return None
    rev = safe_float(row.get("revenue"))
    if rev is None:
        rev = safe_float(row.get("gross_revenue"))
    gp = safe_float(row.get("gross_profit"))
    if gp is None:
        gp = derived_gross_profit(row)
    work = dict(row)
    if gp is not None:
        work["gross_profit"] = gp
    ni = row.get("net_income")
    ibt = row.get("income_before_tax")
    oi = safe_float(row.get("operating_income"))
    if oi is not None and operating_income_sane(
        oi,
        revenue=rev,
        gross_profit=gp,
        net_income=ni,
        income_before_tax=ibt,
    ):
        return oi
    # IBT+interest EBIT: ignore GP ceiling (HTML GP often incomplete for property)
    ibt_oi = None
    interest = normalize_expense_magnitude(work.get("interest_expense"))
    ibt_v = safe_float(ibt)
    if (
        ibt_v is not None
        and interest is not None
        and abs(ibt_v) >= _OI_ANCHOR_MIN
        and abs(interest) >= max(_OI_ANCHOR_MIN, 0.02 * abs(ibt_v))
    ):
        ibt_oi = ibt_v + interest
        if operating_income_sane(
            ibt_oi,
            revenue=rev,
            gross_profit=None,
            net_income=ni,
            income_before_tax=ibt,
            allow_below_ibt=True,
        ):
            return ibt_oi
    for candidate in (
        constructed_operating_income(work),
        derived_operating_income(work),
    ):
        if candidate is not None and operating_income_sane(
            candidate,
            revenue=rev,
            gross_profit=gp,
            net_income=ni,
            income_before_tax=ibt,
            allow_below_ibt=True,
        ):
            return candidate
    return None


def needs_pdf_oi(row) -> bool:
    """
    True when HTML/DB operating income is missing or untrusted for proper ROIC.

    Triggers PDF-prefer merge for non-financials: no usable OI, scraped OI fails
    sanity (incl. <0.4× IBT), or only a derived GP−GA figure is available.
    """
    if not row:
        return True
    preferred = prefer_operating_income(row)
    if preferred is None:
        return True
    oi = safe_float(row.get("operating_income"))
    if oi is None:
        # Only derived path produced a value — still prefer a real PDF EBIT
        return True
    rev = safe_float(row.get("revenue"))
    if rev is None:
        rev = safe_float(row.get("gross_revenue"))
    if not operating_income_sane(
        oi,
        revenue=rev,
        gross_profit=row.get("gross_profit"),
        net_income=row.get("net_income"),
        income_before_tax=row.get("income_before_tax"),
    ):
        return True
    if row.get("operating_income_derived"):
        return True
    return False


def needs_pdf_cash(row) -> bool:
    """True when cash is missing or implausibly tiny vs assets."""
    if not row:
        return True
    cash = safe_float(row.get("cash_and_equivalents"))
    if cash is None:
        return True
    assets = safe_float(row.get("total_assets"))
    if assets is not None and abs(assets) >= _OI_ANCHOR_MIN:
        if abs(cash) < 0.001 * abs(assets):
            return True
    if 1990 <= abs(cash) <= 2100 and abs(abs(cash) - round(abs(cash))) < 1e-9:
        return True
    return False


def needs_pdf_ga(row) -> bool:
    """True when GA is missing or absurdly small vs revenue."""
    if not row:
        return True
    ga = normalize_ga_expense(row.get("ga_expense"))
    if ga is None:
        return True
    rev = safe_float(row.get("revenue"))
    if rev is None:
        rev = safe_float(row.get("gross_revenue"))
    if rev is not None and abs(rev) >= _OI_ANCHOR_MIN and abs(ga) < 0.0005 * abs(rev):
        return True
    return False


def _abs_log_dist(a, b) -> float | None:
    aa, bb = safe_float(a), safe_float(b)
    if aa is None or bb is None or aa == 0 or bb == 0:
        return None
    import math

    return abs(math.log10(abs(aa)) - math.log10(abs(bb)))


def pdf_oi_closer_to_ibt(pdf_oi, html_oi, ibt) -> bool:
    """True when PDF OI is nearer |IBT| than HTML OI (both must be present)."""
    anchor = safe_float(ibt)
    if anchor is None or abs(anchor) < _OI_ANCHOR_MIN:
        return False
    d_pdf = _abs_log_dist(pdf_oi, anchor)
    d_html = _abs_log_dist(html_oi, anchor)
    if d_pdf is None:
        return False
    if d_html is None:
        return True
    return d_pdf < d_html - 1e-9


def sanitize_operating_metrics(metrics, company=None):
    """
    In-place: abs(GA/interest/other); drop insane GP/OI; synthesize GP/OI
    for non-financials (rev−COGS; IBT+interest / GP−GA−other / GP−GA).

    Financial sector: no EBIT/GP synthesis (equity ROIC path).
    When company/sector unknown, synthesis is allowed.
    Sets operating_income_derived when OI was synthesized.
    """
    if not metrics:
        return metrics

    from src.filing_triage import is_financial_sector

    company = company or {}
    financial = bool(
        company
        and is_financial_sector(company.get("sector"), company.get("subsector"))
    )
    allow_synth = not financial

    ga = normalize_ga_expense(metrics.get("ga_expense"))
    if ga is not None:
        metrics["ga_expense"] = ga
    interest = normalize_expense_magnitude(metrics.get("interest_expense"))
    if interest is not None:
        metrics["interest_expense"] = interest
    other = normalize_expense_magnitude(metrics.get("other_expenses"))
    if other is not None:
        metrics["other_expenses"] = other
    cogs = normalize_expense_magnitude(metrics.get("cost_of_sales"))
    if cogs is not None:
        metrics["cost_of_sales"] = cogs

    rev = safe_float(metrics.get("revenue"))
    if rev is None:
        rev = safe_float(metrics.get("gross_revenue"))
    gp = safe_float(metrics.get("gross_profit"))
    if gp is not None and not gross_profit_sane(
        gp,
        revenue=rev,
        total_assets=metrics.get("total_assets"),
        net_income=metrics.get("net_income"),
    ):
        metrics.pop("gross_profit", None)
        gp = None

    if allow_synth and gp is None:
        derived_gp = derived_gross_profit(metrics)
        if derived_gp is not None:
            metrics["gross_profit"] = derived_gp
            metrics["gross_profit_derived"] = True
            gp = derived_gp
        else:
            metrics["gross_profit_derived"] = False
    else:
        metrics["gross_profit_derived"] = False

    oi = safe_float(metrics.get("operating_income"))

    if oi is not None and not operating_income_sane(
        oi,
        revenue=rev,
        gross_profit=gp,
        net_income=metrics.get("net_income"),
        income_before_tax=metrics.get("income_before_tax"),
    ):
        metrics.pop("operating_income", None)
        oi = None

    if oi is None and allow_synth:
        ibt = safe_float(metrics.get("income_before_tax"))
        interest = normalize_expense_magnitude(metrics.get("interest_expense"))
        if (
            ibt is not None
            and interest is not None
            and abs(ibt) >= _OI_ANCHOR_MIN
            and abs(interest) >= max(_OI_ANCHOR_MIN, 0.02 * abs(ibt))
        ):
            ibt_oi = ibt + interest
            if operating_income_sane(
                ibt_oi,
                revenue=rev,
                gross_profit=None,
                net_income=metrics.get("net_income"),
                income_before_tax=ibt,
                allow_below_ibt=True,
            ):
                metrics["operating_income"] = ibt_oi
                metrics["operating_income_derived"] = True
                return metrics
        for candidate in (
            constructed_operating_income(metrics),
            derived_operating_income(metrics),
        ):
            if candidate is not None and operating_income_sane(
                candidate,
                revenue=rev,
                gross_profit=safe_float(metrics.get("gross_profit")),
                net_income=metrics.get("net_income"),
                income_before_tax=metrics.get("income_before_tax"),
                allow_below_ibt=True,
            ):
                metrics["operating_income"] = candidate
                metrics["operating_income_derived"] = True
                return metrics
        metrics["operating_income_derived"] = False
    elif oi is None:
        metrics["operating_income_derived"] = False
    else:
        metrics["operating_income_derived"] = False
    return metrics


def equity_for_roe(latest, company=None):
    """Prefer statement equity; fall back to BVPS × shares."""
    if latest:
        e = safe_float(latest.get("stockholders_equity"))
        if e is not None and abs(e) > 0:
            return e
        bv = safe_float(latest.get("book_value"))
        shares = safe_float(latest.get("outstanding_shares"))
        if shares is None and company is not None:
            shares = safe_float(company.get("outstanding_shares"))
        if bv is not None and shares is not None and abs(shares) > 0:
            return bv * shares
    return None


def _invested_capital(row, *, proper=False):
    """Mirror frontend investedCapital."""
    assets = safe_float(row.get("total_assets"))
    cash = safe_float(row.get("cash_and_equivalents"))
    current_liab = safe_float(row.get("total_current_liabilities"))
    if (
        proper
        and assets is not None
        and cash is not None
        and current_liab is not None
        and assets > cash + current_liab
    ):
        return assets - cash - current_liab
    if assets is not None and current_liab is not None and assets > current_liab:
        return assets - current_liab
    if assets is not None and assets != 0:
        return assets
    liab = safe_float(row.get("total_liabilities"))
    equity = safe_float(row.get("stockholders_equity"))
    if equity is None and assets is not None and liab is not None:
        equity = assets - liab
    if equity is not None and liab is not None:
        return equity + liab
    return equity


def _effective_tax_rate(row):
    tax = safe_float(row.get("income_tax_expense"))
    ibt = safe_float(row.get("income_before_tax"))
    if tax is not None and ibt is not None and ibt != 0:
        t = tax / ibt
        if 0 <= t <= 0.5:
            return t
    return None


def compute_roic_series(financials, company=None):
    """
    Mirror frontend computeRoicSeries.

    Returns {series, mode, statement_scope, tax_assumed}.
    Banks/insurance → mode 'equity' (NI ÷ avg equity); never industrial A−cash−CL.
    Series values are percentage points (e.g. 12.5 = 12.5%).
    """
    from src.filing_triage import is_financial_sector

    rows = _complete_financials(financials)
    statement_scope = None
    for row in rows:
        if row.get("statement_scope") and not statement_scope:
            statement_scope = row.get("statement_scope")

    sector = (company or {}).get("sector")
    subsector = (company or {}).get("subsector")
    if is_financial_sector(sector, subsector):
        out = []
        for i, row in enumerate(rows):
            ni = safe_float(row.get("net_income"))
            eq_end = equity_for_roe(row, company)
            if ni is None or eq_end is None or eq_end == 0:
                continue
            eq = eq_end
            if i > 0:
                eq_beg = equity_for_roe(rows[i - 1], company)
                if eq_beg is not None and eq_beg != 0:
                    eq = (eq_beg + eq_end) / 2.0
            if eq == 0:
                continue
            out.append(
                {
                    "year": str(row["fiscal_year"]),
                    "value": (ni / eq) * 100.0,
                    "mode": "equity",
                }
            )
        return {
            "series": out,
            "mode": "equity",
            "statement_scope": statement_scope,
            "tax_assumed": False,
        }

    can_proper = any(
        prefer_operating_income(r) is not None
        and safe_float(r.get("total_assets")) is not None
        and safe_float(r.get("cash_and_equivalents")) is not None
        and safe_float(r.get("total_current_liabilities")) is not None
        for r in rows
    )
    mode = "proper" if can_proper else "proxy"
    out = []
    tax_assumed = False
    for i, row in enumerate(rows):
        ic_end = _invested_capital(row, proper=mode == "proper")
        if ic_end is None or ic_end == 0:
            continue
        ic = ic_end
        if i > 0:
            ic_beg = _invested_capital(rows[i - 1], proper=mode == "proper")
            if ic_beg is not None and ic_beg != 0:
                ic = (ic_beg + ic_end) / 2.0
        if ic == 0:
            continue
        if mode == "proper":
            op = prefer_operating_income(row)
            if op is None:
                continue
            t = _effective_tax_rate(row)
            if t is None:
                t = 0.25
                tax_assumed = True
            nopat = op * (1.0 - t)
        else:
            nopat = safe_float(row.get("net_income"))
            if nopat is None:
                continue
        out.append(
            {
                "year": str(row["fiscal_year"]),
                "value": (nopat / ic) * 100.0,
                "mode": mode,
            }
        )
    return {
        "series": out,
        "mode": mode,
        "statement_scope": statement_scope,
        "tax_assumed": tax_assumed,
    }


def latest_roic_fraction(company, financials):
    """Latest ROIC as a fraction (0.12 = 12%) for persistence / API filter."""
    result = compute_roic_series(financials, company)
    series = result.get("series") or []
    if not series:
        return None
    pct = safe_float(series[-1].get("value"))
    if pct is None:
        return None
    return pct / 100.0


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


def ratio_pass_from_columns(pe_ratio, pb_ratio, roe, thresholds=None, debt_to_equity=None):
    """
    Evaluate PE/PB/D/E/ROE checks from persisted company columns only
    (list API / hybrid rescore — no filing fallbacks).
    Returns (pe_pass, pb_pass, de_pass, roe_pass) each True/False/None.
    """
    t = normalize_thresholds(thresholds)
    pe = sanitize_ratio(pe_ratio)
    pb = sanitize_ratio(pb_ratio)
    roe_v = safe_float(roe)
    de = safe_float(debt_to_equity)
    pe_pass = pe_check_pass(pe, t["pe_max"])
    pb_pass = pb < t["pb_max"] if pb is not None else None
    de_pass = debt_to_equity_pass(de, t["de_max"])
    roe_pass = roe_v > t["roe_min"] if roe_v is not None else None
    return pe_pass, pb_pass, de_pass, roe_pass


def merge_live_score(struct_pass, struct_eval, pe_pass, pb_pass, roe_pass, de_pass=None):
    """Combine stored structural scores with live ratio passes."""
    passed = int(struct_pass or 0)
    total = int(struct_eval or 0)
    for p in (pe_pass, pb_pass, de_pass, roe_pass):
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
    de_max = t["de_max"]

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
    equity = equity_for_roe(latest, company) or equity
    roe_computed = (
        net_income / equity if equity and net_income is not None and abs(equity) > 0 else None
    )
    roe = prefer_roe(roe_scraped, roe_computed)

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
            "label": f"Debt/Equity < {de_max:g}",
            "pass": debt_to_equity_pass(
                debt_to_equity_ratio(latest, company), de_max
            ),
        },
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


# Per-share cash DPS above this is almost never real PSE cash (JOH-scale junk).
_MAX_PLAUSIBLE_CASH_DPS = 1000.0
# Single cash payment larger than this multiple of price is excluded from yield.
_MAX_CASH_DPS_OVER_PRICE = 2.0


def plausible_cash_dps(amount, price=None):
    """
    Guard TTM yield against entitlement misparses and digit-strip junk.

    Rejects absurd absolute DPS and single payments > 2× last price.
    """
    amt = safe_float(amount)
    if amt is None or amt <= 0:
        return False
    if amt > _MAX_PLAUSIBLE_CASH_DPS:
        return False
    p = safe_float(price)
    if p is not None and p > 0 and amt > p * _MAX_CASH_DPS_OVER_PRICE:
        return False
    return True


def _dividend_rank(d):
    """Prefer COMMON + record_date over legacy null-security duplicates."""
    flagged = d.get("is_common") in (1, True) or str(
        d.get("security") or ""
    ).upper().startswith("COMMON")
    has_record = bool(d.get("record_date"))
    has_security = bool(d.get("security"))
    return (4 if flagged else 0) + (2 if has_record else 0) + (1 if has_security else 0)


def _dedupe_dividends(dividends):
    """Prefer flagged COMMON rows over legacy null-security duplicates."""
    stock_keys = set()
    property_dates = set()
    for d in dividends or []:
        amt = safe_float(d.get("rate", d.get("amount")))
        if amt is None:
            continue
        dtype = str(d.get("type") or "cash").strip().lower() or "cash"
        ex = str(d.get("ex_date") or "")
        if dtype == "stock":
            stock_keys.add((ex, round(amt, 8)))
        if dtype == "property":
            property_dates.add(ex)

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
        # Cash beside a property payout on the same ex-date with a large "rate"
        # is usually an entitlement misparse (LFM 197 next to property).
        if dtype == "cash" and ex in property_dates and amt >= 5.0:
            continue
        key = (ex, round(amt, 8), dtype)
        prev = best.get(key)
        if prev is None or _dividend_rank(d) > _dividend_rank(prev):
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


def common_cash_dividends(dividends, price=None):
    """Deduped common-share cash dividend rows with plausible per-share DPS."""
    out = []
    for d in _dedupe_dividends(dividends):
        if not _is_common_dividend(d) or not _is_cash_dividend(d):
            continue
        amt = safe_float(d.get("rate", d.get("amount")))
        if not plausible_cash_dps(amt, price):
            continue
        out.append(d)
    return out


def annual_dividend_by_calendar_year(dividends, price=None):
    """
    Sum quarterly (and other) cash common dividends into calendar-year DPS.
    Returns {year_int: total_amount}.
    """
    totals = {}
    for d in common_cash_dividends(dividends, price=price):
        ex = _parse_ex_date(d.get("ex_date"))
        amt = safe_float(d.get("rate", d.get("amount")))
        if ex is None or amt is None:
            continue
        totals[ex.year] = totals.get(ex.year, 0.0) + amt
    return totals


def trailing_annual_dividend(dividends, as_of=None, window_days=365, price=None):
    """
    Trailing-twelve-month common cash DPS only.

    Sums each quarterly (and other) cash payment with ex-date in
    (as_of - window_days, as_of]. as_of defaults to today — never to the
    latest historical ex-date, so stale unpaid years cannot inflate yield.
    Returns None when nothing cash/common falls in the window.
    """
    rows = []
    for d in common_cash_dividends(dividends, price=price):
        ex = _parse_ex_date(d.get("ex_date"))
        amt = safe_float(d.get("rate", d.get("amount")))
        if ex is None or amt is None:
            continue
        rows.append((ex, amt))
    if not rows:
        return None

    if as_of is None:
        as_of = date.today()
    elif isinstance(as_of, str):
        as_of = _parse_ex_date(as_of) or date.today()
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
    annual_dps = trailing_annual_dividend(dividends, as_of=as_of, price=price)
    if annual_dps is None or annual_dps <= 0:
        return None
    y = annual_dps / price
    # Hard ceiling — entitlement junk or bad price still cannot print >100%
    if y > 1.0:
        return None
    return y


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
        "roic": latest_roic_fraction(company, financials),
        "debt_to_equity": latest_debt_to_equity(company, financials),
    }
