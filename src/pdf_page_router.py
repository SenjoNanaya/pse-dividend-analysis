"""Page router — find Financial Position / Income statement pages only.

Hardened against common 17-A false positives:
- PFRS/PAS amendment / accounting-policy prose that names statement titles
- MD&A narrative that mentions cash and total assets without a tabular FS
"""

from __future__ import annotations

import re
from typing import Iterable

_POSITION_HINTS = (
    "statements of financial position",
    "statement of financial position",
    "statements of financial condition",
    "statement of financial condition",
)
_INCOME_HINTS = (
    "statements of comprehensive income",
    "statement of comprehensive income",
    "statements of income",
    "statement of income",
    "statements of profit or loss",
    "statement of profit or loss",
)
_CONSOLIDATED_HINT = "consolidated"
_PARENT_HINTS = ("parent company", "parent company statements")

_CF_HINT = "statements of cash flows"
_CF_HINTS = (
    "statements of cash flows",
    "statement of cash flows",
    "statements of cash flow",
    "statement of cash flow",
)

# Accounting-standard / governance prose that names FS titles but is not a statement
_REJECT_SUBSTRINGS = (
    "amended pfrs",
    "amendments to pfrs",
    "amendments to pas",
    "pfrs accounting standards",
    "pas accounting standards",
    "significant accounting policies",
    "the accounting policies adopted",
    "this standard replaces",
    "presentation and disclosure in financial statements",
    "lack of exchangeability",
    "not yet effective as at",
    "have not been applied in preparing",
    "control and compensation information",
    "item 9. directors",
    "table of contents",
    "independent auditor's report",
    "report of independent",
)

# Bare peso-style balances (tabular FS), not "Php29.8 billion" MD&A prose
_LARGE_AMOUNT = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3}){2,}(?:\.\d+)?")

# MD&A / narrative density
_NARRATIVE_CUES = (
    "primarily attributable",
    "increase of php",
    "decrease of php",
    "for the year 20",
    "stood at php",
    "closed at php",
)

_MIN_POSITION_SCORE = 5
_MIN_INCOME_SCORE = 4
_MIN_FALLBACK_SCORE = 6


def count_large_amounts(text: str) -> int:
    return len(_LARGE_AMOUNT.findall(text or ""))


def is_boilerplate_page(text: str) -> bool:
    """True for PFRS/policy/TOC/governance pages that should never be routed."""
    low = (text or "").lower()
    if not low.strip():
        return True
    hits = sum(1 for s in _REJECT_SUBSTRINGS if s in low)
    if hits >= 1 and ("pfrs" in low or "pas " in low or "pas," in low):
        return True
    if hits >= 2:
        return True
    if "significant accounting policies" in low:
        return True
    if "control and compensation information" in low:
        return True
    return False


def _title_strength(text: str, hints: tuple[str, ...]) -> int:
    """3 = title in page head, 1 = title somewhere, 0 = absent."""
    low = (text or "").lower()
    head = low[:600]
    for h in hints:
        if h in head:
            return 3
        if h in low:
            return 1
    return 0


def _narrative_penalty(text: str) -> int:
    low = (text or "").lower()
    cues = sum(1 for c in _NARRATIVE_CUES if c in low)
    billions = low.count("billion") + low.count("million")
    bare = count_large_amounts(text)
    # MD&A: many spoken amounts, few comma-separated balances
    if cues >= 2 and bare < 4:
        return 4
    if billions >= 4 and bare < 3:
        return 3
    return 0


def position_substance_score(text: str) -> int:
    """Score how much a page looks like a balance-sheet statement."""
    if is_boilerplate_page(text):
        return 0
    low = (text or "").lower()
    if len(low.strip()) < 80:
        return 0
    score = 0
    title = _title_strength(text, _POSITION_HINTS)
    score += title
    if "cash and cash equivalents" in low or "cash & cash equivalents" in low:
        score += 2
    if "total assets" in low or "total current assets" in low:
        score += 2
    if "total current liabilities" in low or "current liabilities" in low:
        score += 1
    if re.search(r"\btotal liabilities\b", low):
        score += 1
    if re.search(r"\bassets\b", low) and re.search(r"\bliabilit", low):
        score += 1
    bare = count_large_amounts(text)
    if bare >= 8:
        score += 3
    elif bare >= 4:
        score += 2
    elif bare >= 2:
        score += 1
    score -= _narrative_penalty(text)
    # Cash-flow only pages
    if _CF_HINT in low and title == 0 and "financial position" not in low:
        score -= 3
    return max(0, score)


