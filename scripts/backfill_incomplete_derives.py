"""
Derive incomplete-gate fields from existing anchors + cached AFS.

- net_income ← EPS × shares when NI null
- eps ← NI / shares when EPS null/zero
- book_value ← equity / shares
- clear non-positive derived revenue; re-apply surrogates
- PDF fill for null revenue / NI / EPS / BV (prefer AFS)

Usage:
  python scripts/backfill_incomplete_derives.py --dry-run
  python scripts/backfill_incomplete_derives.py --tickers CHP,DD,FGEN
  python scripts/backfill_incomplete_derives.py
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from src import db
from src.field_sources import merge_source_tags, sources_from_json, sources_to_json
from src.pdf_roic_extract import (
    extract_roic_metrics_from_pdf_path,
    fill_html_whitelist,
    prefer_scope_metrics,
)
from src.report_metrics import (
    clear_invalid_derived_revenue,
    compute_screening_summary,
    incomplete_reasons,
    metric_value,
)
from src.utils import logger, random_delay

from scripts.review_common import iter_cached_pdfs

_WRITE_COLS = (
    "revenue",
    "net_income",
    "eps",
    "book_value",
    "cash_and_equivalents",
    "stockholders_equity",
)


def _is_incomplete(co: dict, fins: list[dict]) -> bool:
    return bool(incomplete_reasons(co, fins))


def _targets(cur, tickers: list[str] | None) -> list[dict]:
    out = []
    for r in cur.execute(
        """
        SELECT c.id, c.ticker, c.name, c.symbol AS cmpy_id, c.sector, c.subsector,
               c.outstanding_shares, c.pe_ratio, c.pb_ratio, c.roe, c.market_cap,
               c.last_traded_price
        FROM companies c ORDER BY c.ticker
        """
    ).fetchall():
        d = dict(r)
        if tickers and d["ticker"].upper() not in tickers:
            continue
        fins = [
            dict(x)
            for x in cur.execute(
                "SELECT * FROM financials WHERE company_id=? ORDER BY fiscal_year",
                (d["id"],),
            ).fetchall()
        ]
        if _is_incomplete(d, fins):
            out.append(d)
    return out


def _seed(cur, company_id: int) -> dict[int, dict]:
    seed = {}
    for r in cur.execute(
        "SELECT * FROM financials WHERE company_id=? ORDER BY fiscal_year",
        (company_id,),
    ).fetchall():
        row = dict(r)
        y = int(row.pop("fiscal_year"))
        src = sources_from_json(row.get("field_sources"))
        if src:
            row["_field_sources"] = src
        # Drop bad derived revenue before merge
        if clear_invalid_derived_revenue(row):
            src = dict(row.get("_field_sources") or {})
            src.pop("revenue", None)
            row["_field_sources"] = src
        seed[y] = row
    return seed


def _extract(company: dict, max_pdfs: int) -> dict[int, dict]:
    paths = iter_cached_pdfs(company, max_files=max_pdfs, prefer_afs=True)
    cands = []
    for p in paths:
        y = extract_roic_metrics_from_pdf_path(str(p), filename_hint=p.name)
        if not y:
            continue
        sample = next(iter(y.values()))
        cands.append((sample.get("statement_scope") or "unknown", y))
    return prefer_scope_metrics(cands) if cands else {}


def _rescreen(conn, company: dict) -> None:
    cur = conn.cursor()
    fins = cur.execute(
        "SELECT * FROM financials WHERE company_id=? ORDER BY fiscal_year",
        (company["id"],),
    ).fetchall()
    divs = cur.execute(
        """
        SELECT ex_date, amount AS rate, type, security, is_common
        FROM dividends WHERE company_id=?
        """,
        (company["id"],),
    ).fetchall()
    screening = compute_screening_summary(
        {
            "name": company["name"],
            "ticker": company["ticker"],
            "sector": company.get("sector"),
            "subsector": company.get("subsector"),
            "pe_ratio": company["pe_ratio"],
            "pb_ratio": company["pb_ratio"],
            "roe": company["roe"],
            "market_cap": company["market_cap"],
            "outstanding_shares": company["outstanding_shares"],
            "last_traded_price": company["last_traded_price"],
        },
        [dict(f) for f in fins],
        dividends=[dict(d) for d in divs],
    )
    db.update_company_screening(
        conn,
        company["id"],
        screening["check_pass_count"],
        screening["check_evaluable_total"],
        screening["info_incomplete"],
        div_yield=screening.get("div_yield"),
        roic=screening.get("roic"),
        debt_to_equity=screening.get("debt_to_equity"),
        check_struct_pass=screening.get("check_struct_pass"),
        check_struct_eval=screening.get("check_struct_eval"),
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--tickers", default="")
    ap.add_argument("--max-pdfs", type=int, default=4)
    args = ap.parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()] or None

    db.init_db()
    conn = db.get_connection()
    cur = conn.cursor()
    targets = _targets(cur, tickers)
    if args.limit > 0:
        targets = targets[: args.limit]
    print(f"Incomplete targets: {len(targets)}{' [dry-run]' if args.dry_run else ''}")

    filled = 0
    field_updates = 0
    for co in targets:
        ticker = co["ticker"]
        meta = {
            "sector": co.get("sector"),
            "subsector": co.get("subsector"),
            "ticker": ticker,
            "symbol": co.get("cmpy_id"),
            "cmpy_id": co.get("cmpy_id"),
            "id": co["id"],
            "outstanding_shares": co.get("outstanding_shares"),
        }
        try:
            seed = _seed(cur, co["id"])
            # Ensure company shares on each year for derives
            for row in seed.values():
                if row.get("outstanding_shares") is None:
                    row["outstanding_shares"] = co.get("outstanding_shares")
            pdf = _extract(meta, args.max_pdfs)
            yearly = fill_html_whitelist(seed, pdf, company=meta)

            notes = []
            company_hits = 0
            for year, metrics in sorted(yearly.items()):
                existing = cur.execute(
                    """
                    SELECT revenue, net_income, eps, book_value,
                           cash_and_equivalents, stockholders_equity, field_sources
                    FROM financials WHERE company_id=? AND fiscal_year=?
                    """,
                    (co["id"], year),
                ).fetchone()
                if not existing:
                    continue
                updates = {}
                for col in _WRITE_COLS:
                    new = metrics.get(col)
                    if new is None:
                        continue
                    # Never persist zero/negative/tiny revenue or zero-EPS placeholders
                    if col in ("revenue", "eps") and metric_value(new, col) is None:
                        continue
                    if col == "revenue" and float(new) < 100_000.0:
                        continue
                    if col == "net_income":
                        try:
                            a = float(metrics.get("total_assets") or 0)
                            if a > 1e6 and abs(float(new)) > 2.0 * a:
                                # Wipeout years: keep when IBT corroborates magnitude
                                ibt = metrics.get("income_before_tax")
                                ibt_f = abs(float(ibt)) if ibt is not None else 0.0
                                if (
                                    ibt_f < 1.0
                                    or abs(abs(float(new)) - ibt_f) / ibt_f > 0.15
                                ):
                                    continue
                        except (TypeError, ValueError):
                            pass
                    old = existing[col]
                    old_missing = old is None or (
                        col in ("revenue", "eps") and metric_value(old, col) is None
                    )
                    if not old_missing:
                        continue
                    updates[col] = float(new)

                # Clear non-positive revenue placeholders (derived or HTML scrap)
                if (
                    "revenue" not in updates
                    and existing["revenue"] is not None
                    and metric_value(existing["revenue"], "revenue") is None
                ):
                    try:
                        if float(existing["revenue"]) <= 0:
                            updates["revenue"] = None
                    except (TypeError, ValueError):
                        pass

                if not updates:
                    continue

                company_hits += 1
                field_updates += len([k for k, v in updates.items() if v is not None])
                bits = ", ".join(
                    f"{k}={'null' if v is None else f'{v:.6g}'}"
                    for k, v in updates.items()
                )
                notes.append(f"FY{year}:{bits}")

                if args.dry_run:
                    continue

                existing_sources = sources_from_json(existing["field_sources"])
                metric_sources = metrics.get("_field_sources") or {}
                src_keys = [k for k in updates if updates[k] is not None]
                sources = merge_source_tags(existing_sources, src_keys, "derived")
                for col in src_keys:
                    tag = metric_sources.get(col)
                    if tag:
                        sources[col] = tag
                if updates.get("revenue") is None:
                    sources.pop("revenue", None)

                payload = {k: v for k, v in updates.items()}
                payload["field_sources"] = sources_to_json(sources)
                sets = ", ".join(f"{c}=?" for c in payload)
                cur.execute(
                    f"UPDATE financials SET {sets} WHERE company_id=? AND fiscal_year=?",
                    (*payload.values(), co["id"], year),
                )

            if company_hits:
                filled += 1
                print(f"  {ticker}: {'; '.join(notes)}")
                if not args.dry_run:
                    conn.commit()
                    _rescreen(conn, co)
            else:
                print(f"  {ticker}: no fills")
            random_delay()
        except Exception as exc:
            logger.error("Incomplete derive failed %s: %s", ticker, exc, exc_info=True)
            conn.rollback()

    print(
        f"{'[dry-run] ' if args.dry_run else ''}"
        f"Done. Companies filled: {filled}; field updates: {field_updates}"
    )


if __name__ == "__main__":
    main()
