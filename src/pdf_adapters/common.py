"""Shared helpers for PDF statement adapters."""

from __future__ import annotations

import re
from typing import Any

_YEAR_RE = re.compile(r"^(19|20)\d{2}$")


def parse_peso_amount(token: str) -> float | None:
    """Parse a single peso amount token; parentheses ⇒ negative."""
    if token is None:
        return None
    text = str(token).strip()
    if not text or text in {"-", "–", "—", "nil", "Nil", "n/a", "N/A"}:
        return None
    cleaned = text.replace("P=", "").replace("P", " ").replace("=", " ")
    cleaned = cleaned.replace(",", "").strip()
    neg = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        neg = True
        cleaned = cleaned[1:-1].strip()
    elif cleaned.startswith("("):
        neg = True
        cleaned = cleaned.lstrip("(").rstrip(")").strip()
    cleaned = re.sub(r"[^\d.\-]", "", cleaned)
    if not cleaned or cleaned in {".", "-", "-."}:
        return None
    try:
        val = float(cleaned)
    except ValueError:
        return None
    return -abs(val) if neg else val


def extract_amounts_from_line(line: str) -> list[float]:
    """Pull all peso-like numbers from a line (order preserved)."""
    amounts: list[float] = []
    working = line.replace("P=", " ").replace("₱", " ")
    for m in re.finditer(
        r"\(?\s*\d{1,3}(?:,\d{3})+(?:\.\d+)?\s*\)?|\(?\s*\d+(?:\.\d+)?\s*\)?",
        working,
    ):
        val = parse_peso_amount(m.group(0))
        if val is not None:
            amounts.append(val)
    return amounts


def is_year_token(tok: str) -> bool:
    return bool(_YEAR_RE.match(str(tok).strip()))


def detect_years_in_text(text: str) -> list[int]:
    years = []
    for m in re.finditer(r"\b((?:19|20)\d{2})\b", text or ""):
        y = int(m.group(1))
        if y not in years:
            years.append(y)
    return years


def normalize_label(label: str) -> str:
    text = re.sub(r"\s+", " ", (label or "").strip().lower())
    text = text.replace("–", "-").replace("—", "-")
    return text


def row_dict(label: str, years: list[int], values: list[float | None]) -> dict[str, Any]:
    by_year: dict[int, float] = {}
    for i, year in enumerate(years):
        if i < len(values) and values[i] is not None:
            by_year[int(year)] = values[i]
    return {"label": normalize_label(label), "raw_label": label.strip(), "values": by_year}
