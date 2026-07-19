"""Document triage for EDGE attachments — fetch less, prefer quality."""

from __future__ import annotations

import re
from typing import Any

# Filename / title heuristics (lowercase match)
_SKIP_PATTERNS = (
    "integrated report",
    "sustainability",
    "esg report",
    "csr report",
    "corporate responsibility",
)
_HIGH_PATTERNS = (
    "17-a",
    "17a",
    "afs",
    "audited financial",
    "financial statements",
    "sec form 17",
)
_CONSOLIDATED_PATTERNS = (
    "consolidated",
    "and subsidiaries",
    "group",
)
_PARENT_PATTERNS = (
    "parent",
    "[parent]",
    "parent company",
)
_PART_RE = re.compile(r"part\s*(\d+)\s*of\s*(\d+)", re.I)

_FINANCIAL_SECTOR_HINTS = (
    "bank",
    "banks",
    "financials",
    "financial services",
    "insurance",
    "other financial institutions",
)


def is_financial_sector(sector: str | None, subsector: str | None = None) -> bool:
    """True when classical ROIC is out of scope (banks / insurance / FI)."""
    blob = f"{sector or ''} {subsector or ''}".lower()
    if not blob.strip():
        return False
    return any(h in blob for h in _FINANCIAL_SECTOR_HINTS)


def is_banks_subsector(sector: str | None, subsector: str | None = None) -> bool:
    """
    Deposit-taking banks (PSE subsector Banks).

    Loan / deposit / NPL / NII / ACL checklist fields apply here only.
    Brokers and other FIs stay on equity ROIC via is_financial_sector.
    """
    sub = (subsector or "").lower()
    if "bank" in sub:
        return True
    # Some rows put Banks in sector with an empty subsector
    sec = (sector or "").lower().strip()
    return sec in ("banks", "bank")


def allows_revenue_surrogate(
    sector: str | None,
    subsector: str | None = None,
    *,
    financials: list | None = None,
) -> bool:
    """
    Holdings, miners/oil, and similar names often lack commercial sales.

    Interest income / equity in associates / gross revenue may stand in for
    the screening revenue gate. Never for deposit banks (NII is separate).

    Also allows shells in any non-bank sector when every stored year has
    null/zero revenue but net income is present (ACE/APC/APL pattern).
    """
    if is_banks_subsector(sector, subsector):
        return False
    blob = f"{sector or ''} {subsector or ''}".lower()
    hints = (
        "holding",
        "mining",
        "oil",
        "oil and gas",
        "exploration",
        "other financial institutions",
        # Shells / explorers filed under Services with no commercial sales line
        "other services",
        "hotel",
        "leisure",
        "information technology",
        "property",
        "construction",
        "infra",
        "services",
    )
    if any(h in blob for h in hints):
        return True
    if financials and all_years_zero_revenue(financials):
        from src.utils import safe_float

        if any(safe_float(f.get("net_income")) is not None for f in financials):
            return True
    return False


def all_years_zero_revenue(financials: list[dict] | None) -> bool:
    """True when every stored year has null/zero commercial revenue."""
    from src.report_metrics import metric_value

    rows = list(financials or [])
    if not rows:
        return False
    for f in rows:
        if metric_value(f.get("revenue"), "revenue") is not None:
            return False
    return True


def is_etf_sector(sector: str | None, subsector: str | None = None) -> bool:
    """True for PSE ETF listings (no commercial sales line)."""
    blob = f"{sector or ''} {subsector or ''}".lower()
    return "etf" in blob


def waives_revenue_completeness(
    company: dict | None,
    financials: list | None,
) -> bool:
    """
    Chronic no-top-line issuers may screen without commercial revenue.

    True when every stored year lacks usable revenue, or the name is a
    deposit bank / ETF. One-year P&L holes (prior year has revenue) return False.
    """
    company = company or {}
    rows = list(financials or [])
    if is_banks_subsector(company.get("sector"), company.get("subsector")):
        return True
    if is_etf_sector(company.get("sector"), company.get("subsector")):
        return True
    return all_years_zero_revenue(rows)


