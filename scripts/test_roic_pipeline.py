"""Smoke tests for ROIC PDF triage / adapters / sector gate (no multi-MB PDFs)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.filing_triage import (
    is_financial_sector,
    rank_attachments,
    select_attachments_to_download,
)
from src.pdf_adapters.sequential_p import parse_sequential_p
from src.pdf_adapters.notes_column import parse_notes_column
from src.pdf_roic_extract import (
    is_blacklisted_operating_label,
    match_whitelist_field,
    rows_to_yearly_metrics,
)


FIX = os.path.join(ROOT, "fixtures", "roic")


def test_triage_skips_integrated_prefers_17a():
    atts = [
        {"file_id": "1", "filename": "2024 BPI Integrated Report.pdf"},
        {"file_id": "2", "filename": "MSRD_SPC_SEC Form 17-A_Part 2 of 3.pdf"},
        {"file_id": "3", "filename": "Alliance Global Group Inc AFS 2024 [Parent].pdf"},
        {"file_id": "4", "filename": "Alliance Global Group Inc and Subsidiaries Annual Report 2024.pdf"},
    ]
    ranked = rank_attachments(atts)
    assert ranked[0]["skip"] is False
    selected = select_attachments_to_download(atts)
    names = [a["filename"].lower() for a in selected]
    assert not any("integrated" in n for n in names)
    assert any("17-a" in n or "17a" in n or "afs" in n or "part" in n for n in names)


def test_financial_sector_gate():
    assert is_financial_sector("Financials", "Banks")
    assert is_financial_sector("Banks")
    assert not is_financial_sector("Property", "Real Estate")


def test_spc_cf_trap_blacklisted():
    assert is_blacklisted_operating_label(
        "Operating income before working capital changes"
    )
    assert match_whitelist_field(
        "Operating income before working capital changes"
    ) is None


def test_spc_parent_fixture_cash_cl():
    text = open(os.path.join(FIX, "spc_parent_fs.txt"), encoding="utf-8").read()
    rows = parse_sequential_p(text, years=[2025, 2024, 2023])
    yearly = rows_to_yearly_metrics(rows, scale=1.0, statement_scope="parent")
    assert 2025 in yearly
    assert abs(yearly[2025]["cash_and_equivalents"] - 4_956_904_737) < 1
    assert abs(yearly[2025]["total_current_liabilities"] - 1_513_676_484) < 1
    assert abs(yearly[2025]["total_assets"] - 9_027_378_119) < 1
    # CF trap must not become operating_income
    # Derived from GP - GA instead
    assert yearly[2025].get("gross_profit") is not None
    assert yearly[2025].get("ga_expense") is not None
    assert yearly[2025].get("operating_income") is not None
    assert abs(
        yearly[2025]["operating_income"]
        - (1_020_122_734 - 222_772_169)
    ) < 1


def test_agi_parent_vs_conso_cash_order():
    parent = open(os.path.join(FIX, "agi_parent_bs.txt"), encoding="utf-8").read()
    conso = open(os.path.join(FIX, "agi_conso_bs_snippet.txt"), encoding="utf-8").read()
    py = rows_to_yearly_metrics(
        parse_notes_column(parent, years=[2024, 2023]),
        statement_scope="parent",
    )
    cy = rows_to_yearly_metrics(
        parse_notes_column(conso, years=[2024, 2023]),
        statement_scope="consolidated",
    )
    assert py[2024]["cash_and_equivalents"] < 3_000_000_000
    assert cy[2024]["cash_and_equivalents"] > 50_000_000_000


def test_disclosure_html_attachments():
    from src.parser import parse_disclosure_attachments

    html = open(
        os.path.join(FIX, "disclosure.html"), encoding="utf-8"
    ).read()
    atts = parse_disclosure_attachments(html)
    assert len(atts) == 3
    assert atts[0]["file_id"] == "1895123"


def test_plausible_years_and_fill_no_orphan_keys():
    from src.pdf_roic_extract import fill_html_whitelist, plausible_fiscal_years

    assert plausible_fiscal_years([2023, 2024, 2031, 2050, 1990]) == [2024, 2023]
    html = {2024: {"net_income": 1.0, "total_assets": 1e9}, 2023: {"net_income": 1.0}}
    pdf = {
        2024: {"cash_and_equivalents": 5e8},
        2031: {"total_assets": 78.1, "cash_and_equivalents": 1e6},
    }
    merged = fill_html_whitelist(html, pdf)
    assert 2031 not in merged
    assert merged[2024]["cash_and_equivalents"] == 5e8


def test_fill_html_nulls_and_rejects():
    from src.parser import _reconcile_balance_sheet
    from src.pdf_roic_extract import fill_html_whitelist

    html = {
        2023: {
            "total_assets": 181_000_000_000.0,
            "total_liabilities": 86_000_000_000.0,
            "stockholders_equity": 95_000_000_000.0,
        }
    }
    pdf = {
        2023: {
            "total_assets": 18_000_000_000.0,  # must not overwrite
            "cash_and_equivalents": -1_000_000.0,  # reject negative
        }
    }
    merged = fill_html_whitelist(html, pdf)
    assert merged[2023]["total_assets"] == 181_000_000_000.0
    assert merged[2023].get("cash_and_equivalents") is None

    html2 = {2024: {"total_assets": 1e11}}
    pdf2 = {2024: {"cash_and_equivalents": 5e9}}
    merged2 = fill_html_whitelist(html2, pdf2)
    assert merged2[2024]["cash_and_equivalents"] == 5e9

    # Identity repair: tiny A vs coherent L+E
    broken = {
        "total_assets": 18_481_934_988.0,
        "total_liabilities": 86_671_575_592.0,
        "stockholders_equity": 94_568_371_283.0,
    }
    fixed = _reconcile_balance_sheet(dict(broken))
    assert abs(fixed["total_assets"] - (86_671_575_592.0 + 94_568_371_283.0)) < 1


def test_html_cash_labels_and_year_junk():
    import pandas as pd
    from src.parser import (
        CASH_BS_PATTERNS,
        CASH_CF_ENDING_PATTERNS,
        _extract_metric_value,
        _label_is_cf_ending_cash,
        _label_matches_metric,
        _reconcile_balance_sheet,
        extract_all_years_metrics,
    )

    assert _label_matches_metric(
        "Cash on hand and in banks",
        "cash on hand and in banks",
        "cash_and_equivalents",
    )
    assert _label_matches_metric(
        "Cash and short-term deposits",
        "cash and short-term deposits",
        "cash_and_equivalents",
    )
    assert _label_matches_metric("Cash", "cash", "cash_and_equivalents")
    assert not _label_matches_metric(
        "Cash flows from operating activities",
        "cash",
        "cash_and_equivalents",
    )
    assert not _label_matches_metric(
        "Cash dividends declared during the year and other long prose",
        "cash",
        "cash_and_equivalents",
    )
    assert _label_is_cf_ending_cash("Cash and cash equivalents at end of year")
    assert not _label_is_cf_ending_cash(
        "Cash and cash equivalents at beginning of year"
    )

    combined = pd.DataFrame(
        {
            2024: [5_432_100_000.0, 100_000_000_000.0],
            2023: [4_100_000_000.0, 90_000_000_000.0],
        },
        index=["Cash on hand and in banks", "Total Assets"],
    )
    cash = _extract_metric_value(
        combined,
        2024,
        CASH_BS_PATTERNS,
        1.0,
        "cash_and_equivalents",
    )
    assert abs(cash - 5_432_100_000.0) < 1

    # CF ending-cash (post-clean_table shape) — used as fallback when BS cash absent
    cf_combined = pd.DataFrame(
        {
            "2024": [2_500_000_000.0, 80_000_000_000.0],
            "2023": [2_100_000_000.0, 75_000_000_000.0],
        },
        index=[
            "Cash and cash equivalents at end of year",
            "Total Assets",
        ],
    )
    cf_cash = _extract_metric_value(
        cf_combined,
        "2024",
        CASH_CF_ENDING_PATTERNS,
        1.0,
        "cash_and_equivalents",
    )
    assert abs(cf_cash - 2_500_000_000.0) < 1
    assert not _label_matches_metric(
        "Cash and cash equivalents at beginning of year",
        "cash and cash equivalents",
        "cash_and_equivalents",
    )
    # extract_all_years_metrics import kept for API smoke
    assert callable(extract_all_years_metrics)

    # Year header must not become cash
    bad = _reconcile_balance_sheet(
        {"cash_and_equivalents": 2024.0, "total_assets": 1e11}
    )
    assert bad.get("cash_and_equivalents") is None
    assert bad.get("total_assets") == 1e11


def test_ocr_sparse_detect_and_soft_skip():
    from src.pdf_roic_extract import (
        _ocr_pages,
        _pages_are_sparse,
        _resolve_tessdata,
        _tesseract_available,
        extract_roic_metrics_from_pdf_path,
    )

    assert _pages_are_sparse([(1, ""), (2, "   abc")])
    assert not _pages_are_sparse([(1, "x" * 250)])

    # Soft-skip path: function returns list (possibly empty) without raising
    class _FakeDoc:
        page_count = 0
        name = "fake.pdf"

    assert _ocr_pages(_FakeDoc(), max_pages=1) == []
    # Glossy filename must not be OCR/extracted
    assert (
        extract_roic_metrics_from_pdf_path(
            __file__,  # not a PDF — would fail open if not skipped
            filename_hint="2024 Integrated Report.pdf",
        )
        == {}
    )
    # Availability probe is boolean; resolve may be a path or None
    assert isinstance(_tesseract_available(), bool)
    td = _resolve_tessdata()
    assert td is None or os.path.isfile(os.path.join(td, "eng.traineddata"))


def test_page_router_rejects_pfrs_and_mda():
    from src.pdf_page_router import (
        find_statement_pages,
        is_boilerplate_page,
        position_substance_score,
    )

    pfrs = open(os.path.join(FIX, "router_pfrs_prose.txt"), encoding="utf-8").read()
    mda = open(os.path.join(FIX, "router_mda_narrative.txt"), encoding="utf-8").read()
    spc = open(os.path.join(FIX, "spc_parent_fs.txt"), encoding="utf-8").read()

    assert is_boilerplate_page(pfrs)
    assert position_substance_score(pfrs) == 0
    assert position_substance_score(mda) < 5

    routed_junk = find_statement_pages([(23, pfrs), (19, mda)])
    assert routed_junk["all"] == []

    routed_spc = find_statement_pages([(1, spc)])
    assert 1 in routed_spc["position"] or 1 in routed_spc["all"]
    assert routed_spc["scope_hint"] == "parent"


def test_thousand_scale_guard():
    from src.scale_guard import has_thousand_scale_jump, repair_thousand_scale_jumps

    shares = 1.2e9
    # SM-like: latest year 1000× too small; BV×shares anchors full pesos
    sm = {
        2023: {
            "total_assets": 1.5e12,
            "stockholders_equity": 0.7e12,
            "net_income": 1e11,
            "book_value": 500.0,
            "outstanding_shares": shares,
        },
        2024: {
            "total_assets": 1.7e12,
            "stockholders_equity": 0.85e12,
            "net_income": 1.1e11,
            "book_value": 550.0,
            "outstanding_shares": shares,
        },
        2025: {
            "total_assets": 1.8e9,
            "stockholders_equity": 0.9e9,
            "net_income": 1.2e8,
            "book_value": 600.0,
            "outstanding_shares": shares,
        },
    }
    assert has_thousand_scale_jump(sm)
    out, actions = repair_thousand_scale_jumps(sm, inplace=False)
    assert actions
    assert abs(out[2025]["total_assets"] - 1.8e12) / 1.8e12 < 0.01
    assert abs(out[2024]["total_assets"] - 1.7e12) / 1.7e12 < 0.01

    # PGOLD-like: older years 1000× too large
    pg_shares = 2.88e9
    pg = {
        2023: {
            "total_assets": 1.72e14,
            "stockholders_equity": 8.84e13,
            "net_income": 8e12,
            "book_value": 30.84,
            "outstanding_shares": pg_shares,
        },
        2024: {
            "total_assets": 1.88e14,
            "stockholders_equity": 9.65e13,
            "net_income": 1e13,
            "book_value": 33.67,
            "outstanding_shares": pg_shares,
        },
        2025: {
            "total_assets": 2.0e11,
            "stockholders_equity": 1.03e11,
            "net_income": 1.1e10,
            "book_value": 35.93,
            "outstanding_shares": pg_shares,
        },
    }
    out2, actions2 = repair_thousand_scale_jumps(pg, inplace=False)
    assert actions2
    assert abs(out2[2023]["total_assets"] - 1.72e11) / 1.72e11 < 0.01
    assert abs(out2[2025]["total_assets"] - 2.0e11) / 2.0e11 < 0.01

    # Normal growth: no change
    ok = {
        2023: {"total_assets": 1.0e11},
        2024: {"total_assets": 1.1e11},
        2025: {"total_assets": 1.2e11},
    }
    out3, actions3 = repair_thousand_scale_jumps(ok, inplace=False)
    assert actions3 == []
    assert out3[2025]["total_assets"] == 1.2e11


if __name__ == "__main__":
    test_triage_skips_integrated_prefers_17a()
    test_financial_sector_gate()
    test_spc_cf_trap_blacklisted()
    test_spc_parent_fixture_cash_cl()
    test_agi_parent_vs_conso_cash_order()
    test_disclosure_html_attachments()
    test_plausible_years_and_fill_no_orphan_keys()
    test_fill_html_nulls_and_rejects()
    test_html_cash_labels_and_year_junk()
    test_ocr_sparse_detect_and_soft_skip()
    test_page_router_rejects_pfrs_and_mda()
    test_thousand_scale_guard()
    print("ok")
