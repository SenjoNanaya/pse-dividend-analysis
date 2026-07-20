"""
Expose local Edge (Django + built SPA) via a Cloudflare Quick Tunnel.

Requires cloudflared on PATH:
  https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/

Usage (repo root):

  python scripts/run_tunnel.py
  python scripts/run_tunnel.py --skip-build
  python scripts/run_tunnel.py --seed-demo

Opens a random https://*.trycloudflare.com URL. PC must stay on; URL changes each run.
Quick tunnels are for personal / demo use (200 in-flight request cap).
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
DIST = FRONTEND / "dist"
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def log(msg: str) -> None:
    print(msg, flush=True)


def wait_http(url: str, timeout: float = 90) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                if resp.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(0.5)
    return False


def find_cloudflared() -> str:
    exe = shutil.which("cloudflared")
    if exe:
        return exe
    raise SystemExit(
        "cloudflared not found on PATH. Install from:\n"
        "  https://developers.cloudflare.com/cloudflare-one/networks/connectors/"
        "cloudflare-tunnel/downloads/"
    )


def npm_build(*, skip: bool) -> None:
    if skip and (DIST / "index.html").is_file():
        log(f"Using existing build: {DIST}")
        return
    if not (FRONTEND / "package.json").is_file():
        raise SystemExit(f"Missing frontend at {FRONTEND}")
    log("Building frontend (npm run build) ...")
    subprocess.check_call(
        ["npm", "run", "build"],
        cwd=FRONTEND,
        shell=os.name == "nt",
    )
    if not (DIST / "index.html").is_file():
        raise SystemExit("frontend/dist/index.html missing after build")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Cloudflare Quick Tunnel for Edge")
    p.add_argument(
        "--skip-build",
        action="store_true",
        help="Reuse frontend/dist if present",
    )
    p.add_argument(
        "--seed-demo",
        action="store_true",
        help="Copy fixtures/demo DB when data/pse_analysis.db is missing",
    )
    p.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Local Django port (default 8000)",
    )
    args = p.parse_args(argv)

    cloudflared = find_cloudflared()
    npm_build(skip=args.skip_build)

    if args.seed_demo:
        subprocess.check_call(
            [sys.executable, str(ROOT / "scripts" / "ensure_sqlite_db.py")],
            cwd=ROOT,
        )

    bind = f"127.0.0.1:{args.port}"
    local_origin = f"http://{bind}"
    child_env = {
        **os.environ,
        "PYTHONUNBUFFERED": "1",
        "DJANGO_DEBUG": os.environ.get("DJANGO_DEBUG", "true"),
        "DJANGO_ALLOWED_HOSTS": os.environ.get(
            "DJANGO_ALLOWED_HOSTS",
            "localhost,127.0.0.1,.trycloudflare.com",
        ),
    }

    procs: list[subprocess.Popen] = []

    def shutdown() -> None:
        for proc in procs:
            if proc.poll() is None:
                proc.terminate()
        time.sleep(0.6)
        for proc in procs:
            if proc.poll() is None:
                proc.kill()

    log(f"Starting Django on {local_origin} (SPA from frontend/dist) ...")
    api = subprocess.Popen(
        [sys.executable, "manage.py", "runserver", bind],
        cwd=ROOT,
        env=child_env,
    )
    procs.append(api)

    try:
        if not wait_http(f"{local_origin}/api/companies/", timeout=90):
            shutdown()
            raise SystemExit("Django did not become ready in time.")
        log("API ready.")

        log("Starting Cloudflare Quick Tunnel ...")
        tunnel = subprocess.Popen(
            [cloudflared, "tunnel", "--url", local_origin],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=child_env,
        )
        procs.append(tunnel)

        public_url = None
        assert tunnel.stdout is not None
        while tunnel.poll() is None:
            line = tunnel.stdout.readline()
            if not line:
                if api.poll() is not None:
                    raise SystemExit(
                        f"Django exited early with code {api.returncode}"
                    )
                time.sleep(0.05)
                continue
            sys.stdout.write(line)
            sys.stdout.flush()
            if public_url is None:
                match = URL_RE.search(line)
                if match:
                    public_url = match.group(0)
                    log("")
                    log(f"Public URL: {public_url}")
                    log("Leave this running. Ctrl+C to stop. URL changes next run.")
                    log("")

        raise SystemExit(
            f"cloudflared exited with code {tunnel.returncode}"
            + ("" if public_url else " (no trycloudflare URL printed)")
        )
    except KeyboardInterrupt:
        log("\nStopping tunnel ...")
    finally:
        shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
