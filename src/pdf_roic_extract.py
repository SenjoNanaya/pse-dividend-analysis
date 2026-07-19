"""Extract closed ROIC whitelist from PDF filings (anti-bloat)."""

from __future__ import annotations

import os
import re
from typing import Any

from src.pdf_adapters.notes_column import parse_notes_column
from src.pdf_adapters.scaled_multi_column import parse_scaled_multi_column
from src.pdf_adapters.sequential_p import parse_sequential_p
from src.pdf_adapters.common import detect_statement_column_years, detect_years_in_text
from src.pdf_page_router import (
    count_large_amounts,
    detect_scale_factor,
    find_bank_asset_quality_pages,
    find_cash_flow_pages,
    find_statement_pages,
    income_substance_score,
    position_substance_score,
)
from src.utils import logger

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment, misc]
    ImageOps = None  # type: ignore[assignment, misc]

try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None  # type: ignore[assignment]

from datetime import date

_PAGE_SPARSE_MIN_CHARS = 80
_DOC_SPARSE_MIN_CHARS = 200
_OCR_PROBE_DPI = 72
_OCR_FULL_DPI = 300
_OCR_MAX_PROBES = 120
_OCR_MAX_FULL = 40
_OCR_THRESHOLD = 180


def plausible_fiscal_years(
    years: list[int] | None,
    *,
    min_year: int = 1995,
    max_year: int | None = None,
) -> list[int]:
    """Keep statement years only — drop note refs / phone digits / far-future junk."""
    if max_year is None:
        # Statement years are never far in the future (allow current calendar year only)
        max_year = date.today().year
    out = []
    for y in years or []:
        try:
            yi = int(y)
        except (TypeError, ValueError):
            continue
        if min_year <= yi <= max_year and yi not in out:
            out.append(yi)
    return sorted(out, reverse=True)


_NONNEG_PDF_FIELDS = (
    "cash_and_equivalents",
    "total_assets",
    "total_current_liabilities",
    "cost_of_sales",
    "interest_expense",
    "other_expenses",
    "total_loans",
    "total_deposits",
    "npl",
    "net_interest_income",
    "allowance_for_credit_losses",
)
_PDF_META_KEYS = frozenset({"operating_income_derived", "statement_scope", "scale"})
_BANK_AQ_FIELDS = frozenset({
    "npl",
    "allowance_for_credit_losses",
})

# BSP performing / non-performing / total table: unlabeled totals row, then
# "Allowance for probable losses". Captures the six column totals (2 years × 3).
_BSP_NPL_TOTALS_RE = re.compile(
    r"(?P<a>\d{1,3}(?:,\d{3})+)\s+"
    r"(?P<npl_new>\d{1,3}(?:,\d{3})+)\s+"
    r"(?P<c>\d{1,3}(?:,\d{3})+)\s+"
    r"(?P<d>\d{1,3}(?:,\d{3})+)\s+"
    r"(?P<npl_old>\d{1,3}(?:,\d{3})+)\s+"
    r"(?P<f>\d{1,3}(?:,\d{3})+)\s+"
    r"allowance\s+for\s+probable",
    re.IGNORECASE,
)


def extract_bsp_npl_totals(
    text: str,
    years: list[int] | None = None,
    *,
    scale: float = 1.0,
) -> dict[int, float]:
    """
    Read gross NPL stock from BSP performing/non-performing tables.

    Column order is Performing | Non-performing | Total for the newer year,
    then the same three for the prior year. The totals row often has no label.
    """
    if not text or (
        "performing and non-performing" not in text.lower()
        and "as reported to the bsp" not in text.lower()
    ):
        return {}
    # Flatten newlines so the six totals can sit across lines
    flat = re.sub(r"[ \t]+", " ", text)
    flat = re.sub(r"\n+", " ", flat)
    m = _BSP_NPL_TOTALS_RE.search(flat)
    if not m:
        return {}
    try:
        npl_new = float(m.group("npl_new").replace(",", "")) * scale
        npl_old = float(m.group("npl_old").replace(",", "")) * scale
    except (TypeError, ValueError):
        return {}
    ys = list(years or [])
    if len(ys) < 2:
        ys = plausible_fiscal_years(detect_years_in_text(text))[:2]
    ys = sorted({int(y) for y in ys}, reverse=True)
    if len(ys) < 2:
        return {}
    # Table columns: newer year (perf/npl/total) then prior year
    y_new, y_old = ys[0], ys[1]
    out: dict[int, float] = {}
    if _sane_absolute(npl_new, "npl"):
        out[y_new] = abs(npl_new)
    if _sane_absolute(npl_old, "npl"):
        out[y_old] = abs(npl_old)
    return out


def _sane_absolute(value: float | None, field: str) -> bool:
    """Reject mis-parsed note numbers / years stored as balances."""
    if value is None:
        return False
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    # Absolute BS/IS pesos (or scaled millions*1e6) — never tiny note indices
    if field in (
        "cash_and_equivalents",
        "total_current_liabilities",
        "total_assets",
        "operating_income",
        "gross_profit",
        "ga_expense",
        "income_before_tax",
        "income_tax_expense",
        "cost_of_sales",
        "interest_expense",
        "other_expenses",
        "total_loans",
        "total_deposits",
        "npl",
        "net_interest_income",
        "allowance_for_credit_losses",
    ):
        # Cash floor is tighter: note indices and unscaled-thousand scraps
        # (e.g. 4000) must not land as balances. Negatives are overdraft /
        # CF misreads (CEI/LODE) — never store as cash.
        if field == "cash_and_equivalents":
            if v <= 0 or v < 10_000.0:
                return False
        else:
            if abs(v) < 1_000.0:
                return False
        # Year headers (e.g. 2024) often land in the assets/cash column
        if field in ("total_assets", "cash_and_equivalents") and 1990 <= abs(v) <= 2100 and abs(v - round(v)) < 1e-9:
            return False
        return True
    return True


def _scale_aq_to_loans(
    value: float,
    loans: float,
    *,
    lo_ratio: float,
    hi_ratio: float,
) -> float | None:
    """
    Note tables often print ACL/NPL in thousands or millions while the
    statement loan line is full pesos. Try ×1 / ×1e3 / ×1e6.
    """
    try:
        v = abs(float(value))
        L = abs(float(loans))
    except (TypeError, ValueError):
        return None
    if L < 1e9 or v < 1:
        return None
    for mult in (1.0, 1_000.0, 1_000_000.0):
        cand = v * mult
        ratio = cand / L
        if lo_ratio <= ratio <= hi_ratio:
            return cand
    return None


def _sanitize_bank_statement_row(row: dict[str, Any]) -> None:
    """In-place: lift under-scaled AQ fields; drop deposit scraps vs loans."""
    try:
        loans = row.get("total_loans")
        loans_f = abs(float(loans)) if loans is not None else None
    except (TypeError, ValueError):
        loans_f = None
    try:
        assets = row.get("total_assets")
        assets_f = abs(float(assets)) if assets is not None else None
    except (TypeError, ValueError):
        assets_f = None

    if loans_f is not None and loans_f >= 1e9:
        for fld, lo, hi in (
            ("allowance_for_credit_losses", 0.0005, 0.25),
            ("npl", 0.0005, 0.40),
        ):
            raw = row.get(fld)
            if raw is None:
                continue
            try:
                v = float(raw)
            except (TypeError, ValueError):
                continue
            scaled = _scale_aq_to_loans(v, loans_f, lo_ratio=lo, hi_ratio=hi)
            if scaled is None:
                row[fld] = None
            elif abs(scaled - abs(v)) > 1.0:
                row[fld] = scaled

        dep = row.get("total_deposits")
        if dep is not None:
            try:
                d = abs(float(dep))
            except (TypeError, ValueError):
                d = None
            if d is not None and d < loans_f * 0.12:
                row["total_deposits"] = None

    if assets_f is not None and assets_f > 1e11:
        dep = row.get("total_deposits")
        if dep is not None:
            try:
                d = abs(float(dep))
            except (TypeError, ValueError):
                d = None
            # Bare "1,000,000" scrap next to trillion-peso books
            if d is not None and 5e5 <= d <= 2.5e6:
                row["total_deposits"] = None
        loans = row.get("total_loans")
        if loans is not None and assets_f > 0:
            try:
                L = abs(float(loans))
            except (TypeError, ValueError):
                L = None
            if L is not None and L > assets_f * 1.25:
                row["total_loans"] = None


def _lift_row_absolute_x1000(row: dict[str, Any]) -> None:
    """HTML was in thousands; lift absolute peso fields to match PDF cash."""
    from src.scale_guard import SCALE_ABSOLUTE_KEYS

    for key in SCALE_ABSOLUTE_KEYS:
        if key == "cash_and_equivalents":
            continue
        raw = row.get(key)
        if raw is None:
            continue
        try:
            row[key] = float(raw) * 1000.0
        except (TypeError, ValueError):
            continue


