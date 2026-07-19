"""
Carve a small demo SQLite DB from data/pse_analysis.db for the one-command demo.

Usage:
  python scripts/export_demo_db.py
  python scripts/export_demo_db.py --source data/pse_analysis.db --out fixtures/demo/pse_demo.db
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Diverse slice: industrial/property/banks/incomplete for UI smoke paths.
# BPI is the dense bank showcase (multi-year loans/deposits/NII/NPL/ACL).
DEFAULT_TICKERS = (
    "AB",  # incomplete
    "AC",
    "ALI",  # proper ROIC / dense FS
    "AUB",  # bank equity return (thinner FS)
    "BDO",
    "BPI",  # bank checklist + PDF bank fields
    "CNVRG",
    "DMC",
    "GLO",
    "JFC",
    "MBT",
    "MER",
    "PGOLD",
    "SM",
    "SMC",
    "TEL",
)

COMPANY_CHILD_TABLES = (
    "financials",
    "dividends",
    "processing_log",
)


def export_demo(source: Path, out: Path, tickers: tuple[str, ...]) -> None:
    if not source.is_file():
        raise SystemExit(f"Source DB not found: {source}")

    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(out))
    try:
        # Copy full schema (tables + indexes) without row data.
        for row in src.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type IN ('table','index') AND name NOT LIKE 'sqlite_%' "
            "AND sql IS NOT NULL"
        ):
            dst.execute(row[0])
        dst.commit()

        placeholders = ",".join("?" * len(tickers))
        company_ids = [
            r[0]
            for r in src.execute(
                f"SELECT id FROM companies WHERE ticker IN ({placeholders})",
                tickers,
            )
        ]
        if not company_ids:
            raise SystemExit("No matching tickers in source DB.")

        id_ph = ",".join("?" * len(company_ids))
        cols = [d[1] for d in src.execute("PRAGMA table_info(companies)")]
        col_list = ", ".join(cols)
        rows = src.execute(
            f"SELECT {col_list} FROM companies WHERE id IN ({id_ph})",
            company_ids,
        ).fetchall()
        dst.executemany(
            f"INSERT INTO companies ({col_list}) VALUES ({','.join('?' * len(cols))})",
            rows,
        )

        for table in COMPANY_CHILD_TABLES:
            exists = src.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if not exists:
                continue
            tcols = [d[1] for d in src.execute(f"PRAGMA table_info({table})")]
            tcol_list = ", ".join(tcols)
            trows = src.execute(
                f"SELECT {tcol_list} FROM {table} WHERE company_id IN ({id_ph})",
                company_ids,
            ).fetchall()
            if trows:
                dst.executemany(
                    f"INSERT INTO {table} ({tcol_list}) VALUES ({','.join('?' * len(tcols))})",
                    trows,
                )

        dst.commit()

        n_co = dst.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        n_fin = dst.execute("SELECT COUNT(*) FROM financials").fetchone()[0]
        n_div = dst.execute("SELECT COUNT(*) FROM dividends").fetchone()[0]
        print(f"Wrote {out}")
        print(f"  companies={n_co} financials={n_fin} dividends={n_div}")
        print(f"  tickers={', '.join(sorted(tickers))}")
    finally:
        src.close()
        dst.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--source",
        type=Path,
        default=ROOT / "data" / "pse_analysis.db",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "fixtures" / "demo" / "pse_demo.db",
    )
    p.add_argument(
        "--tickers",
        nargs="*",
        default=list(DEFAULT_TICKERS),
        help="Tickers to include (default: curated demo set)",
    )
    args = p.parse_args()
    export_demo(args.source, args.out, tuple(args.tickers))


if __name__ == "__main__":
    main()
