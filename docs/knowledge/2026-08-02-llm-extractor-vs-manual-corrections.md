# Can an LLM extractor replace the manual corrections?

**Date:** 2026-08-02 · **Status:** ANSWERED — no, not with the free Nemotron VL.
Best case 53% of rows exact where 100% is required. Hand transcription stays.
**Evidence:** `scripts/scratch_bench_vision_extract.py` via `test-openrouter.yml`
task=`vision`, runs [30718532267](https://github.com/incesalim/Carthago/actions/runs/30718532267),
[30718799791](https://github.com/incesalim/Carthago/actions/runs/30718799791),
[30720123896](https://github.com/incesalim/Carthago/actions/runs/30720123896),
[30720892768](https://github.com/incesalim/Carthago/actions/runs/30720892768).

## Where the manual work actually is

Unit detection is solved by a regex ([2026-08-01](2026-08-01-llm-vs-regex-unit-detection.md)),
so the open question is the rest of the corpus. Two bodies of manual work exist,
and they are different problems:

**457 per-cell overrides** (`data/audit_overrides.json`) — the text is present,
the layout defeats the anchors. **The balance sheet is among the least affected:**

| lane | fixes | lane | fixes |
|---|---:|---|---:|
| `off_balance` | 105 | `fx_position` | 33 |
| `credit_quality` | 100 | `profit_loss` | 30 |
| `capital` | 58 | `npl_movement` | 27 |
| **`assets` + `liabilities`** | **35** | `oci` | 22 |

By bank: ALNTF 91, FIBA 70, ICBCT 31, HAYATK 29, QNBFB 26. So "which table needs
help" is **off-balance and credit quality**, not the balance sheet — which is
consistent with the balance sheet being the lane with the most identity checks
and the longest history of repair.

**59 hand-transcribed whole statements** (`data/manual_statements.json`) — the
page is not text at all, so no anchor work could ever recover it. This is the
only part of the pipeline whose cost is a person's afternoon, and therefore the
only place an LLM could add capability rather than duplicate it.

## ⚠️ An unreadable page has TWO mechanisms, and one of them is invisible

This cost a full bench iteration and is worth stating plainly:

| filing | pages | `get_images()` | `get_drawings()` | text |
|---|---|---:|---:|---:|
| FIBA 2025Q1 uncon | p11 (liabilities) | **368** | — | 267 |
| FIBA 2022Q1 uncon | p10–p16 (whole block) | **0** | **848–1,775** | ~270 |

FIBA 2022Q1 has **zero embedded images**. Its statements are drawn as **vector
paths** — every glyph is a path — so a check like `len(page.get_images()) > 40`
sees nothing wrong and reports the page as fine. The reliable test is
**low text length AND many marks of either kind**:

```python
marks = len(pg.get_drawings()) + len(pg.get_images())
drawn = len(pg.get_text().strip()) < 400 and marks > 200
```

Note `_locate_pages()` returns `{}` for these filings — it anchors on text, and
there is none. The drawn statement pages form one consecutive run in the fixed
BRSA order (assets, liabilities, off-balance, P&L, OCI, equity, cash-flow), which
is how the bench addresses them: verified p10/11/12/13/14/16 for FIBA 2022Q1.

## The result

`nvidia/nemotron-nano-12b-v2-vl:free`, page rendered at 120dpi JPEG, strict
`json_schema`, `reasoning.effort=none`, scored against the human transcript:

| statement | by name | **by position** | TOTAL row |
|---|---|---|---|
| FIBA 2025Q1 uncon liabilities | 5/47 (11%) | **25/47 (53%)** | OK |
| FIBA 2022Q1 uncon liabilities | 5/47 (11%) | 16/47 (34%) | OK |
| FIBA 2022Q1 uncon assets | 9/47 (19%) | 11/47 (23%) | **WRONG** |
| FIBA 2025Q2 uncon liabilities | TRUNCATED | — | — |

**Best case 53% of rows exactly right.** A balance sheet needs 100%: at 53%, ~22
of 47 rows are wrong, every identity check (TL+FC=Total, parent=Σchildren,
Σromans=TOTAL) fails, and the assets case got the **TOTAL row wrong**, which is
fatal however good the rest looks.

Score by position, not by name — the model reads `68.752.573` correctly and then
writes the label as `ALİNAN KREĞLER` or `PARA PIYASAİLARİNA BORŞLAR`. Turkish
diacritics are mangled and a spurious header row shifts everything by one, so
name-matching scored 13.5% when the digits were substantially better than that.
Position is also how the deterministic extractor aligns rows, the chart of
accounts being uniform.

**The failure is not consistent, which is worse than being bad.** FIBA 2022Q1
assets matched 46/47 names but only 9 amounts; FIBA 2025Q1 liabilities matched 5
names and got 25 amounts. Labels right / numbers wrong and numbers right /
labels wrong, from the same model on adjacent pages. There is no error model here
to build a guard against.

## Operational notes on the free VL endpoint

- `max_tokens` 8000 → **"Upstream idle timeout exceeded" (504) on every call**;
  4000 → truncated mid-table. 12000 with 5xx retry still truncated 1 in 4.
  Turkish row names tokenize badly enough that 47 rows exceed a naive estimate.
- A single 47-row page takes **minutes**; a 4-statement sweep cancelled a
  20-minute job. The job timeout is now 45.
- JPEG@120dpi is ~178KB base64 vs ~357KB for PNG@150 — worth halving, though the
  504s were generation speed, not payload.

## What this does and does not settle

**Settled:** the free `nemotron-nano-12b-v2-vl` cannot replace the hand
transcriptions. The 59 statements stay manual.

**Not tested:** a larger or paid vision model. This bench was scoped to Nemotron
by request, and a 12B "nano" is the small end of the range — a stronger VL model
is the obvious next probe, and the harness now takes `--model`.

**Not tested:** the 457 per-cell overrides with a *text* LLM. Those pages DO have
a text layer, so they are a different and much easier problem than this one — the
model would be re-reading text `fitz` already extracted, not doing OCR. That is
the more promising branch and it is untouched.

If any of this is ever promoted: the model returned figures here, which
`AGENTS.md` forbids in production. Nothing from these runs was written to D1, R2
or the snapshot, and a transcription that disagrees with an identity check must
stop for a human rather than be stored.
