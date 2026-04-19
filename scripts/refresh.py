"""One-shot data refresh + deploy orchestrator.

Steps:
  1. Incremental monthly update (only new months BDDK has published).
  2. Incremental weekly update (latest 13-week window).
  3. VACUUM the DB.
  4. Gzip to data/bddk_data.db.gz for Render deployment.
  5. Optionally: git add / commit / push so Render auto-redeploys.

Use with `--push` to also publish. Without it, it only refreshes locally.

Example:
    python scripts/refresh.py          # refresh data locally
    python scripts/refresh.py --push   # refresh + push to GitHub (triggers Render)
"""

from __future__ import annotations

import argparse
import gzip
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "bddk_data.db"
DB_GZ = ROOT / "data" / "bddk_data.db.gz"


def _run_step(name: str, cmd: list[str]) -> None:
    print(f"\n{'='*8} {name} {'='*8}", flush=True)
    res = subprocess.run(cmd, cwd=str(ROOT))
    if res.returncode != 0:
        print(f"{name} exited with code {res.returncode}", flush=True)
        sys.exit(res.returncode)


def vacuum() -> None:
    print("\n======== VACUUM DB ========", flush=True)
    before = DB_PATH.stat().st_size
    c = sqlite3.connect(DB_PATH)
    c.execute("VACUUM")
    c.close()
    after = DB_PATH.stat().st_size
    print(f"{before/1e6:.1f} MB → {after/1e6:.1f} MB", flush=True)


def gzip_db() -> None:
    print("\n======== gzip snapshot ========", flush=True)
    with open(DB_PATH, "rb") as src, gzip.open(DB_GZ, "wb", compresslevel=9) as dst:
        shutil.copyfileobj(src, dst)
    print(f"{DB_GZ.name}: {DB_GZ.stat().st_size/1e6:.1f} MB", flush=True)


def git_push(date_label: str) -> None:
    print("\n======== git push ========", flush=True)
    msg = f"Refresh data snapshot ({date_label})"
    subprocess.run(["git", "add", str(DB_GZ)], cwd=str(ROOT), check=True)
    res = subprocess.run(["git", "commit", "-m", msg], cwd=str(ROOT))
    if res.returncode != 0:
        print("Nothing to commit (snapshot unchanged).", flush=True)
        return
    subprocess.run(["git", "push"], cwd=str(ROOT), check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--push", action="store_true",
                        help="git add/commit/push the new snapshot (triggers Render redeploy)")
    parser.add_argument("--skip-monthly", action="store_true")
    parser.add_argument("--skip-weekly", action="store_true")
    args = parser.parse_args()

    start = datetime.now()
    print(f"Refresh starting at {start:%Y-%m-%d %H:%M}", flush=True)

    if not args.skip_monthly:
        _run_step("Monthly update",
                   [sys.executable, "scripts/update_monthly.py"])
    if not args.skip_weekly:
        _run_step("Weekly update",
                   [sys.executable, "scripts/update_weekly.py"])

    vacuum()
    gzip_db()

    if args.push:
        git_push(start.strftime("%Y-%m-%d"))

    elapsed = (datetime.now() - start).total_seconds() / 60
    print(f"\nRefresh complete in {elapsed:.1f}m.", flush=True)


if __name__ == "__main__":
    main()