def _has_high_value_filing_signal(name: str) -> bool:
    """True when the name looks like a 17-A / AFS even if glossy words appear too."""
    if any(pat in name for pat in _HIGH_PATTERNS):
        return True
    return bool(_PART_RE.search(name))


def _score_attachment(filename: str) -> tuple[int, int, int]:
    """
    Return sort key: higher score first, then prefer consolidated, then earlier part.
    Returns (score, consolidated_bonus, -part_num).
    """
    name = (filename or "").lower().strip()
    if not name or name == "select":
        return (-10_000, 0, 0)

    # Combined packs e.g. "17-A Report and Sustainability Report.pdf" must NOT
    # be skipped — 17-A / AFS signals win over glossy keywords.
    if any(pat in name for pat in _SKIP_PATTERNS) and not _has_high_value_filing_signal(name):
        return (-5_000, 0, 0)

    score = 0
    for pat in _HIGH_PATTERNS:
        if pat in name:
            score += 100

    # Multi-part 17-A packs are high-value even without "AFS" in the name
    part_m = _PART_RE.search(name)
    part_num = int(part_m.group(1)) if part_m else 0
    if part_m:
        score += 80

    if name.endswith(".pdf"):
        score += 10

    # Soft bump for plain annual report PDFs (may still be useful when nothing else)
    if "annual report" in name and score < 50:
        score += 20

    consolidated = 1 if any(p in name for p in _CONSOLIDATED_PATTERNS) else 0
    parent_only = 1 if any(p in name for p in _PARENT_PATTERNS) else 0
    if consolidated:
        score += 40
    if parent_only and not consolidated:
        score -= 15  # defer parent when both exist

    return (score, consolidated, -part_num)


def rank_attachments(attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Sort attachments best-first and annotate with triage metadata.

    Each item: {file_id, filename, ...} → adds score, skip, prefer_consolidated.
    """
    ranked = []
    for att in attachments or []:
        filename = att.get("filename") or att.get("name") or ""
        score, consolidated, neg_part = _score_attachment(filename)
        item = dict(att)
        item["filename"] = filename
        item["triage_score"] = score
        item["is_consolidated_hint"] = bool(consolidated)
        item["skip"] = score < 0
        item["_sort"] = (score, consolidated, neg_part)
        ranked.append(item)

    ranked.sort(key=lambda x: x["_sort"], reverse=True)
    for item in ranked:
        item.pop("_sort", None)
    return ranked


def select_attachments_to_download(
    attachments: list[dict[str, Any]],
    *,
    max_files: int = 6,
    include_parent_if_no_consolidated: bool = True,
) -> list[dict[str, Any]]:
    """
    Choose which PDF attachments to fetch.

    Prefers high-score 17-A/AFS parts; skips integrated/sustainability;
    prefers consolidated; keeps parent only if no consolidated candidate.
    """
    ranked = rank_attachments(attachments)
    usable = [a for a in ranked if not a.get("skip") and a.get("file_id")]
    if not usable:
        return []

    has_consolidated = any(a.get("is_consolidated_hint") for a in usable)
    selected: list[dict[str, Any]] = []
    for att in usable:
        name = (att.get("filename") or "").lower()
        is_parent = any(p in name for p in _PARENT_PATTERNS)
        if is_parent and has_consolidated and not include_parent_if_no_consolidated:
            continue
        if is_parent and has_consolidated:
            # Still allow parent as fill-null fallback, but deprioritize — take after conso
            continue
        selected.append(att)
        if len(selected) >= max_files:
            break

    # If we filtered out all parents and need a fallback, add best parent
    if include_parent_if_no_consolidated and has_consolidated:
        parents = [
            a for a in usable
            if any(p in (a.get("filename") or "").lower() for p in _PARENT_PATTERNS)
        ]
        for p in parents:
            if p not in selected and len(selected) < max_files:
                selected.append(p)

    # Multi-part packs: if we picked Part 1 of N, also keep sibling parts with same stem score
    if any(_PART_RE.search(a.get("filename") or "") for a in selected):
        for att in usable:
            if att in selected:
                continue
            if _PART_RE.search(att.get("filename") or "") and len(selected) < max_files:
                selected.append(att)

    return selected[:max_files]
