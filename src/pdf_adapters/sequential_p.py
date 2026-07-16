"""SPC-like sequential label / P= amount stacks."""

from __future__ import annotations

import re
from typing import Any

from src.pdf_adapters.common import detect_years_in_text, extract_amounts_from_line, row_dict

_HEADER_NOISE = re.compile(
    r"^(notes?|december|years?\s+ended|assets|liabilities and equity|equity|revenue|"
    r"see accompanying|page\s+\d+|sgvfs|\*sgvfs)",
    re.I,
)
_NOTE_ONLY = re.compile(r"^\(?notes?\s*\d+[a-z]?\)?$", re.I)
_SECTION_HDR = re.compile(
    r"^(current assets|noncurrent assets|non-current assets|current liabilities|"
    r"noncurrent liabilities|non-current liabilities|other income|cost of services)$",
    re.I,
)


def _strip_notes(label: str) -> str:
    text = re.sub(r"\(notes?\s*[^)]*\)", "", label, flags=re.I)
    text = re.sub(r"\s+notes?\s+\d+[a-z]?(?:,\s*\d+)*\s*$", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip(" -–—")


def _significant_amounts(line: str) -> list[float]:
    """Ignore bare note numbers; prefer P= lines and comma-formatted magnitudes."""
    if _NOTE_ONLY.match(line.strip()):
        return []
    # Drop inline (Note 6) before scanning
    cleaned = re.sub(r"\(notes?\s*[^)]*\)", " ", line, flags=re.I)
    has_p = "p=" in cleaned.lower() or "₱" in cleaned
    amounts = extract_amounts_from_line(cleaned)
    if has_p:
        return amounts
    # Keep only magnitudes that cannot be footnote indices
    return [a for a in amounts if abs(a) >= 1000]


def parse_sequential_p(text: str, years: list[int] | None = None) -> list[dict[str, Any]]:
    """
    Parse stacked lines where a label is followed by one or more amount lines
    (or amounts on the same line after the label).
    """
    years = years or detect_years_in_text(text)
    years = [y for y in years if isinstance(y, int)]
    if years:
        # Statement headers usually newest first
        years = sorted(set(years), reverse=True)

    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    rows: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if _HEADER_NOISE.match(line) and not _significant_amounts(line):
            i += 1
            continue
        if _SECTION_HDR.match(line):
            i += 1
            continue
        if re.fullmatch(r"20\d{2}", line):
            i += 1
            continue

        amounts_same = _significant_amounts(line)
        has_letters = bool(re.search(r"[A-Za-z]{3,}", line))

        # Pure amount line — skip (consumed when attached to prior label)
        if amounts_same and not has_letters:
            i += 1
            continue

        if not has_letters:
            i += 1
            continue

        label = _strip_notes(line)
        # Remove trailing amounts from same-line labels
        if amounts_same:
            label = re.split(r"P=|\d{1,3}(?:,\d{3})+", label, maxsplit=1)[0]
            label = _strip_notes(label)

        collected = list(amounts_same)
        j = i + 1
        # Wrap continuation labels (e.g. GENERAL AND ADMINISTRATIVE / EXPENSES)
        while j < len(lines) and len(collected) < max(len(years) or 2, 2):
            nxt = lines[j]
            if _NOTE_ONLY.match(nxt):
                j += 1
                continue
            amts = _significant_amounts(nxt)
            labelish = re.sub(r"[\d,.\sP=()₱\-–—]", "", nxt)
            if amts and len(labelish) <= 2:
                collected.extend(amts)
                j += 1
                continue
            if not amts and re.search(r"[A-Za-z]{3,}", nxt) and not collected:
                if _SECTION_HDR.match(nxt) or _HEADER_NOISE.match(nxt):
                    break
                # continuation of label
                label = _strip_notes(f"{label} {nxt}")
                j += 1
                continue
            break

        label = _strip_notes(label)
        if len(label) < 3 or not years or not collected:
            i += 1
            continue

        use_years = years[: len(collected)]
        rows.append(row_dict(label, use_years, collected[: len(use_years)]))
        i = j if j > i else i + 1

    return rows
