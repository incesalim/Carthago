"""Cataloger: walk every PDF in R2 and dump the actual row labels each bank
uses around the III/IV/V NPL classification table.

Output structure:
  build/audit_templates_catalog.json
    {
      "AKBNK": {
        "pdfs_scanned": 16,
        "periods": ["2022Q1", ..., "2026Q1"],
        "npl_brsa_contexts": [
          {
            "period": "2025Q3",
            "kind": "unconsolidated",
            "page": 64,
            "header": "III. Grup IV. Grup V. Grup",
            "lines_above_provision": ["Dönem Sonu Bakiyesi 9.994.445 ...", ...],
            "provision_line": "Karşılık (-) 5.460.388 ...",
            "lines_below_provision": ["Bilançodaki Net Bakiyesi ...", ...]
          },
          ...
        ]
      },
      ...
    }

That JSON is the input to the per-bank template registry I'll hand-curate
afterwards. Running this once is a *finite* task: 32 banks × 4 years × 2
report kinds = ~256 cells, each one inspected for exact row labels.

Usage:
  python scripts/catalog_audit_templates.py --workers 8
  python scripts/catalog_audit_templates.py --ticker AKBNK    # one bank
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import r2_storage  # noqa: E402

import pdfplumber  # noqa: E402

OUT_DIR = REPO_ROOT / "build"
OUT_DIR.mkdir(exist_ok=True)
OUT_FILE = OUT_DIR / "audit_templates_catalog.json"

# Pattern to spot the III/IV/V header on a page.
_HEADER_RE = re.compile(
    r"(?:Group\s+III|III\.?\s*(?:Group|Grup):?)"
    r"\s*(?:Group\s+IV|IV\.?\s*(?:Group|Grup):?)"
    r"\s*(?:Group\s+V|V\.?\s*(?:Group|Grup):?)",
    re.IGNORECASE,
)
# Pattern that catches *any* plausible provision-row label so we can dump
# what the bank actually uses.
_PROVISION_RE = re.compile(
    r"^\s*("
    r"Provisions?\s*\(\s*-\s*\)"
    r"|Provisions?\s+\("                              # EXIM: 'Provisions ('
    r"|Specific\s+Provisions?\s*\(\s*-\s*\)"
    r"|Karşılık\s*(?:Tutarı)?\s*\(\s*-\s*\)"
    r"|Özel\s+Karşılık\s*\(\s*-\s*\)"
    r"|Beklenen\s+Zarar\s+Karşılığı.*?\(\s*-\s*\)"
    r")",
    re.IGNORECASE,
)
# Numeric-data filter: rows with at least 3 thousands-separated tokens.
_DATA_RE = re.compile(r"\d{1,3}[.,]\d{3}")


# Loans-by-stage section anchors. Both column-header phrasings AND the
# universal Turkish section title.
_STAGE12_S1_RE = re.compile(
    r"(?:Standart\s+Nitelikli|Standard\s+[Ll]oans?|Performing\s+Loans?"
    r"|Birinci\s+ve\s+İkinci\s+Grup)",
    re.IGNORECASE,
)
_STAGE12_S2_RE = re.compile(
    r"(?:Yakın\s+İzlemedeki|Loans?\s+Under\s+(?:Close\s+Monitor|Follow)|Close\s+Monitor)",
    re.IGNORECASE,
)
_TOPLAM_RE = re.compile(r"^\s*(?:Toplam|Total)\s+\S", re.IGNORECASE)

# ECL row anchors (loans_ecl_brsa).
_ECL_S1_RE = re.compile(
    r"(?:12\s*Aylık\s*Beklenen\s*(?:Zarar|Kredi\s*Zarar(?:ı|ları))"
    r"|12\s*Months?\s*Expected\s*(?:Credit\s*)?Loss)",
    re.IGNORECASE,
)
_ECL_S2_RE = re.compile(
    r"(?:Kredi\s+Riskinde\s+Önemli\s+Artış|Significant\s+Increase\s+in\s+Credit\s+Risk)",
    re.IGNORECASE,
)


def _scan_pdf(args):
    ticker, period, kind, key, tmp_dir = args
    dest = Path(tmp_dir) / f"{ticker}_{period}_{kind}.pdf"
    npl_contexts: list[dict] = []
    stage_contexts: list[dict] = []
    ecl_contexts: list[dict] = []
    try:
        r2_storage.download_to(key, dest)
        with pdfplumber.open(str(dest)) as pdf:
            for page_idx, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                lines = text.split("\n")

                # --- npl_brsa: III/IV/V tables ---
                if _HEADER_RE.search(text):
                    for i, ln in enumerate(lines):
                        if not _PROVISION_RE.match(ln.strip()):
                            continue
                        above = [lines[j] for j in range(max(0, i - 6), i)]
                        below = [lines[j] for j in range(i + 1, min(len(lines), i + 4))]
                        header_line = ""
                        for la in above[::-1]:
                            if _HEADER_RE.search(la):
                                header_line = la.strip()
                                break
                        npl_contexts.append({
                            "period": period, "kind": kind, "page": page_idx,
                            "header": header_line,
                            "lines_above_provision": above,
                            "provision_line": lines[i],
                            "lines_below_provision": below,
                        })

                # --- loans_by_stage: BRSA 7.2 Toplam rows ---
                if _STAGE12_S1_RE.search(text) and _STAGE12_S2_RE.search(text):
                    for i, ln in enumerate(lines):
                        if not _TOPLAM_RE.match(ln):
                            continue
                        above = [lines[j] for j in range(max(0, i - 8), i)]
                        # Skip if no Yakın İzlemedeki / Standart anchor in the
                        # preceding lines — keeps noise (Total Assets etc) out.
                        ctx = "\n".join(above)
                        if not (_STAGE12_S1_RE.search(ctx) or _STAGE12_S2_RE.search(ctx)):
                            continue
                        stage_contexts.append({
                            "period": period, "kind": kind, "page": page_idx,
                            "lines_above_toplam": above,
                            "toplam_line": ln,
                        })

                # --- loans_ecl_brsa: 12 Aylık + Önemli Artış rows ---
                if _ECL_S1_RE.search(text) and _ECL_S2_RE.search(text):
                    for i, ln in enumerate(lines):
                        if _ECL_S1_RE.search(ln):
                            ecl_contexts.append({
                                "period": period, "kind": kind, "page": page_idx,
                                "kind_label": "s1", "line": ln,
                            })
                        elif _ECL_S2_RE.search(ln):
                            ecl_contexts.append({
                                "period": period, "kind": kind, "page": page_idx,
                                "kind_label": "s2", "line": ln,
                            })
    except Exception as e:
        return ticker, period, kind, False, [], [], [], f"{type(e).__name__}:{str(e)[:80]}"
    finally:
        try:
            dest.unlink()
        except OSError:
            pass
    return ticker, period, kind, True, npl_contexts, stage_contexts, ecl_contexts, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--ticker", help="Limit to one bank ticker.")
    ap.add_argument("--period", help="Limit to one period, e.g. 2025Q3.")
    args = ap.parse_args()

    pdfs: list[tuple[str, str, str, str]] = []
    for ticker, period, kind, key in r2_storage.list_audit_pdfs():
        if args.ticker and ticker != args.ticker.upper():
            continue
        if args.period and period != args.period.upper():
            continue
        pdfs.append((ticker, period, kind, key))

    # Resume from existing catalog if present. We track which (ticker, period,
    # kind) tuples are already scanned by inspecting any non-empty context
    # list keyed on that tuple. To make this clean we use a separate
    # "scanned" set per ticker.
    catalog: dict[str, dict] = defaultdict(lambda: {
        "pdfs_scanned": 0, "periods": set(), "scanned_keys": set(),
        "npl_brsa_contexts": [],
        "loans_by_stage_contexts": [],
        "loans_ecl_brsa_contexts": [],
    })
    if OUT_FILE.exists():
        prev = json.loads(OUT_FILE.read_text(encoding="utf-8"))
        for tk, entry in prev.items():
            catalog[tk]["pdfs_scanned"] = entry.get("pdfs_scanned", 0)
            catalog[tk]["periods"] = set(entry.get("periods", []))
            catalog[tk]["scanned_keys"] = set(tuple(k) for k in entry.get("scanned_keys", []))
            catalog[tk]["npl_brsa_contexts"] = entry.get("npl_brsa_contexts", [])
            catalog[tk]["loans_by_stage_contexts"] = entry.get("loans_by_stage_contexts", [])
            catalog[tk]["loans_ecl_brsa_contexts"] = entry.get("loans_ecl_brsa_contexts", [])
        already = sum(len(catalog[tk]["scanned_keys"]) for tk in catalog)
        if already > 0:
            print(f"[catalog] resuming with {already} PDFs already scanned", flush=True)
            pdfs = [
                (t, p, k, key) for (t, p, k, key) in pdfs
                if (p, k) not in catalog.get(t, {}).get("scanned_keys", set())
            ]

    print(f"[catalog] scanning {len(pdfs)} PDFs with {args.workers} workers", flush=True)
    failed = 0

    def _flush() -> None:
        """Write current catalog state to OUT_FILE atomically."""
        serializable: dict[str, dict] = {}
        for tk, entry in catalog.items():
            serializable[tk] = {
                "pdfs_scanned": entry["pdfs_scanned"],
                "periods": sorted(entry["periods"]),
                "scanned_keys": sorted([list(k) for k in entry["scanned_keys"]]),
                "npl_brsa_contexts": entry["npl_brsa_contexts"],
                "loans_by_stage_contexts": entry["loans_by_stage_contexts"],
                "loans_ecl_brsa_contexts": entry["loans_ecl_brsa_contexts"],
            }
        tmp = OUT_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(serializable, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(OUT_FILE)

    with tempfile.TemporaryDirectory(prefix="catalog_") as tmp_dir, \
         ProcessPoolExecutor(max_workers=args.workers) as ex:
        work = [(t, p, k, key, tmp_dir) for (t, p, k, key) in pdfs]
        futures = [ex.submit(_scan_pdf, w) for w in work]
        for i, fut in enumerate(as_completed(futures), 1):
            ticker, period, kind, ok, npl_c, stage_c, ecl_c, err = fut.result()
            if not ok:
                failed += 1
                print(f"  [{i:>4}/{len(pdfs)}] FAIL {ticker} {period} {kind}: {err}", flush=True)
                continue
            entry = catalog[ticker]
            entry["pdfs_scanned"] += 1
            entry["periods"].add(period)
            entry["scanned_keys"].add((period, kind))
            entry["npl_brsa_contexts"].extend(npl_c)
            entry["loans_by_stage_contexts"].extend(stage_c)
            entry["loans_ecl_brsa_contexts"].extend(ecl_c)
            if i % 50 == 0 or i == len(pdfs):
                _flush()
                print(f"  [{i:>4}/{len(pdfs)}] processed (checkpointed)", flush=True)

    _flush()
    print(f"\n[catalog] wrote {OUT_FILE} ({failed} PDFs failed)")
    print(f"[catalog] banks catalogued: {len(catalog)}")


if __name__ == "__main__":
    main()
