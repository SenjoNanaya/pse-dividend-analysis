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
    data_warnings,
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


def test_persist_pe_guards_absurd_and_secondary():
    from src.parser import (
        resolve_valuation_fallbacks,
        sanitize_pe_for_persist,
    )

    assert sanitize_pe_for_persist(2449) is None
    assert sanitize_pe_for_persist(-1040) is None
    assert sanitize_pe_for_persist(0) is None
    assert sanitize_pe_for_persist(15.2) == 15.2

    absurd = resolve_valuation_fallbacks(
        {
            "ticker": "ATN",
            "pe_ratio": 2449.0,
            "last_traded_price": 0.415,
        },
        {2025: {"eps": 0.0003, "net_income": 1_000_000}},
    )
    assert absurd.get("pe_ratio") is None

    near_zero = resolve_valuation_fallbacks(
        {
            "ticker": "CTS",
            "pe_ratio": None,
            "last_traded_price": 0.38,
        },
        {2025: {"eps": 0.0004, "net_income": 2_000_000}},
    )
    assert near_zero.get("pe_ratio") is None
    assert near_zero.get("pe_source") == "near_zero_eps_blank"

    zero_pe = resolve_valuation_fallbacks(
        {
            "ticker": "BHI",
            "pe_ratio": 0.0,
            "last_traded_price": 0.04,
        },
        {2025: {"eps": -0.008, "net_income": -1_000_000}},
    )
    assert zero_pe.get("pe_ratio") is None

    fund = resolve_valuation_fallbacks(
        {
            "ticker": "FMETF",
            "pe_ratio": 100.01,
            "last_traded_price": 107.0,
        },
        {2025: {"eps": 1.0, "net_income": 10_000_000}},
    )
    assert fund.get("pe_ratio") is None
    assert fund.get("pe_source") == "fund_pe_blank"

    ffi = resolve_valuation_fallbacks(
        {
            "ticker": "FFI",
            "pe_ratio": 326.0,
            "last_traded_price": 7.71,
        },
        {2025: {"eps": 0.02, "net_income": 1_000_000}},
    )
    assert ffi.get("pe_ratio") is None

    kept = resolve_valuation_fallbacks(
        {
            "ticker": "JFC",
            "pe_ratio": 15.2,
            "last_traded_price": 200.0,
        },
        {2025: {"eps": 13.0, "net_income": 10_000_000_000}},
    )
    assert kept.get("pe_ratio") == 15.2

    mfc = resolve_valuation_fallbacks(
        {
            "ticker": "MFC",
            "pe_ratio": 796.75,
            "last_traded_price": 2454.0,
        },
        {2025: {"eps": 3.08}},
    )
    assert mfc.get("pe_ratio") is None
    assert mfc.get("pe_source") == "secondary_listing_blank"

    slf_compute = resolve_valuation_fallbacks(
        {
            "ticker": "SLF",
            "pe_ratio": None,
            "last_traded_price": 4754.0,
        },
        {2025: {"eps": 6.17}},
    )
    assert slf_compute.get("pe_ratio") is None