def _coerce_pdf_cash(
    value: float,
    html_row: dict[str, Any] | None,
) -> tuple[float | None, str]:
    """
    Validate / lightly repair PDF cash before merge.

    Rejects negatives, cash ≫ assets, and implausibly tiny cash vs assets.
    When cash looks like an unscaled thousands figure but ×1000 fits under
    assets, return the scaled value.

    When HTML assets look thousand-scaled (cash fits under assets×1000 but not
    assets), return cash with reason ``html_thousands`` so the caller can lift
    the HTML row before merge.
    """
    v = float(value)
    if v < 0:
        return None, "negative"
    html_row = html_row or {}
    try:
        a = abs(float(html_row["total_assets"])) if html_row.get("total_assets") is not None else 0.0
    except (TypeError, ValueError, KeyError):
        a = 0.0

    if a > 0 and v > a * 1.05:
        # HTML assets in thousands, PDF cash in pesos (PX/PHA/REG/SHLPH/BC).
        # Require HTML assets to look underscaled so DMW-shaped OCR junk
        # (cash ≫ correct multi-billion assets) stays rejected.
        a_k = a * 1000.0
        ratio = v / a
        if (
            a < 500_000_000.0
            and 20.0 <= ratio <= 2000.0
            and v <= a_k * 1.05
            and v >= max(10_000.0, 0.0001 * a_k)
            and _sane_absolute(v, "cash_and_equivalents")
        ):
            return v, "html_thousands"
        # PDF cash printed with an extra ×1000 vs statement assets (AP mega-cap).
        # Prefer ÷1000 when that lands in a normal cash-to-assets band.
        down = v / 1000.0
        if (
            a >= 1_000_000_000.0
            and down <= a * 1.05
            and down >= max(10_000.0, 0.0001 * a)
            and down / a <= 0.35
            and _sane_absolute(down, "cash_and_equivalents")
        ):
            return down, "pdf_thousands"
        return None, "exceeds_html_assets"

    # Tiny vs assets: try ×1000 once, else reject (ION-shaped unscaled scrap).
    if a >= 1_000_000.0 and 0 < v < 0.0001 * a:
        scaled = v * 1000.0
        if scaled <= a * 1.05 and scaled >= 0.0001 * a and scaled >= 10_000.0:
            return scaled, ""
        return None, "implausibly_small_vs_assets"

    if not _sane_absolute(v, "cash_and_equivalents"):
        return None, "below_floor"
    return v, ""


def _pdf_value_ok(
    key: str,
    value: Any,
    html_row: dict[str, Any] | None,
) -> tuple[bool, str]:
    """
    Reject nonsensical PDF whitelist values before merge.
    Returns (ok, reason) — reason is empty when ok.

    Cash merges should call ``_coerce_pdf_cash`` so ×1000 repairs stick.
    """
    if key in _PDF_META_KEYS:
        return True, ""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False, "not_numeric"
    if key == "cash_and_equivalents":
        coerced, reason = _coerce_pdf_cash(v, html_row)
        return (coerced is not None), reason
    if key in _NONNEG_PDF_FIELDS and v < 0:
        return False, "negative"
    if key in LABEL_MAP and not _sane_absolute(v, key):
        return False, "below_floor"
    html_row = html_row or {}
    html_assets = html_row.get("total_assets")
    if html_assets is not None and key == "total_current_liabilities":
        try:
            a = abs(float(html_assets))
        except (TypeError, ValueError):
            a = 0.0
        if a > 0 and v > a * 1.05:
            return False, "exceeds_html_assets"

    # Deposit-bank magnitude checks (MBT false deposits; BDO 1e6 scrap; AQ scale)
    try:
        loans_anchor = html_row.get("total_loans")
        loans_f = abs(float(loans_anchor)) if loans_anchor is not None else None
    except (TypeError, ValueError):
        loans_f = None
    try:
        assets_f = abs(float(html_assets)) if html_assets is not None else None
    except (TypeError, ValueError):
        assets_f = None

    if key == "total_deposits":
        if loans_f is not None and loans_f >= 1e9 and abs(v) < loans_f * 0.12:
            return False, "deposits_lt_loans"
        if assets_f is not None and assets_f > 1e11 and 5e5 <= abs(v) <= 2.5e6:
            return False, "deposit_scrap"
    if key == "total_loans" and assets_f is not None and assets_f > 0:
        if abs(v) > assets_f * 1.25:
            return False, "loans_gt_assets"
    if key in ("allowance_for_credit_losses", "npl") and loans_f is not None:
        lo, hi = (
            (0.0005, 0.25)
            if key == "allowance_for_credit_losses"
            else (0.0005, 0.40)
        )
        if _scale_aq_to_loans(v, loans_f, lo_ratio=lo, hi_ratio=hi) is None:
            return False, "aq_vs_loans"
    rev = html_row.get("revenue")
    if rev is None:
        rev = html_row.get("gross_revenue")
    if key == "operating_income":
        from src.report_metrics import operating_income_sane

        if not operating_income_sane(
            v,
            revenue=rev,
            gross_profit=html_row.get("gross_profit"),
            net_income=html_row.get("net_income"),
            income_before_tax=html_row.get("income_before_tax"),
        ):
            return False, "oi_insane"
    if key == "gross_profit":
        from src.report_metrics import gross_profit_sane

        if not gross_profit_sane(
            v,
            revenue=rev,
            total_assets=html_row.get("total_assets"),
            net_income=html_row.get("net_income"),
        ):
            return False, "gp_insane"
    if key in ("revenue", "gross_revenue"):
        if v <= 0:
            return False, "non_positive"
        # Year headers / note indices misread as top-line
        if 1990 <= v <= 2100 and abs(v - round(v)) < 1e-9:
            return False, "year_as_revenue"
        if v < 100_000.0:
            return False, "below_revenue_floor"
    if key == "net_income" and assets_f is not None and assets_f > 1e6:
        if abs(v) > 2.0 * assets_f:
            # Wipeout years: allow when HTML IBT corroborates magnitude
            ibt = html_row.get("income_before_tax")
            try:
                ibt_f = abs(float(ibt)) if ibt is not None else 0.0
            except (TypeError, ValueError):
                ibt_f = 0.0
            if ibt_f < 1.0 or abs(abs(v) - ibt_f) / ibt_f > 0.15:
                return False, "ni_gt_2x_assets"
    return True, ""

