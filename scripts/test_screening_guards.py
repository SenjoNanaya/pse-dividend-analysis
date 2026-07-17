"""Guards for zero-revenue / signed NI / negative P/E screening."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.report_metrics import (
    build_checklist,
    cagr_rate,
    compute_growth,
    earnings_usable_for_valuation,
    growth_rate,
    incomplete_reasons,
    is_info_incomplete,
    metric_value,
    pe_check_pass,
)


def test_pe_rejects_negative():
    assert pe_check_pass(-281.4, 22) is False
    assert pe_check_pass(15.0, 22) is True
    assert pe_check_pass(22.0, 22) is False
    assert pe_check_pass(None, 22) is None


def test_growth_skips_sign_flip_and_tiny_base():
    # AB-like: loss → small profit
    assert growth_rate(-19_868_783, 1_948_301, key="net_income") is None
    # small profit → large loss
    assert growth_rate(1_948_301, -18_625_674, key="net_income") is None
    # normal
    g = growth_rate(100_000_000, 110_000_000, key="net_income")
    assert g is not None and abs(g - 0.1) < 1e-9
    # tiny profitable base
    assert growth_rate(50_000, 100_000, key="net_income") is None
    # assets still work across modest changes
    a = growth_rate(900_000_000, 950_000_000, key="total_assets")
    assert a is not None and abs(a - (50_000_000 / 900_000_000)) < 1e-12


def test_zero_revenue_eps_missing():
    assert metric_value(0.0, "revenue") is None
    assert metric_value(0.0, "eps") is None
    assert metric_value(1.5, "eps") == 1.5
    assert not earnings_usable_for_valuation(0.01, -18_000_000)
    assert earnings_usable_for_valuation(1.2, 100_000_000)


def test_display_sanitizes_loss_ratios():
    from src.report_metrics import sanitize_pe_display, sanitize_roe_display

    assert sanitize_pe_display(-281.4) is None
    assert sanitize_pe_display(15.2) == 15.2
    assert sanitize_roe_display(-0.0002, -18_000_000) is None
    assert sanitize_roe_display(0.12, 50_000_000) == 0.12
    assert growth_rate(0.37, 0.37, key="book_value") is None


def test_ab_checklist_and_growth_overview():
    company = {
        "name": "Atok-Big Wedge Co., Inc.",
        "ticker": "AB",
        "pe_ratio": -281.4,
        "pb_ratio": 4.27,
        "roe": -0.0002,
        "last_traded_price": 1.58,
        "outstanding_shares": 2_545_000_000,
        "market_cap": 4_250_150_000,
    }
    financials = [
        {
            "fiscal_year": 2023,
            "revenue": 0.0,
            "net_income": -19_868_783.0,
            "eps": -0.01,
            "book_value": 0.36,
            "total_assets": 909_740_221.0,
        },
        {
            "fiscal_year": 2024,
            "revenue": 0.0,
            "net_income": 1_948_301.0,
            "eps": 0.0,
            "book_value": 0.37,
            "total_assets": 951_950_195.0,
        },
        {
            "fiscal_year": 2025,
            "revenue": 0.0,
            "net_income": -18_625_674.0,
            "eps": 0.01,
            "book_value": 0.37,
            "total_assets": 950_775_600.0,
        },
    ]
    checklist = build_checklist(company, financials)
    pe_item = checklist[0]
    assert pe_item["pass"] is False
    assert is_info_incomplete(company, financials) is True
    reasons = incomplete_reasons(company, financials)
    assert "revenue" in reasons

    years = [2023, 2024, 2025]
    company_data = {
        "years": {
            2023: {
                "net_income": -19_868_783.0,
                "gross_revenue": 0.0,
                "eps": -0.01,
                "total_assets": 909_740_221.0,
                "book_value_per_share": 0.36,
            },
            2024: {
                "net_income": 1_948_301.0,
                "gross_revenue": 0.0,
                "eps": 0.0,
                "total_assets": 951_950_195.0,
                "book_value_per_share": 0.37,
            },
            2025: {
                "net_income": -18_625_674.0,
                "gross_revenue": 0.0,
                "eps": 0.01,
                "total_assets": 950_775_600.0,
                "book_value_per_share": 0.37,
            },
        }
    }
    ni = compute_growth("net_income", years, company_data)
    assert ni["yoy"] == {}
    assert ni["cagr"] is None
    rev = compute_growth("gross_revenue", years, company_data)
    assert rev["yoy"] == {}
    assets = compute_growth("total_assets", years, company_data)
    assert 2024 in assets["yoy"]
    assert cagr_rate(100, 121, 2, key="net_income") is None  # below floor
    assert abs(cagr_rate(100_000_000, 121_000_000, 2, key="net_income") - 0.1) < 1e-9


def test_roe_prefer_and_percent_parse():
    from src.parser import normalize_percent_ratio
    from src.report_metrics import prefer_roe, equity_for_roe, build_checklist

    assert abs(normalize_percent_ratio(14.54) - 0.1454) < 1e-9
    assert abs(normalize_percent_ratio(0.19) - 0.19) < 1e-9
    assert abs(normalize_percent_ratio(1.0) - 1.0) < 1e-9

    # SPC-shaped: scraped double-/100 vs NI/equity
    scraped = 0.0019
    computed = 2_222_923_486.0 / 11_568_605_349.0
    assert abs(prefer_roe(scraped, computed) - computed) < 1e-9
    assert prefer_roe(0.19, 0.192) == 0.19  # close → keep scraped
    # Correct FR -6.3% must not lose to absurd NI/E from bad equity scale
    assert prefer_roe(-0.063, -6.31) == -0.063

    company = {
        "name": "SPC Power Corporation",
        "ticker": "SPC",
        "pe_ratio": 6.53,
        "pb_ratio": 1.32,
        "roe": 0.0019,
        "last_traded_price": 10.24,
        "outstanding_shares": 1_496_551_803.0,
        "market_cap": 15_534_207_715.0,
    }
    financials = [
        {
            "fiscal_year": 2025,
            "revenue": 1.0,
            "net_income": 2_222_923_486.0,
            "eps": 1.48,
            "book_value": 7.73,
            "total_assets": 20_000_000_000.0,
            "stockholders_equity": 11_568_605_349.0,
        }
    ]
    e = equity_for_roe(financials[0], company)
    assert e is not None and abs(e - 11_568_605_349.0) < 1
    checklist = build_checklist(company, financials)
    roe_item = checklist[-1]
    assert roe_item["pass"] is True  # ~19% > 10%


def test_oi_sane_and_prefer_lfm_shaped():
    from src.report_metrics import (
        normalize_ga_expense,
        operating_income_sane,
        prefer_operating_income,
        sanitize_operating_metrics,
    )

    assert normalize_ga_expense(-105_121_007.0) == 105_121_007.0
    assert operating_income_sane(50_000_000.0, revenue=200_000_000.0, gross_profit=80_000_000.0)
    assert not operating_income_sane(
        1_375_716_349.0, revenue=1_128_654_646.0, gross_profit=72_866_661.0
    )
    assert not operating_income_sane(200.0, revenue=100.0, gross_profit=None)

    # LFM-shaped: insane OI + negative GA → prefer GP − |GA|
    row = {
        "revenue": 1_128_654_646.0,
        "operating_income": 1_375_716_349.0,
        "gross_profit": 72_866_661.0,
        "ga_expense": -105_121_007.0,
    }
    preferred = prefer_operating_income(row)
    assert preferred is not None
    assert abs(preferred - (72_866_661.0 - 105_121_007.0)) < 1

    cleaned = sanitize_operating_metrics(dict(row))
    assert cleaned["ga_expense"] == 105_121_007.0
    assert abs(cleaned["operating_income"] - preferred) < 1
    assert cleaned.get("operating_income_derived") is True

    # Sane OI below 3× GP kept
    sane_row = {
        "revenue": 500_000_000.0,
        "operating_income": 40_000_000.0,
        "gross_profit": 80_000_000.0,
        "ga_expense": 30_000_000.0,
        "net_income": 35_000_000.0,
    }
    assert prefer_operating_income(sane_row) == 40_000_000.0

    # FCG-shaped: tiny OI vs GP → reject; no GA → prefer None (proxy ROIC)
    fcg = {
        "revenue": 5_671_444_081.0,
        "operating_income": 31_940_510.0,
        "gross_profit": 2_532_297_495.0,
        "net_income": 629_573_160.0,
        "income_before_tax": 672_008_212.0,
        "ga_expense": None,
    }
    assert not operating_income_sane(
        fcg["operating_income"],
        revenue=fcg["revenue"],
        gross_profit=fcg["gross_profit"],
        net_income=fcg["net_income"],
        income_before_tax=fcg["income_before_tax"],
    )
    assert prefer_operating_income(fcg) is None
    cleaned_fcg = sanitize_operating_metrics(dict(fcg))
    assert cleaned_fcg.get("operating_income") is None

    # ALI-shaped: false mid-size OI vs IBT → reject (not equity-pickup)
    ali = {
        "revenue": 148_857_409_000.0,
        "operating_income": 1_780_865_000.0,
        "gross_profit": None,
        "net_income": 29_003_578_000.0,
        "income_before_tax": 36_460_208_000.0,
    }
    assert not operating_income_sane(
        ali["operating_income"],
        revenue=ali["revenue"],
        gross_profit=None,
        net_income=ali["net_income"],
        income_before_tax=ali["income_before_tax"],
    )
    assert prefer_operating_income(ali) is None

    # JFC-shaped: OI and GP both scale-broken vs NI → reject
    jfc = {
        "revenue": 308_012_332_000.0,
        "operating_income": 25_757_341.0,
        "gross_profit": 56_753_279.0,
        "net_income": 11_005_225_000.0,
        "ga_expense": 30_995_938.0,
    }
    assert prefer_operating_income(jfc) is None

    # AEV-shaped: tiny scraped OI, but GP−GA ≫ NI (mixed scales) → no prefer
    aev = {
        "revenue": 313_222_152.0,
        "operating_income": 27_174_042.0,
        "gross_profit": 18_997_895_526.0,
        "ga_expense": 926_460_624.0,
        "net_income": 30_600_449.0,
    }
    assert prefer_operating_income(aev) is None
    from src.report_metrics import gross_profit_sane

    assert not gross_profit_sane(
        aev["gross_profit"],
        revenue=aev["revenue"],
        net_income=aev["net_income"],
    )


def test_construct_ebit_and_derive_gp_ali_shaped():
    from src.pdf_roic_extract import match_whitelist_field
    from src.report_metrics import (
        constructed_operating_income,
        prefer_operating_income,
        sanitize_operating_metrics,
    )

    assert match_whitelist_field("Interest and other financing charges") == "interest_expense"
    assert match_whitelist_field("Interest income") is None
    assert match_whitelist_field("Interest and investment income") is None
    assert match_whitelist_field("Cost of real estate sales") == "cost_of_sales"

    # ALI FY2025 pesos (full scale) — no OI/GP lines
    row = {
        "revenue": 190_210_680_000.0,
        "cost_of_sales": 102_524_716_000.0,
        "ga_expense": 10_033_378_000.0,
        "interest_expense": 17_267_715_000.0,
        "other_expenses": 4_312_548_000.0,
        "income_before_tax": 56_072_323_000.0,
        "net_income": 45_554_129_000.0,
        "total_assets": 997_363_986_000.0,
        "operating_income": None,
        "gross_profit": None,
    }
    out = sanitize_operating_metrics(dict(row), company={"sector": "Property"})
    assert abs(out["gross_profit"] - (190_210_680_000.0 - 102_524_716_000.0)) < 1
    expected_oi = 56_072_323_000.0 + 17_267_715_000.0
    assert abs(out["operating_income"] - expected_oi) < 1
    assert out.get("operating_income_derived") is True
    assert abs(prefer_operating_income(out) - expected_oi) < 1
    assert abs(constructed_operating_income(row) - expected_oi) < 1

    # Banks: no IBT+interest synthesis
    bank = {
        "revenue": 100_000_000_000.0,
        "income_before_tax": 50_000_000_000.0,
        "interest_expense": 10_000_000_000.0,
        "net_income": 40_000_000_000.0,
        "operating_income": None,
        "gross_profit": None,
    }
    bank_out = sanitize_operating_metrics(
        dict(bank), company={"sector": "Financials", "subsector": "Banks"}
    )
    assert bank_out.get("operating_income") is None


def test_needs_pdf_oi_and_pdf_first_merge():
    from src.pdf_roic_extract import fill_html_whitelist
    from src.report_metrics import needs_pdf_oi, pdf_oi_closer_to_ibt

    ali_html = {
        "revenue": 190_210_680_000.0,
        "operating_income": 13_452_968_000.0,
        "net_income": 45_554_129_000.0,
        "income_before_tax": 56_072_323_000.0,
        "total_assets": 997_363_986_000.0,
        "cash_and_equivalents": 18_496_509_000.0,
        "total_current_liabilities": 282_827_689_000.0,
        "gross_profit": None,
        "ga_expense": 10_033_378_000.0,
    }
    good = {
        "revenue": 500_000_000.0,
        "operating_income": 80_000_000.0,
        "net_income": 60_000_000.0,
        "income_before_tax": 90_000_000.0,
        "gross_profit": 200_000_000.0,
    }
    assert needs_pdf_oi(ali_html) is True
    assert needs_pdf_oi(good) is False
    assert pdf_oi_closer_to_ibt(52_000_000_000.0, 13_452_968_000.0, 56_072_323_000.0)

    html_yearly = {2025: dict(ali_html)}
    pdf_yearly = {
        2025: {
            "operating_income": 52_000_000_000.0,
            "ga_expense": 10_033_378_000.0,
            "cash_and_equivalents": 18_496_509_000.0,
        }
    }
    merged = fill_html_whitelist(
        html_yearly,
        pdf_yearly,
        company={"sector": "Property", "subsector": "Property"},
    )
    assert abs(merged[2025]["operating_income"] - 52_000_000_000.0) < 1

    # Banks: no PDF-prefer path — sane HTML OI stays (equity ROIC mode)
    bank_html = {
        2025: {
            "revenue": 100_000_000_000.0,
            "operating_income": 45_000_000_000.0,
            "net_income": 40_000_000_000.0,
            "income_before_tax": 50_000_000_000.0,
            "total_assets": 2_000_000_000_000.0,
            "cash_and_equivalents": 50_000_000_000.0,
        }
    }
    bank_pdf = {2025: {"operating_income": 48_000_000_000.0}}
    bank_merged = fill_html_whitelist(
        bank_html,
        bank_pdf,
        company={"sector": "Financials", "subsector": "Banks"},
    )
    assert abs(bank_merged[2025]["operating_income"] - 45_000_000_000.0) < 1


def test_pl_scale_harmonize_and_ali_proxy_roic():
    from src.report_metrics import (
        compute_roic_series,
        latest_roic_fraction,
        sanitize_operating_metrics,
    )
    from src.scale_guard import harmonize_intra_year_pl_scale
    from src.parser import _pick_scored_candidate

    # JFC-shaped: OI/GP ~×1000 too small vs NI → ×1000 P&L trio
    jfc = {
        "revenue": 308_012_332_000.0,
        "operating_income": 25_757_341.0,
        "gross_profit": 56_753_279.0,
        "ga_expense": 30_995_938.0,
        "net_income": 11_005_225_000.0,
        "income_before_tax": 14_000_000_000.0,
        "total_assets": 250_000_000_000.0,
    }
    msgs = harmonize_intra_year_pl_scale(jfc)
    assert msgs, "expected P&L scale fix"
    assert jfc["operating_income"] > 1_000_000_000

    # ALI cash ×1000 + OI demotion → proxy ROIC ≥ ~6%
    ali_row = {
        "fiscal_year": 2025,
        "revenue": 190_210_680_000.0,
        "operating_income": 13_452_968_000.0,
        "gross_profit": None,
        "ga_expense": 10_033_378.0,
        "net_income": 45_554_129_000.0,
        "income_before_tax": 56_072_323_000.0,
        "income_tax_expense": 10_518_194_000.0,
        "total_assets": 997_363_986_000.0,
        "cash_and_equivalents": 18_496_509.0,
        "total_current_liabilities": 282_827_689_000.0,
        "stockholders_equity": 385_054_413_000.0,
        "total_liabilities": 612_309_573_000.0,
        "eps": 1.0,
        "book_value": 1.0,
    }
    ali_prev = {
        "fiscal_year": 2024,
        "revenue": 180_737_527_000.0,
        "operating_income": 2_174_438_000.0,
        "net_income": 34_236_233_000.0,
        "income_before_tax": 42_770_159_000.0,
        "income_tax_expense": 8_533_926_000.0,
        "total_assets": 918_754_992_000.0,
        "cash_and_equivalents": 21_507_916.0,
        "total_current_liabilities": 249_122_963_000.0,
        "stockholders_equity": 358_495_815_000.0,
        "total_liabilities": 560_259_177_000.0,
        "eps": 1.0,
        "book_value": 1.0,
    }
    for row in (ali_row, ali_prev):
        harmonize_intra_year_pl_scale(row)
        sanitize_operating_metrics(row)
    assert ali_row["cash_and_equivalents"] > 1_000_000_000
    assert ali_row.get("operating_income") is None
    company = {"sector": "Property", "subsector": "Property"}
    series = compute_roic_series([ali_prev, ali_row], company)
    assert series["mode"] == "proxy"
    latest = latest_roic_fraction(company, [ali_prev, ali_row])
    assert latest is not None and latest >= 0.06

    # Multi-candidate OI: prefer value near IBT
    picked = _pick_scored_candidate(
        "operating_income",
        [
            ("Operating income - segment A", 31_940_510.0),
            ("Operating income", 540_000_000.0),
        ],
        {"income_before_tax": 672_008_212.0, "net_income": 629_573_160.0},
    )
    assert picked == 540_000_000.0


def test_dividend_entitlement_and_yield_guards():
    from src.parser import (
        _digit_concat_trap,
        _is_entitlement_or_share_payout_text,
        _parse_dividend_rate,
        _scrub_cash_vs_property_siblings,
    )
    from src.report_metrics import compute_div_yield, plausible_cash_dps

    entitlement = (
        "Every 1 share of Liberty Flour Mills shall be given an entitlement "
        "of 97 shares of LFM Properties Corporation"
    )
    assert _is_entitlement_or_share_payout_text(entitlement)
    assert _parse_dividend_rate(entitlement) is None
    # Old digit-strip: "1" + "97" → 197
    assert _digit_concat_trap(entitlement, 197.0)
    assert _parse_dividend_rate("Php0.60") == 0.6
    assert _parse_dividend_rate("197") == 197.0  # bare number still parses

    scrubbed = _scrub_cash_vs_property_siblings(
        [
            {
                "ex_date": "2024-06-18",
                "rate": 197.0,
                "type": "cash",
                "security": "COMMON",
            },
            {
                "ex_date": "2024-06-18",
                "rate": 1.0,
                "type": "property",
                "security": "COMMON",
            },
            {
                "ex_date": "2025-10-27",
                "rate": 2.8,
                "type": "cash",
                "security": "COMMON",
            },
        ]
    )
    assert not any(
        d["type"] == "cash" and d["rate"] == 197.0 for d in scrubbed
    )
    assert any(d["rate"] == 2.8 for d in scrubbed)

    assert not plausible_cash_dps(197.0, 25.4)
    assert plausible_cash_dps(2.8, 25.4)
    assert not plausible_cash_dps(100027171502.0, 3.98)

    # Yield ignores LFM-style 197 cash even if still typed cash
    divs = [
        {
            "ex_date": "2024-06-18",
            "amount": 197.0,
            "type": "cash",
            "security": "COMMON",
            "is_common": 1,
        },
        {
            "ex_date": "2024-06-18",
            "amount": 1.0,
            "type": "property",
            "security": "COMMON",
            "is_common": 1,
        },
        {
            "ex_date": "2025-10-27",
            "amount": 2.8,
            "type": "cash",
            "security": "COMMON",
            "is_common": 1,
        },
        {
            "ex_date": "2026-01-14",
            "amount": 0.6,
            "type": "cash",
            "security": "COMMON",
            "is_common": 1,
        },
    ]
    y = compute_div_yield(25.4, divs, as_of="2026-07-16")
    assert y is not None
    assert abs(y - (3.4 / 25.4)) < 1e-9


def test_debt_to_equity_check():
    from src.report_metrics import (
        build_checklist,
        debt_to_equity_pass,
        debt_to_equity_ratio,
    )

    row = {
        "total_liabilities": 150_000_000.0,
        "stockholders_equity": 100_000_000.0,
        "total_assets": 250_000_000.0,
    }
    assert abs(debt_to_equity_ratio(row, {"sector": "Property"}) - 1.5) < 1e-9
    assert debt_to_equity_pass(1.5, 2.0) is True
    assert debt_to_equity_pass(2.5, 2.0) is False
    assert debt_to_equity_ratio(row, {"sector": "Financials", "subsector": "Banks"}) is None

    fin = [
        {
            "fiscal_year": 2024,
            "book_value": 10.0,
            "net_income": 50_000_000.0,
            "total_assets": 250_000_000.0,
            "total_liabilities": 150_000_000.0,
            "stockholders_equity": 100_000_000.0,
            "current_ratio": 1.5,
            "quick_ratio": 1.2,
            "eps": 2.0,
            "outstanding_shares": 10_000_000.0,
        },
        {
            "fiscal_year": 2025,
            "book_value": 11.0,
            "net_income": 55_000_000.0,
            "total_assets": 260_000_000.0,
            "total_liabilities": 140_000_000.0,
            "stockholders_equity": 120_000_000.0,
            "current_ratio": 1.6,
            "quick_ratio": 1.3,
            "eps": 2.2,
            "outstanding_shares": 10_000_000.0,
        },
    ]
    company = {
        "ticker": "ALI",
        "sector": "Property",
        "pe_ratio": 10.0,
        "pb_ratio": 0.8,
        "roe": 0.15,
        "outstanding_shares": 10_000_000.0,
        "last_traded_price": 25.0,
        "market_cap": 250_000_000.0,
    }
    cl = build_checklist(company, fin)
    de_item = next(i for i in cl if i["label"].startswith("Debt/Equity"))
    assert de_item["pass"] is True  # 140/120 < 2


def test_threshold_checklist_rescore():
    """Ratio thresholds rewrite labels/passes; structural checks stay put."""
    from src.report_metrics import build_checklist, checklist_score

    financials = [
        {
            "fiscal_year": 2024,
            "book_value": 10.0,
            "net_income": 40_000_000.0,
            "total_assets": 200_000_000.0,
            "total_liabilities": 80_000_000.0,
            "stockholders_equity": 120_000_000.0,
            "current_ratio": 1.5,
            "quick_ratio": 1.2,
            "eps": 2.0,
            "outstanding_shares": 10_000_000.0,
        },
        {
            "fiscal_year": 2025,
            "book_value": 11.0,
            "net_income": 48_000_000.0,
            "total_assets": 220_000_000.0,
            "total_liabilities": 90_000_000.0,
            "stockholders_equity": 130_000_000.0,
            "current_ratio": 1.6,
            "quick_ratio": 1.3,
            "eps": 2.4,
            "outstanding_shares": 10_000_000.0,
        },
    ]
    company = {
        "ticker": "DEMO",
        "name": "Demo Co",
        "sector": "Industrial",
        "pe_ratio": 15.0,
        "pb_ratio": 0.8,
        "roe": 0.12,
        "outstanding_shares": 10_000_000.0,
        "last_traded_price": 36.0,
        "market_cap": 360_000_000.0,
    }

    default_cl = build_checklist(company, financials)
    pe_default = next(i for i in default_cl if i["label"].startswith("P/E"))
    assert pe_default["label"] == "P/E Ratio < 22"
    assert pe_default["pass"] is True
    roe_default = next(i for i in default_cl if i["label"].startswith("ROE"))
    assert roe_default["label"] == "ROE > 10%"
    assert roe_default["pass"] is True
    default_pass, default_eval = checklist_score(default_cl)

    tight_pe = build_checklist(company, financials, thresholds={"pe_max": 10})
    pe_tight = next(i for i in tight_pe if i["label"].startswith("P/E"))
    assert pe_tight["label"] == "P/E Ratio < 10"
    assert pe_tight["pass"] is False

    high_roe = build_checklist(company, financials, thresholds={"roe_min": 0.20})
    roe_high = next(i for i in high_roe if i["label"].startswith("ROE"))
    assert roe_high["label"] == "ROE > 20%"
    assert roe_high["pass"] is False
    high_pass, high_eval = checklist_score(high_roe)
    assert high_eval == default_eval
    assert high_pass == default_pass - 1

    # Structural dilution / liquidity must not flip when only ratio thresholds change
    def _struct(cl):
        return {
            i["label"]: i["pass"]
            for i in cl
            if i["label"] in ("NO Share Dilution", "Quick/Current R > 1", "Increasing BV")
        }

    assert _struct(default_cl) == _struct(tight_pe) == _struct(high_roe)


def test_bank_equity_capital_return_mode():
    from src.report_metrics import compute_roic_series

    company = {
        "ticker": "BDO",
        "name": "BDO Unibank, Inc.",
        "sector": "Financials",
        "subsector": "Banks",
    }
    financials = [
        {
            "fiscal_year": 2023,
            "net_income": 70_000_000_000.0,
            "stockholders_equity": 500_000_000_000.0,
            "total_assets": 4_000_000_000_000.0,
        },
        {
            "fiscal_year": 2024,
            "net_income": 80_000_000_000.0,
            "stockholders_equity": 550_000_000_000.0,
            "total_assets": 4_200_000_000_000.0,
        },
    ]
    result = compute_roic_series(financials, company)
    assert result["mode"] == "equity"
    assert len(result["series"]) == 2
    # 2023: NI / equity end (no prior) = 70/500 = 14%
    assert abs(result["series"][0]["value"] - 14.0) < 1e-9
    # 2024: NI / avg equity = 80 / 525 ≈ 15.238%
    assert abs(result["series"][1]["value"] - (80_000_000_000.0 / 525_000_000_000.0) * 100) < 1e-9

    industrial = compute_roic_series(
        financials,
        {"ticker": "JFC", "sector": "Industrial", "subsector": "Food"},
    )
    assert industrial["mode"] != "equity"


if __name__ == "__main__":
    test_pe_rejects_negative()
    test_growth_skips_sign_flip_and_tiny_base()
    test_zero_revenue_eps_missing()
    test_display_sanitizes_loss_ratios()
    test_ab_checklist_and_growth_overview()
    test_roe_prefer_and_percent_parse()
    test_oi_sane_and_prefer_lfm_shaped()
    test_construct_ebit_and_derive_gp_ali_shaped()
    test_needs_pdf_oi_and_pdf_first_merge()
    test_pl_scale_harmonize_and_ali_proxy_roic()
    test_dividend_entitlement_and_yield_guards()
    test_debt_to_equity_check()
    test_threshold_checklist_rescore()
    test_bank_equity_capital_return_mode()
    print("ok")