def test_roic_absurd_guard_skips_and_warns():
    from src.report_metrics import (
        compute_roic_series,
        data_warnings,
        latest_roic_fraction,
    )

    company = {
        "name": "Shell Co",
        "ticker": "ZHI",
        "sector": "Holding Firms",
        "subsector": "Holding Firms",
    }
    # Tiny invested capital → ROIC >> 100%
    financials = [
        {
            "fiscal_year": 2024,
            "net_income": 10_000_000.0,
            "operating_income": 12_000_000.0,
            "total_assets": 50_000_000.0,
            "cash_and_equivalents": 49_000_000.0,
            "total_current_liabilities": 500_000.0,
            "stockholders_equity": 400_000.0,
        },
        {
            "fiscal_year": 2025,
            "net_income": 15_000_000.0,
            "operating_income": 18_000_000.0,
            "total_assets": 50_000_000.0,
            "cash_and_equivalents": 49_000_000.0,
            "total_current_liabilities": 500_000.0,
            "stockholders_equity": 400_000.0,
        },
    ]
    series = compute_roic_series(financials, company)
    for pt in series.get("series") or []:
        assert abs(pt["value"]) <= 100
    assert latest_roic_fraction(company, financials) is None
    warns = data_warnings(company, financials)
    assert "absurd_roic" in warns

    normal = {
        "name": "Normal Co",
        "ticker": "XYZ",
        "sector": "Industrial",
        "subsector": "Food, Beverage & Tobacco",
    }
    normal_fins = [
        {
            "fiscal_year": 2024,
            "net_income": 1_200_000_000.0,
            "operating_income": 1_600_000_000.0,
            "total_assets": 20_000_000_000.0,
            "cash_and_equivalents": 2_000_000_000.0,
            "total_current_liabilities": 3_000_000_000.0,
            "stockholders_equity": 10_000_000_000.0,
        },
        {
            "fiscal_year": 2025,
            "net_income": 1_400_000_000.0,
            "operating_income": 1_800_000_000.0,
            "total_assets": 22_000_000_000.0,
            "cash_and_equivalents": 2_200_000_000.0,
            "total_current_liabilities": 3_200_000_000.0,
            "stockholders_equity": 11_000_000_000.0,
        },
    ]
    frac = latest_roic_fraction(normal, normal_fins)
    assert frac is not None and 0.05 < frac < 0.25


def test_loss_year_and_rich_pe_blanked():
    from src.parser import resolve_valuation_fallbacks, sanitize_pe_for_persist

    assert sanitize_pe_for_persist(150) is None
    assert sanitize_pe_for_persist(99) == 99.0

    loss = resolve_valuation_fallbacks(
        {
            "ticker": "AT",
            "pe_ratio": 87.0,
            "last_traded_price": 8.75,
        },
        {2025: {"eps": -0.06, "net_income": -246_000_000}},
    )
    assert loss.get("pe_ratio") is None
    assert loss.get("pe_source") == "loss_year_pe_blank"

    rich = resolve_valuation_fallbacks(
        {
            "ticker": "CTS",
            "pe_ratio": 900.0,
            "last_traded_price": 0.38,
        },
        {2025: {"eps": 0.0004, "net_income": 2_000_000}},
    )
    assert rich.get("pe_ratio") is None


def test_thin_capital_nulls_persisted_roic():
    from src.report_metrics import data_warnings, latest_roic_fraction

    company = {
        "name": "Thin Cap",
        "ticker": "SHELL",
        "sector": "Holding Firms",
        "subsector": "Holding Firms",
    }
    # IC ~ assets−cash−CL = 1e6; assets 200e6 → 0.5% < 1% thin capital
    financials = [
        {
            "fiscal_year": 2024,
            "net_income": 50_000.0,
            "operating_income": 60_000.0,
            "total_assets": 200_000_000.0,
            "cash_and_equivalents": 198_000_000.0,
            "total_current_liabilities": 1_000_000.0,
            "stockholders_equity": 500_000.0,
        },
        {
            "fiscal_year": 2025,
            "net_income": 80_000.0,
            "operating_income": 90_000.0,
            "total_assets": 200_000_000.0,
            "cash_and_equivalents": 198_000_000.0,
            "total_current_liabilities": 1_000_000.0,
            "stockholders_equity": 500_000.0,
        },
    ]
    assert latest_roic_fraction(company, financials) is None
    assert "thin_invested_capital" in data_warnings(company, financials)


