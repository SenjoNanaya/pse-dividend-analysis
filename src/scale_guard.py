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
    "cost_of_sales",
    "interest_expense",
    "other_expenses",
    "total_loans",
    "total_deposits",
    "npl",
    "net_interest_income",
    "allowance_for_credit_losses",
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


_PL_HARMONIZE_KEYS = (
    "operating_income",
    "gross_profit",
    "ga_expense",
    "cost_of_sales",
    "interest_expense",
    "other_expenses",
)
_LOG10_1000_LO = 2.5
_LOG10_1000_HI = 3.5


def _sf(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _log10_gap(a: float, b: float) -> float | None:
    if a == 0 or b == 0:
        return None
    aa, bb = abs(a), abs(b)
    if aa <= 0 or bb <= 0:
        return None
    return abs(math.log10(aa) - math.log10(bb))


def _pl_anchor(metrics: dict[str, Any]) -> float | None:
    for key in ("net_income", "income_before_tax", "revenue", "gross_revenue"):
        v = _sf(metrics.get(key))
        if v is not None and abs(v) >= 1_000_000.0:
            return v
    return None


def harmonize_intra_year_pl_scale(metrics: dict[str, Any]) -> list[str]:
    """
    In-place: fix mixed ×1000 scale inside one fiscal year.

    - If OI/GP/GA sit ~1000× off the NI/IBT/revenue anchor, rescale the P&L trio.
    - If cash is &lt;0.1% of assets while NI is large and cash×1000 fits assets, ×1000 cash.
    - If GA alone is absurdly small vs revenue (~×1000), ×1000 GA.

    Returns action log strings.
    """
    if not metrics:
        return []
    from src.report_metrics import (
        gross_profit_sane,
        operating_income_sane,
        sanitize_operating_metrics,
    )

    actions: list[str] = []
    anchor = _pl_anchor(metrics)
    rev = _sf(metrics.get("revenue"))
    if rev is None:
        rev = _sf(metrics.get("gross_revenue"))

    if anchor is not None:
        trial = {k: _sf(metrics.get(k)) for k in _PL_HARMONIZE_KEYS}
        present = {k: v for k, v in trial.items() if v is not None and v != 0}
        if present:
            gaps = {
                k: _log10_gap(v, anchor)
                for k, v in present.items()
                if _log10_gap(v, anchor) is not None
            }
            need = [
                k
                for k, g in gaps.items()
                if g is not None and _LOG10_1000_LO <= g <= _LOG10_1000_HI
            ]
            # Only upscale small P&L toward a larger NI/IBT/rev anchor (JFC-shaped).
            # Never shrink huge GP toward a micro NI (AEV-shaped) — leave that to GP sane.
            need_up = [
                k
                for k in need
                if abs(present[k]) < abs(anchor)
            ]
            if need_up:
                # Keep OI/GP/GA on one scale when any of them needs ×1000
                pl_core = ("operating_income", "gross_profit", "ga_expense")
                if any(k in need_up for k in pl_core):
                    for k in pl_core:
                        if (
                            k not in need_up
                            and k in present
                            and abs(present[k]) < abs(anchor)
                        ):
                            need_up.append(k)
                mult = 1000.0
                candidate = dict(metrics)
                for k in need_up:
                    try:
                        candidate[k] = float(candidate[k]) * mult
                    except (TypeError, ValueError):
                        pass
                oi = _sf(candidate.get("operating_income"))
                gp = _sf(candidate.get("gross_profit"))
                # Only re-check OI/GP sanity when those keys were scaled
                oi_ok = (
                    "operating_income" not in need_up
                    or oi is None
                    or operating_income_sane(
                        oi,
                        revenue=_sf(candidate.get("revenue"))
                        or _sf(candidate.get("gross_revenue")),
                        gross_profit=gp,
                        net_income=candidate.get("net_income"),
                        income_before_tax=candidate.get("income_before_tax"),
                    )
                )
                gp_ok = (
                    "gross_profit" not in need_up
                    or gp is None
                    or gross_profit_sane(
                        gp,
                        revenue=_sf(candidate.get("revenue"))
                        or _sf(candidate.get("gross_revenue")),
                        total_assets=candidate.get("total_assets"),
                        net_income=candidate.get("net_income"),
                    )
                )
                if oi_ok and gp_ok:
                    for k in need_up:
                        metrics[k] = float(metrics[k]) * mult
                    actions.append(f"pl×{mult:g} keys={','.join(need_up)}")
                    logger.info("Intra-year P&L scale: ×%g on %s", mult, need_up)

    # Cash ×1000 when tiny vs assets (ALI-shaped)
    cash = _sf(metrics.get("cash_and_equivalents"))
    assets = _sf(metrics.get("total_assets"))
    ni = _sf(metrics.get("net_income"))
    if (
        cash is not None
        and assets is not None
        and abs(assets) >= 1_000_000.0
        and abs(cash) > 0
        and abs(cash) < 0.001 * abs(assets)
        and ni is not None
        and abs(ni) >= 1_000_000.0
    ):
        scaled = abs(cash) * 1000.0
        if scaled < abs(assets) * 0.5 and scaled > abs(assets) * 0.001:
            metrics["cash_and_equivalents"] = cash * 1000.0
            actions.append(f"cash×1000 {cash:.6g}→{cash * 1000.0:.6g}")
            logger.info("Intra-year cash scale: ×1000")

    # Lone GA ×1000 when absurdly small vs revenue
    ga = _sf(metrics.get("ga_expense"))
    if (
        ga is not None
        and rev is not None
        and abs(rev) >= 1_000_000.0
        and abs(ga) > 0
        and abs(ga) < 0.0005 * abs(rev)
    ):
        gap = _log10_gap(ga, rev * 0.05)  # typical GAE ~ few % of rev
        if gap is not None and _LOG10_1000_LO <= gap <= _LOG10_1000_HI:
            scaled_ga = abs(ga) * 1000.0
            if scaled_ga < 0.8 * abs(rev):
                metrics["ga_expense"] = abs(ga) * 1000.0
                actions.append(f"ga×1000 {ga:.6g}→{abs(ga) * 1000.0:.6g}")
                logger.info("Intra-year GA scale: ×1000")

    if actions:
        sanitize_operating_metrics(metrics)
    return actions


def harmonize_yearly_pl_scale(
    yearly: dict[int, dict[str, Any]],
    *,
    inplace: bool = True,
) -> tuple[dict[int, dict[str, Any]], list[str]]:
    """Apply harmonize_intra_year_pl_scale to each fiscal year."""
    if not yearly:
        return yearly, []
    work = yearly if inplace else {y: dict(row) for y, row in yearly.items()}
    actions: list[str] = []
    for y in sorted(work):
        for msg in harmonize_intra_year_pl_scale(work[y]):
            actions.append(f"FY{y} {msg}")
    return work, actions