# Closed ROIC field synonyms (label substring match, lowercase)
LABEL_MAP: dict[str, tuple[str, ...]] = {
    "cash_and_equivalents": (
        "cash and cash equivalents",
        "cash & cash equivalents",
        "cash and cash equivalent",
        "cash & cash equivalent",
        "cash and equivalents",
        "cash and short-term deposits",
        "cash and short term deposits",
        "cash and cash in banks",
        "cash in bank and on hand",
        "cash in banks and on hand",
        "cash on hand and in banks",
        "cash on hand and in bank",
        "cash in banks",
        "cash in bank",
        "unrestricted cash",
        "cash on hand",
        # CF ending balance (used when BS cash absent; activity lines filtered below)
        "cash and cash equivalents at end of year",
        "cash and cash equivalents at end of the year",
        "cash and cash equivalents at end of period",
        "cash and cash equivalents, end of year",
        "cash and cash equivalents, end of the year",
        "cash and cash equivalents, ending",
        "cash at end of year",
        "cash at end of the year",
        "ending cash and cash equivalents",
        "cash and cash equivalents at year-end",
        "cash and cash equivalents at year end",
        "due from bangko sentral ng pilipinas",
        "due from bsp",
        "cash",  # bare BS label last; guarded in match_whitelist_field
    ),
    "total_current_liabilities": (
        "total current liabilities",
        "total current liability",
    ),
    "total_assets": (
        "total assets",
    ),
    "operating_income": (
        "operating income",
        "operating profit",
        "income from operations",
        "earnings before interest and tax",
        "earnings before interest and taxes",
        "ebit",
    ),
    "gross_profit": (
        "gross profit",
        "gross income",
    ),
    "ga_expense": (
        "selling general and administrative expenses",
        "selling, general and administrative expenses",
        "selling general and administrative",
        "sg&a expenses",
        "sg&a",
        "general and administrative expenses",
        "general and administrative expense",
        "general & administrative expenses",
        "general and administrative",
        "administrative expenses",
        "administrative expense",
    ),
    "income_before_tax": (
        "income before income tax",
        "income before tax",
        "income/(loss) before income tax",
        "income (loss) before income tax",
    ),
    "income_tax_expense": (
        "provision for income tax",
        "income tax expense",
        "provision for tax",
    ),
    "eps": (
        "earnings per share (basic)",
        "earnings/(loss) per share (basic)",
        "basic and diluted earnings per share",
        "basic/diluted earnings per share",
        "earnings/(loss) per share",
        "loss per share (basic)",
        "basic earnings per share",
        "earnings per share",
        "basic/diluted eps",
        "basic eps",
    ),
    "cost_of_sales": (
        "cost of real estate sales",
        "cost of real estate",
        "cost of goods sold",
        "cost of sales",
        "cost of services",
    ),
    "interest_expense": (
        "interest and other financing charges",
        "interest and financing charges",
        "finance costs",
        "financing charges",
        "interest expense",
    ),
    "other_expenses": (
        "other operating expenses",
        "other expenses",
    ),
    "npl": (
        "total non-performing loans",
        "total non-performing",
        "non-performing loans",
        "non performing loans",
        "nonperforming loans",
        "gross non-performing loans",
        "credit-impaired loans",
        "credit impaired loans",
        "stage 3 loans",
        "stage 3 gross carrying amount",
        "past due and non-performing",
        "past due loans",
        "impaired loans and receivables",
        "impaired loans",
    ),
    "allowance_for_credit_losses": (
        "allowance for credit losses",
        "allowance for probable losses",
        "allowance for impairment",
        "allowance for credit and impairment losses",
        "allowance for loan losses",
        "allowance for expected credit losses",
    ),
    "total_loans": (
        "loans and other receivables - net",
        "loans and other receivables–net",
        "loans and other receivables",
        "loans and receivables at amortized cost",
        "loans and receivables - net of allowance",
        "loans and receivables–net of allowance",
        "loans and receivables - net",
        "loans and receivables–net",
        "loans and receivables",
        "loans and advances - net",
        "loans and advances–net",
        "loans and advances",
        "loans - net",
        "loans–net",
        "net loans and receivables",
        "net loans",
        "total loans and receivables",
        "total loans",
    ),
    "total_deposits": (
        "deposit liabilities",
        "due to depositors",
        "deposits from customers",
        "total deposit liabilities",
        "total deposits",
    ),
    "net_interest_income": (
        "net interest income",
        "net interest revenue",
    ),
    "revenue": (
        "net sales",
        "sales and services",
        "service income",
        "rental income",
        "total revenue",
        "revenues",
        "revenue",
    ),
    "gross_revenue": (
        "gross revenue",
        "gross sales",
    ),
    "equity_in_earnings": (
        "equity in net earnings of associates",
        "equity in net earnings of associates and joint ventures",
        "equity in net earnings",
        "share in net earnings of associates",
        "share of profit of associates",
    ),
    "interest_income": (
        "interest and other income",
        "investment income",
        "interest income",
    ),
    "net_income": (
        "net income/(loss) attributable to equity holders of the parent",
        "net income attributable to equity holders of the parent",
        "net income/(loss) attributable to parent",
        "net income attributable to owners of the parent",
        "net income attributable to parent",
        "net income/(loss) after tax",
        "net income after tax",
        "net loss attributable to parent",
        "net loss",
        "net income",
    ),
    "book_value": (
        "book value per share",
        "net book value per share",
    ),
}

# Never map these to operating_income
_OPERATING_BLACKLIST = (
    "before working capital",
    "working capital changes",
    "cash flows from operating",
    "operating activities",
    "discontinued operation",
    "discontinued operations",
)

_PL_LABEL_NOISE = (
    "share of",
    "associate",
    "joint venture",
    "segment",
    "margin",
    "per share",
    "%",
)

_SCORED_PDF_FIELDS = frozenset({
    "operating_income",
    "gross_profit",
    "ga_expense",
    "cash_and_equivalents",
})


def is_blacklisted_operating_label(label: str) -> bool:
    low = (label or "").lower()
    return any(b in low for b in _OPERATING_BLACKLIST)


def match_whitelist_field(label: str) -> str | None:
    low = (label or "").lower()
    if is_blacklisted_operating_label(low):
        return None
    for field, pats in LABEL_MAP.items():
        for pat in pats:
            if pat in low:
                # Avoid "total liabilities and equity" as total_assets
                if field == "total_assets" and "liabilit" in low:
                    continue
                if field == "total_current_liabilities" and "equity" in low:
                    continue
                if field in (
                    "operating_income",
                    "gross_profit",
                    "ga_expense",
                    "cost_of_sales",
                    "interest_expense",
                    "other_expenses",
                ):
                    if any(x in low for x in _PL_LABEL_NOISE):
                        continue
                if field == "interest_expense":
                    if "interest income" in low or "investment income" in low:
                        continue
                    if "net interest" in low:
                        continue
                    if "from financing" in low:
                        continue
                if field == "other_expenses":
                    # Prefer short IS labels; skip note prose
                    if len(low.strip()) > 48:
                        continue
                    if "income" in low and "operating" not in low:
                        continue
                if field == "total_loans":
                    if "non-performing" in low or "non performing" in low or "npl" in low:
                        continue
                    if "allowance" in low or "provision" in low:
                        continue
                    if "credit-impaired" in low or "credit impaired" in low:
                        continue
                    # Interest-income sub-lines: "On loans and advances" / "Interest income on loans…"
                    if "interest income" in low or "interest on" in low:
                        continue
                    if re.search(r"\bon\s+loans\b", low):
                        continue
                    if "income on loans" in low or "income from loans" in low:
                        continue
                    if len(low.strip()) > 72:
                        continue
                if field == "total_deposits":
                    if (
                        "cash and short-term deposits" in low
                        or "cash and short term deposits" in low
                    ):
                        continue
                if field == "npl":
                    if "ratio" in low or "%" in low or "coverage" in low:
                        continue
                    if "breakdown" in low or "net of allowance" in low:
                        continue
                    if len(low.strip()) > 72:
                        continue
                if field == "allowance_for_credit_losses":
                    if "deferred" in low or "undrawn" in low or "tax" in low:
                        continue
                    if "impairment losses" in low and "allowance" not in low:
                        continue
                    if "increased to" in low or "increase of" in low:
                        continue
                    if len(low.strip()) > 72:
                        continue
                if field == "net_interest_income":
                    if "expense" in low and "income" not in low:
                        continue
                    if "interest income" in low and "net interest" not in low:
                        continue
                if field == "interest_income":
                    if "net interest" in low:
                        continue
                    if "expense" in low:
                        continue
                    # IS breakdown lines ("Interest income on loans…") are not
                    # holding-company top-line surrogates
                    if re.search(r"\bon\s+loans\b", low) or "from loans" in low:
                        continue
                    if "loans and advances" in low or "loans and receivables" in low:
                        continue
                    if len(low.strip()) > 40:
                        continue
                if field == "revenue":
                    if "unearned" in low or "deferred" in low:
                        continue
                    if "interest" in low or "dividend" in low:
                        continue
                    if len(low.strip()) > 48:
                        continue
                if field == "cash_and_equivalents":
                    # Allow CF ending-cash; reject beginning / activity / dividend lines
                    if any(
                        x in low
                        for x in (
                            "beginning",
                            "start of",
                            "at start",
                            "from operating",
                            "from investing",
                            "from financing",
                        )
                    ):
                        continue
                    ending = any(
                        e in low
                        for e in (
                            "at end of year",
                            "at end of the year",
                            "at end of period",
                            "end of year",
                            "end of period",
                            "ending cash",
                            ", ending",
                            ", end of",
                        )
                    )
                    if ending:
                        return field
                    if "flow" in low or "flows" in low:
                        continue
                    if "dividend" in low or "generated" in low or "used in" in low:
                        continue
                    # Bare "cash" only as a whole word on short BS labels (AB style).
                    # Reject "Cashier", "cashflow", narrative "specifically on Cash."
                    if pat == "cash":
                        if not re.search(r"(?<![a-z])cash(?![a-z])", low):
                            continue
                        if any(
                            x in low
                            for x in ("cashier", "cashflow", "specifically on", "quick ratio")
                        ):
                            continue
                        if len(low.strip()) > 40:
                            continue
                if field == "operating_income" and is_blacklisted_operating_label(low):
                    continue
                if field == "ga_expense" and (
                    "cost of sales" in low
                    or "cost of goods" in low
                    or "operating activities" in low
                ):
                    continue
                return field
    return None


def choose_adapter(text: str) -> str:
    low = (text or "").lower()
    if "in millions" in low or "(in millions" in low:
        return "scaled_multi_column"
    if re.search(r"\bnotes?\b", low) and "current assets" in low:
        # AGI-style headers
        if "p=" not in low.replace(" ", ""):
            return "notes_column"
        # mixed — if many orphan "P" lines, notes_column
        if len(re.findall(r"(?m)^P\.?\s*$", text or "")) >= 2:
            return "notes_column"
    if "p=" in low:
        return "sequential_p"
    if "notes" in low[:800]:
        return "notes_column"
    return "sequential_p"


