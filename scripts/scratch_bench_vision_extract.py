#!/usr/bin/env python3
"""Scratch bench: can a VISION model extract the statements a human had to
hand-transcribe?

`data/manual_statements.json` holds 59 whole statements typed in by hand because
the statement PAGE is drawn rather than typed — e.g. FIBA 2025Q1 unconsolidated
liabilities is a page carrying 368 embedded images and 267 characters of text,
while the assets page beside it extracts cleanly from 4,226. `fitz` has nothing
to read, so the deterministic extractor cannot help and OCR was ruled out of
scope. Those 59 statements are the only part of this pipeline whose cost is a
person's afternoon.

That makes them the one place an LLM could add capability rather than duplicate
it — and it makes them a *scored* test, because the hand-transcribed rows are
ground truth that already passed every identity check (TL+FC=Total,
parent=Σchildren, Σromans=TOTAL, assets total = liabilities total).

The model is shown a rendered page image and asked for rows. It IS being asked
for numbers here, which the production rule forbids — this is a bench, nothing
it returns is written anywhere, and the comparison against the human transcript
is the entire point. Read `docs/knowledge/` before promoting any of it.

Read-only: pulls PDFs from R2, writes nothing to R2, D1 or the local snapshot.
Scratch by design.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.audit_reports import r2_storage  # noqa: E402

BASE = "https://openrouter.ai/api/v1"
HEADERS_EXTRA = {"HTTP-Referer": "https://carthago.app", "X-Title": "carthago"}
ROOT = Path(__file__).resolve().parents[1]
DELAY = float(os.environ.get("BENCH_DELAY", "2"))
DPI = int(os.environ.get("BENCH_DPI", "120"))

# Statements whose page we can locate deterministically. The point of the bench
# is the transcription, not the page hunt, so anything we cannot address
# reliably is skipped and reported rather than guessed at.
PAGE_FOR = {
    "assets": lambda loc: loc.get("bs_assets"),
    "liabilities": lambda loc: (loc.get("bs_assets") + 1) if loc.get("bs_assets") else None,
    "off_balance": lambda loc: loc.get("off_bs"),
    "profit_loss": lambda loc: loc.get("pl"),
}

SYSTEM = (
    "You transcribe a table from an image of a Turkish bank's BRSA financial "
    "statement. Report ONLY the CURRENT period columns (the left block, headed "
    "'Cari Dönem'), not the prior period.\n"
    "Each row has: a hierarchy marker (Roman numeral like 'I.', 'XIV.', or a "
    "decimal like '4.1'), a name, and three amounts: TP (Turkish lira), YP "
    "(foreign currency), Toplam (total).\n"
    "A dash '-' means ZERO, not missing. Amounts use '.' as the thousands "
    "separator: transcribe 68.752.573 as the integer 68752573. Parentheses mean "
    "negative: (59.278) is -59278.\n"
    'Reply with STRICT JSON only: {"rows": [{"h": "I.", "name": "MEVDUAT", '
    '"tl": 68752573, "fc": 28082140, "total": 96834713}, ...]}\n'
    "Transcribe EVERY row in order, including the final TOTAL row. Do not "
    "compute, infer or correct any figure — copy exactly what is printed."
)

ROWS_SCHEMA = {
    "name": "statement_rows",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "h": {"type": "string"},
                        "name": {"type": "string"},
                        "tl": {"type": "number"},
                        "fc": {"type": "number"},
                        "total": {"type": "number"},
                    },
                    "required": ["h", "name", "tl", "fc", "total"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["rows"],
        "additionalProperties": False,
    },
}


def _auth(key: str) -> dict:
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
            **HEADERS_EXTRA}


def render_page(pdf: Path, page_1: int) -> tuple[bytes, dict]:
    import fitz

    doc = fitz.open(pdf)
    try:
        pg = doc[page_1 - 1]
        meta = {"images": len(pg.get_images()), "textlen": len(pg.get_text().strip()),
                "rotation": pg.rotation, "pages": doc.page_count}
        # JPEG, not PNG: at 120dpi this is ~178KB base64 against ~357KB for PNG
        # at 150. The free VL endpoint is slow enough that payload size is worth
        # halving even though the 504s below are an idle timeout, not a size cap.
        return pg.get_pixmap(dpi=DPI).tobytes("jpg", jpg_quality=82), meta
    finally:
        doc.close()


def fallback_page(pdf: Path, statement: str) -> int | None:
    """Locate a drawn balance sheet when _locate_pages finds nothing.

    When BOTH halves of the balance sheet are images (FIBA 2022Q1), there is no
    text for the normal locator to anchor on and it returns {}. The drawn
    statement pages are still identifiable: they are the image-dense pages near
    the front. Assets is the first, liabilities the next.
    """
    import fitz

    doc = fitz.open(pdf)
    try:
        dense = [i + 1 for i in range(min(30, doc.page_count))
                 if len(doc[i].get_images()) > 40]
        if not dense:
            return None
        if statement == "assets":
            return dense[0]
        if statement == "liabilities":
            return dense[1] if len(dense) > 1 else None
        return None
    finally:
        doc.close()


def transcribe(key: str, model: str, png: bytes) -> tuple[list[dict], str, dict]:
    url = "data:image/jpeg;base64," + base64.b64encode(png).decode()
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": [
                {"type": "text", "text": "Transcribe the current-period columns of this statement."},
                {"type": "image_url", "image_url": {"url": url}},
            ]},
        ],
        "temperature": 0,
        "seed": 7,
        # A 47-row table is ~1.5k tokens of JSON. 8000 let the free endpoint run
        # long enough to hit "Upstream idle timeout exceeded" (504) on every
        # call, which is a generation-speed failure, not a size one.
        "max_tokens": 4000,
        # effort=none was the round-2 finding: reasoning tokens otherwise eat the
        # budget and the JSON comes back truncated, scoring as a model failure.
        "reasoning": {"effort": "none"},
        "response_format": {"type": "json_schema", "json_schema": ROWS_SCHEMA},
    }
    for attempt in range(4):
        r = requests.post(f"{BASE}/chat/completions", headers=_auth(key),
                          json=body, timeout=300)
        # Free vision endpoints 429 under load and 5xx on slow generation; both
        # are worth retrying, and neither should be scored as a wrong answer.
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(5 * (attempt + 1))
            continue
        # A 200 can still carry an upstream error object rather than choices.
        if "Upstream idle timeout" in r.text or '"code": 504' in r.text:
            time.sleep(5 * (attempt + 1))
            continue
        break
    if r.status_code != 200:
        return [], f"HTTP {r.status_code}: {r.text[:200]}", {}
    d = r.json()
    if not d.get("choices"):
        return [], f"NO_CHOICES: {json.dumps(d)[:200]}", {}
    choice = d["choices"][0]
    content = (choice["message"]["content"] or "").strip()
    usage = dict(d.get("usage") or {})
    usage["finish_reason"] = choice.get("finish_reason")
    try:
        return json.loads(content).get("rows", []), "", usage
    except (json.JSONDecodeError, AttributeError):
        why = "TRUNCATED" if choice.get("finish_reason") == "length" else "UNPARSEABLE"
        return [], f"{why}: {content[:150]}", usage


def _norm(s: str) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def score(truth: list[dict], got: list[dict]) -> dict:
    """Match on name, then compare the three amounts exactly.

    Matching on NAME rather than position is deliberate: a model that drops or
    inserts one row would otherwise misalign everything after it and score ~0,
    which would tell us the alignment broke, not how well it read.
    """
    by_name = {}
    for r in got:
        by_name.setdefault(_norm(r.get("name", "")), r)

    matched = exact = 0
    wrong: list[str] = []
    for t in truth:
        g = by_name.get(_norm(t.get("name", "")))
        if not g:
            continue
        matched += 1
        ok = all(int(t.get(f) or 0) == int(g.get(f) or 0) for f in ("tl", "fc", "total"))
        if ok:
            exact += 1
        elif len(wrong) < 6:
            wrong.append(
                f"{t.get('name', '')[:28]}: want "
                f"{int(t.get('tl') or 0)}/{int(t.get('fc') or 0)}/{int(t.get('total') or 0)} "
                f"got {int(g.get('tl') or 0)}/{int(g.get('fc') or 0)}/{int(g.get('total') or 0)}")

    # The total row carries the whole statement; getting it wrong is fatal even
    # if every other row is right.
    tt = truth[-1] if truth else {}
    gt = by_name.get(_norm(tt.get("name", "")))
    total_ok = bool(gt) and all(
        int(tt.get(f) or 0) == int(gt.get(f) or 0) for f in ("tl", "fc", "total"))

    return {"truth_rows": len(truth), "got_rows": len(got), "matched": matched,
            "exact": exact, "total_row_ok": total_ok, "wrong": wrong}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="nvidia/nemotron-nano-12b-v2-vl:free")
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--statements", default="liabilities,assets,off_balance,profit_loss")
    args = ap.parse_args()

    key = os.environ.get("OPEN_ROUTER_API") or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("OPEN_ROUTER_API not set — secrets are CI-only.")
        return 1

    want = {s.strip() for s in args.statements.split(",") if s.strip()}
    manual = json.loads(
        (ROOT / "data/manual_statements.json").read_text(encoding="utf-8"))["statements"]
    todo = [s for s in manual if s["statement"] in want and s["statement"] in PAGE_FOR]
    print(f"model: {args.model}\n{len(manual)} hand-transcribed statements, "
          f"{len(todo)} addressable, running {min(args.limit, len(todo))}\n")

    from src.audit_reports.extractor import _locate_pages

    results = []
    for s in todo[:args.limit]:
        tag = f"{s['bank']} {s['period']} {s['kind'][:5]} {s['statement']}"
        r2key = f"{s['bank'].lower()}/{s['bank']}_{s['period']}_{s['kind']}.pdf"
        dest = Path("data/_bench") / f"{s['bank']}_{s['period']}_{s['kind']}.pdf"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            if not r2_storage.exists(r2key):
                print(f"  {tag}: not in R2"); continue
            r2_storage.download_to(r2key, dest)

        loc = _locate_pages(str(dest))
        page = PAGE_FOR[s["statement"]](loc) or fallback_page(dest, s["statement"])
        if not page:
            print(f"  {tag}: page not locatable ({loc})"); continue

        png, meta = render_page(dest, page)
        time.sleep(DELAY)
        rows, err, usage = transcribe(key, args.model, png)
        if err:
            print(f"  {tag}: p{page} FAILED {err[:110]}")
            results.append({"tag": tag, "error": err[:200]})
            continue

        sc = score(s["rows"], rows)
        pct = 100.0 * sc["exact"] / max(1, sc["truth_rows"])
        print(f"  {tag}: p{page} (imgs={meta['images']} text={meta['textlen']}) "
              f"rows {sc['got_rows']}/{sc['truth_rows']} matched={sc['matched']} "
              f"exact={sc['exact']} ({pct:.0f}%) total_row={'OK' if sc['total_row_ok'] else 'WRONG'}")
        for w in sc["wrong"]:
            print(f"        {w}")
        results.append({"tag": tag, "page": page, **meta, **sc})

    ok = [r for r in results if "exact" in r]
    if ok:
        tr = sum(r["truth_rows"] for r in ok)
        ex = sum(r["exact"] for r in ok)
        print(f"\n== {len(ok)} statement(s): {ex}/{tr} cells exact "
              f"({100.0 * ex / max(1, tr):.1f}%), "
              f"{sum(1 for r in ok if r['total_row_ok'])}/{len(ok)} total rows correct ==")
    Path("bench_vision_extract.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote bench_vision_extract.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
