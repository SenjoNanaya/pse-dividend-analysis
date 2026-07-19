"""Shared helpers for offline DB / parser DQ review scripts."""
from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from src.field_sources import sources_from_json
from src.filing_triage import is_banks_subsector, is_financial_sector
from src.report_metrics import (
    ZERO_AS_MISSING_KEYS,
    data_warnings,
    incomplete_reasons,
    metric_value,
    _complete_financials,
)
from src.utils import safe_float

ROOT = Path(__file__).resolve().parents[1]
FILINGS_ROOT = ROOT / "data" / "filings"
REVIEWS_ROOT = ROOT / "data" / "reviews"

ACTIONABLE_WARNINGS = frozenset(
    {
        "thin_core_history",
        "thin_shares_series",
        "no_cash_for_proper_roic",
        "absurd_roic",
    }
)

CORE_FIELDS = (
    "revenue",
    "net_income",
    "total_assets",
    "eps",
    "book_value",
)

REVIEW_FIELDS = CORE_FIELDS + (
    "cash_and_equivalents",
    "outstanding_shares",
    "stockholders_equity",
    "total_liabilities",
    "total_loans",
    "total_deposits",
    "npl",
    "net_interest_income",
    "allowance_for_credit_losses",
)

PDF_WHITELIST_FIELDS = frozenset(
    {
        "cash_and_equivalents",
        "total_assets",
        "total_liabilities",
        "stockholders_equity",
        "total_current_liabilities",
        "operating_income",
        "eps",
        "total_loans",
        "total_deposits",
        "npl",
        "net_interest_income",
        "allowance_for_credit_losses",
    }
)

HTML_CORE_FIELDS = frozenset(CORE_FIELDS)


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def ensure_reviews_dir(run_id: str | None = None) -> Path:
    out = REVIEWS_ROOT / (run_id or stamp())
    out.mkdir(parents=True, exist_ok=True)
    return out


def company_dict_from_row(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "ticker": row["ticker"] or row["symbol"],
        "symbol": row["symbol"],
        "sector": row["sector"],
        "subsector": row["subsector"],
        "outstanding_shares": row["outstanding_shares"]
        if "outstanding_shares" in row.keys()
        else None,
        "pe_ratio": row["pe_ratio"] if "pe_ratio" in row.keys() else None,
        "pb_ratio": row["pb_ratio"] if "pb_ratio" in row.keys() else None,
        "roe": row["roe"] if "roe" in row.keys() else None,
        "roic": row["roic"] if "roic" in row.keys() else None,
        "market_cap": row["market_cap"] if "market_cap" in row.keys() else None,
        "last_traded_price": row["last_traded_price"]
        if "last_traded_price" in row.keys()
        else None,
        "info_incomplete": row["info_incomplete"]
        if "info_incomplete" in row.keys()
        else None,
    }


def financial_dict_from_row(row) -> dict[str, Any]:
    keys = (
        "fiscal_year",
        "revenue",
        "net_income",
        "eps",
        "book_value",
        "total_assets",
        "total_liabilities",
        "stockholders_equity",
        "outstanding_shares",
        "cash_and_equivalents",
        "total_current_liabilities",
        "operating_income",
        "total_loans",
        "total_deposits",
        "npl",
        "net_interest_income",
        "allowance_for_credit_losses",
        "statement_scope",
    )
    out: dict[str, Any] = {}
    for k in keys:
        if k in row.keys():
            out[k] = row[k]
    raw_src = row["field_sources"] if "field_sources" in row.keys() else None
    out["field_sources"] = sources_from_json(raw_src)
    return out


def load_companies(cur, ticker: str | None = None) -> list[dict[str, Any]]:
    if ticker:
        rows = cur.execute(
            """
            SELECT * FROM companies
            WHERE UPPER(COALESCE(ticker, symbol, '')) = UPPER(?)
            ORDER BY ticker, symbol
            """,
            (ticker,),
        ).fetchall()
    else:
        rows = cur.execute(
            "SELECT * FROM companies ORDER BY ticker, symbol"
        ).fetchall()
    return [company_dict_from_row(r) for r in rows]