def _run_adapter(name: str, text: str, years: list[int] | None) -> list[dict[str, Any]]:
    if name == "notes_column":
        return parse_notes_column(text, years)
    if name == "scaled_multi_column":
        return parse_scaled_multi_column(text, years)
    return parse_sequential_p(text, years)


def rows_to_yearly_metrics(
    rows: list[dict[str, Any]],
    *,
    scale: float = 1.0,
    statement_scope: str = "unknown",
) -> dict[int, dict[str, Any]]:
    """Map adapter rows → {year: {field: value, ...}}."""
    from src.parser import _pick_scored_candidate
    from src.report_metrics import sanitize_operating_metrics
    from src.scale_guard import harmonize_intra_year_pl_scale

    yearly: dict[int, dict[str, Any]] = {}
    candidates: dict[int, dict[str, list[tuple[str, float]]]] = {}
    meta_scale = scale
    for row in rows:
        if row.get("label") == "__meta_scale__":
            meta_scale = float(row.get("scale") or scale)
            continue
        label = row.get("label") or ""
        field = match_whitelist_field(label)
        if not field:
            continue
        for year, raw in (row.get("values") or {}).items():
            if raw is None:
                continue
            y = int(year)
            yearly.setdefault(y, {})
            try:
                # Per-share lines — never apply statement thousands/millions scale.
                if field in ("eps", "book_value"):
                    scaled = float(raw)
                else:
                    scaled = float(raw) * meta_scale
            except (TypeError, ValueError):
                continue
            if field in ("allowance_for_credit_losses", "npl"):
                # Contra-asset / NPL stock often printed in parentheses
                scaled = abs(scaled)
            if field in ("eps", "book_value"):
                # Reject year-like junk and absurd OCR spikes
                if abs(scaled) > 1_000_000:
                    continue
                if 1990 <= abs(scaled) <= 2100 and abs(scaled - round(scaled)) < 1e-9:
                    continue
            elif not _sane_absolute(scaled, field):
                continue
            if field in _SCORED_PDF_FIELDS:
                candidates.setdefault(y, {}).setdefault(field, []).append(
                    (str(label), scaled)
                )
            elif field not in yearly[y]:
                yearly[y][field] = scaled

    for y, fields in candidates.items():
        anchors = dict(yearly.get(y) or {})
        # Score GP before OI/GA so anchors include GP when chosen
        for field in ("gross_profit", "ga_expense", "operating_income", "cash_and_equivalents"):
            cands = fields.get(field) or []
            if not cands:
                continue
            if field == "ga_expense" and yearly[y].get("gross_profit") is not None:
                anchors["gross_profit"] = yearly[y]["gross_profit"]
            picked = _pick_scored_candidate(field, cands, anchors)
            if picked is not None:
                yearly[y][field] = picked
                anchors[field] = picked

    for y, m in yearly.items():
        m["statement_scope"] = statement_scope
        m["scale"] = meta_scale
        harmonize_intra_year_pl_scale(m)
        sanitize_operating_metrics(m)
    return yearly


def merge_yearly_metrics(
    base: dict[int, dict[str, Any]],
    overlay: dict[int, dict[str, Any]],
    *,
    overlay_wins: bool = True,
) -> dict[int, dict[str, Any]]:
    """
    Merge overlay into base.

    When overlay_wins, overlay fills and overwrites; used when overlay is
    higher-precedence (e.g. consolidated over parent). Caller should pass
    higher-quality dict as overlay with overlay_wins=True, or use fill-nulls
    by setting overlay_wins=False.

    Cash / assets: do not let a higher-precedence pack replace a smaller
    plausible value with a ≥100× larger one (common when consolidated OCR
    treats thousands as pesos and blows past parent AFS figures).
    """
    protect_scale = frozenset({"cash_and_equivalents", "total_assets"})
    out = {y: dict(m) for y, m in (base or {}).items()}
    for y, m in (overlay or {}).items():
        out.setdefault(y, {})
        for k, v in m.items():
            if v is None:
                continue
            existing = out[y].get(k)
            if existing is not None and k in protect_scale and overlay_wins:
                try:
                    ev, nv = abs(float(existing)), abs(float(v))
                except (TypeError, ValueError):
                    ev, nv = 0.0, 0.0
                if ev > 0 and nv > ev * 100.0:
                    logger.info(
                        "keep prior %s y=%s (%.6g) over overlay %.6g (scale jump)",
                        k,
                        y,
                        existing,
                        v,
                    )
                    continue
            if overlay_wins or existing is None:
                out[y][k] = v
    return out


def prefer_scope_metrics(
    candidates: list[tuple[str, dict[int, dict[str, Any]]]],
) -> dict[int, dict[str, Any]]:
    """
    candidates: list of (scope, yearly_metrics) in any order.
    Prefer consolidated > unknown > parent.
    """
    order = {"consolidated": 0, "unknown": 1, "parent": 2}
    ranked = sorted(candidates, key=lambda x: order.get(x[0], 9))
    merged: dict[int, dict[str, Any]] = {}
    # Start with worst, overlay better so best wins
    for scope, metrics in reversed(ranked):
        merged = merge_yearly_metrics(merged, metrics, overlay_wins=True)
    return merged


def _alnum_char_count(text: str) -> int:
    return sum(1 for c in (text or "") if c.isalnum())


def _page_is_sparse(text: str, *, min_chars: int = _PAGE_SPARSE_MIN_CHARS) -> bool:
    """True when a single page has almost no native text."""
    return _alnum_char_count(text) < min_chars


def _pages_are_sparse(pages: list[tuple[int, str]], *, min_chars: int = _DOC_SPARSE_MIN_CHARS) -> bool:
    """True when the pack has almost no extractable text (likely image-only)."""
    total = sum(_alnum_char_count(t) for _, t in pages)
    return total < min_chars


def _resolve_tessdata() -> str | None:
    """
    Directory containing eng.traineddata for PyMuPDF / Tesseract OCR.

    Prefer TESSDATA_PREFIX when set.
    """
    candidates: list[str] = []
    env = os.environ.get("TESSDATA_PREFIX")
    if env:
        candidates.append(env.strip().strip('"'))
    candidates.extend(
        [
            r"C:\Program Files\Tesseract-OCR\tessdata",
            r"C:\Program Files (x86)\Tesseract-OCR\tessdata",
            "/usr/share/tesseract-ocr/5/tessdata",
            "/usr/share/tesseract-ocr/4.00/tessdata",
            "/usr/share/tessdata",
            "/usr/local/share/tessdata",
        ]
    )
    for path in candidates:
        if not path:
            continue
        eng = os.path.join(path, "eng.traineddata")
        if os.path.isfile(eng):
            return path
        nested = os.path.join(path, "tessdata", "eng.traineddata")
        if os.path.isfile(nested):
            return os.path.join(path, "tessdata")
    return None


def _configure_pytesseract(tessdata: str | None) -> bool:
    """Point pytesseract at the Tesseract binary next to tessdata when possible."""
    if pytesseract is None or not tessdata:
        return False
    root = os.path.dirname(tessdata.rstrip("\\/"))
    for candidate in (
        os.path.join(root, "tesseract.exe"),
        os.path.join(root, "tesseract"),
        os.path.join(tessdata, "..", "tesseract.exe"),
        os.path.join(tessdata, "..", "tesseract"),
    ):
        path = os.path.normpath(candidate)
        if os.path.isfile(path):
            pytesseract.pytesseract.tesseract_cmd = path
            return True
    return True  # rely on PATH


def _tesseract_available() -> bool:
    """True when eng.traineddata is findable."""
    return _resolve_tessdata() is not None


def _preprocess_pixmap_for_ocr(pix) -> Any:
    """
    Convert a PyMuPDF pixmap to a binarized PIL L image for Tesseract.
    """
    if Image is None or ImageOps is None:
        raise ImportError("Pillow is required for OCR preprocess")
    w, h, n = int(pix.width), int(pix.height), int(pix.n)
    samples = pix.samples
    if n >= 4:
        img = Image.frombytes("RGBA", [w, h], samples).convert("L")
    elif n == 3:
        img = Image.frombytes("RGB", [w, h], samples).convert("L")
    else:
        img = Image.frombytes("L", [w, h], samples)
    img = ImageOps.autocontrast(img)
    thr = _OCR_THRESHOLD
    return img.point(lambda x, t=thr: 255 if x > t else 0)


def _ocr_pil_image(img) -> str:
    if pytesseract is None:
        raise ImportError("pytesseract is required for Pillow OCR path")
    return pytesseract.image_to_string(img, lang="eng", config="--psm 6") or ""


