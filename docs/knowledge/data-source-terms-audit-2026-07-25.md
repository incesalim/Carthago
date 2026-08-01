# Data source terms-of-use audit — 2026-07-25

**Status:** 🟡 **PARTIAL** — 4 of 8 sources verified against their own published
terms; 4 could not be retrieved and need a human to open the footer link.
**Question asked:** what may we redistribute, and what changes if we charge money?

Prompted by the AGPL licensing pass (2026-07-25), which put a claim in `README.md`
that upstream terms govern redistribution — a claim neither of us had checked.

---

## The headline

Most Turkish public institutions share one boilerplate:

> **Publishable with attribution. Commercial use requires written permission.**

Verified verbatim at TCMB and TBB, and the insurance regulator SEDDK uses the
identical sentence. This is **not** a prohibition — it is a permission you have
not asked for yet. The remedy is a letter, not a rebuild.

> **⚠️ Amended 2026-08-01.** The original version of this document said
> "*Turkish public institutions share one boilerplate*" and predicted BDDK would
> use the same sentence. **It does not.** BDDK permits only *kısmen alıntı* —
> **partial quotation** — where TCMB permits publication outright. Since
> `/api/v1` is BDDK-only, the source we assumed was safest is in fact the
> strictest, and it governs our most aggressive redistribution surface. Detail in
> the BDDK section below. Treat the remaining three unread sources as genuinely
> unknown rather than presumed-standard.

The one genuine outright exception is Yahoo, which forbids redistribution.

## Verified

| Source | What it says | Free site | If we charge |
|---|---|---|---|
| **TCMB / EVDS** | "Sitede yer alan bilgiler, kaynak gösterilmek suretiyle yayımlanabilir, ancak bu bilgilerin ticari amaçlarla kullanımı TCMB'nin yazılı iznine tabidir." | ✅ with attribution | ⚠️ **written permission required** |
| **TBB** | "Web sitemizde yayınlanan çalışmalar kaynak gösterilmek suretiyle izinsiz yayımlanabilir, ancak bu bilgilerin ticari amaçlarla kullanımı Türkiye Bankalar Birliği'nin yazılı iznine tabidir." | ✅ with attribution | ⚠️ **written permission required** |
| **TÜİK** | Reuse from the site, publications or databases is permitted **with attribution and without needing permission** — no commercial carve-out. | ✅ | ✅ clean |
| **BDDK** *(read 2026-08-01)* | "Web sitemizde yayınlanan çalışmalardan, kaynak gösterilmek suretiyle **kısmen alıntı** yapılabilir ancak bu bilgilerin ticari amaçlarla kullanımı BDDK'nın yazılı iznine tabidir." | ⚠️ **partial quotation only** — see below | ⚠️ **written permission required** |
| **Yahoo Finance** (BIST prices) | Must **not redistribute** information displayed on or provided by Yahoo Finance; automated access prohibited without written permission. | ❌ **already offside** | ❌ must be replaced |