def load_financials_by_company(cur) -> dict[int, list[dict[str, Any]]]:
    rows = cur.execute(
        """
        SELECT * FROM financials
        ORDER BY company_id, fiscal_year
        """
    ).fetchall()
    out: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        cid = int(r["company_id"])
        out.setdefault(cid, []).append(financial_dict_from_row(r))
    return out


def field_present(row: dict[str, Any], key: str) -> bool:
    if key in ZERO_AS_MISSING_KEYS:
        return metric_value(row.get(key), key) is not None
    return safe_float(row.get(key)) is not None


def actionable_warnings(warnings: Iterable[str]) -> list[str]:
    return [w for w in warnings if w in ACTIONABLE_WARNINGS]


def has_actionable_issue(reasons: list[str], warnings: list[str]) -> bool:
    return bool(reasons) or bool(actionable_warnings(warnings))


def core_year_count(financials: list[dict[str, Any]]) -> int:
    return len(_complete_financials(financials))


def share_year_count(financials: list[dict[str, Any]]) -> int:
    n = 0
    for f in financials:
        shares = safe_float(f.get("outstanding_shares"))
        if shares is not None and shares > 0:
            n += 1
    return n


def latest_complete_year(financials: list[dict[str, Any]]) -> dict[str, Any] | None:
    fin = _complete_financials(financials)
    return fin[-1] if fin else None


def source_tag(row: dict[str, Any] | None, key: str) -> str:
    if not row:
        return ""
    src = row.get("field_sources") or {}
    if isinstance(src, dict):
        return str(src.get(key) or "")
    return ""


def edge_cmpy_id(company: dict[str, Any] | int | str) -> str:
    """
    EDGE disclosure company id used under data/filings/<id>/.

    Pass a company row with ``symbol`` or ``cmpy_id`` (same value as CSV cmpy_id).
    Bare int/str is treated as an EDGE id, never as SQLite companies.id.
    """
    if isinstance(company, dict):
        edge = company.get("symbol") or company.get("cmpy_id")
        if edge is None or str(edge).strip() == "":
            raise ValueError(
                "filings path needs companies.symbol (EDGE cmpy_id); "
                "do not use SQLite companies.id"
            )
        return str(edge).strip()
    if company is None or str(company).strip() == "":
        raise ValueError("empty EDGE cmpy_id")
    return str(company).strip()


def filings_dir_for_company(
    company: dict[str, Any] | int | str,
) -> Path:
    """
    Cached PDFs live under data/filings/<EDGE cmpy_id>/ (see main.py).
    EDGE id is companies.symbol; never SQLite companies.id.
    """
    return FILINGS_ROOT / edge_cmpy_id(company)


def count_pdf_cache(company: dict[str, Any] | int | str) -> tuple[int, int]:
    """Return (pdf_file_count, edge_dir_count)."""
    try:
        root = filings_dir_for_company(company)
    except ValueError:
        return 0, 0
    if not root.is_dir():
        return 0, 0
    pdfs = list(root.rglob("*.pdf"))
    dirs = [p for p in root.iterdir() if p.is_dir()] if root.exists() else []
    return len(pdfs), len(dirs)


def iter_cached_pdfs(
    company: dict[str, Any] | int | str,
    *,
    max_files: int = 8,
    prefer_afs: bool = False,
) -> list[Path]:
    """Prefer 17-A / AFS-like filenames, then newest mtime.

    When prefer_afs=True (bank backfill), rank dedicated AFS / audited FS
    ahead of glossy 17-A packs that often have no statement tables.
    """
    try:
        root = filings_dir_for_company(company)
    except ValueError:
        return []
    if not root.is_dir():
        return []
    pdfs = list(root.rglob("*.pdf"))
    if not pdfs:
        return []

    def rank(p: Path) -> tuple[int, int, float]:
        name = p.name.lower()
        demote = ("sustainab", "17-l", "integrated report", "esg")
        if any(s in name for s in demote):
            tier = 3
        elif prefer_afs and (
            "afs" in name
            or "audited financial" in name
            or "audited_financial" in name
        ):
            tier = 0
        elif any(
            s in name
            for s in (
                "17-a",
                "17a",
                "afs",
                "audited",
                "financial",
                "sec_form",
                "sec form",
            )
        ):
            tier = 1
        else:
            tier = 2
        try:
            mtime = -p.stat().st_mtime
        except OSError:
            mtime = 0.0
        return (tier, 0, mtime)

    pdfs.sort(key=rank)
    return pdfs[:max_files]


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def histogram(items: Iterable[str]) -> list[tuple[str, int]]:
    c = Counter(items)
    return sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))


