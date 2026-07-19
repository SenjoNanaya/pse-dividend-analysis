"""
Flag anomalous P/E and ROIC values in the screening DB.

Usage (from repo root):
  python scripts/analyze_pe_roic_anomalies.py
  python scripts/analyze_pe_roic_anomalies.py --ticker ENEX
  python scripts/analyze_pe_roic_anomalies.py --out data/reviews/my_run
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from src import db
from src.report_metrics import (
    compute_roic_series,
    earnings_usable_for_valuation,
    sanitize_pe_display,
)
from src.utils import DB_PATH, safe_float

from review_common import (  # noqa: E402
    ensure_reviews_dir,
    load_companies,
    load_financials_by_company,
    stamp,
    write_csv,
    write_text,
)

CSV_FIELDS = [
    "ticker",
    "name",
    "sector",
    "subsector",
    "rules",
    "pe_ratio",
    "pe_display",
    "pe_recomputed",
    "price",
    "latest_year",
    "eps",
    "net_income",
    "earnings_usable",
    "roic_db",
    "roic_pct",
    "roic_series_pct",
    "roic_mode",
    "operating_income",
    "cash",
    "total_assets",
    "total_current_liabilities",
    "stockholders_equity",
]


def flag_rules(company: dict[str, Any]) -> list[str]:
    pe = safe_float(company.get("pe_ratio"))
    roic = safe_float(company.get("roic"))
    price = safe_float(company.get("last_traded_price"))
    rules: list[str] = []
    if pe is not None:
        if abs(pe) > 1000:
            rules.append("absurd_pe")
        if abs(pe) > 100 or pe > 50:
            rules.append("extreme_pe")
        if pe < -50:
            rules.append("extreme_neg_pe")
        if pe == 0 and price is not None and price > 0:
            rules.append("zero_pe_with_price")
    if roic is not None and abs(roic) > 0.40:
        rules.append("extreme_roic")
    return rules


def _latest_row(financials: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not financials:
        return None
    return max(financials, key=lambda r: str(r.get("fiscal_year") or ""))


def diagnose_anomaly(
    company: dict[str, Any], financials: list[dict[str, Any]]
) -> dict[str, Any] | None:
    rules = flag_rules(company)
    if not rules:
        return None

    pe = safe_float(company.get("pe_ratio"))
    roic = safe_float(company.get("roic"))
    price = safe_float(company.get("last_traded_price"))
    latest = _latest_row(financials)
    eps = safe_float(latest.get("eps")) if latest else None
    ni = safe_float(latest.get("net_income")) if latest else None
    usable = earnings_usable_for_valuation(eps, ni)

    pe_recomputed = None
    if price is not None and eps is not None and eps != 0:
        pe_recomputed = price / eps

    roic_info = compute_roic_series(financials, company)
    series = roic_info.get("series") or []
    series_pct = safe_float(series[-1].get("value")) if series else None
    mode = series[-1].get("mode") if series else (roic_info.get("mode") or "")

    return {
        "ticker": company.get("ticker") or company.get("symbol") or "",
        "name": company.get("name") or "",
        "sector": company.get("sector") or "",
        "subsector": company.get("subsector") or "",
        "rules": ";".join(rules),
        "pe_ratio": pe,
        "pe_display": sanitize_pe_display(pe),
        "pe_recomputed": pe_recomputed,
        "price": price,
        "latest_year": latest.get("fiscal_year") if latest else "",
        "eps": eps,
        "net_income": ni,
        "earnings_usable": usable,
        "roic_db": roic,
        "roic_pct": (roic * 100.0) if roic is not None else None,
        "roic_series_pct": series_pct,
        "roic_mode": mode or "",
        "operating_income": safe_float(latest.get("operating_income")) if latest else None,
        "cash": safe_float(latest.get("cash_and_equivalents")) if latest else None,
        "total_assets": safe_float(latest.get("total_assets")) if latest else None,
        "total_current_liabilities": (
            safe_float(latest.get("total_current_liabilities")) if latest else None
        ),
        "stockholders_equity": (
            safe_float(latest.get("stockholders_equity")) if latest else None
        ),
        "_rules": rules,
    }


def _fmt(v: Any, digits: int = 2) -> str:
    if v is None or v == "":
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(f) >= 1000:
        return f"{f:.1f}"
    return f"{f:.{digits}f}"


def build_markdown(rows: list[dict[str, Any]], db_path: str, out_dir: Path) -> str:
    rule_counts: Counter[str] = Counter()
    for r in rows:
        for rule in r["_rules"]:
            rule_counts[rule] += 1

    lines = [
        "# P/E and ROIC anomaly review",
        "",
        f"- Generated: `{stamp()}`",
        f"- DB: `{db_path}`",
        f"- Flagged companies: **{len(rows)}**",
        "",
        "## Rule histogram",
        "",
    ]
    if rule_counts:
        for token, count in rule_counts.most_common():
            lines.append(f"- `{token}`: {count}")
    else:
        lines.append("- (none)")

    lines.extend(
        [
            "",
            "## Flagged companies (DB)",
            "",
            "| Ticker | PE | ROIC% | Mode | Price | EPS | Rules | Name |",
            "| --- | ---: | ---: | --- | ---: | ---: | --- | --- |",
        ]
    )
    for r in rows:
        lines.append(
            "| {ticker} | {pe} | {roic} | {mode} | {px} | {eps} | `{rules}` | {name} |".format(
                ticker=r["ticker"],
                pe=_fmt(r["pe_ratio"]),
                roic=_fmt(r["roic_pct"], 1),
                mode=r["roic_mode"] or "",
                px=_fmt(r["price"]),
                eps=_fmt(r["eps"], 4),
                rules=r["rules"],
                name=(r["name"] or "").replace("|", "/"),
            )
        )

    lines.extend(
        [
            "",
            "## Web spot-checks",
            "",
            "Fill in after cursory online lookups. Verdicts: `plausible`, `db_wrong`, "
            "`web_also_extreme`, `unverifiable`.",
            "",
            "| Ticker | DB PE | DB ROIC% | Web PE | Web ROIC / notes | Source | Verdict | Likely cause |",
            "| --- | ---: | ---: | ---: | --- | --- | --- | --- |",
        ]
    )
    for r in rows:
        lines.append(
            "| {ticker} | {pe} | {roic} |  |  |  |  |  |".format(
                ticker=r["ticker"],
                pe=_fmt(r["pe_ratio"]),
                roic=_fmt(r["roic_pct"], 1),
            )
        )

    lines.extend(
        [
            "",
            "## Fix candidates",
            "",
            "- Persist / scrape: drop or null `|PE| > 1000` before writing `companies.pe_ratio`.",
            "- Dual-list / FX: guard foreign parents (e.g. MFC, SLF) where PSE PHP price "
            "is mixed with home-market EPS.",
            "- Near-zero EPS: prefer N/M over huge computed PE when `|EPS|` is tiny vs price.",
            "- ROIC: reject or warn when `|ROIC| > 100%` (tiny / negative invested capital).",
            "- Holding shells: ROIC on near-zero equity can explode; prefer incomplete over absurd.",
            "",
            "## Outputs",
            "",
            f"- `{out_dir / 'pe_roic_anomalies.csv'}`",
            f"- `{out_dir / 'pe_roic_anomalies.md'}`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Flag anomalous P/E and ROIC in the DB")
    ap.add_argument("--ticker", default=None, help="Single ticker filter")
    ap.add_argument(
        "--out",
        default=None,
        help="Output directory (default data/reviews/<timestamp>)",
    )
    ap.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Exit 1 when any company is flagged (CI / gate mode)",
    )
    args = ap.parse_args()

    db.init_db()
    conn = db.get_connection()
    cur = conn.cursor()

    companies = load_companies(cur, ticker=args.ticker)
    fins_by_id = load_financials_by_company(cur)

    rows: list[dict[str, Any]] = []
    for co in companies:
        fins = fins_by_id.get(int(co["id"]), [])
        diag = diagnose_anomaly(co, fins)
        if diag:
            rows.append(diag)

    rows.sort(
        key=lambda r: (
            -max(abs(safe_float(r["pe_ratio"]) or 0), abs(safe_float(r["roic_pct"]) or 0)),
            r["ticker"],
        )
    )

    out_dir = Path(args.out) if args.out else ensure_reviews_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    write_csv(out_dir / "pe_roic_anomalies.csv", rows, CSV_FIELDS)
    md = build_markdown(rows, os.path.abspath(DB_PATH), out_dir)
    write_text(out_dir / "pe_roic_anomalies.md", md)

    print(md)
    print(f"\nWrote review to {out_dir}")
    conn.close()
    if args.fail_on_findings and rows:
        print(f"\n--fail-on-findings: {len(rows)} flagged company(ies)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
