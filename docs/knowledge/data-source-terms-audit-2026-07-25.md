# Data source terms-of-use audit — 2026-07-25

**Status:** 🟡 **PARTIAL** — 4 of 8 sources verified against their own published
terms; 4 could not be retrieved and need a human to open the footer link.
**Question asked:** what may we redistribute, and what changes if we charge money?

Prompted by the AGPL licensing pass (2026-07-25), which put a claim in `README.md`
that upstream terms govern redistribution — a claim neither of us had checked.

---

## The headline

Turkish public institutions share one boilerplate, and it is the finding that
matters:

> **Publishable with attribution. Commercial use requires written permission.**

Verified verbatim at TCMB and TBB, and the insurance regulator SEDDK uses the
identical sentence. This is **not** a prohibition — it is a permission you have
not asked for yet. The remedy is a letter, not a rebuild.

The one genuine exception is Yahoo, which forbids redistribution outright.

## Verified

| Source | What it says | Free site | If we charge |
|---|---|---|---|
| **TCMB / EVDS** | "Sitede yer alan bilgiler, kaynak gösterilmek suretiyle yayımlanabilir, ancak bu bilgilerin ticari amaçlarla kullanımı TCMB'nin yazılı iznine tabidir." | ✅ with attribution | ⚠️ **written permission required** |
| **TBB** | "Web sitemizde yayınlanan çalışmalar kaynak gösterilmek suretiyle izinsiz yayımlanabilir, ancak bu bilgilerin ticari amaçlarla kullanımı Türkiye Bankalar Birliği'nin yazılı iznine tabidir." | ✅ with attribution | ⚠️ **written permission required** |
| **TÜİK** | Reuse from the site, publications or databases is permitted **with attribution and without needing permission** — no commercial carve-out. | ✅ | ✅ clean |
| **Yahoo Finance** (BIST prices) | Must **not redistribute** information displayed on or provided by Yahoo Finance; automated access prohibited without written permission. | ❌ **already offside** | ❌ must be replaced |

Sources: [TCMB Kullanım Şartları](https://www.tcmb.gov.tr/wps/wcm/connect/TR/TCMB+TR/Bottom+Menu/Diger/Kullanim+Sartlari) ·
[TBB Kullanım Koşulları](https://www.tbb.org.tr/kullanim-kosullari) ·
[TÜİK Yasal Uyarı](https://www.tuik.gov.tr/Kurumsal/Yasal_Uyari) ·
[Yahoo Finance data providers](https://help.yahoo.com/kb/SLN2310.html)

## NOT verified — someone must open these by hand

Their terms pages are JS-rendered with no fetchable URL; search did not surface
the text. **Do not treat the guesses below as findings.**

| Source | Expectation | Why it matters |
|---|---|---|
| **BDDK** | Almost certainly the same attribution/commercial-permission formula — every peer institution (TCMB, TBB, SEDDK) uses the identical sentence | **The highest stakes of all: `/api/v1` is BDDK-only.** See below |
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

**2. `/api/v1` is BDDK-only — which concentrates the risk in the one source we
could not verify.** The catalog is `BDDK.<DATASET>.<ITEM>.<BANKTYPE>.<COL>`,
monthly tables 1–17 plus the weekly datasets. Nothing from TCMB, Yahoo, TEFAS or
TBB leaves through the API. That is fortunate — an API is the most aggressive form
of redistribution — but it means **reading BDDK's terms is the single highest-value
thing left to do.**

**3. Charging money is a paperwork problem, not an engineering one.**
If we ever monetise, we need written permission from TCMB and TBB (and probably
BDDK). These are routine requests that public institutions grant for legitimate
analytical use. Budget weeks for a reply, not a redesign. The one thing that would
have to be **rebuilt** is the BIST price feed.

**4. Replacing Yahoo is an open question.** Candidates: Borsa İstanbul's own data
products (paid), a licensed vendor, or dropping live prices and deriving what we
can from KAP filings. Not yet investigated.

## Next actions

- [ ] Open BDDK's footer "Kullanım Şartları" by hand and record the wording — highest value, five minutes
- [ ] Same for KAP, TEFAS, TKBB
- [ ] Decide on the Yahoo/BIST feed — it is offside today, not merely on monetisation
- [ ] Before any paid tier: written-permission letters to TCMB, TBB, BDDK

## Caveat

This is a reading of published terms, not legal advice, and four sources are
unread. Turkish law also treats bare factual figures as largely uncopyrightable —
what these terms protect is the *compilation*. A lawyer would refine this
considerably; it is a map of where to look, not a clearance.

Related: [[project_repo_history_rewrite]] (the AGPL pass that prompted it).