def _mupdf_ocr_page(page, *, dpi: int, tessdata: str) -> str:
    tp = page.get_textpage_ocr(
        language="eng",
        dpi=dpi,
        full=True,
        tessdata=tessdata,
    )
    return page.get_text("text", textpage=tp) or ""


def _ocr_page_preprocessed(page, *, dpi: int = _OCR_FULL_DPI) -> tuple[str, str]:
    """
    Full OCR at dpi with pixmap preprocess when Pillow+pytesseract work.
    Returns (text, engine) where engine is 'pillow' or 'mupdf'.
    """
    tessdata = _resolve_tessdata()
    if not tessdata:
        return "", "none"
    _configure_pytesseract(tessdata)

    if fitz is not None and Image is not None and pytesseract is not None:
        try:
            zoom = dpi / 72.0
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            img = _preprocess_pixmap_for_ocr(pix)
            text = _ocr_pil_image(img)
            if text.strip():
                return text, "pillow"
        except Exception as exc:
            logger.warning(
                "Pillow OCR failed on page %s: %s; trying MuPDF OCR",
                getattr(page, "number", "?"),
                exc,
            )

    try:
        return _mupdf_ocr_page(page, dpi=dpi, tessdata=tessdata), "mupdf"
    except Exception as exc:
        logger.warning(
            "OCR failed on page %s: %s",
            getattr(page, "number", "?"),
            exc,
        )
        return "", "none"


def _probe_page_text(page, *, dpi: int = _OCR_PROBE_DPI) -> str:
    """Cheap OCR/text for ranking sparse pages (prefer fast MuPDF OCR)."""
    tessdata = _resolve_tessdata()
    if not tessdata:
        return ""
    try:
        return _mupdf_ocr_page(page, dpi=dpi, tessdata=tessdata)
    except Exception:
        text, _ = _ocr_page_preprocessed(page, dpi=dpi)
        return text


def _candidate_score(text: str) -> int:
    """Rank probe text for statement likelihood (router scores + peso density)."""
    if not (text or "").strip():
        return 0
    pos = position_substance_score(text)
    inc = income_substance_score(text)
    amounts = count_large_amounts(text)
    return max(pos, inc) + min(5, amounts)


def _sparse_page_indices(pages: list[tuple[int, str]]) -> list[int]:
    """0-based indices into pages/doc for sparse native pages."""
    return [i for i, (_pno, text) in enumerate(pages) if _page_is_sparse(text)]


def _select_probe_indices(sparse_idxs: list[int], *, max_probes: int = _OCR_MAX_PROBES) -> list[int]:
    """First 60 sparse pages, then every other, up to max_probes."""
    if len(sparse_idxs) <= max_probes:
        return list(sparse_idxs)
    first = sparse_idxs[:60]
    rest = sparse_idxs[60:]
    strided = rest[::2]
    out = first + strided
    return out[:max_probes]


def _rank_ocr_candidates(
    doc,
    pages: list[tuple[int, str]],
    *,
    max_probes: int = _OCR_MAX_PROBES,
    max_full: int = _OCR_MAX_FULL,
    probe_fn=None,
) -> tuple[list[int], int]:
    """
    Probe sparse pages, score, expand ±1 neighbors, return 0-based indices for full OCR.
    Returns (indices, probe_count).
    """
    sparse = _sparse_page_indices(pages)
    if not sparse:
        return [], 0

    probe = probe_fn or (lambda idx: _probe_page_text(doc[idx]))
    to_probe = _select_probe_indices(sparse, max_probes=max_probes)
    scores: dict[int, int] = {}
    probe_count = 0
    for idx in to_probe:
        try:
            text = probe(idx) or ""
        except Exception as exc:
            logger.warning("OCR probe failed on page %s: %s", idx + 1, exc)
            text = ""
        probe_count += 1
        scores[idx] = _candidate_score(text)

    # Expand neighbors of any positive score (continuation pages)
    n_pages = int(doc.page_count)
    expanded: set[int] = set()
    neighbor_scores: dict[int, int] = {}
    for idx, sc in tuple(scores.items()):
        if sc <= 0:
            continue
        for j in (idx - 1, idx, idx + 1):
            if 0 <= j < n_pages and _page_is_sparse(pages[j][1]):
                expanded.add(j)
                if j not in scores and j not in neighbor_scores:
                    neighbor_scores[j] = sc
    scores.update(neighbor_scores)

    ranked = sorted(
        scores.keys(),
        key=lambda i: (-scores.get(i, 0), i),
    )
    # Prefer scored hits; if all zero, still take strided probe order (deep coverage)
    if all(scores.get(i, 0) <= 0 for i in ranked):
        ranked = list(to_probe)

    # Ensure neighbors of top hits are included early
    ordered: list[int] = []
    seen: set[int] = set()
    for idx in ranked:
        for j in (idx - 1, idx, idx + 1):
            if j in expanded or j == idx or j in scores:
                if 0 <= j < n_pages and j not in seen and _page_is_sparse(pages[j][1]):
                    seen.add(j)
                    ordered.append(j)
        if len(ordered) >= max_full:
            break
    if not ordered:
        ordered = [i for i in to_probe if i not in seen][:max_full]
    return ordered[:max_full], probe_count


def _apply_per_page_ocr(
    doc,
    pages: list[tuple[int, str]],
    *,
    max_probes: int = _OCR_MAX_PROBES,
    max_full: int = _OCR_MAX_FULL,
    full_ocr_fn=None,
    probe_fn=None,
) -> tuple[list[tuple[int, str]], int, int]:
    """
    Score-then-OCR sparse pages; merge text into pages.
    Returns (pages, full_ocr_count, probe_count).
    """
    if not _tesseract_available():
        logger.info("OCR skipped: Tesseract tessdata not found (set TESSDATA_PREFIX)")
        return pages, 0, 0

    indices, probe_count = _rank_ocr_candidates(
        doc,
        pages,
        max_probes=max_probes,
        max_full=max_full,
        probe_fn=probe_fn,
    )
    if not indices:
        return pages, 0, probe_count

    ocr_fn = full_ocr_fn or (lambda idx: _ocr_page_preprocessed(doc[idx], dpi=_OCR_FULL_DPI))
    out = list(pages)
    full_count = 0
    engine_used = "none"
    for idx in indices:
        try:
            result = ocr_fn(idx)
            if isinstance(result, tuple):
                text, engine = result
            else:
                text, engine = result, "custom"
        except Exception as exc:
            logger.warning("OCR failed on page %s: %s", idx + 1, exc)
            continue
        if not (text or "").strip():
            continue
        pno = out[idx][0]
        out[idx] = (pno, text)
        full_count += 1
        if engine_used == "none":
            engine_used = engine or "pillow"

    logger.info(
        "OCR per-page: probed=%s full=%s dpi=%s preprocess=%s",
        probe_count,
        full_count,
        _OCR_FULL_DPI,
        engine_used,
    )
    return out, full_count, probe_count


def _ocr_pages(
    doc,
    *,
    max_pages: int = 40,
    dpi: int = 200,
) -> list[tuple[int, str]]:
    """
    Legacy helper: OCR first max_pages via MuPDF (tests / soft-skip).
    Prefer _apply_per_page_ocr for production extract.
    """
    tessdata = _resolve_tessdata()
    if not tessdata:
        logger.info("OCR skipped: Tesseract tessdata not found (set TESSDATA_PREFIX)")
        return []
    out: list[tuple[int, str]] = []
    n = min(int(getattr(doc, "page_count", 0) or 0), max_pages)
    for i in range(n):
        page = doc[i]
        try:
            text = _mupdf_ocr_page(page, dpi=dpi, tessdata=tessdata)
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "OCR failed on page %s of %s: %s",
                i + 1,
                getattr(doc, "name", "?"),
                exc,
            )
            continue
        out.append((i + 1, text))
    return out


def extract_roic_metrics_from_pdf_path(
    pdf_path: str,
    *,
    filename_hint: str | None = None,
) -> dict[int, dict[str, Any]]:
    """Open a PDF and extract ROIC whitelist metrics from statement pages."""
    if fitz is None:
        logger.warning("PyMuPDF (fitz) not installed; skipping PDF extract for %s", pdf_path)
        return {}

    hint_name = (filename_hint or os.path.basename(pdf_path) or "").lower()
    # Never OCR glossy / integrated packs — but allow combined 17-A packs that
    # also mention sustainability (common EDGE filename pattern).
    _glossy = (
        "integrated report",
        "sustainability",
        "esg report",
        "csr report",
    )
    _filing = ("17-a", "17a", "afs", "audited financial", "financial statements", "sec form 17")
    if any(s in hint_name for s in _glossy) and not any(s in hint_name for s in _filing):
        logger.info("PDF ROIC skip glossy filename %s", hint_name or os.path.basename(pdf_path))
        return {}

    doc = fitz.open(pdf_path)
    try:
        return _extract_roic_metrics_from_doc(doc, pdf_path, hint_name)
    finally:
        doc.close()