def income_substance_score(text: str) -> int:
    """Score how much a page looks like an income / comprehensive income statement."""
    if is_boilerplate_page(text):
        return 0
    low = (text or "").lower()
    if len(low.strip()) < 80:
        return 0
    score = 0
    title = _title_strength(text, _INCOME_HINTS)
    score += title
    if any(
        x in low
        for x in (
            "net income",
            "net sales",
            "revenues",
            "revenue",
            "gross profit",
            "operating income",
            "income before",
        )
    ):
        score += 2
    if "cost of" in low or "operating expenses" in low or "general and administrative" in low:
        score += 1
    bare = count_large_amounts(text)
    if bare >= 6:
        score += 3
    elif bare >= 3:
        score += 2
    elif bare >= 1:
        score += 1
    score -= _narrative_penalty(text)
    if _CF_HINT in low and title == 0:
        score -= 3
    return max(0, score)


def _page_kind(text: str) -> str | None:
    low = (text or "").lower()
    if is_boilerplate_page(text):
        return None
    if _CF_HINT in low and "financial position" not in low and "comprehensive income" not in low:
        return None
    has_pos = any(h in low for h in _POSITION_HINTS)
    has_inc = any(h in low for h in _INCOME_HINTS)
    # Accept strong substance even without a title (some packs omit headers on spill pages)
    pos_ok = has_pos or position_substance_score(text) >= _MIN_FALLBACK_SCORE
    inc_ok = has_inc or income_substance_score(text) >= _MIN_FALLBACK_SCORE + 1
    if has_pos and has_inc:
        return "both"
    if pos_ok and has_pos:
        return "position"
    if inc_ok and has_inc:
        return "income"
    if has_pos:
        return "position"  # scored later; may be dropped
    if has_inc:
        return "income"
    return None


def _scope_bonus(text: str) -> int:
    low = (text or "").lower()
    if _CONSOLIDATED_HINT in low:
        return 2
    if any(h in low for h in _PARENT_HINTS):
        return 0
    return 1


def _is_continuation(text: str, kind: str) -> bool:
    """Allow ±1 expand onto spillover pages without a fresh title."""
    if is_boilerplate_page(text):
        return False
    low = (text or "").lower()
    bare = count_large_amounts(text)
    if bare < 3:
        return False
    if "continued" in low or "(continued)" in low:
        return True
    if kind == "position":
        return position_substance_score(text) >= 3 or (
            bare >= 4
            and ("liabilit" in low or "equity" in low or "assets" in low)
        )
    return income_substance_score(text) >= 3 or (
        bare >= 3
        and any(x in low for x in ("income", "revenue", "expense", "profit"))
    )


def find_statement_pages(
    pages: Iterable[tuple[int, str]],
    *,
    prefer_consolidated: bool = True,
) -> dict[str, list[int] | str]:
    """
    pages: iterable of (1-based page_number, text)
    Returns {position, income, all, scope_hint}
    """
    page_map: dict[int, str] = {}
    position_hits: list[tuple[int, int, int]] = []  # (score, scope_bonus, page)
    income_hits: list[tuple[int, int, int]] = []

    for page_no, text in pages:
        page_map[page_no] = text or ""
        kind = _page_kind(text)
        if not kind:
            continue
        if len((text or "").strip()) < 80:
            continue

        pos_score = position_substance_score(text)
        inc_score = income_substance_score(text)
        bonus = _scope_bonus(text)

        if kind in ("position", "both") and pos_score >= _MIN_POSITION_SCORE:
            # Prefer titled pages; untitled fallback-only handled below
            if _title_strength(text, _POSITION_HINTS) > 0 or pos_score >= _MIN_FALLBACK_SCORE:
                position_hits.append((pos_score, bonus, page_no))
        if kind in ("income", "both") and inc_score >= _MIN_INCOME_SCORE:
            if _title_strength(text, _INCOME_HINTS) > 0 or inc_score >= _MIN_FALLBACK_SCORE:
                income_hits.append((inc_score, bonus, page_no))

    def pick(hits: list[tuple[int, int, int]], kind: str) -> list[int]:
        if not hits:
            return []
        # Rank by substance first, then consolidated preference
        if prefer_consolidated:
            hits = sorted(hits, key=lambda h: (h[0], h[1]), reverse=True)
            top_score = hits[0][0]
            # Keep pages within 2 of best substance score
            band = [h for h in hits if h[0] >= top_score - 2]
            best_scope = max(h[1] for h in band)
            chosen = sorted({p for s, b, p in band if b == best_scope or s == top_score})
        else:
            chosen = sorted({p for _, _, p in hits})

        expanded: set[int] = set()
        for p in chosen:
            expanded.add(p)
            for cand in (p - 1, p + 1):
                if cand not in page_map:
                    continue
                if cand in chosen or _is_continuation(page_map[cand], kind):
                    expanded.add(cand)
        return sorted(p for p in expanded if p >= 1)

    pos_pages = pick(position_hits, "position")
    inc_pages = pick(income_hits, "income")

    # Substance-only fallback when titles never matched real statements
    if not pos_pages and not inc_pages:
        pos_pages, inc_pages = _fallback_substance_scan(page_map)

    scope = "unknown"
    scoped = position_hits + income_hits
    if scoped:
        all_text_bonus = max(h[1] for h in scoped)
        if all_text_bonus >= 2:
            scope = "consolidated"
        else:
            parentish = any(b == 0 for _, b, _ in scoped)
            if parentish and all_text_bonus == 0:
                scope = "parent"

    # Scope from accepted pages only (avoid PFRS "consolidated financial statements" prose)
    if pos_pages or inc_pages:
        accepted_text = " ".join(
            page_map[p] for p in set(pos_pages + inc_pages) if p in page_map
        )
        scope = _infer_scope(accepted_text, filename_bonus=False)

    return {
        "position": pos_pages,
        "income": inc_pages,
        "all": sorted(set(pos_pages + inc_pages)),
        "scope_hint": scope,
    }


