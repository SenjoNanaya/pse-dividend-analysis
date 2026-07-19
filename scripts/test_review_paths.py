"""Regression: review tooling must key PDF caches by EDGE symbol, not DB id."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scripts import review_common as rc


def test_filings_dir_uses_edge_symbol_not_db_id():
    # AB historically had SQLite id=1 while EDGE MB lives under filings/1.
    # BPI showcase: id may collide; symbol 234 is the EDGE key.
    company = {"id": 1, "symbol": "234", "ticker": "BPI", "cmpy_id": "234"}
    path = rc.filings_dir_for_company(company)
    assert path == rc.FILINGS_ROOT / "234"
    assert path.name == "234"
    assert "1" != path.name or path == rc.FILINGS_ROOT / "234"


def test_filings_dir_rejects_dict_without_symbol():
    try:
        rc.filings_dir_for_company({"id": 1, "ticker": "AB"})
    except ValueError as exc:
        assert "symbol" in str(exc).lower() or "edge" in str(exc).lower()
    else:
        raise AssertionError("expected ValueError when symbol missing")


def test_count_pdf_cache_zero_without_symbol():
    n_files, n_dirs = rc.count_pdf_cache({"id": 1, "ticker": "AB"})
    assert n_files == 0 and n_dirs == 0


def test_edge_cmpy_id_bare_is_edge_not_sqlite():
    assert rc.edge_cmpy_id("234") == "234"
    assert rc.edge_cmpy_id(234) == "234"


def test_iter_cached_pdfs_prefer_afs(tmp_path, monkeypatch=None):
    # Lightweight: create fake tree under a temp FILINGS_ROOT
    edge = "999001"
    root = tmp_path / edge
    root.mkdir()
    (root / "glossy_17-A_Annual_Report.pdf").write_bytes(b"%PDF-1.4")
    (root / "Issuer_AFS_December_2024.pdf").write_bytes(b"%PDF-1.4")
    old = rc.FILINGS_ROOT
    rc.FILINGS_ROOT = tmp_path
    try:
        ordered = rc.iter_cached_pdfs(
            {"symbol": edge, "id": 42}, max_files=8, prefer_afs=True
        )
        assert ordered, "expected pdfs"
        assert "afs" in ordered[0].name.lower()
    finally:
        rc.FILINGS_ROOT = old


if __name__ == "__main__":
    test_filings_dir_uses_edge_symbol_not_db_id()
    test_filings_dir_rejects_dict_without_symbol()
    test_count_pdf_cache_zero_without_symbol()
    test_edge_cmpy_id_bare_is_edge_not_sqlite()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        edge = "999001"
        root = tmp / edge
        root.mkdir()
        (root / "glossy_17-A_Annual_Report.pdf").write_bytes(b"%PDF-1.4")
        (root / "Issuer_AFS_December_2024.pdf").write_bytes(b"%PDF-1.4")
        old = rc.FILINGS_ROOT
        rc.FILINGS_ROOT = tmp
        try:
            ordered = rc.iter_cached_pdfs(
                {"symbol": edge, "id": 42}, max_files=8, prefer_afs=True
            )
            assert ordered and "afs" in ordered[0].name.lower()
        finally:
            rc.FILINGS_ROOT = old
    print("ok")
