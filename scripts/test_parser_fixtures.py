"""HTML fixture tests for scale notes and net-income row selection."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.parser import extract_all_years_metrics, parse_report_html
from src.utils import parse_scale_factor

FIX = os.path.join(ROOT, "fixtures", "parser")


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


if __name__ == "__main__":
    test_parse_scale_factor_strings()
    test_scale_thousands_fixture()
    test_scale_millions_fixture()
    test_net_income_skips_zero_parent()
    print("ok")
