"""
Offline backfill orchestrator (no EDGE network).

Order:
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


def _load_script(stem):
    path = ROOT / "scripts" / f"{stem}.py"
    spec = importlib.util.spec_from_file_location(f"backfill_{stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    p = argparse.ArgumentParser(description="Run offline company-column backfills.")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print steps only (underlying scripts have no dry-run).",
    )
    args = p.parse_args()

    steps = [
        "backfill_stockholders_equity",
        "backfill_div_yield",
        "backfill_roic",
        "backfill_struct_checks",
    ]

    if args.dry_run:
        for name in steps:
            print(f"DRY-RUN would run: {name}")
        return

    for name in steps:
        print(f"=== {name} ===")
        mod = _load_script(name)
        mod.main()
    print("backfill_all done.")


if __name__ == "__main__":
    main()