Sources: [TCMB Kullanım Şartları](https://www.tcmb.gov.tr/wps/wcm/connect/TR/TCMB+TR/Bottom+Menu/Diger/Kullanim+Sartlari) ·
[TBB Kullanım Koşulları](https://www.tbb.org.tr/kullanim-kosullari) ·
[TÜİK Yasal Uyarı](https://www.tuik.gov.tr/Kurumsal/Yasal_Uyari) ·
[Yahoo Finance data providers](https://help.yahoo.com/kb/SLN2310.html) ·
BDDK terms of use, rendered site-wide (read via [Sss/Liste/110](https://www.bddk.org.tr/Sss/Liste/110))

### ⚠️ BDDK is NOT the same boilerplate — read this before assuming it is

The 2026-07-25 expectation was that BDDK would use the identical peer sentence.
**It does not, and the difference is the operative word.** TCMB says information
*"yayımlanabilir"* — may be **published**. BDDK says only that *"kısmen alıntı
yapılabilir"* — **partial quotation** may be made.

That is a materially narrower grant, and it lands squarely on the one surface the
last audit flagged as highest-risk:

- **`/api/v1` is BDDK-only**, serves monthly tables 1–17 plus the weekly datasets,
  with `MAX_LIMIT = 25000` and CORS `*`. Serving a complete series wholesale
  through a machine interface is not naturally read as *partial quotation*. This
  is the clearest exposure in the audit after Yahoo, and unlike Yahoo it was
  believed clean.
- **The dashboard is a much easier case** — pages show derived aggregates,
  charted excerpts and computed ratios with sources labelled, which is closer to
  quotation-with-attribution than bulk redistribution.

Two further points from the same terms, both in our favour to state and neither
requiring action: BDDK disclaims any warranty as to accuracy or completeness
(*"hiçbir taahhüdü bulunmamaktadır"*), and reserves the right to change published
content without notice. Our `<Colophon/>` already attributes; that satisfies the
*kaynak gösterilmek* condition.

**This does not make the API unlawful** — bare factual figures are largely
uncopyrightable under Turkish law and what the terms protect is the compilation
(see the caveat at the foot). But "BDDK almost certainly permits republication"
is no longer a safe assumption to build a paid tier on, and the API is the piece
to raise in a permission letter rather than the piece to assume is covered.

## NOT verified — someone must open these by hand

Their terms pages are JS-rendered with no fetchable URL; search did not surface
the text. **Do not treat the guesses below as findings.** Note that the BDDK
result above is the reason to actually read the remaining three rather than
extrapolate: the "every institution uses the same sentence" prior was wrong once.

| Source | Expectation | Why it matters |
|---|---|---|
| **KAP** | Has a "Telif Hakkı ve Çekince İhbarı" page; content unread | Feeds `/actions`, ownership, subsidiaries |
| **TEFAS** (Takasbank) | Third-party wrappers describe "redistribution prohibited without written consent" — hearsay, not the terms | Feeds `/funds` + 4 aggregate tables |
| **TKBB** | Unknown | Feeds the participation lane |

## What this means concretely

**1. The free site is fine today — except Yahoo.**
Every verified source permits republication with attribution. We already label
sources on every page and carry a `<Colophon/>`. The Yahoo problem is not about
money: fetching `query1.finance.yahoo.com` on a schedule is automated access, and
serving those prices is redistribution. Both are prohibited whether or not we
charge. This is the only item that is a defect **right now**.

**2. `/api/v1` is BDDK-only — and BDDK turned out to be the strictest source, not
the most permissive.** *(Updated 2026-08-01: the terms are now read — see the BDDK
row and the section under it.)* The catalog is
`BDDK.<DATASET>.<ITEM>.<BANKTYPE>.<COL>`, monthly tables 1–17 plus the weekly
datasets. Nothing from TCMB, Yahoo, TEFAS or TBB leaves through the API. The
concentration that looked fortunate now cuts the other way: BDDK permits only
*partial quotation*, and an unauthenticated API serving complete series is the
least defensible reading of that. **This is the item to name in a permission
letter, and the reason not to assume the API is covered.**

**3. Charging money is a paperwork problem, not an engineering one.**
If we ever monetise, we need written permission from TCMB and TBB (and probably
BDDK). These are routine requests that public institutions grant for legitimate
analytical use. Budget weeks for a reply, not a redesign. The one thing that would
have to be **rebuilt** is the BIST price feed.

**4. Replacing Yahoo is an open question.** Candidates: Borsa İstanbul's own data
products (paid), a licensed vendor, or dropping live prices and deriving what we
can from KAP filings. Not yet investigated.

## Next actions

- [x] ~~Open BDDK's "Kullanım Şartları" and record the wording~~ — **done 2026-08-01.
      Result was not the expected boilerplate: partial quotation only. See above.**
- [ ] Same for KAP, TEFAS, TKBB — and do **read** them; the BDDK result shows the
      peer-boilerplate assumption is not reliable
- [ ] Decide on the Yahoo/BIST feed — it is offside today, not merely on monetisation
- [ ] Decide what `/api/v1` should serve given "kısmen alıntı" — the options are
      leave it (accepting the reading risk), bound it so a caller cannot pull a
      complete series, or seek written permission naming the API specifically
- [ ] Before any paid tier: written-permission letters to TCMB, TBB, BDDK

## Caveat

This is a reading of published terms, not legal advice, and four sources are
unread. Turkish law also treats bare factual figures as largely uncopyrightable —
what these terms protect is the *compilation*. A lawyer would refine this
considerably; it is a map of where to look, not a clearance.

Related: [[project_repo_history_rewrite]] (the AGPL pass that prompted it).