def test_eps_plausible_rejects_scale_mismatch():
    from src.report_metrics import eps_plausible

    row = {
        "net_income": 2_650_000.0,
        "outstanding_shares": 3_500_000_000.0,
    }
    # Implied EPS ~0.00076; PDF-style 265 is >10× off and > price
    assert not eps_plausible(265.0, row, price=4.2)
    assert eps_plausible(0.00076, row, price=4.2)


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
    # Chronic zero-revenue shells are complete for screening; soft-warn instead
    assert is_info_incomplete(company, financials) is False
    reasons = incomplete_reasons(company, financials)
    assert "revenue" not in reasons
    warns = data_warnings(
        {**company, "sector": "Property", "subsector": "Property"},
        financials,
    )
    assert "no_commercial_revenue" in warns
    assert "no_cash_for_proper_roic" in warns

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
    # Stand-alone interest income is a revenue surrogate for holdings/miners (not NII)
    assert match_whitelist_field("Interest income") == "interest_income"
    assert match_whitelist_field("Interest and investment income") == "interest_income"
    assert match_whitelist_field("Net interest income") == "net_interest_income"
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
    from src.report_metrics import compute_roic_series, data_warnings

    company = {
        "ticker": "BDO",
        "name": "BDO Unibank, Inc.",
        "sector": "Financials",
        "subsector": "Banks",
    }
    assert "industrial_roic_na_use_equity" in data_warnings(
        company,
        [
            {
                "fiscal_year": 2024,
                "revenue": 1.0,
                "net_income": 1.0,
                "total_assets": 1.0,
                "eps": 1.0,
                "book_value": 1.0,
            }
        ],
    )
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


