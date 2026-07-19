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
        # Combined EDGE pack: 17-A + Sustainability in one filename must download
        {
            "file_id": "5",
            "filename": (
                "Apr 30, 2026 MSRD_Manila Electric Company_2025_17-A "
                "Report and Sustainability Report.pdf"
            ),
        },
    ]
    ranked = rank_attachments(atts)
    assert ranked[0]["skip"] is False
    by_id = {a["file_id"]: a for a in ranked}
    assert by_id["1"]["skip"] is True
    assert by_id["5"]["skip"] is False
    selected = select_attachments_to_download(atts)
    names = [a["filename"].lower() for a in selected]
    assert not any(n.startswith("2024 bpi integrated") for n in names)
    assert any("17-a" in n or "17a" in n or "afs" in n or "part" in n for n in names)
    assert any("manila electric" in n and "17-a" in n for n in names)

    from src.pdf_roic_extract import extract_roic_metrics_from_pdf_path

    # Glossy-only still skipped; combined 17-A+sustainability is not.
    assert (
        extract_roic_metrics_from_pdf_path(
            __file__,
            filename_hint="2024 Sustainability Report.pdf",
        )
        == {}
    )


def test_financial_sector_gate():
    assert is_financial_sector("Financials", "Banks")
    assert is_financial_sector("Banks")
    assert not is_financial_sector("Property", "Real Estate")
    from src.filing_triage import is_banks_subsector

    assert is_banks_subsector("Financials", "Banks")
    assert not is_banks_subsector("Financials", "Other Financial Institutions")


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


def test_ab_bare_cash_skips_footnote_and_mda_variance():
    """AB: bare Cash + note index before P=; MD&A Increase/(Decrease) must not route."""
    from src.pdf_adapters.common import detect_statement_column_years
    from src.pdf_page_router import position_substance_score
    from src.pdf_roic_extract import match_whitelist_field, rows_to_yearly_metrics

    assert match_whitelist_field("Cash") == "cash_and_equivalents"
    assert match_whitelist_field(
        "Cash generated from operations in the year ended"
    ) is None

    ab_bs = """
    CONSOLIDATED STATEMENTS OF FINANCIAL POSITION
    December 31
    2025
    2024
    Cash
    4
    P=24,502,597
    P=27,232,864
    Total Current Liabilities
    1,692,275
    3,383,458
    Total Assets
    P=950,775,600
    P=951,950,195
    """
    years = detect_statement_column_years(ab_bs)
    assert years[:2] == [2025, 2024]
    rows = parse_sequential_p(ab_bs, years=years)
    yearly = rows_to_yearly_metrics(rows, scale=1.0, statement_scope="consolidated")
    assert abs(yearly[2025]["cash_and_equivalents"] - 24_502_597) < 1
    assert abs(yearly[2024]["cash_and_equivalents"] - 27_232_864) < 1

    mda = """
    CONSOLIDATED STATEMENTS OF FINANCIAL POSITION
    December 31, 2025 and 2024 Increase/(Decrease)
    Cash 24,502,597 27,232,864 (2,730,267) -10.03%
    Total Current Liabilities 1,692,275 3,383,458 (1,691,183) -49.98%
    """
    assert position_substance_score(mda) == 0


