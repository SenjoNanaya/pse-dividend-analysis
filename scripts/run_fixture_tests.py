"""
Run committed fixture / guard test modules. Exit 1 on first failure.

Usage:
  python scripts/run_fixture_tests.py
"""
from __future__ import annotations

import importlib
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

MODULES = (
    "test_parser_fixtures",
    "test_screening_guards",
    "test_roic_pipeline",
    "test_demo_bank",
    "test_news_feed",
)


def main() -> int:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(SCRIPTS))

    for name in MODULES:
        print(f"== {name} ==", flush=True)
        try:
            mod = importlib.import_module(name)
            # Prefer explicit main block functions when listed
            if hasattr(mod, "__name__"):
                # Re-run by invoking the module as __main__ would
                run = getattr(mod, "__dict__", {})
                # Call every test_* in definition order
                tests = [
                    (k, v)
                    for k, v in run.items()
                    if k.startswith("test_") and callable(v)
                ]
                if not tests:
                    raise RuntimeError(f"{name}: no test_* functions found")
                for tname, fn in tests:
                    fn()
                    print(f"  ok {tname}", flush=True)
            print(f"ok {name}", flush=True)
        except Exception:
            traceback.print_exc()
            print(f"FAIL {name}", flush=True)
            return 1
    print("all ok", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
