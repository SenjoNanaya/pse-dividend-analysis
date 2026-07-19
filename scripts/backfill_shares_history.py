"""
Backfill outstanding_shares history from EDGE Shares disclosures (17-C / 17-12-A).

Targets companies with fewer than 2 fiscal years of share counts (thin_shares_series).

Usage (from repo root):
  python scripts/backfill_shares_history.py --dry-run --limit 5
  python scripts/backfill_shares_history.py --tickers AB,BLOOM,SMPH
  python scripts/backfill_shares_history.py --limit 50
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
from src.parser import collect_historical_shares
from src.report_metrics import compute_screening_summary, map_shares_to_fiscal_years
from src.scraper import PSEScraper
from src.utils import logger, random_delay


def _thin_companies(cur, tickers: list[str] | None) -> list[dict]:
    rows = cur.execute(
        """
        SELECT c.id, c.ticker, c.name, c.symbol AS cmpy_id, c.sector, c.subsector,
               c.outstanding_shares, c.pe_ratio, c.pb_ratio, c.roe, c.market_cap,
               c.last_traded_price,
               SUM(CASE WHEN f.outstanding_shares IS NOT NULL
                         AND f.outstanding_shares > 0 THEN 1 ELSE 0 END) AS share_years
        FROM companies c
        JOIN financials f ON f.company_id = c.id
        GROUP BY c.id
        HAVING share_years < 2
        ORDER BY c.ticker
        """
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if tickers and (d.get("ticker") or "").upper() not in tickers:
            continue
        out.append(d)
    return out


def _rescreen(conn, company: dict) -> None:
    cur = conn.cursor()
    fins = cur.execute(
        """
        SELECT fiscal_year, revenue, net_income, eps, book_value,
               total_assets, total_liabilities, current_ratio, quick_ratio,
               outstanding_shares, cash_and_equivalents, total_current_liabilities,
               operating_income, gross_profit, ga_expense
        FROM financials WHERE company_id = ? ORDER BY fiscal_year
        """,
        (company["id"],),
    ).fetchall()
    divs = cur.execute(
        """
        SELECT ex_date, amount AS rate, type, security, is_common
        FROM dividends WHERE company_id = ?
        """,
        (company["id"],),
    ).fetchall()
    screening = compute_screening_summary(
        {
            "name": company["name"],
            "ticker": company["ticker"],
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
    ap.add_argument("--max-pages", type=int, default=20)
    args = ap.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()] or None

    db.init_db()
    conn = db.get_connection()
    cur = conn.cursor()
    targets = _thin_companies(cur, tickers)
    if args.limit and args.limit > 0:
        targets = targets[: args.limit]

    print(
        f"Thin-shares companies: {len(targets)}"
        f"{' [dry-run]' if args.dry_run else ''}"
    )

    scraper = PSEScraper()
    filled_companies = 0
    filled_rows = 0

    for co in targets:
        ticker = co["ticker"]
        cmpy_id = str(co["cmpy_id"])
        try:
            historical = collect_historical_shares(
                scraper, cmpy_id, max_pages=args.max_pages
            )
            fins = cur.execute(
                """
                SELECT fiscal_year, outstanding_shares, field_sources
                FROM financials WHERE company_id=? ORDER BY fiscal_year
                """,
                (co["id"],),
            ).fetchall()
            fiscal_years = [int(r["fiscal_year"]) for r in fins]
            mapped = map_shares_to_fiscal_years(
                historical,
                fiscal_years,
                stock_shares=co.get("outstanding_shares"),
            )
            company_fills = 0
            notes = []
            for row in fins:
                y = int(row["fiscal_year"])
                new = mapped.get(y)
                if new is None:
                    continue
                old = row["outstanding_shares"]
                # Only fill null share years (preserve existing 17-C / stock values)
                if old is not None:
                    continue

                src = "html"
                for hy in (y, y + 1, y - 1):
                    if hy in historical and historical[hy] is not None:
                        try:
                            if abs(float(historical[hy]) - float(new)) < 1.0:
                                src = "form17c"
                                break
                        except (TypeError, ValueError):
                            pass

                if args.dry_run:
                    notes.append(f"FY{y}→{new:.0f}({src})")
                    company_fills += 1
                    filled_rows += 1
                    continue

                sources = merge_source_tags(
                    sources_from_json(row["field_sources"]),
                    ["outstanding_shares"],
                    src,
                )
                cur.execute(
                    """
                    UPDATE financials
                    SET outstanding_shares = ?, field_sources = ?
                    WHERE company_id = ? AND fiscal_year = ?
                    """,
                    (float(new), sources_to_json(sources), co["id"], y),
                )
                notes.append(f"FY{y}→{new:.0f}({src})")
                company_fills += 1
                filled_rows += 1

            if company_fills:
                filled_companies += 1
                print(f"  {ticker}: hist={sorted(historical.items())}; {', '.join(notes)}")
                if not args.dry_run:
                    conn.commit()
                    _rescreen(conn, co)
            else:
                print(
                    f"  {ticker}: no fills (hist_years={sorted(historical.keys())})"
                )
            random_delay()
        except Exception as exc:
            logger.error("Shares backfill failed for %s: %s", ticker, exc, exc_info=True)
            conn.rollback()

    print(
        f"Done. Companies filled: {filled_companies}; share row fills: {filled_rows}"
    )


if __name__ == "__main__":
    main()
