"""
Backfill deposit-bank checklist fields from cached AFS PDFs.

Targets PSE subsector Banks missing loans / deposits / NPL / NII / ACL.
Uses data/filings/<EDGE cmpy_id>/ (companies.symbol). Prefers AFS filenames.

Usage (from repo root):
  python scripts/backfill_bank_fields.py --dry-run --limit 5
  python scripts/backfill_bank_fields.py --tickers PNB,SECB,BDO
  python scripts/backfill_bank_fields.py
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
from src.filing_triage import is_banks_subsector
from src.pdf_roic_extract import (
    extract_roic_metrics_from_pdf_path,
    fill_html_whitelist,
    prefer_scope_metrics,
)
from src.report_metrics import compute_screening_summary
from src.scale_guard import repair_thousand_scale_jumps
from src.utils import logger, random_delay

from scripts.review_common import iter_cached_pdfs

_BANK_COLS = (
    "total_loans",
    "total_deposits",
    "npl",
    "net_interest_income",
    "allowance_for_credit_losses",
)


def _needs_bank(fins: list[dict]) -> bool:
    for f in fins:
        src = sources_from_json(f.get("field_sources"))
        for col in _BANK_COLS:
            if f.get(col) is None:
                return True
            if src.get(col) != "pdf":
                return True
    return False


def _targets(cur, tickers: list[str] | None) -> list[dict]:
    rows = cur.execute(
        """
        SELECT c.id, c.ticker, c.name, c.symbol AS cmpy_id, c.sector, c.subsector,
               c.outstanding_shares, c.pe_ratio, c.pb_ratio, c.roe, c.market_cap,
               c.last_traded_price
        FROM companies c
        ORDER BY c.ticker
        """
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if not is_banks_subsector(d.get("sector"), d.get("subsector")):
            continue
        if tickers and (d.get("ticker") or "").upper() not in tickers:
            continue
        fins = [
            dict(x)
            for x in cur.execute(
                """
                SELECT fiscal_year, total_loans, total_deposits, npl,
                       net_interest_income, allowance_for_credit_losses,
                       field_sources
                FROM financials WHERE company_id=? ORDER BY fiscal_year
                """,
                (d["id"],),
            ).fetchall()
        ]
        if fins and _needs_bank(fins):
            out.append(d)
    return out


def _load_seed(cur, company_id: int) -> dict[int, dict]:
    rows = cur.execute(
        """
        SELECT fiscal_year, revenue, net_income, operating_income,
               income_before_tax, gross_profit, ga_expense, eps,
               total_assets, total_liabilities, stockholders_equity,
               cash_and_equivalents, total_current_liabilities,
               outstanding_shares, total_loans, total_deposits, npl,
               net_interest_income, allowance_for_credit_losses, field_sources
        FROM financials WHERE company_id=? ORDER BY fiscal_year
        """,
        (company_id,),
    ).fetchall()
    seed = {}
    for r in rows:
        row = dict(r)
        y = int(row.pop("fiscal_year"))
        seed[y] = row
    return seed


def _extract_ranked_pdfs(company: dict, *, max_pdfs: int) -> dict[int, dict]:
    paths = iter_cached_pdfs(company, max_files=max_pdfs, prefer_afs=True)
    candidates = []
    for path in paths:
        yearly = extract_roic_metrics_from_pdf_path(
            str(path), filename_hint=path.name
        )
        if not yearly:
            continue
        sample = next(iter(yearly.values()))
        scope = sample.get("statement_scope") or "unknown"
        candidates.append((scope, yearly))
    if not candidates:
        return {}
    return prefer_scope_metrics(candidates)


def _rescreen(conn, company: dict) -> None:
    cur = conn.cursor()
    fins = cur.execute(
        """
        SELECT fiscal_year, revenue, net_income, eps, book_value,
               total_assets, total_liabilities, stockholders_equity,
               outstanding_shares, current_ratio, quick_ratio,
               cash_and_equivalents, total_current_liabilities,
               operating_income, income_before_tax, income_tax_expense,
               gross_profit, ga_expense, statement_scope,
               total_loans, total_deposits, npl, net_interest_income,
               allowance_for_credit_losses
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
    ap.add_argument("--max-pdfs", type=int, default=6)
    args = ap.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()] or None

    db.init_db()
    conn = db.get_connection()
    cur = conn.cursor()
    targets = _targets(cur, tickers)
    if args.limit and args.limit > 0:
        targets = targets[: args.limit]

    print(
        f"Bank targets: {len(targets)}"
        f"{' [dry-run]' if args.dry_run else ''}"
    )

    filled_companies = 0
    field_updates = 0

    for co in targets:
        ticker = co["ticker"]
        company_meta = {
            "sector": co.get("sector"),
            "subsector": co.get("subsector"),
            "ticker": ticker,
            "symbol": co.get("cmpy_id"),
            "cmpy_id": co.get("cmpy_id"),
            "id": co["id"],
            "outstanding_shares": co.get("outstanding_shares"),
        }
        try:
            html_seed = _load_seed(cur, co["id"])
            pdf_yearly = _extract_ranked_pdfs(company_meta, max_pdfs=args.max_pdfs)
            yearly = fill_html_whitelist(html_seed, pdf_yearly, company=company_meta)
            yearly, _notes = repair_thousand_scale_jumps(yearly, inplace=False)

            company_hits = 0
            notes = []
            for year, metrics in sorted(yearly.items()):
                existing = cur.execute(
                    """
                    SELECT total_loans, total_deposits, npl, net_interest_income,
                           allowance_for_credit_losses, field_sources
                    FROM financials WHERE company_id=? AND fiscal_year=?
                    """,
                    (co["id"], year),
                ).fetchone()
                if not existing:
                    continue
                updates = {}
                for col in _BANK_COLS:
                    new = metrics.get(col)
                    if new is None:
                        continue
                    old = existing[col]
                    if old is not None:
                        try:
                            if abs(float(old) - float(new)) < 1e-6:
                                continue
                        except (TypeError, ValueError):
                            pass
                    # Always allow overwrite for bank cols (correct FPs / scale)
                    updates[col] = float(new)

                existing_sources = sources_from_json(existing["field_sources"])
                src_updates = list(updates.keys())
                for col in _BANK_COLS:
                    if col in src_updates:
                        continue
                    new = metrics.get(col)
                    old = existing[col]
                    if new is None or old is None:
                        continue
                    try:
                        if abs(float(old) - float(new)) >= 1e-3:
                            continue
                    except (TypeError, ValueError):
                        continue
                    if existing_sources.get(col) != "pdf":
                        src_updates.append(col)

                if not updates and not src_updates:
                    continue

                company_hits += 1
                field_updates += len(updates)
                bits = ", ".join(
                    f"{k}={updates[k]:.6g}" for k in updates
                ) or ("sources " + ",".join(src_updates))
                notes.append(f"FY{year}:{bits}")

                if args.dry_run:
                    continue

                metric_sources = metrics.get("_field_sources") or {}
                sources = merge_source_tags(existing_sources, src_updates, "pdf")
                for col in src_updates:
                    tag = metric_sources.get(col)
                    if tag:
                        sources[col] = tag
                payload = dict(updates)
                payload["field_sources"] = sources_to_json(sources)
                sets = ", ".join(f"{c}=?" for c in payload)
                cur.execute(
                    f"UPDATE financials SET {sets} WHERE company_id=? AND fiscal_year=?",
                    (*payload.values(), co["id"], year),
                )

            # Prior-FY NPL carry: latest years missing NPL inherit prior pdf/derived stock
            years_sorted = sorted(html_seed.keys())
            for i, year in enumerate(years_sorted):
                if i == 0:
                    continue
                cur_row = cur.execute(
                    """
                    SELECT npl, field_sources FROM financials
                    WHERE company_id=? AND fiscal_year=?
                    """,
                    (co["id"], year),
                ).fetchone()
                if not cur_row or cur_row["npl"] is not None:
                    continue
                prev = cur.execute(
                    """
                    SELECT npl, field_sources FROM financials
                    WHERE company_id=? AND fiscal_year=?
                    """,
                    (co["id"], years_sorted[i - 1]),
                ).fetchone()
                if not prev or prev["npl"] is None:
                    continue
                prev_src = sources_from_json(prev["field_sources"]).get("npl")
                if prev_src not in ("pdf", "derived", "form17c"):
                    # Allow carry from any non-null prior when extract missed latest
                    if prev_src is None and float(prev["npl"]) <= 0:
                        continue
                npl_v = float(prev["npl"])
                notes.append(f"FY{year}:npl_carry={npl_v:.6g}")
                company_hits += 1
                field_updates += 1
                if args.dry_run:
                    continue
                src = sources_from_json(cur_row["field_sources"])
                src = merge_source_tags(src, ["npl"], "derived")
                cur.execute(
                    """
                    UPDATE financials SET npl=?, field_sources=?
                    WHERE company_id=? AND fiscal_year=?
                    """,
                    (npl_v, sources_to_json(src), co["id"], year),
                )

            if company_hits:
                filled_companies += 1
                print(f"  {ticker}: {'; '.join(notes)}")
                if not args.dry_run:
                    conn.commit()
                    _rescreen(conn, co)
            else:
                hist = sorted(pdf_yearly.keys()) if pdf_yearly else []
                print(f"  {ticker}: no fills (pdf_years={hist})")
            random_delay()
        except Exception as exc:
            logger.error("Bank backfill failed %s: %s", ticker, exc, exc_info=True)
            conn.rollback()

    print(
        f"{'[dry-run] ' if args.dry_run else ''}"
        f"Done. Companies filled: {filled_companies}; field updates: {field_updates}"
    )


if __name__ == "__main__":
    main()