def test_bank_checklist_loans_deposits_npl_nii():
    from src.pdf_roic_extract import match_whitelist_field, rows_to_yearly_metrics
    from src.pdf_adapters.sequential_p import parse_sequential_p
    from src.report_metrics import build_checklist, structural_checklist_score
    from src.parser import _label_matches_metric

    assert match_whitelist_field("Loans and receivables - net") == "total_loans"
    assert match_whitelist_field("Loans and other receivables - net") == "total_loans"
    assert match_whitelist_field("Loans and receivables at amortized cost") == (
        "total_loans"
    )
    assert match_whitelist_field("Loans and advances, net") == "total_loans"
    assert match_whitelist_field("Non-performing loans") == "npl"
    assert match_whitelist_field("Total Non-performing") == "npl"
    assert match_whitelist_field("Deposit liabilities") == "total_deposits"
    assert match_whitelist_field("Total deposits") == "total_deposits"
    assert match_whitelist_field("Net interest income") == "net_interest_income"
    assert match_whitelist_field("Allowance for credit losses") == (
        "allowance_for_credit_losses"
    )
    assert match_whitelist_field("Allowance for impairment") == (
        "allowance_for_credit_losses"
    )
    assert match_whitelist_field("Cash and short-term deposits") != "total_deposits"
    assert match_whitelist_field("Non-performing loans") != "total_loans"
    # BPI / bank IS: interest-income sub-line must not become total_loans
    assert match_whitelist_field("On loans and advances") is None
    assert match_whitelist_field("Interest income on loans and advances") is None
    assert match_whitelist_field(
        "Breakdown of performing and non-performing loans net of allowance"
    ) is None
    assert _label_matches_metric(
        "net interest income", "net interest income", "net_interest_income"
    )
    assert not _label_matches_metric(
        "cash and short-term deposits", "total deposits", "total_deposits"
    )
    assert not _label_matches_metric(
        "on loans and advances", "loans and advances", "total_loans"
    )

    from src.pdf_roic_extract import fill_html_whitelist

    # Financials: PDF loan book must overwrite HTML interest-income false positive
    merged_bank = fill_html_whitelist(
        {
            2025: {
                "total_loans": 183_758_000_000.0,
                "total_deposits": 2_838_525_000_000.0,
                "total_assets": 3_651_488_000_000.0,
            }
        },
        {2025: {"total_loans": 2_567_131_000_000.0}},
        company={"sector": "Financials", "subsector": "Banks", "ticker": "BPI"},
    )
    assert abs(merged_bank[2025]["total_loans"] - 2_567_131_000_000.0) < 1

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    text = open(
        os.path.join(root, "fixtures", "roic", "bank_bs_is_snippet.txt"),
        encoding="utf-8",
    ).read()
    rows = parse_sequential_p(text, years=[2025, 2024])
    yearly = rows_to_yearly_metrics(rows, scale=1.0, statement_scope="consolidated")
    assert abs(yearly[2025]["total_loans"] - 1_850_000_000) < 1
    assert abs(yearly[2024]["total_deposits"] - 1_950_000_000) < 1
    assert abs(yearly[2025]["npl"] - 42_000_000) < 1
    assert abs(yearly[2025]["net_interest_income"] - 95_000_000) < 1
    assert abs(yearly[2025]["allowance_for_credit_losses"] - 38_000_000) < 1

    from src.pdf_roic_extract import extract_bsp_npl_totals

    bsp_snip = """
    Breakdown of performing and non-performing loans net of allowance for credit losses,
    as reported to the BSP, are as follows:
    2,533,841
    56,866
    2,590,707
    2,226,400
    48,364
    2,274,764
    Allowance for
    probable losses
    """
    bsp_npl = extract_bsp_npl_totals(bsp_snip, [2025, 2024], scale=1_000_000)
    assert abs(bsp_npl[2025] - 56_866_000_000) < 1
    assert abs(bsp_npl[2024] - 48_364_000_000) < 1

    company = {
        "ticker": "BPI",
        "sector": "Financials",
        "subsector": "Banks",
        "pe_ratio": 10.0,
        "pb_ratio": 0.8,
        "roe": 0.15,
        "last_traded_price": 100.0,
        "outstanding_shares": 1e9,
    }
    fins = [
        {
            "fiscal_year": 2024,
            "net_income": 40_000_000.0,
            "eps": 4.0,
            "book_value": 10.0,
            "total_assets": 2_800_000_000.0,
            "stockholders_equity": 250_000_000.0,
            "total_loans": 1_700_000_000.0,
            "total_deposits": 1_950_000_000.0,
            "npl": 50_000_000.0,
            "net_interest_income": 88_000_000.0,
        },
        {
            "fiscal_year": 2025,
            "net_income": 45_000_000.0,
            "eps": 4.5,
            "book_value": 11.0,
            "total_assets": 3_000_000_000.0,
            "stockholders_equity": 280_000_000.0,
            "total_loans": 1_850_000_000.0,
            "total_deposits": 2_100_000_000.0,
            "npl": 42_000_000.0,
            "net_interest_income": 95_000_000.0,
        },
    ]
    cl = build_checklist(company, fins)
    by_label = {i["label"]: i["pass"] for i in cl}
    assert "Loan growth YoY > 0" in by_label
    assert by_label["Loan growth YoY > 0"] is True
    assert by_label["Deposit growth YoY > 0"] is True
    assert by_label["Loans/Deposits < 1.05"] is True
    assert by_label["NPL ratio < 5%"] is True
    assert by_label["Equity/Assets ≥ 8%"] is True
    assert by_label["NII growth YoY > 0 (or NIM proxy)"] is True
    assert "Quick/Current R > 1" not in by_label
    assert "Increasing BV" not in by_label
    struct_pass, struct_eval = structural_checklist_score(cl, company)
    assert struct_eval == 6  # all bank mid slots including NII
    assert struct_pass == 6

    # Missing NPL → NA on that slot
    thin = [dict(fins[0]), dict(fins[1])]
    thin[1]["npl"] = None
    thin[0]["npl"] = None
    cl2 = build_checklist(company, thin)
    assert {i["label"]: i["pass"] for i in cl2}["NPL ratio < 5%"] is None


def test_derive_ni_from_eps_shares():
    from src.report_metrics import derive_ni_from_eps_shares, incomplete_reasons
    from src.pdf_roic_extract import fill_html_whitelist

    row = {
        "eps": -0.3,
        "net_income": None,
        "outstanding_shares": 1_000_000_000.0,
        "revenue": 1e10,
        "total_assets": 5e10,
        "book_value": 1.0,
    }
    ni = derive_ni_from_eps_shares(row)
    assert ni is not None and abs(ni - (-300_000_000.0)) < 1

    merged = fill_html_whitelist(
        {
            2025: {
                "eps": -0.65,
                "net_income": None,
                "outstanding_shares": 500_000_000.0,
                "revenue": 1e8,
                "total_assets": 1e9,
                "book_value": 9.0,
            }
        },
        {},
        company={"ticker": "PRC", "outstanding_shares": 500_000_000.0},
    )
    assert abs(merged[2025]["net_income"] - (-325_000_000.0)) < 1
    assert merged[2025].get("_field_sources", {}).get("net_income") == "derived"

    # ABSP-shaped: NI≈0 and EPS=0 is complete
    reasons = incomplete_reasons(
        {"ticker": "ABSP", "name": "ABSP"},
        [
            {
                "fiscal_year": 2025,
                "revenue": 2_500_000.0,
                "net_income": 0.0,
                "eps": 0.0,
                "total_assets": 1e8,
                "book_value": 0.0,
            }
        ],
    )
    assert "eps" not in reasons


