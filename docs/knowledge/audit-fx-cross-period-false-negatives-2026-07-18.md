# FX net-open-position: the false-NEGATIVE sweep (cross-period anchor)

**Status: COMPLETE / SHIPPED 2026-07-18.** Lane coverage `1022 ok / 28 manual / 0 err
/ 0 miss`. Follow-on to the same-day first pass (21 err + 66 miss → 0/0, which cleared
every RED cell). This pass attacked the GREENS and found **79 cells** that read a flawless
green while storing an incomplete or wrong net FX position. Two cross-lane WRONG-PDF
findings surfaced as a by-product.

## Why the greens were wrong (and invisible)

`check_fx_position` verified only INTERNAL identities — Σccy=TOTAL, assets−liab=net_on,
net_on+net_off=net_position — and **every one skips an absent field** (the house rule that
avoids false-fails). So a partition that dropped the Net Off-Balance row still footed on
the surviving columns and read green, while `net_position` (the lane headline, shown on
`/market-risk`) silently collapsed to `net_on` only. The net_on+net_off=net_position check
is worse than useless there: it "verifies" a number the extractor itself computed —
circular. No internal identity can see a dropped row; only an EXTERNAL anchor can.

The diagnostic that exposed it: the prior column of any quarterly filing re-prints the
**prior YEAR-END** (31 Dec), unchanged across all four quarters of the next year (verified:
each bank's four prior columns are byte-identical). So `prior(2024Qx).net_position` must
equal `2023Q4.current.net_position`, independently extracted. Comparing them across the
corpus: **88 mismatched pairs.**

## The checks added (all in `check_fx_position`, calibrated 0-FP)

1. **`fx_net_position_missing`** — TOTAL has gross assets/liab but no net_on (only the
   gross rows captured). GARAN pattern.
2. **`fx_current_incomplete` / `fx_prior_incomplete`** — SYMMETRIC: neither column may
   drop a field (assets/liab/net_on/net_off, non-zero) the OTHER carries. They are the
   same rows one year apart, so an asymmetry is a drop. Guard: the reference field must be
   non-zero (a genuine no-off-balance bank prints net_off = 0 in BOTH columns → never
   flagged; ATBANK/DUNYAK/ENPARA verified clean).
3. **`fx_cross_period`** — prior TOTAL net_position vs the prior year-end's current TOTAL
   net_position (`_fx_prior_ye_totals` in `revalidate_audit_db.py` binds it, house pattern
   `check_stages(bs_loans=...)`). Runs UNLESS completeness (1/2) already owns the
   partition — so it is **NOT gated on prior net_off being present**: a net-off row dropped
   from BOTH columns is invisible to the symmetric check (no asymmetry) yet collapses
   net_position, and only a cross-period read against the year-end catches it (BURGAN).

## Resolution of the 79 flagged cells

**~53 systematic extractor drops → recovered from source** (fitz-only, gated on the table's
own identities so 0 regression; isolated diff = 18 changed, all prior-column + BURGAN, 21
controls byte-identical):
- **Label miss** — the prior block's net-off row uses a variant label the current block
  doesn't: an en-dash "Net Off –Balance" (TSKB) or a different Turkish phrase "Net Bilanço
  Dışı Pozisyon" (KUVEYT, and BURGAN 2026Q1 which switched EN→TR mid-series). Broadened the
  net-off patterns (any-unicode-dash; added the Turkish phrase). BURGAN dropped it from
  BOTH columns → only the (now un-gated) cross-period anchor caught it.
- **Value-column ROW-SHIFT** — ISCTR-cons / QNBFB print the prior block's figures offset
  from their labels, so ≤3px y-clustering glues each value to the wrong row (Total Assets
  reads blank; everything lands one field high). Fix: collect the prior figures by value,
  re-pair positionally onto the canonical field order, and accept the candidate ONLY when
  the label parse fails the table's own identities and the positional one passes (`_foots`
  — net_on=assets−liab AND Σccy=TOTAL, far too tight to satisfy by accident).
- **Gap-fill** — QNBFB 2025Q2 prints only 2 of 4 net-balance columns; derive a missing
  PRIOR net_on = assets − liab (prior only; a blank CURRENT net-on signals a shifted
  current block and must fail loudly).

