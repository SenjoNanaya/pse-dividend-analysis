"""Extract closed ROIC whitelist from PDF filings (anti-bloat)."""

from __future__ import annotations

import os
import re
from typing import Any

from src.pdf_adapters.notes_column import parse_notes_column
from src.pdf_adapters.scaled_multi_column import parse_scaled_multi_column
from src.pdf_adapters.sequential_p import parse_sequential_p
from src.pdf_adapters.common import detect_years_in_text
from src.pdf_page_router import (
    detect_scale_factor,
    find_cash_flow_pages,
    find_statement_pages,
)
from src.utils import logger

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None

from datetime import date


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
)
_PDF_META_KEYS = frozenset({"operating_income_derived", "statement_scope", "scale"})


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
    ):
        if abs(v) < 1_000:
            return False
        # Year headers (e.g. 2024) often land in the assets/cash column
        if field in ("total_assets", "cash_and_equivalents") and 1990 <= abs(v) <= 2100 and abs(v - round(v)) < 1e-9:
            return False
        return True
    return True


def _pdf_value_ok(
    key: str,
    value: Any,
    html_row: dict[str, Any] | None,
) -> tuple[bool, str]:
    """
    Reject nonsensical PDF whitelist values before merge.
    Returns (ok, reason) — reason is empty when ok.
    """
    if key in _PDF_META_KEYS:
        return True, ""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False, "not_numeric"
    if key in _NONNEG_PDF_FIELDS and v < 0:
        return False, "negative"
    if key in LABEL_MAP and not _sane_absolute(v, key):
        return False, "below_floor"
    html_row = html_row or {}
    html_assets = html_row.get("total_assets")
    if html_assets is not None and key in (
        "cash_and_equivalents",
        "total_current_liabilities",
    ):
        try:
            a = abs(float(html_assets))
        except (TypeError, ValueError):
            a = 0.0
        if a > 0 and v > a * 1.05:
            return False, "exceeds_html_assets"
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
    return True, ""

# Closed ROIC field synonyms (label substring match, lowercase)
LABEL_MAP: dict[str, tuple[str, ...]] = {
    "cash_and_equivalents": (
        "cash and cash equivalents",
        "cash & cash equivalents",
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
        "cash at end of year",
        "cash at end of the year",
        "ending cash and cash equivalents",
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
                    if "from financing" in low:
                        continue
                if field == "other_expenses":
                    # Prefer short IS labels; skip note prose
                    if len(low.strip()) > 48:
                        continue
                    if "income" in low and "operating" not in low:
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
                        )
                    )
                    if ending:
                        return field
                    if "flow" in low or "flows" in low:
                        continue
                    if "dividend" in low or "generated" in low or "used in" in low:
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
                scaled = float(raw) * meta_scale
            except (TypeError, ValueError):
                continue
            if not _sane_absolute(scaled, field):
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
    """
    out = {y: dict(m) for y, m in (base or {}).items()}
    for y, m in (overlay or {}).items():
        out.setdefault(y, {})
        for k, v in m.items():
            if v is None:
                continue
            if overlay_wins or k not in out[y] or out[y][k] is None:
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


def _pages_are_sparse(pages: list[tuple[int, str]], *, min_chars: int = 200) -> bool:
    """True when the pack has almost no extractable text (likely image-only)."""
    total = sum(_alnum_char_count(t) for _, t in pages)
    return total < min_chars


def _resolve_tessdata() -> str | None:
    """
    Directory containing eng.traineddata for PyMuPDF OCR.

    MuPDF does not auto-discover Windows installs — pass this path explicitly
    to get_textpage_ocr(tessdata=...). Prefer TESSDATA_PREFIX when set.
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
        # Accept either .../tessdata or the Tesseract root
        eng = os.path.join(path, "eng.traineddata")
        if os.path.isfile(eng):
            return path
        nested = os.path.join(path, "tessdata", "eng.traineddata")
        if os.path.isfile(nested):
            return os.path.join(path, "tessdata")
    return None


def _tesseract_available() -> bool:
    """True when eng.traineddata is findable for PyMuPDF OCR."""
    return _resolve_tessdata() is not None


