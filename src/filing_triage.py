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


def _score_attachment(filename: str) -> tuple[int, int, int]:
    """
    Return sort key: higher score first, then prefer consolidated, then earlier part.
    Returns (score, consolidated_bonus, -part_num).
    """
    name = (filename or "").lower().strip()
    if not name or name == "select":
        return (-10_000, 0, 0)

    for pat in _SKIP_PATTERNS:
        if pat in name:
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
