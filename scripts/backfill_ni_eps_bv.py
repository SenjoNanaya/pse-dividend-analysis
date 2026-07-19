"""
Backfill net_income / eps / book_value gaps from cached PDFs + derives.

Usage:
  python scripts/backfill_ni_eps_bv.py --dry-run
  python scripts/backfill_ni_eps_bv.py --tickers CHP,FGEN,ABSP
  python scripts/backfill_ni_eps_bv.py
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
from src.report_metrics import compute_screening_summary, metric_value
from src.utils import safe_float
from src.scale_guard import repair_thousand_scale_jumps
from src.utils import logger, random_delay

from scripts.review_common import iter_cached_pdfs

_COLS = ("net_income", "eps", "book_value", "revenue", "stockholders_equity")


def _needs(fins: list[dict]) -> bool:
    for f in fins:
        if safe_float(f.get("net_income")) is None:
            return True
        if metric_value(f.get("eps"), "eps") is None:
            return True
        if safe_float(f.get("book_value")) is None:
            return True
    return False


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
    targets = []
    for r in cur.execute(
        """
        SELECT c.id, c.ticker, c.name, c.symbol AS cmpy_id, c.sector, c.subsector,
               c.outstanding_shares, c.pe_ratio, c.pb_ratio, c.roe, c.market_cap,
               c.last_traded_price, c.info_incomplete
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
        if _needs(fins) or d.get("info_incomplete"):
            targets.append(d)

    print(f"NI/EPS/BV targets: {len(targets)}{' [dry-run]' if args.dry_run else ''}")
    field_updates = 0
    for co in targets:
        meta = {
            "sector": co.get("sector"),
            "subsector": co.get("subsector"),
            "ticker": co["ticker"],
            "symbol": co.get("cmpy_id"),
            "outstanding_shares": co.get("outstanding_shares"),
            "id": co["id"],
        }
        try:
            seed = {
                int(r["fiscal_year"]): dict(r)
                for r in cur.execute(
                    "SELECT * FROM financials WHERE company_id=? ORDER BY fiscal_year",
                    (co["id"],),
                ).fetchall()
            }
            paths = iter_cached_pdfs(meta, max_files=args.max_pdfs, prefer_afs=True)
            cands = []
            for p in paths:
                y = extract_roic_metrics_from_pdf_path(str(p), filename_hint=p.name)
                if y:
                    sample = next(iter(y.values()))
                    cands.append((sample.get("statement_scope") or "unknown", y))
            pdf = prefer_scope_metrics(cands) if cands else {}
            yearly = fill_html_whitelist(seed, pdf, company=meta)
            yearly, _ = repair_thousand_scale_jumps(yearly, inplace=False)
            notes = []
            for y, row in sorted(yearly.items()):
                existing = seed.get(y)
                if not existing:
                    continue
                updates = {}
                for col in _COLS:
                    new = row.get(col)
                    if new is None:
                        continue
                    if col == "eps" and metric_value(new, "eps") is None:
                        continue
                    if col == "revenue" and metric_value(new, "revenue") is None:
                        continue
                    old = existing.get(col)
                    if col == "eps":
                        if metric_value(old, "eps") is not None:
                            try:
                                if abs(float(old) - float(new)) < 1e-9:
                                    continue
                            except (TypeError, ValueError):
                                pass
                            if float(old) != 0.0:
                                continue
                        updates[col] = float(new)
                        continue
                    if old is not None:
                        continue
                    updates[col] = float(new)
                if not updates:
                    continue
                notes.append(
                    "FY{}:{}".format(
                        y, ",".join(f"{k}={updates[k]:.6g}" for k in updates)
                    )
                )
                field_updates += len(updates)
                if args.dry_run:
                    continue
                src = sources_from_json(existing.get("field_sources"))
                tags = row.get("_field_sources") or {}
                for col in updates:
                    src = merge_source_tags(src, [col], tags.get(col) or "pdf")
                payload = dict(updates)
                payload["field_sources"] = sources_to_json(src)
                sets = ", ".join(f"{c}=?" for c in payload)
                cur.execute(
                    f"UPDATE financials SET {sets} WHERE company_id=? AND fiscal_year=?",
                    (*payload.values(), co["id"], y),
                )
            if notes:
                print(f"  {co['ticker']}: {'; '.join(notes)}")
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
            logger.error("NI/EPS/BV backfill failed %s: %s", co["ticker"], exc, exc_info=True)
            conn.rollback()

    print(f"{'[dry-run] ' if args.dry_run else ''}Done. field updates: {field_updates}")


if __name__ == "__main__":
    main()
