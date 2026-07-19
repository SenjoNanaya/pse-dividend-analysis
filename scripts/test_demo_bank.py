"""Fixture checks against fixtures/demo/pse_demo.db (recruiter click-path)."""
from __future__ import annotations

import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_DB = os.path.join(ROOT, "fixtures", "demo", "pse_demo.db")


def _bpi_rows(con: sqlite3.Connection) -> tuple[dict, list[dict]]:
    con.row_factory = sqlite3.Row
    co = con.execute(
        "SELECT * FROM companies WHERE ticker = ?", ("BPI",)
    ).fetchone()
    assert co is not None, "demo DB must include BPI"
    fins = [
        dict(r)
        for r in con.execute(
            """
            SELECT * FROM financials
            WHERE company_id = ?
            ORDER BY fiscal_year
            """,
            (co["id"],),
        )
    ]
    return dict(co), fins


def test_demo_bpi_dense_bank_series():
    """BPI ships with multi-year loans / deposits / NII / NPL / ACL."""
    assert os.path.isfile(DEMO_DB), f"missing {DEMO_DB}; run export_demo_db.py"
    con = sqlite3.connect(DEMO_DB)
    try:
        company, fins = _bpi_rows(con)
    finally:
        con.close()

    assert company.get("sector") == "Financials"
    assert len(fins) >= 3
    for row in fins[-3:]:
        for key in (
            "total_loans",
            "total_deposits",
            "net_interest_income",
            "npl",
            "allowance_for_credit_losses",
            "net_income",
            "stockholders_equity",
            "total_assets",
        ):
            assert row.get(key) is not None, f"FY{row.get('fiscal_year')} missing {key}"
            assert float(row[key]) > 0


def test_demo_bpi_equity_mode_and_npl_metric():
    """Equity capital-return mode + one bank checklist metric (NPL ratio)."""
    from src.report_metrics import build_checklist, compute_roic_series

    con = sqlite3.connect(DEMO_DB)
    try:
        company, fins = _bpi_rows(con)
    finally:
        con.close()

    roic = compute_roic_series(fins, company)
    assert roic["mode"] == "equity"
    assert len(roic["series"]) >= 2
    assert all(p["value"] is not None and p["value"] > 0 for p in roic["series"])

    cl = build_checklist(company, fins)
    by_label = {i["label"]: i["pass"] for i in cl}
    assert "NPL ratio < 5%" in by_label
    assert by_label["NPL ratio < 5%"] is True
    assert "Loan growth YoY > 0" in by_label
    # Industrial liquidity slot must not appear for banks
    assert "Quick/Current R > 1" not in by_label


if __name__ == "__main__":
    test_demo_bpi_dense_bank_series()
    test_demo_bpi_equity_mode_and_npl_metric()
    print("ok")
