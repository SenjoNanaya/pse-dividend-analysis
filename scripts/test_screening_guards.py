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


if __name__ == "__main__":
    test_pe_rejects_negative()
    test_growth_skips_sign_flip_and_tiny_base()
    test_zero_revenue_eps_missing()
    test_display_sanitizes_loss_ratios()
    test_ab_checklist_and_growth_overview()
    print("ok")
