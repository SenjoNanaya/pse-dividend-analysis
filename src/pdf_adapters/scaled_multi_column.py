"""Scaled multi-column statements (e.g. In Millions; Consolidated | Parent)."""

from __future__ import annotations

import re
from typing import Any

from src.pdf_adapters.common import detect_years_in_text, extract_amounts_from_line, row_dict
from src.pdf_page_router import detect_scale_factor


def parse_scaled_multi_column(text: str, years: list[int] | None = None) -> list[dict[str, Any]]:
    """
    Prefer Consolidated column group when both Consolidated and Parent appear.

    Amounts in the text are already in statement units; caller applies scale.
    """
    scale = detect_scale_factor(text)
    years = years or detect_years_in_text(text)
    years = sorted(set(years), reverse=True)

    low = (text or "").lower()
    has_consolidated = "consolidated" in low
    has_parent = "parent" in low

    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    rows: list[dict[str, Any]] = []

    for line in lines:
        if not re.search(r"[A-Za-z]{3,}", line):
            continue
        amounts = extract_amounts_from_line(line)
        if not amounts:
            continue
        label = re.split(r"\d{1,3}(?:,\d{3})+|\d+\.\d+", line, maxsplit=1)[0]
        label = re.sub(r"\(note[^)]*\)", "", label, flags=re.I).strip(" -–—:")
        if len(label) < 3:
            continue

        # When consolidated+parent share a row, BPI style often has 3 conso + 3 parent years.
        use_amounts = amounts
        if has_consolidated and has_parent and len(amounts) >= 4 and years:
            n = min(len(years), len(amounts) // 2)
            use_amounts = amounts[:n]  # left group = consolidated
        elif years:
            use_amounts = amounts[: len(years)]

        use_years = years[: len(use_amounts)]
        if not use_years:
            continue
        # Store raw statement units; scale applied in extract layer via meta
        rows.append(row_dict(label, use_years, use_amounts))

    # Annotate scale on a synthetic meta row for the extract layer
    if rows:
        rows.append(
            {
                "label": "__meta_scale__",
                "raw_label": "__meta_scale__",
                "values": {},
                "scale": scale,
            }
        )
    return rows
