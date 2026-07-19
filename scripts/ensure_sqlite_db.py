"""
Ensure the warehouse SQLite file exists before gunicorn starts.

If DB_PATH (or data/pse_analysis.db) is missing, copy fixtures/demo/pse_demo.db.
Does not overwrite an existing database.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO_DB = ROOT / "fixtures" / "demo" / "pse_demo.db"


def resolve_db_path() -> Path:
    raw = os.environ.get("DB_PATH", "").strip()
    if not raw:
        return ROOT / "data" / "pse_analysis.db"
    p = Path(raw)
    if p.is_absolute():
        return p
    return ROOT / p


def main() -> int:
    target = resolve_db_path()
    if target.is_file():
        print(f"SQLite OK: {target}", flush=True)
        return 0
    if not DEMO_DB.is_file():
        print(f"Missing demo DB at {DEMO_DB}", file=sys.stderr)
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DEMO_DB, target)
    print(f"Seeded demo SQLite -> {target}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
