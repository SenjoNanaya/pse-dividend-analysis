"""
Detect and repair ~1000× cross-year scale mismatches on absolute statement metrics.

PSE EDGE HTML often reports figures "in thousands"; a missed Currency scale on one
disclosure leaves one fiscal year ~1000× off while A≈L+E still holds.

When book value/share and shares are present, prefer the magnitude that makes
stockholders_equity ≈ book_value × shares.
"""
from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

# Adjacent asset ratio band that indicates a thousands-unit error (not real growth).
NEAR_1000_LO = 500.0
NEAR_1000_HI = 2000.0

_ALIGN_MULTS = (0.001, 1.0, 1000.0)

# Absolute peso fields (HTML pipeline names + DB column names).
SCALE_ABSOLUTE_KEYS = (
    "total_assets",
    "total_liabilities",
    "total_current_liabilities",
    "stockholders_equity",
    "gross_revenue",
    "revenue",
    "net_income",
    "cash_and_equivalents",
    "operating_income",
    "income_before_tax",
    "income_tax_expense",
    "gross_profit",
    "ga_expense",
)


def _assets(row: dict[str, Any]) -> float | None:
    raw = row.get("total_assets")
    if raw is None:
        return None
    try:
        val = abs(float(raw))
    except (TypeError, ValueError):
        return None
    return val if val > 0 else None


def asset_ratio(a: float, b: float) -> float | None:
    if a <= 0 or b <= 0:
        return None
    return max(a, b) / min(a, b)


def has_thousand_scale_jump(yearly: dict[int, dict[str, Any]]) -> bool:
    years = sorted(y for y, row in yearly.items() if _assets(row) is not None)
    for i in range(1, len(years)):
        a0 = _assets(yearly[years[i - 1]])
        a1 = _assets(yearly[years[i]])
        r = asset_ratio(a0, a1) if a0 and a1 else None
        if r is not None and NEAR_1000_LO <= r <= NEAR_1000_HI:
            return True
    return False


def _book_value(row: dict[str, Any]) -> float | None:
    raw = row.get("book_value")
    if raw is None:
        raw = row.get("book_value_per_share")
    if raw is None:
        return None
    try:
        val = abs(float(raw))
    except (TypeError, ValueError):
        return None
    return val if val > 0 else None


def _shares(row: dict[str, Any], fallback: float | None) -> float | None:
    raw = row.get("outstanding_shares")
    if raw is None:
        raw = fallback
    if raw is None:
        return None
    try:
        val = abs(float(raw))
    except (TypeError, ValueError):
        return None
    return val if val > 0 else None


def _equity_bv_log_err(
    row: dict[str, Any],
    *,
    equity_mult: float = 1.0,
    shares_fallback: float | None = None,
) -> float | None:
    """|log10(BV×shares) - log10(equity×mult)|; None if anchors missing."""
    eq = row.get("stockholders_equity")
    bv = _book_value(row)
    sh = _shares(row, shares_fallback)
    if eq is None or bv is None or sh is None:
        return None
    try:
        eq = abs(float(eq) * equity_mult)
    except (TypeError, ValueError):
        return None
    if eq <= 0:
        return None
    implied = bv * sh
    if implied <= 0:
        return None
    return abs(math.log10(implied) - math.log10(eq))


def _best_mult_to_ref(value: float, ref: float) -> tuple[float, float]:
    best_m, best_err = 1.0, abs(math.log10(value) - math.log10(ref))
    for m in _ALIGN_MULTS:
        if m == 1.0:
            continue
        err = abs(math.log10(value * m) - math.log10(ref))
        if err < best_err:
            best_m, best_err = m, err
    return best_m, best_err


def _max_adjacent_yoy(scaled_assets: dict[int, float]) -> float:
    years = sorted(scaled_assets)
    worst = 1.0
    for i in range(1, len(years)):
        r = asset_ratio(scaled_assets[years[i - 1]], scaled_assets[years[i]])
        if r is not None and r > worst:
            worst = r
    return worst


def _scale_row(row: dict[str, Any], mult: float) -> None:
    for key in SCALE_ABSOLUTE_KEYS:
        raw = row.get(key)
        if raw is None:
            continue
        try:
            row[key] = float(raw) * mult
        except (TypeError, ValueError):
            continue


def repair_thousand_scale_jumps(
    yearly: dict[int, dict[str, Any]],
    *,
    inplace: bool = True,
    shares_fallback: float | None = None,
) -> tuple[dict[int, dict[str, Any]], list[str]]:
    """
    If any adjacent years show a ~1000× total_assets jump, rescale absolute metrics
    so years align. Prefer the plan that also makes equity ≈ BV × shares when
    those anchors exist.

    Returns (yearly, action log strings). Per-share fields are left untouched.
    """
    if not yearly:
        return yearly, []

    work = yearly if inplace else {y: dict(row) for y, row in yearly.items()}
    if not has_thousand_scale_jump(work):
        return work, []

    years = sorted(y for y, row in work.items() if _assets(row) is not None)
    assets = {y: _assets(work[y]) for y in years}
    assets = {y: a for y, a in assets.items() if a is not None}
    years = sorted(assets)
    if len(years) < 2:
        return work, []

    # score: (max_yoy, bv_err_sum, asset_align_err, -bv_anchors, corrections, mults)
    best: tuple | None = None
    for ref_y in years:
        ref_a = assets[ref_y]
        mults: dict[int, float] = {}
        align_err = 0.0
        corrections = 0
        for y in years:
            m, err = _best_mult_to_ref(assets[y], ref_a)
            if m != 1.0:
                aligned = assets[y] * m
                r = asset_ratio(aligned, ref_a)
                if r is None or r > 5.0:
                    m, err = 1.0, abs(math.log10(assets[y]) - math.log10(ref_a))
                else:
                    corrections += 1
            mults[y] = m
            align_err += err

        scaled = {y: assets[y] * mults[y] for y in years}
        max_yoy = _max_adjacent_yoy(scaled)
        if corrections == 0 or max_yoy >= NEAR_1000_LO:
            continue

        bv_err = 0.0
        bv_n = 0
        for y in years:
            err = _equity_bv_log_err(
                work[y],
                equity_mult=mults[y],
                shares_fallback=shares_fallback,
            )
            if err is None:
                continue
            bv_err += err
            bv_n += 1

        # Missing BV anchors → large placeholder so BV-informed plans win ties
        bv_score = bv_err if bv_n else 1e9
        plan = (max_yoy, bv_score, align_err, -bv_n, corrections, mults)
        if best is None or plan[:5] < best[:5]:
            best = plan

    if best is None:
        logger.warning(
            "Thousand-scale jump detected but no stable repair; leaving unchanged"
        )
        return work, []

    mults = best[5]
    actions: list[str] = []
    for y, m in sorted(mults.items()):
        if m == 1.0:
            continue
        before = assets[y]
        _scale_row(work[y], m)
        after = _assets(work[y])
        actions.append(f"FY{y}×{m:g} assets {before:.6g}→{after:.6g}")
        logger.info("Scale guard: FY%s absolute metrics ×%g", y, m)

    return work, actions
