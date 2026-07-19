"""
One-command local demo: sample DB + Django API + Vite frontend.

Usage (from repo root, with Python 3.8+ and Node 18+ on PATH):

  python scripts/run_demo.py

Options:
  python scripts/run_demo.py --skip-install   # reuse existing .venv / node_modules
  python scripts/run_demo.py --api-only
  python scripts/run_demo.py --no-browser
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO_DB = ROOT / "fixtures" / "demo" / "pse_demo.db"
DATA_DIR = ROOT / "data"
TARGET_DB = DATA_DIR / "pse_analysis.db"
VENV_DIR = ROOT / ".venv"
FRONTEND = ROOT / "frontend"
API_URL = "http://127.0.0.1:8000/api/companies/"
UI_URL = "http://127.0.0.1:5173/"


def log(msg: str) -> None:
    print(msg, flush=True)


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def venv_pip() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "pip.exe"
    return VENV_DIR / "bin" / "pip"


def ensure_venv_and_deps(skip_install: bool) -> Path:
    py = venv_python()
    if not py.is_file():
        log("Creating virtualenv at .venv ...")
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV_DIR)], cwd=ROOT)
    if not skip_install:
        log("Installing Python requirements ...")
        subprocess.check_call(
            [str(venv_pip()), "install", "-r", str(ROOT / "requirements.txt")],
            cwd=ROOT,
        )
        if not (FRONTEND / "node_modules").is_dir():
            log("Installing frontend dependencies (npm install) ...")
            subprocess.check_call(["npm", "install"], cwd=FRONTEND, shell=os.name == "nt")
        else:
            log("frontend/node_modules present; skipping npm install.")
    return py


def install_demo_db(*, force: bool) -> None:
    if not DEMO_DB.is_file():
        raise SystemExit(
            f"Missing demo DB at {DEMO_DB}.\n"
            "Build it with: python scripts/export_demo_db.py"
        )
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    backup = DATA_DIR / "pse_analysis.db.bak-before-demo"
    if TARGET_DB.is_file():
        same = (
            TARGET_DB.stat().st_size == DEMO_DB.stat().st_size
            and TARGET_DB.read_bytes() == DEMO_DB.read_bytes()
        )
        if same:
            log("Demo DB already installed; leaving data/pse_analysis.db as-is.")
            return
        if backup.is_file() and not force:
            raise SystemExit(
                f"Refusing to overwrite {TARGET_DB.name}: backup already at {backup.name}.\n"
                "Restore your scrape from the backup, or re-run with --force-db to replace again."
            )
        if not backup.is_file():
            shutil.copy2(TARGET_DB, backup)
            log(f"Backed up existing DB to {backup.name}")
        elif force:
            log(f"Overwriting DB (--force-db); previous backup kept at {backup.name}")
    shutil.copy2(DEMO_DB, TARGET_DB)
    log(f"Installed demo DB -> {TARGET_DB.relative_to(ROOT)}")


def wait_http(url: str, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if 200 <= resp.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.4)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Skip pip/npm install (use existing .venv and node_modules)",
    )
    parser.add_argument(
        "--api-only",
        action="store_true",
        help="Start Django only (no Vite)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open the browser",
    )
    parser.add_argument(
        "--force-db",
        action="store_true",
        help=(
            "Allow replacing data/pse_analysis.db when "
            "pse_analysis.db.bak-before-demo already exists"
        ),
    )
    args = parser.parse_args()

    os.chdir(ROOT)
    py = ensure_venv_and_deps(args.skip_install)
    install_demo_db(force=args.force_db)

    procs: list[subprocess.Popen] = []

    def shutdown() -> None:
        for proc in procs:
            if proc.poll() is None:
                proc.terminate()
        time.sleep(0.6)
        for proc in procs:
            if proc.poll() is None:
                proc.kill()

    log("Starting Django on http://127.0.0.1:8000 ...")
    child_env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    api = subprocess.Popen(
        [str(py), "manage.py", "runserver", "127.0.0.1:8000"],
        cwd=ROOT,
        env=child_env,
    )
    procs.append(api)

    ui = None
    if not args.api_only:
        log("Starting Vite on http://127.0.0.1:5173 ...")
        npm_cmd = ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173"]
        ui = subprocess.Popen(
            npm_cmd,
            cwd=FRONTEND,
            shell=os.name == "nt",
            env=child_env,
        )
        procs.append(ui)

    try:
        if not wait_http(API_URL, timeout=90):
            shutdown()
            raise SystemExit("Django API did not become ready in time.")
        log(f"API ready: {API_URL}")

        if ui is not None:
            if wait_http(UI_URL, timeout=90):
                log(f"UI ready:  {UI_URL}")
            else:
                log("Vite not responding yet; open the URL Vite prints if needed.")

        log("")
        log("Demo running. Try tickers ALI, BDO/AUB (banks), AB (incomplete).")
        log("Ctrl+C to stop.")
        if not args.no_browser and not args.api_only:
            webbrowser.open(UI_URL)

        # Wait until a child exits or user interrupts.
        while True:
            for proc in procs:
                code = proc.poll()
                if code is not None:
                    raise SystemExit(f"Process exited early with code {code}")
            time.sleep(0.5)
    except KeyboardInterrupt:
        log("\nStopping demo ...")
    finally:
        shutdown()


if __name__ == "__main__":
    main()