def _extract_roic_metrics_from_doc(doc, pdf_path: str, hint_name: str) -> dict[int, dict[str, Any]]:
    pages: list[tuple[int, str]] = []
    for i in range(doc.page_count):
        text = doc[i].get_text("text") or ""
        pages.append((i + 1, text))

    used_ocr = False
    if not _tesseract_available() and _pages_are_sparse(pages):
        logger.info(
            "PDF ROIC sparse/no-OCR %s (image-only and tessdata unavailable)",
            os.path.basename(pdf_path),
        )
        return {}

    if _sparse_page_indices(pages):
        pages, ocr_count, _probe_count = _apply_per_page_ocr(doc, pages)
        used_ocr = ocr_count > 0
        if _pages_are_sparse(pages) and ocr_count == 0:
            logger.info(
                "PDF ROIC sparse/no-OCR %s (image-only; OCR produced no text)",
                os.path.basename(pdf_path),
            )
            return {}

    routed = find_statement_pages(pages, prefer_consolidated=True)
    target_pages = list(routed.get("all") or [])
    income_pages = list(routed.get("income") or [])
    # Soft fallback removed: cash+assets string match was picking MD&A / PFRS prose.
    # Router already runs a substance-scored fallback when titles fail.

    scope_hint = routed.get("scope_hint") or "unknown"
    if "consolidated" in hint_name or "subsidiar" in hint_name:
        scope_hint = "consolidated"
    elif "parent" in hint_name:
        scope_hint = "parent"

    blobs: list[str] = []
    for pno, text in pages:
        if pno in target_pages:
            blobs.append(text)
    combined = "\n".join(blobs)
    if not combined.strip():
        return {}

    # Prefer BS header years (avoids +1 shift when note prose injects a future year)
    pos_text = "\n".join(
        t for pno, t in pages if pno in (routed.get("position") or [])
    )
    years = detect_statement_column_years(pos_text)
    if len(years) < 2:
        years = plausible_fiscal_years(detect_years_in_text(combined))[:4]
    else:
        years = plausible_fiscal_years(years)[:4] or years[:4]
    if not years:
        return {}
    scale = detect_scale_factor(combined)
    adapter = choose_adapter(combined)
    rows = _run_adapter(adapter, combined, years)
    # If sparse, try alternate adapter
    mapped = rows_to_yearly_metrics(rows, scale=scale, statement_scope=scope_hint)
    # Drop empty / junk year dicts
    mapped = {
        y: m for y, m in mapped.items()
        if plausible_fiscal_years([y]) and _score_metrics({y: m}) > 0
    }
    if not any("cash_and_equivalents" in m for m in mapped.values()):
        alt = "notes_column" if adapter != "notes_column" else "sequential_p"
        rows2 = _run_adapter(alt, combined, years)
        mapped2 = rows_to_yearly_metrics(rows2, scale=scale, statement_scope=scope_hint)
        mapped2 = {
            y: m for y, m in mapped2.items()
            if plausible_fiscal_years([y]) and _score_metrics({y: m}) > 0
        }
        mapped = merge_yearly_metrics(mapped, mapped2, overlay_wins=False)
        mapped = merge_yearly_metrics(mapped2, mapped, overlay_wins=False)
        # Prefer whichever has more whitelist keys
        if _score_metrics(mapped2) > _score_metrics(mapped):
            mapped = mapped2

    # Income-only fallback: when combined position+income blob missed OI/GA
    if income_pages and not any(
        m.get("operating_income") is not None or m.get("ga_expense") is not None
        for m in mapped.values()
    ):
        inc_text = "\n".join(t for pno, t in pages if pno in income_pages)
        if inc_text.strip():
            inc_years = plausible_fiscal_years(detect_years_in_text(inc_text))[:4] or years
            inc_scale = detect_scale_factor(inc_text) or scale
            inc_adapter = choose_adapter(inc_text)
            inc_rows = _run_adapter(inc_adapter, inc_text, inc_years)
            inc_mapped = rows_to_yearly_metrics(
                inc_rows, scale=inc_scale, statement_scope=scope_hint
            )
            oi_ga_overlay: dict[int, dict[str, Any]] = {}
            for y, row in inc_mapped.items():
                if y not in mapped:
                    continue  # never invent fiscal years
                patch = {}
                for fld in (
                    "operating_income",
                    "ga_expense",
                    "gross_profit",
                    "cost_of_sales",
                    "interest_expense",
                    "other_expenses",
                ):
                    if row.get(fld) is not None:
                        patch[fld] = row[fld]
                if patch:
                    oi_ga_overlay[y] = patch
            if oi_ga_overlay:
                mapped = merge_yearly_metrics(mapped, oi_ga_overlay, overlay_wins=True)
                logger.info(
                    "PDF income-only OI/GA fallback %s years=%s",
                    os.path.basename(pdf_path),
                    sorted(oi_ga_overlay),
                )

    # CF ending-cash fallback for years still missing cash (not only when all null).
    # WEB/ABA-shaped: BS hit one year; CF can fill the sibling year.
    if mapped and any(m.get("cash_and_equivalents") is None for m in mapped.values()):
        cf_pages = find_cash_flow_pages(pages)
        if cf_pages:
            cf_text = "\n".join(t for pno, t in pages if pno in cf_pages)
            cf_years = plausible_fiscal_years(detect_years_in_text(cf_text))[:4] or years
            cf_scale = detect_scale_factor(cf_text) or scale
            cf_adapter = choose_adapter(cf_text)
            cf_rows = _run_adapter(cf_adapter, cf_text, cf_years)
            cf_mapped = rows_to_yearly_metrics(
                cf_rows, scale=cf_scale, statement_scope=scope_hint
            )
            filled_cf = False
            for y, row in cf_mapped.items():
                cash = row.get("cash_and_equivalents")
                if cash is None or not plausible_fiscal_years([y]):
                    continue
                if y not in mapped:
                    continue  # never invent years from CF alone
                if mapped[y].get("cash_and_equivalents") is None and _sane_absolute(
                    float(cash), "cash_and_equivalents"
                ):
                    mapped[y]["cash_and_equivalents"] = float(cash)
                    filled_cf = True
            if filled_cf:
                logger.info(
                    "PDF ROIC CF ending-cash fill %s pages=%s",
                    os.path.basename(pdf_path),
                    cf_pages,
                )

    # Bank NPL / allowance notes (BSP tables) when BS/IS pages missed them
    if mapped and any(
        m.get(fld) is None for m in mapped.values() for fld in _BANK_AQ_FIELDS
    ):
        aq_pages = find_bank_asset_quality_pages(pages)
        if aq_pages:
            aq_text = "\n".join(t for pno, t in pages if pno in aq_pages)
            aq_years = plausible_fiscal_years(detect_years_in_text(aq_text))[:4] or years
            aq_scale = detect_scale_factor(aq_text) or scale
            aq_adapter = choose_adapter(aq_text)
            aq_rows = _run_adapter(aq_adapter, aq_text, aq_years)
            aq_mapped = rows_to_yearly_metrics(
                aq_rows, scale=aq_scale, statement_scope=scope_hint
            )
            # Unlabeled BSP non-performing column totals (BPI and peers)
            for y, npl_v in extract_bsp_npl_totals(
                aq_text, aq_years, scale=aq_scale
            ).items():
                aq_mapped.setdefault(y, {})
                if aq_mapped[y].get("npl") is None:
                    aq_mapped[y]["npl"] = npl_v
            aq_overlay: dict[int, dict[str, Any]] = {}
            for y, row in aq_mapped.items():
                if y not in mapped or not plausible_fiscal_years([y]):
                    continue
                patch = {}
                for fld in _BANK_AQ_FIELDS:
                    val = row.get(fld)
                    if val is None or mapped[y].get(fld) is not None:
                        continue
                    if _sane_absolute(float(val), fld):
                        patch[fld] = float(val)
                if patch:
                    aq_overlay[y] = patch
            if aq_overlay:
                mapped = merge_yearly_metrics(mapped, aq_overlay, overlay_wins=False)
                logger.info(
                    "PDF ROIC bank asset-quality fill %s pages=%s fields=%s",
                    os.path.basename(pdf_path),
                    aq_pages,
                    sorted({k for row in aq_overlay.values() for k in row}),
                )

    for _y, _row in mapped.items():
        _sanitize_bank_statement_row(_row)

    logger.info(
        "PDF ROIC extract %s adapter=%s scope=%s ocr=%s years=%s",
        os.path.basename(pdf_path),
        adapter,
        scope_hint,
        used_ocr,
        sorted(mapped.keys()),
    )
    return mapped