def test_derive_bv_and_negative_revenue_clear():
    from src.pdf_roic_extract import fill_html_whitelist, _sane_absolute
    from src.report_metrics import (
        clear_invalid_derived_revenue,
        derive_book_value_per_share,
        metric_value,
    )

    bv = derive_book_value_per_share(
        {
            "book_value": None,
            "stockholders_equity": 3_596_575_505.0,
            "outstanding_shares": 3_596_575_505.0,
        }
    )
    assert bv is not None and abs(bv - 1.0) < 1e-9

    merged = fill_html_whitelist(
        {
            2025: {
                "stockholders_equity": 3_859_000_000.0,
                "outstanding_shares": 3_596_575_505.0,
                "revenue": 900_000_000.0,
                "net_income": 200_000_000.0,
                "eps": 0.05,
                "total_assets": 10_000_000_000.0,
            }
        },
        {},
        company={"ticker": "FGEN", "outstanding_shares": 3_596_575_505.0},
    )
    assert merged[2025].get("book_value") is not None
    assert abs(merged[2025]["book_value"] - (3_859_000_000.0 / 3_596_575_505.0)) < 1e-6

    bad = {"revenue": -343045.0, "_field_sources": {"revenue": "derived"}}
    assert clear_invalid_derived_revenue(bad) is True
    assert bad.get("revenue") is None
    assert metric_value(-100.0, "revenue") is None
    assert not _sane_absolute(-1_000_000.0, "cash_and_equivalents")

    from src.pdf_roic_extract import _coerce_pdf_cash

    down, reason = _coerce_pdf_cash(
        2_423_306_484_000.0,
        {"total_assets": 622_797_852_000.0},
    )
    assert reason == "pdf_thousands"
    assert down is not None and abs(down - 2_423_306_484.0) < 1


def test_revenue_surrogate_holdings_and_miners():
    from src.filing_triage import allows_revenue_surrogate
    from src.pdf_roic_extract import rows_to_yearly_metrics
    from src.pdf_adapters.sequential_p import parse_sequential_p
    from src.report_metrics import apply_revenue_surrogate, incomplete_reasons

    assert allows_revenue_surrogate("Holding Firms", "Holding Firms")
    assert allows_revenue_surrogate("Mining and Oil", "Mining")
    assert allows_revenue_surrogate("Services", "Hotel & Leisure")
    assert not allows_revenue_surrogate("Financials", "Banks")
    shell_fins = [
        {"revenue": 0.0, "net_income": -1e6},
        {"revenue": None, "net_income": -2e6},
    ]
    assert allows_revenue_surrogate(
        "Industrial", "Food, Beverage & Tobacco", financials=shell_fins
    )

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    hold = open(
        os.path.join(root, "fixtures", "roic", "holding_equity_earnings_revenue.txt"),
        encoding="utf-8",
    ).read()
    rows = parse_sequential_p(hold, years=[2025, 2024])
    yearly = rows_to_yearly_metrics(rows, scale=1.0, statement_scope="consolidated")
    co = {"sector": "Holding Firms", "subsector": "Holding Firms", "ticker": "PA"}
    assert apply_revenue_surrogate(yearly[2025], co) == "equity_in_earnings"
    assert abs(yearly[2025]["revenue"] - 125_000_000) < 1

    mine = open(
        os.path.join(root, "fixtures", "roic", "mining_interest_income_revenue.txt"),
        encoding="utf-8",
    ).read()
    rows_m = parse_sequential_p(mine, years=[2025, 2024])
    yearly_m = rows_to_yearly_metrics(rows_m, scale=1.0, statement_scope="consolidated")
    co_m = {"sector": "Mining and Oil", "subsector": "Mining", "ticker": "AB"}
    assert apply_revenue_surrogate(yearly_m[2025], co_m) == "interest_income"
    assert abs(yearly_m[2025]["revenue"] - 8_200_000) < 1

    reasons = incomplete_reasons(
        co_m,
        [
            {
                "fiscal_year": 2025,
                "interest_income": 8_200_000,
                "net_income": -15_000_000,
                "total_assets": 450_000_000,
                "eps": -0.1,
                "book_value": 5.0,
            }
        ],
    )
    assert "revenue" not in reasons


