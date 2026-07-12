# Design artefact register

Every mockup, concept and prototype made for Carthago, with what happened to it.
Design work is expensive to redo and cheap to forget — this file exists so a
future session (or a future you) can find the thinking behind a shipped page, or
reuse a concept that was made but never built.

The design system these all serve is `web/DESIGN.md` ("The Desk"). This file is
the *archive*; DESIGN.md is the *law*.

## Where artefacts live

| What | Where | Why |
|---|---|---|
| Mockup source (standalone HTML) | `docs/design/mockups/YYYY-MM-DD-<slug>.html` | Open with `file://` — no server needed |
| Screenshots | `docs/design/mockups/YYYY-MM-DD-<slug>-{desktop,mobile}.png` | So the archive reads without rendering |
| Published copy (shareable link) | claude.ai artifact — URL recorded below | Viewable on a phone, sendable to someone |
| Design critiques / audits | `docs/knowledge/*.md` (dated) | Prose analysis, not artefacts |

**Never put mockups in `web/public/`.** That directory is served by Next.js, so
anything in it ships in every production deploy and is publicly reachable on
carthago.app. Six mockups were live there by accident until 2026-07-12.

Rules for a new artefact: date-prefix the filename, publish it if it needs to be
shared, and **add a row here in the same change** — an unrecorded artefact is a
lost one.

Status vocabulary: **SHIPPED** (built, live) · **PROPOSED** (made, not built) ·
**NOT CHOSEN** (lost a bake-off) · **SUPERSEDED** (overtaken by a later design) ·
**EXPLAINER** (teaching artefact, not a UI proposal).

---

## 2026-07-12 — tab-by-tab redesigns

Each page of the site taken back to a mockup and rebuilt against the Desk brief.

