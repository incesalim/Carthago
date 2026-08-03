# The narrative-prose lane — audit-report prose as section-scoped item rows

**Date:** 2026-08-03
**Status:** BUILT, tested locally on 162 filings. **Not backfilled** — no D1 write,
no workflow run. Migration `0035` is written but unapplied.
**Code:** `src/audit_reports/prose.py`, validator `check_prose`,
table `bank_audit_prose`, registry key `prose`, tests `tests/test_audit_prose.py`

## What it produces

One row per prose block, shaped like a statement's item rows so the control
centre renders it with the same machinery as the tables:

| column | meaning |
|---|---|
| `item_order` | ordinal within the filing — with (bank, period, kind), the row identity |
| `section` | the **printed** Bölüm number (1–8) |
| `section_role` | what that section *is*, read off the filing's own declared title |
| `heading` / `heading_path` | the note heading and its mandated marker (`IV`, `a`, `2.1`) |
| `page_start` / `page_end` | page span |
| `lang` | `tr` / `en` |
| `text` | the reflowed paragraph |

AKBNK 2024Q1 unconsolidated, 315 rows, as `/admin` lists them:

```
  §1 general_info                7 rows    2,168 chars
  §2 financial_statements       22 rows    2,661 chars
  §3 accounting_policies        49 rows   58,962 chars
  §4 risk                      142 rows   57,097 chars
  §5 notes                      79 rows   15,788 chars
  §6 audit_report                7 rows    1,452 chars
  §7 interim_activity_report     9 rows   10,387 chars
```

## `section` is not `section_role`, and the number is not the meaning

The printed number cannot be trusted, in three independent ways measured on the
corpus:

- **§6 and §7 swap.** Annual: §6 other explanations, §7 audit report. Interim:
  §6 review-report pointer, §7 interim activity report.
- **The count varies by bank.** ARAP TÜRK prints **six** sections; most print
  seven; KUVEYT TÜRK and ALTERNATİFBANK print **eight**.
- **The roles are not positional.** They are read from each filing's own
  contents page and classified by keyword.

So every query joins on `section_role`. A check keyed to a section *number*
passes on a mislabelled filing — `test_validator_checks_roles_not_section_numbers`
pins that.

## Tables vs prose is decided geometrically

Numeric density does not work. It files

> …31 Mart 2022 itibarıyla Grup'un kıdem tazminatı yükümlülüğü **29.447 TL**'dir

under "table" — a sentence stating a figure, which is exactly what the lane
exists to capture. The decidable signal is column alignment: a table row's tokens
sit on x-positions shared with the rows above and below; a prose line's do not.

`_fitz_page_text` already read `page.get_text("words")` with full bounding boxes
and then returned a string, throwing the coordinates away. It was split into
`_fitz_page_line_tokens` (the geometry) plus a one-line join — **verified
byte-identical across 951 pages of 8 filings** before anything else was built, so
no extractor sees a different character than it did.

Three rules, in order:

1. a token gap ≥ 35 pt is column whitespace, or ≥ 2 tokens standing on the
   page's column anchors with ≥ 1 figure among them → table;
2. **unless** ≥ 8 words at gaps < 22 pt — a page holding a table gives every line
   on it column anchors, including the narrative wrapped around the table;
3. then a smoothing pass: an isolated "row" among prose is a sentence, and a
   short line inside a run of rows is a cell.

Page furniture (bank name, statement title, period, unit declaration) is dropped
by line frequency — 5.4% of one measured filing.

## Section resolution: four anchors, because banks print four different things

Resolution is the part that fails, and it fails silently. Measured before this
work: taking the first heading match put all seven sections on the contents page;
taking the last put them on cross-references (**1/10 filings monotonic**); a
Turkish-only pattern returned **zero sections and no error** on the 32% of
filings that are English convenience translations.

| anchor | who needs it |
|---|---|
| **divider line** — `BEŞİNCİ BÖLÜM` / `SECTION FIVE` | most filings |
| **roman running header** — `SECTION III:` | HALKBANK prints no in-body divider at all |
| **declared title** from the contents page | FİBABANKA §7, ALTERNATİFBANK §2 |
| **note numbering** — `4.2.7`, `5.6.6` | GARANTİ prints no section marker anywhere |

Starts are then chosen as the **highest-scoring strictly increasing chain in
document line order** — not page order, because in an annual filing §6 and §7
both open on the final page, and a page-based chain can hold only one of them
(that single bug accounted for 31 of 39 failures in the first corpus run).
Contents-page candidates are dropped outright, bounded to the first 15 pages —
KUVEYT's *last* page opens §6, §7 and §8 together, and an unbounded rule reads
that as a contents page and truncates the filing at §5.

## Corpus result

162 local filings, 30 banks, 2022Q1–2026Q1 — **153 fully resolved (94.4%)**,
zero exceptions, **60,288 prose rows**, median 368 rows and 157k prose chars per
filing.

The 6 filings that do not resolve, and why:

| filings | cause |
|---|---|
| GARAN ×4 | §1 has no anchor of any of the four kinds; its contents entry is the column header "Page No" |
| ICBCT 2023Q4 cons (9 pp), TSKB 2026Q1 (14 pp) | **the stored PDF is a fragment**, not a full report — a data defect this lane surfaced, not an extractor failure |

Fixed along the way, each having looked like an extractor failure and turned out
to be an assumption: ATBANK ×3 resolves 1–6, which is **correct** (its contents
page lists six); KUVEYT ×3 needed the contents-page page bound; İŞ BANKASI ×3
resolves a clean 1–8 whose §8 is an addendum with no role rule.

The fragment PDFs are worth acting on separately: two of 162 R2 objects are
partial filings, and no existing lane notices, because the statements they *do*
contain extract fine.

## The validator

`check_prose` checks the sectioning, not the sentences — transcription has no
arithmetic identity, but sectioning does:

- `sections_missing` — fewer than 6 (the observed floor, ARAP TÜRK)
- `sections_not_contiguous` — a gap in 1..N
- `sections_out_of_order` — start pages must not go **backwards**; non-decreasing,
  not strictly increasing, or every annual filing red-flags
- `role_missing` — the four roles every filing carries (general info, accounting
  policies, risk, notes)
- `sections_truncated` — an auditor's/activity section must appear among the last
  three. **This is the check that caught KUVEYT**, which resolved a clean,
  contiguous, in-order 1–5 and simply stopped at the notes; no count or ordering
  test sees that. Among the last *three* rather than strictly the last, because
  İŞ BANKASI ends on an §8 addendum this classifier has no rule for.
- `empty_narrative_role` — a role resolved but carrying no prose

## Cost

330k rows for the fleet at 1,050 filings — **$0.33** at D1's $1/M rows written,
one-off, and re-runs skip unchanged partitions. ~157 MB of text, which roughly
triples `bank_audit.db` (83.5 MB today) but sits far inside D1's limit. No model
tokens: the lane is deterministic end to end.

## Not done

- **No backfill has run.** The standing no-D1-writes rule holds; this is an
  extractor plus a migration, and nothing has been pushed.
- GARAN's §1 (4 filings) and the two fragment PDFs.
- The `/admin` drawer lists sections, row counts and a sample per section. Full
  block-level browsing of the text is not built.

## Related

- [[reference_audit_report_full_structure]] — the 7-Bölüm inventory this corrects
- [[reference_text_layer_is_not_the_filing]] — why an empty page is ambiguous
- `2026-08-03-audit-text-lane-prototype.md` — the tier-1 raw-text lane and the
  measurements that led here