def test_cash_miss_label_cf_and_notes_fixtures():
    """LABEL_MAP / CF ending / notes_column shapes from cash router-miss review."""
    from src.pdf_adapters.notes_column import parse_notes_column
    from src.pdf_adapters.sequential_p import parse_sequential_p
    from src.pdf_page_router import find_cash_flow_pages, position_substance_score
    from src.pdf_roic_extract import match_whitelist_field, rows_to_yearly_metrics

    assert match_whitelist_field("Cashier") is None
    assert match_whitelist_field("specifically on Cash.") is None
    assert match_whitelist_field("Cash and cash equivalent") == "cash_and_equivalents"
    assert (
        match_whitelist_field("Cash and cash equivalents, end of year")
        == "cash_and_equivalents"
    )

    bc = open(os.path.join(FIX, "cash_miss_label_bc_style.txt"), encoding="utf-8").read()
    assert position_substance_score(bc) >= 3
    rows = parse_sequential_p(bc, years=[2024, 2023])
    yearly = rows_to_yearly_metrics(rows, scale=1.0, statement_scope="consolidated")
    assert abs(yearly[2024]["cash_and_equivalents"] - 1_753_715_000) < 1
    assert abs(yearly[2023]["cash_and_equivalents"] - 774_192_000) < 1

    cf = open(os.path.join(FIX, "cash_miss_cf_ending_comma.txt"), encoding="utf-8").read()
    cf_pages = find_cash_flow_pages([(1, cf)])
    assert 1 in cf_pages
    cf_rows = parse_sequential_p(cf, years=[2024, 2023])
    cf_yearly = rows_to_yearly_metrics(cf_rows, scale=1.0, statement_scope="parent")
    assert abs(cf_yearly[2024]["cash_and_equivalents"] - 280_000_000) < 1
    # Beginning-of-year must not win over ending
    assert cf_yearly[2024]["cash_and_equivalents"] != 200_000_000

    notes = open(
        os.path.join(FIX, "cash_miss_notes_ocr_singular.txt"), encoding="utf-8"
    ).read()
    n_rows = parse_notes_column(notes, years=[2025, 2024])
    n_yearly = rows_to_yearly_metrics(n_rows, scale=1.0, statement_scope="parent")
    assert abs(n_yearly[2025]["cash_and_equivalents"] - 2_776_049_000) < 1
    assert abs(n_yearly[2024]["cash_and_equivalents"] - 2_957_958_000) < 1


def test_eps_pdf_whitelist_and_derive():
    """PDF EPS overwrites EDGE 0.0; NI/shares derive fills when PDF has no EPS."""
    from src.pdf_adapters.sequential_p import parse_sequential_p
    from src.pdf_roic_extract import (
        fill_html_whitelist,
        match_whitelist_field,
        rows_to_yearly_metrics,
    )
    from src.report_metrics import derive_eps_from_ni_shares, needs_pdf_eps

    assert (
        match_whitelist_field("Basic and diluted earnings per share") == "eps"
    )
    text = open(os.path.join(FIX, "eps_is_basic_diluted.txt"), encoding="utf-8").read()
    rows = parse_sequential_p(text, years=[2025, 2024])
    pdf = rows_to_yearly_metrics(rows, scale=1000.0, statement_scope="parent")
    # scale must NOT apply to EPS
    assert abs(pdf[2025]["eps"] - 0.0126) < 1e-9
    assert "net_income" not in pdf[2025]  # not on PDF LABEL_MAP

    html = {
        2025: {
            "net_income": 185_000_000.0,
            "eps": 0.0,
            "outstanding_shares": 14_700_000_000.0,
            "total_assets": 1e10,
        }
    }
    # Force PDF eps (unscaled) onto HTML zero
    pdf_eps = {2025: {"eps": 0.0126}}
    merged = fill_html_whitelist(html, pdf_eps)
    assert abs(merged[2025]["eps"] - 0.0126) < 1e-9

    assert needs_pdf_eps({"eps": 0.0, "net_income": 185e6})
    assert not needs_pdf_eps({"eps": 0.0, "net_income": 0.0})
    derived = derive_eps_from_ni_shares(
        {"eps": 0.0, "net_income": 185_000_000.0, "outstanding_shares": 14_700_000_000.0}
    )
    assert derived is not None and abs(derived - 185e6 / 14.7e9) < 1e-9
    # Derive path when PDF has no eps
    html2 = {
        2024: {
            "net_income": 185_000_000.0,
            "eps": 0.0,
            "outstanding_shares": 14_700_000_000.0,
        }
    }
    merged2 = fill_html_whitelist(html2, {})
    assert abs(merged2[2024]["eps"] - 185e6 / 14.7e9) < 1e-9
    assert merged2[2024]["_field_sources"]["eps"] == "derived"