def _score_metrics(yearly: dict[int, dict[str, Any]]) -> int:
    score = 0
    for m in yearly.values():
        for k in (
            "cash_and_equivalents",
            "total_current_liabilities",
            "total_assets",
            "operating_income",
            "income_before_tax",
            "income_tax_expense",
        ):
            if m.get(k) is not None:
                score += 1
    return score


def extract_roic_metrics_from_pdf_bytes(
    data: bytes,
    *,
    filename_hint: str | None = None,
    cache_path: str | None = None,
) -> dict[int, dict[str, Any]]:
    """Write bytes to cache_path (or temp) and extract."""
    import tempfile

    if cache_path:
        os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
        with open(cache_path, "wb") as f:
            f.write(data)
        return extract_roic_metrics_from_pdf_path(cache_path, filename_hint=filename_hint)

    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        with open(path, "wb") as f:
            f.write(data)
        return extract_roic_metrics_from_pdf_path(path, filename_hint=filename_hint)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _values_effectively_equal(a: Any, b: Any, *, rel_tol: float = 1e-6) -> bool:
    """True when HTML and PDF agree (no merge write / log needed)."""
    if a is None or b is None:
        return False
    if isinstance(a, str) or isinstance(b, str):
        return str(a).strip().lower() == str(b).strip().lower()
    try:
        fa, fb = float(a), float(b)
    except (TypeError, ValueError):
        return a == b
    if fa == fb:
        return True
    scale = max(abs(fa), abs(fb), 1.0)
    return abs(fa - fb) / scale <= rel_tol


def _html_field_replaceable(key: str, html_row: dict[str, Any]) -> bool:
    """True when HTML is null or fails sane/scale checks (PDF may overwrite)."""
    existing = html_row.get(key)
    if existing is None:
        return True
    rev = html_row.get("revenue")
    if rev is None:
        rev = html_row.get("gross_revenue")
    if key == "operating_income":
        from src.report_metrics import needs_pdf_oi, operating_income_sane

        if needs_pdf_oi(html_row):
            return True
        return not operating_income_sane(
            existing,
            revenue=rev,
            gross_profit=html_row.get("gross_profit"),
            net_income=html_row.get("net_income"),
            income_before_tax=html_row.get("income_before_tax"),
        )
    if key == "gross_profit":
        from src.report_metrics import gross_profit_sane

        return not gross_profit_sane(
            existing,
            revenue=rev,
            total_assets=html_row.get("total_assets"),
            net_income=html_row.get("net_income"),
        )
    if key == "cash_and_equivalents":
        from src.report_metrics import needs_pdf_cash

        return needs_pdf_cash(html_row)
    if key == "ga_expense":
        from src.report_metrics import needs_pdf_ga

        return needs_pdf_ga(html_row)
    if key == "eps":
        from src.report_metrics import needs_pdf_eps

        return needs_pdf_eps(html_row)
    return False


def _pdf_prefer_field(
    key: str,
    html_row: dict[str, Any],
    pdf_value: Any,
    *,
    pdf_first: bool,
) -> bool:
    """
    Whether PDF may replace non-null HTML for this field under PDF-first policy.

    Non-financial + untrusted HTML: prefer PDF OI/GA/cash when PDF is sane and
    (for OI) closer to IBT than HTML, or HTML needs PDF.
    """
    # Bank checklist fields: always allow PDF overwrite (even when pdf_first is
    # False for financials — HTML/DB often holds interest-income false positives).
    if key in (
        "total_loans",
        "total_deposits",
        "npl",
        "net_interest_income",
        "allowance_for_credit_losses",
    ):
        return True
    if not pdf_first:
        return _html_field_replaceable(key, html_row)
    if key == "gross_profit":
        return _html_field_replaceable(key, html_row)
    if key == "operating_income":
        from src.report_metrics import needs_pdf_oi, pdf_oi_closer_to_ibt

        if needs_pdf_oi(html_row):
            return True
        existing = html_row.get(key)
        if existing is None:
            return True
        return pdf_oi_closer_to_ibt(
            pdf_value, existing, html_row.get("income_before_tax")
        )
    if key == "ga_expense":
        from src.report_metrics import needs_pdf_ga, safe_float

        if not needs_pdf_ga(html_row):
            return False
        # Reject wrong-scale OCR GA (e.g. thousands vs HTML pesos)
        existing = safe_float(html_row.get(key))
        pdf_f = safe_float(pdf_value)
        if existing is not None and pdf_f is not None and abs(existing) >= 1_000:
            ratio = abs(pdf_f) / abs(existing)
            if ratio < 0.05 or ratio > 20:
                return False
        return True
    if key == "cash_and_equivalents":
        from src.report_metrics import needs_pdf_cash

        return needs_pdf_cash(html_row)
    if key == "eps":
        from src.report_metrics import needs_pdf_eps

        return needs_pdf_eps(html_row)
    return _html_field_replaceable(key, html_row)


