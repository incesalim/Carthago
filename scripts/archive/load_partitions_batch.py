"""Batch version of load_partition.py: pull the snapshot ONCE, overlay the
hand-transcribed manual statements for several image-only partitions, revalidate
each, then push + sync + upload ONCE. Pass partitions as `BANK:PERIOD:KIND`.

  python scripts/load_partitions_batch.py FIBA:2022Q1:consolidated ISCTR:2025Q1:consolidated ...
  python scripts/load_partitions_batch.py ... --dry-run    # local DB only, print validation
"""
from __future__ import annotations

import gzip
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import r2_storage  # noqa: E402
from src.audit_reports.extractor import extract  # noqa: E402
from src.audit_reports.loader import upsert_report  # noqa: E402
from scripts.load_partition import _FIELD, _rows_to_statementrows, _revalidate  # noqa: E402
from scripts.audit_d1 import (  # noqa: E402
    AUDIT_TABLES, _ensure_d1_schema, _guard_against_ci_writers, _retry_wrangler,
)

DB = REPO / "data" / "bank_audit.db"
GZ = REPO / "data" / "bank_audit.db.gz"
MAN = REPO / "data" / "manual_statements.json"
SNAP = "state/bank_audit.db.gz"


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    parts = [tuple(a.split(":")) for a in args]
    manual_all = json.loads(MAN.read_text(encoding="utf-8"))["statements"]

    if not dry:
        _guard_against_ci_writers()
        r2_storage.download_to(SNAP, str(GZ))
        with gzip.open(GZ, "rb") as s, open(DB, "wb") as d:
            shutil.copyfileobj(s, d)
        print(f"[lpb] pulled snapshot → {DB.stat().st_size / 1e6:.1f} MB")

    fails: dict = {}
    with sqlite3.connect(str(DB)) as conn:
        for b, p, k in parts:
            manual = [m for m in manual_all
                      if m["bank"].upper() == b.upper() and m["period"].upper() == p.upper()
                      and m["kind"] == k]
            if not manual:
                print(f"[lpb] {b} {p} {k}: NO manual statements — skip")
                continue
            key = f"{b.lower()}/{b}_{p}_{k}.pdf"
            with tempfile.TemporaryDirectory(prefix="bddk_lpb_") as td:
                pdf = Path(td) / "r.pdf"
                r2_storage.download_to(key, str(pdf))
                rep = extract(str(pdf))
            for m in manual:
                setattr(rep, _FIELD[m["statement"]], _rows_to_statementrows(m["rows"]))
            upsert_report(conn, b, p, k, rep, key)
            f = _revalidate(conn, b, p, k)
            lanes = "+".join(m["statement"] for m in manual)
            print(f"[lpb] {b} {p} {k}: overlaid [{lanes}] — validation fails={f}")
            if f:
                fails[(b, p, k)] = f
        conn.commit()

    if fails:
        print(f"[lpb] ABORT: {len(fails)} partition(s) fail validation — not pushing: {fails}")
        return 1
    if dry:
        print("[lpb] dry-run — not pushing")
        return 0

    _ensure_d1_schema()
    subprocess.run([sys.executable, str(REPO / "scripts" / "push_to_d1.py"),
                    "--db", str(DB), "--hours", "1", "--only-tables", ",".join(AUDIT_TABLES)],
                   check=True)
    subprocess.run([sys.executable, str(REPO / "scripts" / "sync_audit_expected.py"),
                    "--db", str(DB), "--push"], check=True)
    with sqlite3.connect(str(DB)) as c:
        c.execute("VACUUM")
    with open(DB, "rb") as s, gzip.open(GZ, "wb", compresslevel=6) as d:
        shutil.copyfileobj(s, d)
    print(f"[lpb] uploaded snapshot ({GZ.stat().st_size / 1e6:.1f} MB)")
    r2_storage.upload_file(str(GZ), SNAP, content_type="application/gzip")
    print("[lpb] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
