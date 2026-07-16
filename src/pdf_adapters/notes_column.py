"""AGI-like notes-column financial statement layout."""

from __future__ import annotations

import re
from typing import Any

from src.pdf_adapters.common import detect_years_in_text, extract_amounts_from_line, row_dict


def parse_notes_column(text: str, years: list[int] | None = None) -> list[dict[str, Any]]:
    """
    Layout: label, optional note number, then year amounts (often with orphan P markers).
    """
    years = years or detect_years_in_text(text)
    if len(years) < 2:
        # Keep chronological left-to-right as found
        years = sorted(years, reverse=True) if years else []

    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    rows: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        low = line.lower()
        if low in {"notes", "current assets", "non-current assets", "noncurrent assets"}:
            i += 1
            continue
        if re.fullmatch(r"20\d{2}", line):
            i += 1
            continue

        amounts_here = extract_amounts_from_line(line)
        # Bare "P" marker lines — skip
        if re.fullmatch(r"P\.?", line):
            i += 1
            continue

        if amounts_here and not re.search(r"[A-Za-z]{3,}", line):
            i += 1
            continue

        # Start of a label
        if not re.search(r"[A-Za-z]{3,}", line):
            i += 1
            continue

        label_parts = [line]
        collected: list[float] = []
        j = i + 1
        # Optional continuation of wrapped label (no digits yet)
        while j < len(lines):
            nxt = lines[j]
            if re.fullmatch(r"P\.?", nxt):
                j += 1
                continue
            if re.fullmatch(r"[\d,\s]+", nxt) and len(nxt) <= 4:
                # Likely a note number
                j += 1
                continue
            amts = extract_amounts_from_line(nxt)
            labelish = re.sub(r"[\d,.\sP=()₱\-–—]", "", nxt)
            if amts and len(labelish) <= 2:
                collected.extend(amts)
                j += 1
                # Keep consuming amount / P lines for this row
                while j < len(lines) and len(collected) < max(len(years), 2):
                    nxt2 = lines[j]
                    if re.fullmatch(r"P\.?", nxt2):
                        j += 1
                        continue
                    amts2 = extract_amounts_from_line(nxt2)
                    labelish2 = re.sub(r"[\d,.\sP=()₱\-–—]", "", nxt2)
                    if amts2 and len(labelish2) <= 2:
                        collected.extend(amts2)
                        j += 1
                        continue
                    break
                break
            # Wrapped label without amounts yet
            if not amts and re.search(r"[A-Za-z]{3,}", nxt) and len(collected) == 0:
                # Stop if it looks like a new section header in ALL CAPS short form
                if nxt.isupper() and len(nxt) < 40:
                    break
                label_parts.append(nxt)
                j += 1
                continue
            break

        label = " ".join(label_parts)
        label = re.sub(r"\s+", " ", label).strip()
        # Drop trailing orphan note digits glued in text
        label = re.sub(r"\s+\d{1,2}$", "", label)

        if collected and years:
            # AGI typically shows latest year first (2024, 2023)
            use_years = years[: len(collected)]
            if len(use_years) >= 2 and use_years[0] < use_years[1]:
                # ensure descending header matches left-to-right amounts
                use_years = sorted(years, reverse=True)[: len(collected)]
            rows.append(row_dict(label, use_years, collected[: len(use_years)]))
            i = j
            continue

        # Amounts on same line as label
        if amounts_here and years:
            label = re.split(r"\d{1,3}(?:,\d{3})+", line, maxsplit=1)[0].strip()
            use_years = sorted(years, reverse=True)[: len(amounts_here)]
            if label:
                rows.append(row_dict(label, use_years, amounts_here[: len(use_years)]))
        i += 1 if j <= i else max(j - i, 1)

    return rows