def test_waive_revenue_chronic_shell_bank_etf():
    from src.report_metrics import data_warnings, derive_ni_from_ibt, incomplete_reasons

    shell = {
        "ticker": "ACE",
        "name": "ACE",
        "sector": "Services",
        "subsector": "Hotel & Leisure",
    }
    shell_fins = [
        {
            "fiscal_year": 2024,
            "revenue": 0.0,
            "net_income": -1e6,
            "total_assets": 1e8,
            "eps": -0.1,
            "book_value": 1.0,
        },
        {
            "fiscal_year": 2025,
            "revenue": None,
            "net_income": -2e6,
            "total_assets": 9e7,
            "eps": -0.2,
            "book_value": 0.9,
        },
    ]
    assert "revenue" not in incomplete_reasons(shell, shell_fins)
    assert "no_commercial_revenue" in data_warnings(shell, shell_fins)

    bank = {
        "ticker": "NXGEN",
        "name": "NXGEN",
        "sector": "Financials",
        "subsector": "Banks",
    }
    bank_fins = [
        {
            "fiscal_year": 2025,
            "revenue": None,
            "net_income": -1e6,
            "total_assets": 5e8,
            "eps": -0.01,
            "book_value": 0.5,
        }
    ]
    assert "revenue" not in incomplete_reasons(bank, bank_fins)
    assert "no_commercial_revenue" in data_warnings(bank, bank_fins)

    etf = {
        "ticker": "FMETF",
        "name": "FMETF",
        "sector": "ETF",
        "subsector": "ETF-Equity",
    }
    etf_fins = [
        {
            "fiscal_year": 2024,
            "revenue": 1e6,
            "net_income": -1e5,
            "total_assets": 1e9,
            "eps": -0.01,
            "book_value": 10.0,
        },
        {
            "fiscal_year": 2025,
            "revenue": -49587945.0,
            "net_income": -6e7,
            "total_assets": 1e9,
            "eps": -0.05,
            "book_value": 9.0,
        },
    ]
    # Prior year has commercial revenue → one-year hole, do not waive
    # (negative latest is missing, but prior positive blocks chronic path;
    # ETF sector still waives)
    assert "revenue" not in incomplete_reasons(etf, etf_fins)

    hole = {
        "ticker": "MRC",
        "name": "MRC",
        "sector": "Property",
        "subsector": "Property",
    }
    hole_fins = [
        {
            "fiscal_year": 2024,
            "revenue": 50_000_000.0,
            "net_income": -1e6,
            "total_assets": 1e9,
            "eps": -0.1,
            "book_value": 5.0,
        },
        {
            "fiscal_year": 2025,
            "revenue": None,
            "net_income": -2e6,
            "total_assets": 1e9,
            "eps": -0.2,
            "book_value": 4.5,
        },
    ]
    assert "revenue" in incomplete_reasons(hole, hole_fins)

    sun = {
        "ticker": "SUN",
        "name": "SUN",
        "sector": "Property",
        "subsector": "Property",
    }
    sun_fins = [
        {
            "fiscal_year": 2025,
            "revenue": 575170.0,
            "net_income": None,
            "eps": -4.15,
            "income_before_tax": -30_116_051_137.0,
            "income_tax_expense": 5_858_279.0,
            "total_assets": 4_946_875_140.0,
            "book_value": -2.97,
            "outstanding_shares": 7_250_000_000.0,
        }
    ]
    assert "net_income" in incomplete_reasons(sun, sun_fins)
    ni = derive_ni_from_ibt(sun_fins[0])
    assert ni is not None and abs(ni - (-30_121_909_416.0)) < 1