def test_glo_column_years_ignore_spurious_future():
    from src.pdf_adapters.common import detect_statement_column_years
    from src.pdf_adapters.notes_column import parse_notes_column
    from src.pdf_roic_extract import rows_to_yearly_metrics

    pos = """
    CONSOLIDATED STATEMENTS OF FINANCIAL POSITION
    December 31
    2024
    2023
    Cash and cash equivalents
    4
    16,645,077
    15,200,000
    """
    polluted_years = [2025, 2024, 2023, 2022]  # would cause +1 shift
    header = detect_statement_column_years(pos)
    assert header[:2] == [2024, 2023]
    rows = parse_notes_column(pos, years=header)
    yearly = rows_to_yearly_metrics(rows, scale=1000.0, statement_scope="consolidated")
    assert abs(yearly[2024]["cash_and_equivalents"] - 16_645_077_000) < 1
    assert abs(yearly[2023]["cash_and_equivalents"] - 15_200_000_000) < 1
    # Contrast: polluted years map amounts to the wrong fiscal keys
    bad = rows_to_yearly_metrics(
        parse_notes_column(pos, years=polluted_years),
        scale=1000.0,
        statement_scope="consolidated",
    )
    assert 2025 in bad and 2023 not in bad



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
    assert merged[2024]["_field_sources"]["cash_and_equivalents"] == "pdf"
    assert merged[2024]["_field_sources"]["net_income"] == "html"