def _ocr_pages(
    doc,
    *,
    max_pages: int = 40,
    dpi: int = 200,
) -> list[tuple[int, str]]:
    """
    OCR first max_pages of an image-only PDF via PyMuPDF + Tesseract tessdata.
    Soft-fails to [] when tessdata is missing or OCR errors.
    """
    tessdata = _resolve_tessdata()
    if not tessdata:
        logger.info("OCR skipped: Tesseract tessdata not found (set TESSDATA_PREFIX)")
        return []
    out: list[tuple[int, str]] = []
    n = min(int(doc.page_count), max_pages)
    for i in range(n):
        page = doc[i]
        try:
            tp = page.get_textpage_ocr(
                language="eng",
                dpi=dpi,
                full=True,
                tessdata=tessdata,
            )
            text = page.get_text("text", textpage=tp) or ""
        except Exception as exc:  # pragma: no cover - depends on local tessdata
            logger.warning(
                "OCR failed on page %s of %s: %s",
                i + 1,
                getattr(doc, "name", "?"),
                exc,
            )
            return out
        out.append((i + 1, text))
    logger.info(
        "OCR extracted text from %s pages (%s alnum chars) tessdata=%s",
        len(out),
        sum(_alnum_char_count(t) for _, t in out),
        tessdata,
    )
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
    # Never OCR glossy / integrated packs even if somehow passed in
    if any(
        s in hint_name
        for s in (
            "integrated report",
            "sustainability",
            "esg report",
            "csr report",
        )
    ):
        logger.info("PDF ROIC skip glossy filename %s", hint_name or os.path.basename(pdf_path))
        return {}

    doc = fitz.open(pdf_path)
    pages: list[tuple[int, str]] = []
    for i in range(doc.page_count):
        text = doc[i].get_text("text") or ""
        pages.append((i + 1, text))

    used_ocr = False
    if _pages_are_sparse(pages):
        ocr_pages = _ocr_pages(doc, max_pages=40)
        if ocr_pages:
            pages = ocr_pages
            used_ocr = True
        else:
            logger.info(
                "PDF ROIC sparse/no-OCR %s (image-only and tessdata unavailable)",
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

    years = detect_years_in_text(combined)
    years = plausible_fiscal_years(years)[:4]
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

    # CF ending-cash fallback when position/income pages had no cash line
    if not any(m.get("cash_and_equivalents") is not None for m in mapped.values()):
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
            if any(m.get("cash_and_equivalents") is not None for m in mapped.values()):
                logger.info(
                    "PDF ROIC CF ending-cash fill %s pages=%s",
                    os.path.basename(pdf_path),
                    cf_pages,
                )

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
        from src.report_metrics import needs_pdf_ga, needs_pdf_oi

        return needs_pdf_ga(html_row) or needs_pdf_oi(html_row)
    if key == "cash_and_equivalents":
        from src.report_metrics import needs_pdf_cash

        return needs_pdf_cash(html_row)
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
    from src.filing_triage import is_financial_sector
    from src.parser import _reconcile_balance_sheet
    from src.report_metrics import normalize_ga_expense, sanitize_operating_metrics
    from src.scale_guard import harmonize_intra_year_pl_scale

    company = company or {}
    financial = is_financial_sector(company.get("sector"), company.get("subsector"))
    pdf_first = not financial

    replaceable = frozenset({
        "operating_income",
        "gross_profit",
        "ga_expense",
        "cash_and_equivalents",
    })
    # Banks: never prefer-PDF overwrite OI/GA (cash null-fill still ok via replaceable)
    if financial:
        prefer_keys = frozenset({"cash_and_equivalents", "gross_profit"})
    else:
        prefer_keys = replaceable

    merged = {y: dict(m) for y, m in (html_yearly or {}).items()}
    html_years = set(merged.keys())
    whitelist_keys = set(LABEL_MAP.keys()) | set(_PDF_META_KEYS)
    for y, m in (pdf_yearly or {}).items():
        if y not in html_years:
            continue
        if not plausible_fiscal_years([y]):
            continue
        html_row = merged[y]
        for k, v in m.items():
            if v is None:
                continue
            if k not in whitelist_keys:
                if k not in html_row or html_row[k] is None:
                    merged[y][k] = v
                continue

            ok, reason = _pdf_value_ok(k, v, html_row)
            if not ok:
                logger.info(
                    "skip PDF %s y=%s reason=%s value=%s",
                    k,
                    y,
                    reason,
                    v,
                )
                continue

            existing = html_row.get(k)
            if existing is not None:
                may_replace = (
                    k in prefer_keys
                    and _pdf_prefer_field(k, html_row, v, pdf_first=pdf_first)
                )
                if not may_replace:
                    # Fall back to insane-only replaceable for GP etc.
                    if k not in replaceable or not _html_field_replaceable(k, html_row):
                        logger.info(
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
            merged[y][k] = v

    for y in list(merged.keys()):
        row = _reconcile_balance_sheet(merged[y])
        harmonize_intra_year_pl_scale(row)
        merged[y] = sanitize_operating_metrics(row, company=company)
    return merged