def find_cash_flow_pages(
    pages: Iterable[tuple[int, str]],
    *,
    max_pages: int = 6,
) -> list[int]:
    """
    Pages that look like the cash-flow statement (for ending-cash fallback only).
    Excludes PFRS/policy boilerplate.
    """
    hits: list[tuple[int, int]] = []  # (score, page)
    for page_no, text in pages:
        if is_boilerplate_page(text):
            continue
        low = (text or "").lower()
        if len(low.strip()) < 80:
            continue
        title = _title_strength(text, _CF_HINTS)
        if title == 0 and not any(h in low for h in _CF_HINTS):
            continue
        # Need an ending-cash cue so we don't pull random CF activity pages
        ending = any(
            e in low
            for e in (
                "at end of year",
                "at end of the year",
                "at end of period",
                "end of year",
                "ending cash",
                "cash and cash equivalents",
            )
        )
        if not ending:
            continue
        bare = count_large_amounts(text)
        score = title * 2 + min(bare, 6)
        if score >= 3:
            hits.append((score, page_no))
    hits.sort(reverse=True)
    return sorted({p for _, p in hits[:max_pages]})


def _infer_scope(text: str, *, filename_bonus: bool = False) -> str:
    low = (text or "").lower()
    if _CONSOLIDATED_HINT in low and not is_boilerplate_page(text):
        # Prefer consolidated only when substance exists
        if position_substance_score(text) >= 3 or income_substance_score(text) >= 3:
            return "consolidated"
        if filename_bonus:
            return "consolidated"
    if any(h in low for h in _PARENT_HINTS):
        return "parent"
    return "unknown"


def _fallback_substance_scan(page_map: dict[int, str]) -> tuple[list[int], list[int]]:
    """Scan for tabular FS pages when statement titles are missing or OCR-poor."""
    pos: list[tuple[int, int]] = []  # (score, page)
    inc: list[tuple[int, int]] = []
    # Prefer early pages (statements usually before deep notes), but scan all
    ordered = sorted(page_map.keys())
    for pno in ordered:
        text = page_map[pno]
        if is_boilerplate_page(text):
            continue
        ps = position_substance_score(text)
        ii = income_substance_score(text)
        if ps >= _MIN_FALLBACK_SCORE:
            pos.append((ps, pno))
        if ii >= _MIN_FALLBACK_SCORE + 1:
            inc.append((ii, pno))

    def top_cluster(hits: list[tuple[int, int]], kind: str, limit: int = 4) -> list[int]:
        if not hits:
            return []
        hits = sorted(hits, key=lambda h: h[0], reverse=True)
        best = hits[0][0]
        pages = sorted(p for s, p in hits if s >= best - 1)[:limit]
        expanded: set[int] = set(pages)
        for p in pages:
            for cand in (p - 1, p + 1):
                if cand in page_map and _is_continuation(page_map[cand], kind):
                    expanded.add(cand)
        return sorted(expanded)

    return top_cluster(pos, "position"), top_cluster(inc, "income")


def detect_scale_factor(text: str) -> float:
    """Return multiplier for stated units (1 or 1e6 / 1e3)."""
    low = (text or "").lower()
    if re.search(r"in\s+millions?\s+of\s+pesos", low) or re.search(
        r"\(in\s+millions?\)", low
    ):
        return 1_000_000.0
    if re.search(r"in\s+thousands?\s+of\s+pesos", low) or re.search(
        r"\(in\s+thousands?\)", low
    ):
        return 1_000.0
    return 1.0