def company_is_bank(company: dict[str, Any]) -> bool:
    """Deposit banks only (loan/NPL checklist); not brokers / other FI."""
    return is_banks_subsector(company.get("sector"), company.get("subsector"))


def company_is_financial(company: dict[str, Any]) -> bool:
    return is_financial_sector(company.get("sector"), company.get("subsector"))


def diagnose_company(
    company: dict[str, Any],
    financials: list[dict[str, Any]],
) -> dict[str, Any]:
    reasons = incomplete_reasons(company, financials)
    warnings = data_warnings(company, financials)
    actionable = actionable_warnings(warnings)
    latest = latest_complete_year(financials)
    if latest is None and financials:
        # Fall back to last stored year for field inventory
        sorted_f = sorted(
            financials,
            key=lambda r: int(r.get("fiscal_year") or 0),
        )
        latest = sorted_f[-1] if sorted_f else None

    pdf_files, pdf_dirs = count_pdf_cache(company)
    null_cash_latest = (
        latest is None or not field_present(latest, "cash_and_equivalents")
    )
    null_shares_latest = (
        latest is None or not field_present(latest, "outstanding_shares")
    )

    missing_latest = []
    if latest:
        check_keys = list(CORE_FIELDS) + ["cash_and_equivalents", "outstanding_shares"]
        if company_is_bank(company):
            check_keys.extend(
                [
                    "total_loans",
                    "total_deposits",
                    "npl",
                    "net_interest_income",
                    "allowance_for_credit_losses",
                ]
            )
        for k in check_keys:
            if not field_present(latest, k):
                missing_latest.append(k)

    source_bits = []
    if latest:
        for k in (
            "cash_and_equivalents",
            "outstanding_shares",
            "revenue",
            "eps",
            "total_loans",
            "total_deposits",
        ):
            tag = source_tag(latest, k)
            if tag:
                source_bits.append(f"{k}:{tag}")

    return {
        "company_id": company["id"],
        "ticker": company.get("ticker") or company.get("symbol") or "",
        "name": company.get("name") or "",
        "sector": company.get("sector") or "",
        "subsector": company.get("subsector") or "",
        "bank": int(company_is_bank(company)),
        "info_incomplete": int(bool(reasons)),
        "incomplete_reasons": ";".join(reasons),
        "data_warnings": ";".join(warnings),
        "actionable_warnings": ";".join(actionable),
        "core_years": core_year_count(financials),
        "share_years": share_year_count(financials),
        "fiscal_years": len(financials),
        "latest_year": latest.get("fiscal_year") if latest else "",
        "null_cash_latest": int(null_cash_latest),
        "null_shares_latest": int(null_shares_latest),
        "missing_latest": ";".join(missing_latest),
        "latest_sources": " ".join(source_bits),
        "pdf_file_count": pdf_files,
        "pdf_dir_count": pdf_dirs,
        "has_actionable": int(has_actionable_issue(reasons, warnings)),
        "_reasons": reasons,
        "_warnings": warnings,
        "_actionable": actionable,
        "_latest": latest,
        "_financials": financials,
        "_company": company,
    }


def field_inventory_rows(diag: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    ticker = diag["ticker"]
    bank = bool(diag["bank"])
    keys = list(REVIEW_FIELDS)
    if not bank:
        keys = [k for k in keys if k not in {
            "total_loans",
            "total_deposits",
            "npl",
            "net_interest_income",
            "allowance_for_credit_losses",
        }]
    for f in diag["_financials"]:
        year = f.get("fiscal_year")
        for key in keys:
            rows.append(
                {
                    "ticker": ticker,
                    "company_id": diag["company_id"],
                    "fiscal_year": year,
                    "field": key,
                    "present": int(field_present(f, key)),
                    "source_tag": source_tag(f, key),
                    "value": f.get(key) if field_present(f, key) else "",
                }
            )
    return rows