def test_fill_html_nulls_and_rejects():
    from src.parser import _reconcile_balance_sheet
    from src.pdf_roic_extract import fill_html_whitelist

    # Identical PDF vs HTML: no source flip / no overwrite churn
    same = fill_html_whitelist(
        {
            2025: {
                "ga_expense": 9_914_418.0,
                "income_before_tax": -18_401_813.0,
                "total_current_liabilities": 1_692_275.0,
                "operating_income": 1.0,  # tiny → needs_pdf_oi path
                "revenue": 1e9,
                "net_income": 1e8,
            }
        },
        {
            2025: {
                "ga_expense": 9_914_418.0,
                "income_before_tax": -18_401_813.0,
                "total_current_liabilities": 1_692_275.0,
            }
        },
        company={"sector": "Property", "subsector": "Property"},
    )
    assert same[2025]["ga_expense"] == 9_914_418.0
    assert same[2025]["_field_sources"].get("ga_expense") == "html"
    assert same[2025]["_field_sources"].get("income_before_tax") == "html"

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
    assert merged[2023]["_field_sources"]["total_assets"] == "html"

    html2 = {2024: {"total_assets": 1e11}}
    pdf2 = {2024: {"cash_and_equivalents": 5e9}}
    merged2 = fill_html_whitelist(html2, pdf2)
    assert merged2[2024]["cash_and_equivalents"] == 5e9
    assert merged2[2024]["_field_sources"]["cash_and_equivalents"] == "pdf"

    # Reject cash ≫ assets (DMW-shaped scale miss).
    huge = fill_html_whitelist(
        {2024: {"total_assets": 55e9}},
        {2024: {"cash_and_equivalents": 2.48e12}},
    )
    assert huge[2024].get("cash_and_equivalents") is None
    # Unscaled thousands that ×1000 fit under assets are repaired (ION-shaped).
    scaled = fill_html_whitelist(
        {2025: {"total_assets": 121e6}},
        {2025: {"cash_and_equivalents": 4000.0}},
    )
    assert abs(scaled[2025]["cash_and_equivalents"] - 4_000_000.0) < 1
    # Still-too-small after ×1000 (or below cash floor) is rejected.
    scrap = fill_html_whitelist(
        {2024: {"total_assets": 500e9}},
        {2024: {"cash_and_equivalents": 50.0}},
    )
    assert scrap[2024].get("cash_and_equivalents") is None
    # HTML assets in thousands, PDF cash in pesos (PX/PHA/REG) — accept cash
    # and lift HTML absolutes ×1000 so ROIC stays coherent.
    underscaled = fill_html_whitelist(
        {
            2024: {
                "total_assets": 53_274_256.0,
                "total_liabilities": 20_000_000.0,
                "stockholders_equity": 33_274_256.0,
            }
        },
        {2024: {"cash_and_equivalents": 4_058_409_000.0}},
    )
    assert abs(underscaled[2024]["cash_and_equivalents"] - 4_058_409_000.0) < 1
    assert abs(underscaled[2024]["total_assets"] - 53_274_256_000.0) < 1
    # Negative cash always rejected (CEI-shaped).
    neg = fill_html_whitelist(
        {2025: {"total_assets": 2.5e9}},
        {2025: {"cash_and_equivalents": -17_220_520.0}},
    )
    assert neg[2025].get("cash_and_equivalents") is None

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
        _apply_per_page_ocr,
        _ocr_pages,
        _page_is_sparse,
        _pages_are_sparse,
        _preprocess_pixmap_for_ocr,
        _rank_ocr_candidates,
        _resolve_tessdata,
        _tesseract_available,
        extract_roic_metrics_from_pdf_path,
    )

    assert _page_is_sparse("")
    assert _page_is_sparse("abc")
    assert not _page_is_sparse("x" * 100)
    assert _pages_are_sparse([(1, ""), (2, "   abc")])
    assert not _pages_are_sparse([(1, "x" * 250)])

    class _FakeDoc:
        page_count = 0
        name = "fake.pdf"

        def __getitem__(self, i):
            raise IndexError(i)

    assert _ocr_pages(_FakeDoc(), max_pages=1) == []

    # Glossy filename must not be OCR/extracted
    assert (
        extract_roic_metrics_from_pdf_path(
            __file__,
            filename_hint="2024 Integrated Report.pdf",
        )
        == {}
    )
    assert isinstance(_tesseract_available(), bool)
    td = _resolve_tessdata()
    assert td is None or os.path.isfile(os.path.join(td, "eng.traineddata"))

    # Preprocess: synthetic RGB pixmap → L binary image
    try:
        import fitz
        from PIL import Image
    except ImportError:
        fitz = None
        Image = None
    if fitz is not None and Image is not None:
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 8, 8), 0)
        pix.set_rect(pix.irect, (200, 200, 200))
        img = _preprocess_pixmap_for_ocr(pix)
        assert img.mode == "L"
        assert img.size == (8, 8)

    # Hybrid: dense page kept; only sparse page full-OCR'd
    class _HybridDoc:
        page_count = 2
        name = "hybrid.pdf"

        def __getitem__(self, i):
            return i

    dense = "Total Assets " + ("x" * 100)
    pages = [(1, dense), (2, "")]
    calls = []

    def fake_probe(idx):
        return "Statements of Financial Position total assets 1,234,567" if idx == 1 else ""

    def fake_full(idx):
        calls.append(idx)
        return ("OCR PAGE %s CASH" % (idx + 1), "pillow")

    # Patch tesseract available for this unit path
    import src.pdf_roic_extract as pre

    orig_avail = pre._tesseract_available
    pre._tesseract_available = lambda: True
    try:
        out, full_n, probe_n = _apply_per_page_ocr(
            _HybridDoc(),
            pages,
            max_probes=10,
            max_full=40,
            full_ocr_fn=fake_full,
            probe_fn=fake_probe,
        )
    finally:
        pre._tesseract_available = orig_avail
    assert out[0][1] == dense
    assert "OCR PAGE 2" in out[1][1]
    assert calls == [1]
    assert full_n == 1
    assert probe_n >= 1

    # Deep rank: sparse high-score only on page 85 (index 84)
    class _DeepDoc:
        page_count = 100
        name = "deep.pdf"

        def __getitem__(self, i):
            return i

    deep_pages = [(i + 1, "") for i in range(100)]
    # Make early sparse pages score 0; page 85 scores high via probe
    def deep_probe(idx):
        if idx == 84:
            return (
                "Consolidated Statements of Financial Position\n"
                "Cash and cash equivalents 1,234,567,890\n"
                "Total Assets 9,876,543,210\n"
                "Total current liabilities 1,111,111,111\n"
            )
        return "cover photo"

    ranked, probed = _rank_ocr_candidates(
        _DeepDoc(),
        deep_pages,
        max_probes=120,
        max_full=40,
        probe_fn=deep_probe,
    )
    assert probed > 0
    assert 84 in ranked
    # Neighbor sparse pages may be included
    assert any(i >= 80 for i in ranked)

    # Continue-on-error: first full OCR fails, second succeeds
    class _ErrDoc:
        page_count = 3
        name = "err.pdf"

        def __getitem__(self, i):
            return i

    err_pages = [(1, ""), (2, ""), (3, "dense " + ("y" * 100))]
    err_calls = []

    def err_probe(idx):
        return "Total Assets 1,000,000 net income 500,000 statements of income"

    def err_full(idx):
        err_calls.append(idx)
        if idx == 0:
            raise RuntimeError("boom")
        return ("ok-%s" % idx, "pillow")

    pre._tesseract_available = lambda: True
    try:
        out2, full2, _ = _apply_per_page_ocr(
            _ErrDoc(),
            err_pages,
            max_probes=10,
            max_full=40,
            full_ocr_fn=err_full,
            probe_fn=err_probe,
        )
    finally:
        pre._tesseract_available = orig_avail
    assert full2 >= 1
    assert any(t.startswith("ok-") for _p, t in out2)


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

    # PH bank AFS title (BPI): "Statements of Condition" must route as position
    bank_bs = """
    BANK OF THE PHILIPPINE ISLANDS
    STATEMENTS OF CONDITION
    December 31, 2025 and 2024
    (In Millions of Pesos)
    Consolidated
    ASSETS
    CASH AND OTHER CASH ITEMS 53,018 49,762
    LOANS AND ADVANCES, net 2,567,131 2,238,765
    TOTAL ASSETS 3,651,488 3,318,813
    LIABILITIES AND CAPITAL FUNDS
    DEPOSIT LIABILITIES 2,838,525 2,614,802
    """
    routed_bank = find_statement_pages([(88, bank_bs)])
    assert 88 in routed_bank["position"]
    assert position_substance_score(bank_bs) >= 5