def fill_html_whitelist(
    html_yearly: dict[int, dict[str, Any]],
    pdf_yearly: dict[int, dict[str, Any]],
    company: dict[str, Any] | None = None,
) -> dict[int, dict[str, Any]]:
    """
    Merge policy: PDF fills nulls — and overwrites insane / untrusted HTML
    OI/GP/GA/cash — on existing HTML fiscal years only.

    For non-financial companies, prefer PDF OI/GA/cash when HTML needs PDF
    (``needs_pdf_oi`` / cash/GA trust signals) or PDF OI is closer to IBT.

    - Never invent new fiscal-year keys from PDF.
    - Never overwrite with PDF that fails ``_pdf_value_ok``.
    - Financial sector: never PDF-prefer OI (equity ROIC path).
    """
    from src.filing_triage import is_banks_subsector, is_financial_sector
    from src.parser import _reconcile_balance_sheet
    from src.report_metrics import normalize_ga_expense, sanitize_operating_metrics
    from src.scale_guard import harmonize_intra_year_pl_scale

    company = company or {}
    financial = is_financial_sector(company.get("sector"), company.get("subsector"))
    deposit_bank = is_banks_subsector(company.get("sector"), company.get("subsector"))
    pdf_first = not financial

    replaceable = frozenset({
        "operating_income",
        "gross_profit",
        "ga_expense",
        "cash_and_equivalents",
        "eps",
    })
    bank_keys = frozenset({
        "total_loans",
        "total_deposits",
        "npl",
        "net_interest_income",
        "allowance_for_credit_losses",
    })
    # Financials: never prefer-PDF overwrite OI/GA (cash null-fill still ok).
    # Deposit banks: PDF AFS wins on loan/deposit/NPL/NII/ACL checklist fields.
    if deposit_bank:
        prefer_keys = frozenset({"cash_and_equivalents", "gross_profit", "eps"}) | bank_keys
    elif financial:
        prefer_keys = frozenset({"cash_and_equivalents", "gross_profit", "eps"})
    else:
        prefer_keys = replaceable

    from src.field_sources import apply_derived_flags, init_sources_from_metrics, set_source
    from src.report_metrics import derive_eps_from_ni_shares

    merged = {y: dict(m) for y, m in (html_yearly or {}).items()}
    for y, row in merged.items():
        if "_field_sources" not in row:
            init_sources_from_metrics(row, "html")
    html_years = set(merged.keys())
    whitelist_keys = set(LABEL_MAP.keys()) | set(_PDF_META_KEYS)
    for y, m in (pdf_yearly or {}).items():
        if y not in html_years:
            continue
        if not plausible_fiscal_years([y]):
            continue
        html_row = merged[y]
        # If PDF cash proves HTML assets are in thousands, lift before any
        # field merge so TCL/OI checks use the same peso scale.
        raw_cash = m.get("cash_and_equivalents")
        if raw_cash is not None:
            try:
                _, pre_reason = _coerce_pdf_cash(float(raw_cash), html_row)
            except (TypeError, ValueError):
                pre_reason = ""
            if pre_reason == "html_thousands":
                logger.info(
                    "PDF cash y=%s fits HTML×1000 assets; lifting HTML absolutes",
                    y,
                )
                _lift_row_absolute_x1000(html_row)
        for k, v in m.items():
            if v is None:
                continue
            if k not in whitelist_keys:
                if k not in html_row or html_row[k] is None:
                    merged[y][k] = v
                    set_source(merged[y], k, "pdf")
                continue

            if k == "cash_and_equivalents":
                try:
                    raw = float(v)
                except (TypeError, ValueError):
                    logger.info("skip PDF %s y=%s reason=not_numeric value=%s", k, y, v)
                    continue
                coerced, cash_reason = _coerce_pdf_cash(raw, html_row)
                if coerced is None:
                    logger.info(
                        "skip PDF %s y=%s reason=%s value=%s",
                        k,
                        y,
                        cash_reason,
                        v,
                    )
                    continue
                if coerced != raw:
                    logger.info(
                        "PDF cash y=%s scaled %s → %s",
                        y,
                        raw,
                        coerced,
                    )
                v = coerced

            if k in ("allowance_for_credit_losses", "npl"):
                try:
                    raw_aq = float(v)
                except (TypeError, ValueError):
                    continue
                loans_anchor = m.get("total_loans")
                if loans_anchor is None:
                    loans_anchor = html_row.get("total_loans")
                if loans_anchor is not None:
                    lo, hi = (
                        (0.0005, 0.25)
                        if k == "allowance_for_credit_losses"
                        else (0.0005, 0.40)
                    )
                    scaled = _scale_aq_to_loans(
                        raw_aq, float(loans_anchor), lo_ratio=lo, hi_ratio=hi
                    )
                    if scaled is None:
                        logger.info(
                            "skip PDF %s y=%s reason=aq_vs_loans value=%s",
                            k,
                            y,
                            v,
                        )
                        continue
                    if abs(scaled - abs(raw_aq)) > 1.0:
                        logger.info(
                            "PDF %s y=%s scaled %s → %s vs loans",
                            k,
                            y,
                            raw_aq,
                            scaled,
                        )
                    v = scaled

            # Prefer PDF loans when present so deposit/AQ checks use them.
            # Only overlay PDF total_assets when HTML lacks them or the two
            # agree within ~100× — otherwise OCR/scale scrap (AP 7e6) poisons
            # cash / TCL gates against correct EDGE HTML assets.
            check_row = dict(html_row)
            if m.get("total_loans") is not None:
                check_row["total_loans"] = m.get("total_loans")
            pdf_assets = m.get("total_assets")
            html_assets = html_row.get("total_assets")
            if pdf_assets is not None:
                use_pdf_assets = html_assets is None
                if not use_pdf_assets:
                    try:
                        ha = abs(float(html_assets))
                        pa = abs(float(pdf_assets))
                        if ha > 0 and pa > 0:
                            ratio = max(ha, pa) / min(ha, pa)
                            use_pdf_assets = ratio <= 100.0
                    except (TypeError, ValueError):
                        use_pdf_assets = False
                if use_pdf_assets:
                    check_row["total_assets"] = pdf_assets

            ok, reason = _pdf_value_ok(k, v, check_row)
            if not ok:
                logger.info(
                    "skip PDF %s y=%s reason=%s value=%s",
                    k,
                    y,
                    reason,
                    v,
                )
                continue

            if k == "eps":
                from src.report_metrics import eps_plausible

                price = company.get("last_traded_price")
                if not eps_plausible(v, check_row, price=price):
                    logger.info(
                        "skip PDF eps y=%s reason=scale_vs_ni_or_price value=%s",
                        y,
                        v,
                    )
                    continue

            from src.report_metrics import metric_value as _metric_value

            existing = html_row.get(k)
            # Exact 0 revenue/EPS are placeholders (ZERO_AS_MISSING); treat as null
            existing_missing = existing is None or (
                k in ("revenue", "gross_revenue", "eps")
                and _metric_value(existing, k) is None
            )
            if not existing_missing:
                if _values_effectively_equal(existing, v):
                    # Same number already in HTML — keep source, no churn
                    continue
                may_replace = (
                    k in prefer_keys
                    and _pdf_prefer_field(k, html_row, v, pdf_first=pdf_first)
                )
                if not may_replace:
                    # Fall back to insane-only replaceable for GP etc.
                    if k not in replaceable or not _html_field_replaceable(k, html_row):
                        # Routine: HTML already has a value; PDF fill-nulls skips.
                        logger.debug(
                            "skip PDF %s y=%s reason=html_present value=%s",
                            k,
                            y,
                            v,
                        )
                        continue
                logger.info(
                    "overwrite HTML %s y=%s html=%s pdf=%s pdf_first=%s",
                    k,
                    y,
                    existing,
                    v,
                    pdf_first,
                )

            if k == "ga_expense":
                v = normalize_ga_expense(v)
                if v is None:
                    continue
            if k == "net_income":
                # Parent-loss tables sometimes land unsigned; prefer IBT sign
                try:
                    ibt = html_row.get("income_before_tax")
                    ibt_f = float(ibt) if ibt is not None else None
                    vf = float(v)
                except (TypeError, ValueError):
                    ibt_f = None
                    vf = None
                if (
                    ibt_f is not None
                    and vf is not None
                    and abs(ibt_f) > 1.0
                    and (vf > 0) != (ibt_f > 0)
                    and abs(abs(vf) - abs(ibt_f)) / abs(ibt_f) <= 0.15
                ):
                    v = -abs(vf) if ibt_f < 0 else abs(vf)
                    logger.info(
                        "PDF net_income y=%s sign-aligned to IBT → %s", y, v
                    )
            merged[y][k] = v
            set_source(merged[y], k, "pdf")

    from src.report_metrics import (
        apply_revenue_surrogate,
        derive_book_value_per_share,
        derive_eps_from_ni_shares,
        derive_ni_from_eps_shares,
        derive_ni_from_ibt,
    )

    shares_fb = company.get("outstanding_shares")
    price = company.get("last_traded_price")
    fin_rows = list(merged.values())
    for y, row in merged.items():
        # Drop non-positive revenue before surrogate so shells can refill
        from src.report_metrics import clear_invalid_derived_revenue, eps_plausible
        from src.utils import safe_float as _sf

        if clear_invalid_derived_revenue(row):
            src_map = row.get("_field_sources")
            if isinstance(src_map, dict):
                src_map.pop("revenue", None)
        src = apply_revenue_surrogate(row, company, financials=fin_rows)
        if src:
            set_source(row, "revenue", "derived")
            logger.info(
                "revenue surrogate y=%s from %s → %s", y, src, row.get("revenue")
            )
        # Drop absurd EPS (e.g. PDF 265 vs NI/shares ~0.001) before derives
        existing_eps = _sf(row.get("eps"))
        if existing_eps is not None and not eps_plausible(
            existing_eps, row, price=price
        ):
            logger.info("drop absurd EPS y=%s value=%s", y, existing_eps)
            row["eps"] = None
            src_map = row.get("_field_sources")
            if isinstance(src_map, dict):
                src_map.pop("eps", None)
        # IBT first on wipeout years (SUN), then EPS×shares
        derived_ni = derive_ni_from_ibt(row)
        if derived_ni is not None:
            row["net_income"] = derived_ni
            set_source(row, "net_income", "derived")
            logger.info("derived NI y=%s from IBT−tax → %s", y, derived_ni)
        else:
            derived_ni = derive_ni_from_eps_shares(row, shares_fallback=shares_fb)
            if derived_ni is not None:
                row["net_income"] = derived_ni
                set_source(row, "net_income", "derived")
                logger.info("derived NI y=%s from EPS×shares → %s", y, derived_ni)
        derived = derive_eps_from_ni_shares(
            row, shares_fallback=shares_fb, price=price
        )
        if derived is not None:
            row["eps"] = derived
            set_source(row, "eps", "derived")
            logger.info("derived EPS y=%s from NI/shares → %s", y, derived)
        bv = derive_book_value_per_share(row, shares_fallback=shares_fb)
        if bv is not None:
            row["book_value"] = bv
            set_source(row, "book_value", "derived")
            logger.info("derived book_value y=%s from equity/shares → %s", y, bv)

    # Prior-FY NPL carry when extract hit older years but missed the latest
    years_sorted = sorted(merged.keys())
    for i, y in enumerate(years_sorted):
        if i == 0:
            continue
        if merged[y].get("npl") is not None:
            continue
        prev_npl = merged[years_sorted[i - 1]].get("npl")
        if prev_npl is None:
            continue
        try:
            npl_v = float(prev_npl)
        except (TypeError, ValueError):
            continue
        if npl_v <= 0 or not _sane_absolute(npl_v, "npl"):
            continue
        merged[y]["npl"] = npl_v
        set_source(merged[y], "npl", "derived")
        logger.info("NPL prior-FY carry y=%s ← %s value=%s", y, years_sorted[i - 1], npl_v)

    for y in list(merged.keys()):
        # Preserve sources across reconcile / scale / sanitize
        sources = dict(merged[y].get("_field_sources") or {})
        row = _reconcile_balance_sheet(merged[y])
        harmonize_intra_year_pl_scale(row)
        row["_field_sources"] = sources
        merged[y] = sanitize_operating_metrics(row, company=company)
        apply_derived_flags(merged[y])
    return merged