**4 value-corrections → overrides** (each grounded in the table's OWN derivative-leg rows
AND confirmed by the adjacent filing, so the cross-period anchor then reconciles genuinely,
not by fiat):
| partition | defect | correction |
|---|---|---|
| KLNMA 2023Q4 unco current | net_off ADDS the USD payable (6,794,888+1,934,433) | subtract → 4,860,455; net FX 3,775,981 → **−92,885** |
| EXIM 2025Q4 unco current | every net_off leg sign-flipped vs its deriv rows | negate → TOTAL −2,210,894; net FX 5,711,622 → **1,289,834** |
| EXIM 2024Q2 unco prior | on_bs_liab dropped (a spurious internal space in the EUR figure) | liab = assets − net_on per ccy (Σ 347,579,772) |
| ALNTF 2026Q1 conso prior | TOTAL net_on lost its sign ("(12,885,781" close-paren dropped) | −12,885,781; net FX 23,057,752 → **−2,713,810** |

**8 curated `_FX_XPERIOD_SKIP`** — the prior column faithfully re-prints a year-end that
LEGITIMATELY differs from our independent copy (footing + completeness stay live; only the
cross-period anchor is withheld): HALKB 2025Q3/Q4 + ALBRK 2023Q1 (genuine restatements —
off-balance byte-identical, only on-balance legs revised); TOMK 2024Q1–Q4 (a new bank
whose filings print blank/malformed prior columns — the value the source doesn't print
can't be an override); ALNTF 2023Q1 (the "31 Aralık 2022" prior column prints 2021 data —
a filer year-swap).

**2 WRONG-PDF partitions the anchor exposed — then FIXED at source (2026-07-18):**
- **GARAN 2023Q4 `unconsolidated`** — the R2 object was the CONSOLIDATED report (all 181
  pages "Consolidated"). GARAN's English IR URL `31_December_2023_Unconsolidated_Financial_Report.pdf`
  is poisoned (real PDF, consolidated content); the correct file is the Turkish-site original
  `…/tr/images/pdf/31_Aralik_2023_Konsolide_Olmayan_Finansal_tablo_ve_aciklamalari.pdf`
  (183pp, "Konsolide Olmayan", §4 net FX 25,130,006).
- **KUVEYT 2026Q1 `consolidated`** — the R2 object was the UNCONSOLIDATED report; the registry
  had listed the unconsolidated `denetim-raporu-…-3926.pdf` under BOTH keys. The real
  consolidated is `konsolide-denetim-raporu-31-mart-2026-3925.pdf` (85pp, consolidated;
  id 3925 = unco 3926 − 1, not the usual +1).

**Fix:** `data/banks/audit_report_urls.json` corrected, PDFs re-fetched to R2 (overwriting
the wrong objects), and BOTH partitions re-extracted across ALL 17 statement lanes (not just
fx) via `reextract_statement.py --force`. Both now reconcile through the cross-period anchor
with NO skip — `_FX_WRONGPDF_SKIP` removed. GARAN 2024Q1–Q4 prior (25,130,005) = the corrected
2023Q4 current; KUVEYT 2026Q1 prior (−1,632,877) = 2025Q4 consolidated current. We did NOT
copy fx from a neighbour (that would have papered over the corrupt BS/PL); the whole partition
is now the right report. (One knock-on: GARAN's Turkish sector table needed a `loans_by_sector`
override — the extractor had parsed the English consolidated one.)

## Lessons

- **An internal identity that skips NULLs verifies nothing about what's missing.** The lane
  read 0 error while 79 greens were incomplete/wrong. Only an external anchor (cross-period,
  cross-statement) finds green-but-wrong.
- **My own guard hid the case the anchor existed for.** Gating cross-period on "prior
  net_off present" (to avoid double-flagging the completeness check) skipped exactly the
  both-columns-dropped case (BURGAN) that completeness structurally cannot see. Fix: run the
  anchor unless completeness already owns the partition — never gate an external check on
  the presence of the field most likely to be the thing that's wrong.
- **Never repair a cell FROM the value the check compares it against** — that makes the
  check pass by construction (tautology). Prior-column drops were recovered from their OWN
  PDF, not copied from the year-end; the wrong-PDF partitions were skipped, not back-filled.
- **The cross-period anchor is a cheap wrong-PDF detector.** A misfiled partition disagrees
  wildly with its own neighbours; two whole-partition provenance bugs fell out for free.

## Related
- [[project_market_risk_lane]] (memory), [[reference_text_layer_is_not_the_filing]]
- `docs/knowledge/validator-robustness-audit-2026-07-17.md` (flagged check_fx_position as
  29.4% tautological — this closes that finding for the lane)
- Follow-ups: `parse_num('-319.110')→-319.11` hyphen-thousands bug is corpus-wide; the two
  wrong-PDF partitions need re-acquisition.