def test_nopat_synonym_labels():
    from src.parser import _label_matches_metric
    from src.pdf_roic_extract import match_whitelist_field, rows_to_yearly_metrics

    assert _label_matches_metric(
        "Earnings before interest and taxes",
        "earnings before interest and taxes",
        "operating_income",
    )
    assert _label_matches_metric("EBIT", "ebit", "operating_income")
    assert not _label_matches_metric(
        "Income from discontinued operations",
        "income from continuing operations",
        "operating_income",
    )
    assert _label_matches_metric(
        "Selling, general and administrative expenses",
        "selling, general and administrative expenses",
        "ga_expense",
    )
    assert match_whitelist_field("Income from operations") == "operating_income"
    assert match_whitelist_field("SG&A expenses") == "ga_expense"
    assert match_whitelist_field("Cash flows from operating activities") is None
    # Continuing ops is not an OI synonym (non-ops / after-items trap)
    assert match_whitelist_field("Income from continuing operations") is None

    # PDF yearly path: abs(GA) + derive when scraped OI fails vs GP
    yearly = rows_to_yearly_metrics(
        [
            {
                "label": "Gross profit",
                "values": {2025: 72_866_661.0},
            },
            {
                "label": "General and administrative expenses",
                "values": {2025: -105_121_007.0},
            },
            {
                "label": "Operating income",
                "values": {2025: 1_375_716_349.0},
            },
        ],
        scale=1.0,
        statement_scope="consolidated",
    )
    assert yearly[2025]["ga_expense"] == 105_121_007.0
    assert abs(yearly[2025]["operating_income"] - (72_866_661.0 - 105_121_007.0)) < 1
    assert yearly[2025].get("operating_income_derived") is True