| Artefact | Status | Local | Link |
|---|---|---|---|
| Per-bank page, rethought | **SHIPPED** — `9f918d3` five tabs, no duplication | — | [artifact](https://claude.ai/code/artifact/4b7dd17d-ba99-43c3-b10a-409b840e37d0) |
| Financials tab, rethought | **SHIPPED** — `896d4f5` four lenses + shape layer + flow | — | [artifact](https://claude.ai/code/artifact/be778eab-6c4d-48a4-94aa-a13418e65146) |
| Banks (the register) | **SHIPPED** — `75a28f5`, `a08ef55` | — | [artifact](https://claude.ai/code/artifact/084362b4-20ff-4914-9ff3-1cdd0e8c3905) |
| Overview — the depth layer, realigned | **SHIPPED** — `e081959` evidence layer speaks the brief's language | — | [artifact](https://claude.ai/code/artifact/41bca20a-36e0-46a4-9d0b-bfedb94628e3) |
| Compare — redesign proposal | **PROPOSED** — not built | — | [artifact](https://claude.ai/code/artifact/97ada54b-e315-4a80-80cc-c4d4716726c6) |
| Regulations tab | **PROPOSED** — not built, never published | [html](mockups/2026-07-12-regulations-tab.html) · [desktop](mockups/2026-07-12-regulations-tab-desktop.png) · [mobile](mockups/2026-07-12-regulations-tab-mobile.png) | — |
| Credit tab | **SHIPPED** — `7ffa75a`. Premise held: the headline is mostly *not* credit. Strip lira + CPI and the book **shrank 2.1%**. Built with the bridge, growth attribution (contributions reconcile to the print), SME nested inside commercial, and computed flags | [html](mockups/2026-07-12-credit-tab.html) · [desktop](mockups/2026-07-12-credit-tab-desktop.png) · [mobile](mockups/2026-07-12-credit-tab-mobile.png) | — |
| Deposits tab | **SHIPPED** — `d4de0e6`. Premise held: the page never stated its own finding — **~91% of the book reprices inside three months**. Brief gained Movers/Flags/Standings/Ahead (it had none); evidence layer converted to the Overview contract; `Flags showCleared` added so a rule prints whether or not it fires | [html](mockups/2026-07-12-deposits-tab.html) · [desktop](mockups/2026-07-12-deposits-tab-desktop.png) · [mobile](mockups/2026-07-12-deposits-tab-mobile.png) | [artifact](https://claude.ai/code/artifact/77a1403c-ef5a-4899-8605-e264b5ace793) |
| Asset Quality tab | **PROPOSED** — not built. Premise: the page prints **NPL 2.69%** and looks calm, but the ratio is the *denominator's* story — the bad-loan **stock** grew **+79.8% (+34.9% real)** while the ratio moved +0.70pp. Bad loans alone would put it at **3.97%**; a book growing 36.6% took **−1.06pp** back off. Signature = the printed ratio vs the **constant-book ratio** with the gap shaded. Plus the stress ladder (Stage 2 = 9.2% at **9.8% cover** vs Stage 3 3.1% at 62.3% → problem loans **4.0×** the headline). Kills a false story on the way: the ratio is **not** managed down by disposals — exits are **77% collections** and formation is **2.2×** (₺673bn, net +₺404bn). Rationale + item_id traps: [knowledge](../knowledge/asset-quality-tab-redesign-2026-07-12.md) | [html](mockups/2026-07-12-asset-quality-tab.html) · [desktop](mockups/2026-07-12-asset-quality-tab-desktop.png) · [mobile](mockups/2026-07-12-asset-quality-tab-mobile.png) | [artifact](https://claude.ai/code/artifact/02583087-eae5-4b10-826c-dee7c9a32fd0) |
| Liquidity tab | **PROPOSED** — not built. Premise: the page **derives** net reserves and the swap stock — the most careful arithmetic on the site — then draws them as one line among three and says nothing. Read out: gross **$159.7bn** → net **$52.2bn** → net excl. swaps **$34.5bn** (22% of the headline); **$107.5bn** of "gross" is the *banks'* own FX at the CBRT and **$17.7bn** is swapped in. Second finding, from two series the page never compares: residents hold **$138.3bn** in FX + gold, **3.1×** the CBRT's net reserves (same-date). Note the mark: a stacked decomposition would **lie** — the CBRT's own net FX is negative in 42 of 150 weeks (−$68.6bn at worst), so it is three lines with the gaps shaded | [html](mockups/2026-07-12-liquidity-tab.html) · [desktop](mockups/2026-07-12-liquidity-tab-desktop.png) · [mobile](mockups/2026-07-12-liquidity-tab-mobile.png) | [artifact](https://claude.ai/code/artifact/27299533-1ade-441e-8b18-a9617bf0b4a1) |

## 2026-07-11 — the identity bake-off

Seven whole-site identities, built as rival concepts and judged against each
other. **The Desk won** and became the design system; the other six are kept
because their ideas are still harvestable.

| Concept | Status | Link |
|---|---|---|
| **The Desk** | **SHIPPED** — became `web/DESIGN.md`; white sheet on paper ground, hairlines, mono figures | [artifact](https://claude.ai/code/artifact/5bc55305-0e5e-425c-abaf-e08924c6099b) |
| The Desk — full sector suite | **SHIPPED** — the winner extended across all six sector tabs | [artifact](https://claude.ai/code/artifact/28b72bb4-fade-433b-a2dc-aff39e31860e) |
| The Bulletin | NOT CHOSEN | [artifact](https://claude.ai/code/artifact/c2ae9467-7410-4715-b873-224696548292) |
| The Bulletin v2 | NOT CHOSEN — second pass at the Bulletin | [artifact](https://claude.ai/code/artifact/d738a135-2021-4449-b9d3-a282b34977c6) |
| The Ledger | NOT CHOSEN | [artifact](https://claude.ai/code/artifact/3dab3040-e321-4e30-be9d-27ebe673fb9f) |
| The Terminal | NOT CHOSEN | [artifact](https://claude.ai/code/artifact/eef04b57-2b80-4af8-a576-7a20cc5f27fe) |
| The Folio | NOT CHOSEN | [artifact](https://claude.ai/code/artifact/8647d9fc-72c5-4c6c-97a1-acca96be78a6) |
| The Atlas | NOT CHOSEN | [artifact](https://claude.ai/code/artifact/4fc6c5e9-b207-4f67-b4b3-c0057e881df3) |
| The Observatory | NOT CHOSEN | [artifact](https://claude.ai/code/artifact/49a81608-c246-41a1-a5e1-80a783ac3c60) |

## 2026-07-10 — the pre-Desk round

Came out of the design critique (`docs/knowledge/design-critique-2026-07-10.md`,
`design-system-audit-2026-07-10.md`), which is what triggered the bake-off above.

| Artefact | Status | Link |
|---|---|---|
| Overview redesign prototype | SUPERSEDED — by the Desk identity a day later | [artifact](https://claude.ai/code/artifact/74fc9bd1-cb5e-4c85-a9ec-a942e9052083) |
| By bank — capital adequacy (preview) | SUPERSEDED — preview of the by-bank treatment | [artifact](https://claude.ai/code/artifact/9410c8ae-b4ef-404a-8f2d-35b43541921d) |

## 2026-07-04

| Artefact | Status | Link |
|---|---|---|
| Reading a Turkish Bank Audit Report | **EXPLAINER** — how a BRSA report is structured; not a UI proposal | [artifact](https://claude.ai/code/artifact/f21baa76-ed53-432b-bb2f-6c3832bdc3dd) |

---

## Open design debt

- **Compare, Regulations, Liquidity, Asset Quality** are mocked but unbuilt — four ready
  designs waiting on implementation. (Credit shipped 2026-07-12 `7ffa75a`; Deposits
  `d4de0e6`; Overview `e081959`.)
- **Five sector tabs still run the pre-contract evidence layer** (asset-quality,
  capital, profitability, market-risk, and the economy pages): boxed `Stat` cards,
  boxed `Takeaway`, charts in `ChartCard` chrome. `web/DESIGN.md` → "the evidence
  layer speaks the brief's language" is the contract to convert them against.
- Regulations and Credit exist **only** as local files; publish them if they need
  to be reviewed away from the repo.
