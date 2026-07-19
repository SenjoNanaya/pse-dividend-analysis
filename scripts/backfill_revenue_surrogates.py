"""
Fill null revenue for holdings / miners from gross_revenue, equity in associates,
or interest income (cached AFS + existing HTML seed columns).

Usage:
  python scripts/backfill_revenue_surrogates.py --dry-run
  python scripts/backfill_revenue_surrogates.py --tickers AB,LODE,FPI
  python scripts/backfill_revenue_surrogates.py
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
from src.filing_triage import allows_revenue_surrogate
from src.pdf_roic_extract import (
    extract_roic_metrics_from_pdf_path,
    fill_html_whitelist,
    prefer_scope_metrics,
)
from src.report_metrics import (
    apply_revenue_surrogate,
    compute_screening_summary,
    metric_value,
)
from src.utils import logger, random_delay

from scripts.review_common import iter_cached_pdfs


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
        if not allows_revenue_surrogate(d.get("sector"), d.get("subsector")):
            continue
        fins = cur.execute(
            """
            SELECT fiscal_year, revenue FROM financials
            WHERE company_id=? ORDER BY fiscal_year
            """,
            (d["id"],),
        ).fetchall()
        if any(metric_value(f["revenue"], "revenue") is None for f in fins):
            out.append(d)
    return out


def _seed(cur, company_id: int) -> dict[int, dict]:
    rows = cur.execute(
        "SELECT * FROM financials WHERE company_id=? ORDER BY fiscal_year",
        (company_id,),
    ).fetchall()
    return {int(r["fiscal_year"]): dict(r) for r in rows}


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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--tickers", default="")
    ap.add_argument("--max-pdfs", type=int, default=4)
    args = ap.parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()] or None

    db.init_db()
    conn = db.get_connection()
    cur = conn.cursor()
    targets = _targets(cur, tickers)
    print(f"Revenue-surrogate targets: {len(targets)}{' [dry-run]' if args.dry_run else ''}")

    fills = 0
    for co in targets:
        meta = {
            "sector": co.get("sector"),
            "subsector": co.get("subsector"),
            "ticker": co["ticker"],
            "symbol": co.get("cmpy_id"),
            "outstanding_shares": co.get("outstanding_shares"),
        }
        try:
            seed = _seed(cur, co["id"])
            pdf = _extract({**meta, "id": co["id"]}, args.max_pdfs)
            merged = fill_html_whitelist(seed, pdf, company=meta)
            notes = []
            for y, row in sorted(merged.items()):
                # Also try surrogate on seed-only rows (gross_revenue already in DB)
                apply_revenue_surrogate(row, meta)
                new = metric_value(row.get("revenue"), "revenue")
                if new is None:
                    continue
                old_row = seed.get(y) or {}
                old = metric_value(old_row.get("revenue"), "revenue")
                if old is not None:
                    continue
                notes.append(f"FY{y}→{new:.6g}")
                fills += 1
                if args.dry_run:
                    continue
                src = sources_from_json(old_row.get("field_sources"))
                src = merge_source_tags(src, ["revenue"], "derived")
                cur.execute(
                    """
                    UPDATE financials SET revenue=?, field_sources=?
                    WHERE company_id=? AND fiscal_year=?
                    """,
                    (float(new), sources_to_json(src), co["id"], y),
                )
            if notes:
                print(f"  {co['ticker']}: {', '.join(notes)}")
                if not args.dry_run:
                    conn.commit()
                    fins = [
                        dict(x)
                        for x in cur.execute(
                            "SELECT * FROM financials WHERE company_id=? ORDER BY fiscal_year",
                            (co["id"],),
                        ).fetchall()
                    ]
                    screening = compute_screening_summary(
                        {
                            "name": co["name"],
                            "ticker": co["ticker"],
                            "sector": co.get("sector"),
                            "subsector": co.get("subsector"),
                            "pe_ratio": co["pe_ratio"],
                            "pb_ratio": co["pb_ratio"],
                            "roe": co["roe"],
                            "market_cap": co["market_cap"],
                            "outstanding_shares": co["outstanding_shares"],
                            "last_traded_price": co["last_traded_price"],
                        },
                        fins,
                    )
                    db.update_company_screening(
                        conn,
                        co["id"],
                        screening["check_pass_count"],
                        screening["check_evaluable_total"],
                        screening["info_incomplete"],
                        div_yield=screening.get("div_yield"),
                        roic=screening.get("roic"),
                        debt_to_equity=screening.get("debt_to_equity"),
                        check_struct_pass=screening.get("check_struct_pass"),
                        check_struct_eval=screening.get("check_struct_eval"),
                    )
            else:
                print(f"  {co['ticker']}: no fills")
            random_delay()
        except Exception as exc:
            logger.error("revenue surrogate failed %s: %s", co["ticker"], exc, exc_info=True)
            conn.rollback()

    print(f"{'[dry-run] ' if args.dry_run else ''}Done. revenue fills: {fills}")


if __name__ == "__main__":
    main()