def test_bank_peer_fixtures_and_guards():
    from src.filing_triage import is_banks_subsector, is_financial_sector
    from src.pdf_roic_extract import (
        _sanitize_bank_statement_row,
        _scale_aq_to_loans,
        match_whitelist_field,
        rows_to_yearly_metrics,
    )
    from src.pdf_adapters.sequential_p import parse_sequential_p
    from src.report_metrics import build_checklist

    assert is_banks_subsector("Financials", "Banks")
    assert not is_banks_subsector("Financials", "Other Financial Institutions")
    assert is_financial_sector("Financials", "Other Financial Institutions")

    # Other FI: industrial mid-checklist, not loan/NPL slots
    other_fi = {
        "ticker": "COL",
        "sector": "Financials",
        "subsector": "Other Financial Institutions",
        "pe_ratio": 10.0,
        "pb_ratio": 1.0,
        "roe": 0.12,
        "last_traded_price": 50.0,
        "outstanding_shares": 1e9,
    }
    cl = build_checklist(
        other_fi,
        [
            {
                "fiscal_year": 2024,
                "net_income": 1e9,
                "eps": 1.0,
                "book_value": 10.0,
                "total_assets": 5e9,
                "stockholders_equity": 2e9,
            },
            {
                "fiscal_year": 2025,
                "net_income": 1.2e9,
                "eps": 1.2,
                "book_value": 11.0,
                "total_assets": 5.5e9,
                "stockholders_equity": 2.2e9,
            },
        ],
    )
    labels = [c["label"] for c in cl]
    assert "Loan growth YoY > 0" not in labels
    assert "Increasing BV" in labels

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _yearly(name, years):
        text = open(
            os.path.join(root, "fixtures", "roic", name), encoding="utf-8"
        ).read()
        rows = parse_sequential_p(text, years=years)
        return rows_to_yearly_metrics(rows, scale=1.0, statement_scope="consolidated")

    bdo = _yearly("bank_bdo_loans_amortized.txt", [2025, 2024])
    assert abs(bdo[2025]["total_loans"] - 2_450_000_000_000) < 1
    assert abs(bdo[2025]["total_deposits"] - 3_100_000_000_000) < 1

    aub = _yearly("bank_aub_npl_acl.txt", [2024, 2023])
    assert abs(aub[2024]["npl"] - 3_461_528_000) < 1
    assert abs(aub[2024]["allowance_for_credit_losses"] - 4_223_036_000) < 1

    mbt = _yearly("bank_mbt_deposit_false_positive.txt", [2025, 2024])
    _sanitize_bank_statement_row(mbt[2025])
    assert mbt[2025].get("total_deposits") is None
    assert mbt[2025].get("total_loans") is not None

    acl_row = {
        "total_loans": 1_976_438_000_000.0,
        "allowance_for_credit_losses": 51_877.0,
        "npl": 38_500.0,
        "total_assets": 3_500_000_000_000.0,
    }
    _sanitize_bank_statement_row(acl_row)
    assert abs(acl_row["allowance_for_credit_losses"] - 51_877_000_000.0) < 1
    assert abs(acl_row["npl"] - 38_500_000_000.0) < 1

    lifted = _scale_aq_to_loans(
        51_877.0, 1_976_438_000_000.0, lo_ratio=0.0005, hi_ratio=0.25
    )
    assert lifted is not None and abs(lifted - 51_877_000_000.0) < 1

    assert match_whitelist_field("Allowance for expected credit losses") == (
        "allowance_for_credit_losses"
    )


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
    test_bank_checklist_loans_deposits_npl_nii()
    test_derive_ni_from_eps_shares()
    test_derive_bv_and_negative_revenue_clear()
    test_revenue_surrogate_holdings_and_miners()
    test_waive_revenue_chronic_shell_bank_etf()
    test_bank_peer_fixtures_and_guards()
    print("ok")
