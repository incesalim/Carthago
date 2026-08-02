"""What is the CEILING of the retrieval step? No API calls.

Every accuracy gain in this investigation came from fixing which pages and which
row the model was shown. That part is deterministic, so it can be measured
directly: for each cell the extractor failed on, is the human's value even
PRESENT in the text we hand the model?

If the value is not in the window, no model can answer and the score is measuring
retrieval, not comprehension. This gives the per-lane page offset where the value
actually lives — the right WINDOW_FOR, derived rather than guessed.
"""

import collections
import json
import pathlib
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\Users\Salim\Desktop\code\claude\carthago")
import fitz  # noqa: E402

from src.audit_reports import r2_storage  # noqa: E402

ROOT = pathlib.Path(r"C:\Users\Salim\Desktop\code\claude\carthago")
CACHE = pathlib.Path(
    r"C:\Users\Salim\AppData\Local\Temp\claude"
    r"\C--Users-Salim-Desktop-code-claude-carthago"
    r"\23fcd9e3-ffa8-428b-9b3c-2fd2ea91ee0f\scratchpad\pdfs")
CACHE.mkdir(parents=True, exist_ok=True)

FIELD_LANES = {
    "capital": "bank_audit_capital",
    "liquidity": "bank_audit_liquidity",
    "npl_movement": "bank_audit_npl_movement",
    "fx_position": "bank_audit_fx_position",
    "credit_quality": "bank_audit_credit_quality",
    "repricing": "bank_audit_repricing",
}
MAX_PDFS = int(sys.argv[1]) if len(sys.argv) > 1 else 25
SCAN = 8   # pages after source_page to look in


def variants(v: float) -> list[str]:
    """How the figure could be printed: 1.234.567 / 1,234,567 / 1234567, and
    ratios with either decimal mark."""
    out = set()
    if abs(v - round(v)) < 1e-9:
        n = abs(int(round(v)))
        s = f"{n:,}"
        out |= {s, s.replace(",", "."), str(n)}
    else:
        for dp in (1, 2):
            t = f"{abs(v):.{dp}f}"
            out |= {t, t.replace(".", ",")}
    return [x for x in out if len(x) >= 2]


ov = json.loads((ROOT / "data/audit_overrides.json").read_text(encoding="utf-8"))["overrides"]
db = sqlite3.connect(f"file:{ROOT / 'data/bank_audit.db'}?mode=ro", uri=True)
db.row_factory = sqlite3.Row

targets = []
for x in ov:
    st = x.get("statement")
    if st not in FIELD_LANES or not isinstance(x.get("fields"), dict):
        continue
    page = x.get("source_page") or x["fields"].get("source_page")
    if page is None:
        row = db.execute(
            f"SELECT source_page FROM {FIELD_LANES[st]} WHERE bank_ticker=? "
            f"AND period=? AND kind=? LIMIT 1",
            (x["bank_ticker"], x["period"], x["kind"])).fetchone()
        page = row["source_page"] if row else None
    if not page:
        continue
    for f, v in x["fields"].items():
        if f == "source_page" or not isinstance(v, (int, float)) or v == 0:
            continue
        targets.append((x["bank_ticker"], x["period"], x["kind"], st, f, float(v), page))

print(f"{len(targets)} non-zero failed cells with a page")

pdfs = collections.OrderedDict()
for t in targets:
    pdfs.setdefault((t[0], t[1], t[2]), None)
use = list(pdfs)[:MAX_PDFS]
print(f"checking {len(use)} PDFs\n")

offsets: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
for bank, period, kind in use:
    dest = CACHE / f"{bank}_{period}_{kind}.pdf"
    key = f"{bank.lower()}/{bank}_{period}_{kind}.pdf"
    if not dest.exists():
        if not r2_storage.exists(key):
            continue
        r2_storage.download_to(key, dest)
    doc = fitz.open(dest)
    text = {}
    for t in targets:
        if (t[0], t[1], t[2]) != (bank, period, kind):
            continue
        _, _, _, st, _f, v, page = t
        vs = variants(v)
        hit = None
        for off in range(0, SCAN):
            p = page + off
            if not (1 <= p <= doc.page_count):
                continue
            if p not in text:
                text[p] = re.sub(r"\s+", " ", doc[p - 1].get_text())
            if any(s in text[p] for s in vs):
                hit = off
                break
        offsets[st][hit if hit is not None else "ABSENT"] += 1
    doc.close()

print(f"{'lane':16s} {'n':>4s}  offset distribution (pages after source_page)")
print("-" * 74)
for lane, c in sorted(offsets.items()):
    n = sum(c.values())
    found = n - c.get("ABSENT", 0)
    dist = " ".join(f"+{k}:{v}" for k, v in sorted(
        (kk, vv) for kk, vv in c.items() if kk != "ABSENT"))
    print(f"{lane:16s} {n:4d}  present {found}/{n} ({100.0 * found / max(1, n):.0f}%)  "
          f"{dist}  ABSENT:{c.get('ABSENT', 0)}")
db.close()
