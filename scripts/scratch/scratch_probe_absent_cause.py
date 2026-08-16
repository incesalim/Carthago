"""Is the 14% npl_movement ceiling real, or a blind spot in my matcher?

The ceiling probe calls a value ABSENT when none of its formatted variants
appears in the pages after source_page. That is only trustworthy if the variant
list covers how the filing actually prints numbers. Here: take ABSENT cases and
search the WHOLE pdf, digits-only, ignoring every separator — the loosest
possible match. Anything still absent is genuinely not printed.
"""

import json
import pathlib
import re
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import fitz  # noqa: E402

CACHE = ROOT / "data" / "_bench"

ov = json.loads((ROOT / "data/audit_overrides.json").read_text(encoding="utf-8"))["overrides"]
db = sqlite3.connect(f"file:{ROOT / 'data/bank_audit.db'}?mode=ro", uri=True)
db.row_factory = sqlite3.Row

cases = []
for x in ov:
    if x.get("statement") != "npl_movement" or not isinstance(x.get("fields"), dict):
        continue
    for f, v in x["fields"].items():
        if f == "source_page" or not isinstance(v, (int, float)) or v == 0:
            continue
        pg = x.get("source_page") or x["fields"].get("source_page")
        cases.append((x["bank_ticker"], x["period"], x["kind"], f, float(v),
                      " ".join((x.get("note") or "").split())[:110], pg))

print(f"{len(cases)} non-zero npl_movement corrected values\n")

checked = found_loose = 0
offs = []
examples = []
for bank, period, kind, f, v, note, srcpg in cases:
    pdf = CACHE / f"{bank}_{period}_{kind}.pdf"
    if not pdf.exists():
        continue
    checked += 1
    if checked > 40:
        break
    doc = fitz.open(pdf)
    digits = str(abs(int(round(v))))
    hit = None
    for i in range(doc.page_count):
        # strip EVERY separator, then substring-match the raw digits
        flat = re.sub(r"[^\d]", "", doc[i].get_text())
        if digits in flat:
            hit = i + 1
            break
    doc.close()
    if hit:
        found_loose += 1
        if srcpg:
            offs.append(hit - srcpg)
        else:
            offs.append(None)
    elif len(examples) < 6:
        examples.append(f"{bank} {period} {kind[:5]} {f}={int(v):,} | {note}")

print(f"checked {min(checked, 40)} with a cached PDF")
print(f"  digits found ANYWHERE in the pdf: {found_loose}")
print(f"  genuinely not printed:            {min(checked, 40) - found_loose}")
known = [o for o in offs if o is not None]
if known:
    import collections
    print(f"  page offset from source_page: {sorted(collections.Counter(known).items())}")
else:
    print("  (no override recorded a source_page, so offset is unknown)")
if examples:
    print("\nnot printed anywhere — with the human's note:")
    for e in examples:
        print("  -", e)
db.close()
