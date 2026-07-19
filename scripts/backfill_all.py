"""
Offline backfill orchestrator (no EDGE network).

Order:
  0. prune out-of-range fiscal years (< 1995 or > current year)
  1. stockholders_equity (A − L when missing)
  2. div_yield
  3. roic
  4. structural / screening checks

Usage (from repo root):
  python scripts/backfill_all.py
"""
import argparse
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db  # noqa: E402


def _load_script(stem):
    path = ROOT / "scripts" / f"{stem}.py"
    spec = importlib.util.spec_from_file_location(f"backfill_{stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _prune_out_of_range():
    db.init_db()
    conn = db.get_connection()
    deleted = db.delete_out_of_range_financials(conn)
    conn.close()
    print(f"Deleted {deleted} out-of-range fiscal year row(s).")


def main():
    p = argparse.ArgumentParser(description="Run offline company-column backfills.")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print steps only (underlying scripts have no dry-run).",
    )
    args = p.parse_args()

    steps = [
        ("prune_out_of_range", _prune_out_of_range),
        ("backfill_stockholders_equity", None),
        ("backfill_div_yield", None),
        ("backfill_roic", None),
        ("backfill_struct_checks", None),
    ]

    if args.dry_run:
        for name, _ in steps:
            print(f"DRY-RUN would run: {name}")
        return

    for name, fn in steps:
        print(f"=== {name} ===")
        if fn is not None:
            fn()
        else:
            mod = _load_script(name)
            mod.main()
    print("backfill_all done.")


if __name__ == "__main__":
    main()
