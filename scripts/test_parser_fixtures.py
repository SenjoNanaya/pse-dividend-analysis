"""HTML fixture tests for scale notes, NI row selection, and EDGE layout canaries."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.parser import extract_all_years_metrics, parse_report_html
from src.utils import parse_scale_factor

FIX = os.path.join(ROOT, "fixtures", "parser")

# Keys the canary must produce after scale (layout drift → empty or wrong set).
CANARY_REQUIRED_KEYS = frozenset(
    {
        "gross_revenue",
        "net_income",
        "eps",
        "total_assets",
        "total_liabilities",
        "stockholders_equity",
    }
)


def _load(name):
    path = os.path.join(FIX, name)
    with open(path, encoding="utf-8") as f:
        return f.read()


def _metrics_from_html(html):
    disc = parse_report_html(html)
    assert disc.get("type") != "form17c"
    assert disc.get("tables"), "expected type1 tables"
    return disc["scale_factor"], extract_all_years_metrics(
        disc["tables"], disc["scale_factor"]
    )


def _assert_keys(got_keys, expected_keys, context):
    got = set(got_keys)
    exp = set(expected_keys)
    missing = sorted(exp - got)
    extra_note = sorted(got - exp)
    assert not missing, (
        f"{context}: missing keys expected={sorted(exp)} got={sorted(got)} "
        f"missing={missing} other_present={extra_note}"
    )


def test_parse_scale_factor_strings():
    assert parse_scale_factor("Philippine Peso (Thousands)") == 1000
    assert parse_scale_factor("Philippine Peso (Millions)") == 1_000_000
    assert parse_scale_factor("Philippine Peso (Billions)") == 1_000_000_000
    assert parse_scale_factor("Philippine Peso") == 1


def test_scale_thousands_fixture():
    # Table amounts are in thousands; extract must multiply by 1000.
    scale, yearly = _metrics_from_html(_load("scale_thousands.html"))
    assert scale == 1000
    assert 2025 in yearly
    # 9,100 × 1000 = 9,100,000
    assert abs(yearly[2025]["total_assets"] - 9_100_000) < 1
    assert abs(yearly[2024]["total_assets"] - 8_200_000) < 1
    # 400 × 1000 = 400,000
    assert abs(yearly[2025]["net_income"] - 400_000) < 1
    # EPS is not an absolute metric; stays unscaled
    assert abs(yearly[2025]["eps"] - 0.40) < 1e-9


def test_scale_millions_fixture():
    scale, yearly = _metrics_from_html(_load("scale_millions_note.html"))
    assert scale == 1_000_000
    assert 2025 in yearly
    # 120 × 1,000,000 = 120,000,000
    assert abs(yearly[2025]["total_assets"] - 120_000_000) < 1
    assert abs(yearly[2024]["total_assets"] - 110_000_000) < 1


def test_net_income_skips_zero_parent():
    scale, yearly = _metrics_from_html(_load("net_income_zero_parent.html"))
    assert scale == 1
    assert 2025 in yearly and 2024 in yearly
    # Must not stay on the zero parent-attributable placeholder
    assert abs(yearly[2025]["net_income"] - 84_470_169) < 1
    assert abs(yearly[2024]["net_income"] - 12_782_747) < 1


def test_canary_edge_tables_layout():
    """
    Loud canary for EDGE type1 caption/row drift.
    If scale notes, BS/IS captions, or NI row selection break, this fails first.
    """
    html = _load("canary_edge_tables.html")
    disc = parse_report_html(html)
    assert disc.get("tables"), (
        f"canary: expected type1 tables, got type={disc.get('type')!r} "
        f"keys={sorted(disc.keys())}"
    )
    scale = disc["scale_factor"]
    assert scale == 1000, f"canary: expected scale 1000, got {scale}"

    yearly = extract_all_years_metrics(disc["tables"], scale)
    assert 2025 in yearly and 2024 in yearly, (
        f"canary: expected years 2024/2025, got {sorted(yearly.keys())}"
    )
    y25 = yearly[2025]
    _assert_keys(y25.keys(), CANARY_REQUIRED_KEYS, "canary 2025")

    # Thousands scale applied to absolutes; EPS unscaled
    assert abs(y25["total_assets"] - 10_000_000) < 1, (
        f"canary: total_assets expected 10000000 got {y25.get('total_assets')}"
    )
    assert abs(y25["net_income"] - 500_000) < 1, (
        f"canary: net_income expected 500000 (skip zero parent) got {y25.get('net_income')}"
    )
    assert abs(y25["gross_revenue"] - 3_000_000) < 1, (
        f"canary: gross_revenue expected 3000000 got {y25.get('gross_revenue')}"
    )
    assert abs(y25["eps"] - 0.50) < 1e-9, (
        f"canary: eps expected 0.50 got {y25.get('eps')}"
    )
    # Liabilities must be 4,000×1000, not the liabilities+equity total
    assert abs(y25["total_liabilities"] - 4_000_000) < 1, (
        f"canary: total_liabilities expected 4000000 (not L+E) got {y25.get('total_liabilities')}"
    )
    assert abs(y25["stockholders_equity"] - 6_000_000) < 1, (
        f"canary: equity expected 6000000 got {y25.get('stockholders_equity')}"
    )


def test_eps_basic_and_diluted_html():
    scale, yearly = _metrics_from_html(_load("eps_basic_and_diluted.html"))
    assert scale == 1
    assert 2024 in yearly
    assert abs(yearly[2024]["eps"] - 0.0126) < 1e-9
    # Net income still absolute
    assert abs(yearly[2024]["net_income"] - 185_000_000) < 1


def test_form_1712a_top100_outstanding_shares():
    from src.parser import parse_report_html

    disc = parse_report_html(_load("form_1712a_top100_common.html"))
    assert disc.get("type") == "form1712a"
    assert disc.get("year") == 2025
    assert disc.get("common_shares_outstanding") == 2_545_000_000


if __name__ == "__main__":
    test_parse_scale_factor_strings()
    test_scale_thousands_fixture()
    test_scale_millions_fixture()
    test_net_income_skips_zero_parent()
    test_canary_edge_tables_layout()
    test_eps_basic_and_diluted_html()
    test_form_1712a_top100_outstanding_shares()
    print("ok")