def test_ali_style_construct_ebit_from_fixture():
    from src.pdf_adapters.notes_column import parse_notes_column
    from src.pdf_adapters.sequential_p import parse_sequential_p
    from src.pdf_roic_extract import (
        choose_adapter,
        match_whitelist_field,
        rows_to_yearly_metrics,
    )
    from src.report_metrics import sanitize_operating_metrics

    text = open(os.path.join(FIX, "synthetic_ali_style_is.txt"), encoding="utf-8").read()
    assert match_whitelist_field("Interest and other financing charges") == "interest_expense"
    adapter = choose_adapter(text)
    parse = parse_notes_column if adapter == "notes_column" else parse_sequential_p
    yearly = rows_to_yearly_metrics(
        parse(text, years=[2025, 2024, 2023]),
        scale=1000.0,
        statement_scope="consolidated",
    )
    assert 2025 in yearly
    # Seed HTML-scale revenue so GP/OI synthesis has anchors
    yearly[2025]["revenue"] = 190_210_680_000.0
    yearly[2025]["net_income"] = 45_554_129_000.0
    out = sanitize_operating_metrics(
        yearly[2025], company={"sector": "Property"}
    )
    assert out.get("cost_of_sales") is not None
    assert out.get("interest_expense") is not None
    assert abs(out["interest_expense"] - 17_267_715_000.0) < 1_000
    assert out.get("operating_income") is not None
    assert abs(out["operating_income"] - (out["income_before_tax"] + out["interest_expense"])) < 1
    assert out.get("gross_profit") is not None


def test_income_substance_and_synthetic_oi_near_ibt():
    from src.pdf_adapters.sequential_p import parse_sequential_p
    from src.pdf_page_router import income_substance_score
    from src.pdf_roic_extract import fill_html_whitelist, rows_to_yearly_metrics

    text = open(os.path.join(FIX, "synthetic_income_oi.txt"), encoding="utf-8").read()
    assert income_substance_score(text) >= 5
    yearly = rows_to_yearly_metrics(
        parse_sequential_p(text, years=[2025, 2024]),
        scale=1.0,
        statement_scope="consolidated",
    )
    assert 2025 in yearly
    oi = yearly[2025].get("operating_income")
    assert oi is not None
    assert abs(oi - 52_000_000_000) < 1

    html = {
        2025: {
            "revenue": 190_000_000_000.0,
            "operating_income": 13_000_000_000.0,
            "net_income": 45_000_000_000.0,
            "income_before_tax": 56_000_000_000.0,
            "total_assets": 900_000_000_000.0,
            "cash_and_equivalents": 19_000_000_000.0,
        }
    }
    merged = fill_html_whitelist(
        html,
        {2025: {"operating_income": oi}},
        company={"sector": "Property", "subsector": "Property"},
    )
    assert abs(merged[2025]["operating_income"] - 52_000_000_000) < 1


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


def test_rank_ocr_neighbor_expand_no_runtime_error():
    """Neighbor expansion must not mutate scores while iterating."""
    from src.pdf_roic_extract import _rank_ocr_candidates

    class _Doc:
        page_count = 5

    pages = [(i + 1, "x") for i in range(5)]

    def probe(idx):
        if idx == 2:
            return (
                "STATEMENTS OF FINANCIAL POSITION\n"
                "Cash and cash equivalents 1,000,000 900,000\n"
                "Total assets 10,000,000 9,000,000\n"
            )
        return "x"

    idxs, n = _rank_ocr_candidates(
        _Doc(), pages, max_probes=5, max_full=5, probe_fn=probe
    )
    assert n >= 1
    assert 2 in idxs


if __name__ == "__main__":
    test_triage_skips_integrated_prefers_17a()
    test_financial_sector_gate()
    test_spc_cf_trap_blacklisted()
    test_spc_parent_fixture_cash_cl()
    test_ab_bare_cash_skips_footnote_and_mda_variance()
    test_cash_miss_label_cf_and_notes_fixtures()
    test_eps_pdf_whitelist_and_derive()
    test_glo_column_years_ignore_spurious_future()
    test_agi_parent_vs_conso_cash_order()
    test_disclosure_html_attachments()
    test_plausible_years_and_fill_no_orphan_keys()
    test_fill_html_nulls_and_rejects()
    test_html_cash_labels_and_year_junk()
    test_ocr_sparse_detect_and_soft_skip()
    test_page_router_rejects_pfrs_and_mda()
    test_nopat_synonym_labels()
    test_ali_style_construct_ebit_from_fixture()
    test_income_substance_and_synthetic_oi_near_ibt()
    test_thousand_scale_guard()
    test_rank_ocr_neighbor_expand_no_runtime_error()
    print("ok")
