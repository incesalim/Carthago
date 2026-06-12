"""Profile every audit PDF in R2 → data/audit_profiles.json (Phase 0 census).

Read-only over R2; no DB or production writes. Profiles observe formatting
(see src/audit_reports/profiler.py) — they never drive parsing.

  python scripts/profile_audit_corpus.py                # full fleet (~1-2 h)
  python scripts/profile_audit_corpus.py --only ALBRK --periods 2026Q1
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import r2_storage  # noqa: E402

OUT = REPO / "data" / "audit_profiles.json"


def _worker(args):
    """Download one PDF, profile it, clean up. Top-level for pickling."""
    ticker, period, kind, key, tmp_dir = args
    import time as _t

    from src.audit_reports import r2_storage as _r2
    from src.audit_reports.profiler import profile_pdf
    t0 = _t.time()
    dest = Path(tmp_dir) / f"{ticker}_{period}_{kind}.pdf"
    try:
        _r2.download_to(key, dest)
        prof = profile_pdf(str(dest))
        prof.pop("pdf", None)
        return (ticker, period, kind, True, prof, "", _t.time() - t0)
    except Exception as e:  # noqa: BLE001
        return (ticker, period, kind, False, None,
                f"{type(e).__name__}:{str(e)[:120]}", _t.time() - t0)
    finally:
        try:
            dest.unlink()
        except OSError:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--only", type=str, default="", help="comma-separated tickers")
    ap.add_argument("--periods", type=str, default="", help="comma-separated periods")
    ap.add_argument("--out", type=str, default=str(OUT))
    args = ap.parse_args()

    pdfs = r2_storage.list_audit_pdfs()
    if args.only:
        want = {t.strip().upper() for t in args.only.split(",") if t.strip()}
        pdfs = [p for p in pdfs if p[0].upper() in want]
    if args.periods:
        want_p = {p.strip().upper() for p in args.periods.split(",") if p.strip()}
        pdfs = [p for p in pdfs if p[1].upper() in want_p]
    print(f"[profile] {len(pdfs)} PDFs to profile")

    import tempfile
    profiles: dict[str, dict] = {}
    fails: list[str] = []
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="bddk_prof_") as tmp:
        work = [(t, p, k, key, tmp) for (t, p, k, key) in pdfs]
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(_worker, w) for w in work]
            for n, fut in enumerate(as_completed(futs), 1):
                ticker, period, kind, ok, prof, err, secs = fut.result()
                pkey = f"{ticker}|{period}|{kind}"
                if ok:
                    profiles[pkey] = prof
                else:
                    fails.append(f"{pkey}: {err}")
                    print(f"  [FAIL] {pkey} {err}", flush=True)
                if n % 25 == 0:
                    print(f"  [profile] {n}/{len(work)} ({time.time() - t0:.0f}s)", flush=True)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Merge into any existing profiles file so partial runs accumulate.
    existing: dict[str, dict] = {}
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            existing = {}
    existing.update(profiles)
    out_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8")
    print(f"[profile] wrote {len(profiles)} new / {len(existing)} total → {out_path}")
    if fails:
        print(f"[profile] {len(fails)} failure(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
