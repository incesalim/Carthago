# `scripts/` — what each script is and when it runs

This is the index for the Python entry points. Each row says **what** the script does,
**who runs it** (a cron/CI workflow, the `/admin` panel, or by hand), the **lane** it
belongs to, and its **class**:

- **pipeline** — load-bearing; invoked by a scheduled workflow. Don't break these.
- **gate** — a standalone CI/health check (`check_*.py`); fails a build or alerts
  when the thing it guards drifts.
- **operational** — run by hand or `/admin` for an ongoing purpose (backfills, repairs).
- **diagnostic** — inspection / profiling only; in `scripts/diagnostics/` (plus a
  few by-hand tools listed in the lane tables).
- **scratch** — one-off benches / probes that answered a question; in
  `scripts/scratch/`. Read-only on production.
- **archived** — one-off campaign / migration that's done; in `scripts/archive/` for reference.

This index is itself CI-gated: `check_scripts_index.py` fails the build when a
script exists with no row here, or a row names a script that is gone.

The lanes themselves are described in [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md); the
audit lane and its repair playbook are in [`docs/AUDIT_PIPELINE.md`](../docs/AUDIT_PIPELINE.md).

## Shared / infrastructure
| Script | Purpose | Run by | Class |
|---|---|---|---|
| `push_to_d1.py` | Incremental SQLite→D1 sync (`INSERT OR REPLACE` rows newer than `--hours`); `--db`, `--only-tables`, `--table-set`. The one D1 writer every lane uses. **Full-rebuild tables (`api_series`, the audit spine) are skipped when their content hash is unchanged** — D1 bills rows written and those are ~20k-row DELETE+INSERT cycles; `--force-rebuild` overrides after direct D1 edits. See OPERATIONS §D1 write budget. | every refresh workflow | pipeline |
| `notify.py` | Telegram/Discord alert (lib + CLI). | called by workflows + scripts on failure | pipeline |
| `healthcheck.py` | Daily D1 freshness check + audit-failure count. | `healthcheck.yml` | pipeline |
| `verify_chart_spec.py` | Re-resolve every reproduced chart spec in D1 (regression catch). | `healthcheck.yml` | pipeline |
| `check_amount_integrity.py` | Sweep every audit amount column (ratio columns excluded by name) for a fractional value — BRSA prints whole thousands of TL, so a fraction is a mis-read thousands separator, i.e. a figure stored 1000× too small. `--db` sweeps a snapshot, default is remote D1. Alerts only on that class; marker leakage is reported. | `healthcheck.yml`; by hand | pipeline |
| `_bank_types.py` | BDDK bank-type code taxonomy (library; no `__main__`). | imported by `verify_chart_spec`, tests | pipeline (lib) |
| `check_pipeline_graph_sync.py` | Stdlib-only CI gate: every ingestion workflow ↔ `/pipeline` graph node stays in sync (both directions), and every node `href` resolves to a real route. Scratch lanes that move no production data are exempt via `SCRATCH_WORKFLOWS`, and an exemption naming a deleted workflow fails the gate. | `ci.yml` | pipeline |
| `metric_knowledge.py` | CLI over the banking-metrics knowledge registry (`data/metric_knowledge/registry.json`): list / show / validate. | by hand | operational |
| `setup_telegram_webhook.py` | `set` / `info` / `check` the Q&A-bot Telegram webhook; `check --alert` is the daily drift probe. | `telegram-webhook.yml`; `healthcheck.yml` | pipeline |
| `build_api_catalog.py` | Rebuild the `/api/v1` series catalogue (`api_series` — a full-rebuild table, pushed by name). | `refresh-data.yml` | pipeline |
| `audit_d1.py` | Shared D1/R2 helpers (remote exec, retry semantics) for the audit repair scripts. Library, no `__main__`. | imported | pipeline (lib) |
| `generate_presentation.py` | One-off HTML/PDF presentation from live data → `reports/`. | by hand | operational |
| `make_brand_assets.py` | Regenerate brand assets (icons, OG images). | by hand | operational |
| `fetch_bank_logos.py` | Fetch bank logos → `web/app/lib/bank-logos.generated.ts`. | by hand | operational |
| `fetch_bddk_english_labels.py` | Fetch BDDK's English series labels → `data/bddk_labels_en.json`. | by hand | operational |

## CI gates (`check_*.py`)

Four more gates live in the lane tables (`check_pipeline_graph_sync`,
`check_amount_integrity` above; `check_audit_quality`,
`check_capture_reconcile` in the audit tables).

| Script | Guards | Run by | Class |
|---|---|---|---|
| `check_scripts_index.py` | THIS index ↔ the scripts that exist, both directions. | `ci.yml` | gate |
| `check_docs_sync.py` | OPERATIONS/ADMIN/TELEGRAM_BOT name every workflow, secret and env key the code reads. | `ci.yml` | gate |
| `check_schema_naming.py` | D1 migrations ≥ 0022 follow SCHEMA_CONVENTIONS.md. | `ci.yml` | gate |
| `check_no_pdfplumber.py` | PDF extraction stays fitz-only. | `ci.yml` | gate |
| `check_prose_claims.py` | A dashboard sentence asserting a direction/level/ranking is computed, not typed. | `ci.yml` | gate |
| `check_contrast.py` | Every text token clears WCAG AA 4.5:1 on every surface it sits on, both themes. | `ci.yml` | gate |
| `check_calendar_fresh.py` | The hand-typed MPC calendar fallback keeps ≥ 90 days of runway. | `ci.yml` | gate |
| `check_workflow_state.py` | `data/workflow_state.json` ↔ which workflows are actually enabled on GitHub. | `ci.yml` | gate |
| `check_agents_registry.py` | `/admin/agents` dispatch forms ↔ each workflow's declared inputs. | `ci.yml` | gate |
| `check_public_api.py` | The published `/api/v1` contract still answers as documented. | `healthcheck.yml` | gate |
| `check_body_freshness.py` | `news_items.body_text` stays fresh enough for the compiled `/regulation` figures. | `healthcheck.yml` | gate |
| `check_bot_answers.py` | The Q&A bot still answers its pinned eval questions correctly. | `healthcheck.yml` | gate |
| `check_bot_schema.py` | The bot's schema prompt ↔ the live D1 schema. | `healthcheck.yml` | gate |
| `check_briefing_facts.py` | The briefing states the hand-verified published figures (checklist in `src/news/briefing_facts.py`) AND every cited release states its bullet's figures (`src/news/briefing_citations.py`) — both shared with the generator's own gates. **Publication gate** since 2026-08-16: `--fail-under 0.75` or any miscited bullet blocks the D1 push + snapshot, keeping last week's verified text live. | `summarize-regulations.yml`; `test-openrouter.yml` | gate |

## Bulletin / EVDS lane (BDDK monthly+weekly, EVDS, TBB, TKBB, KAP, TEFAS)
| Script | Purpose | Run by | Class |
|---|---|---|---|
| `refresh.py` | Orchestrator: monthly + weekly + EVDS + TBB + TKBB + KAP + TEFAS → snapshot. `--skip-*`, cadence-aware `--evds-frequencies`, and `--change-file` so workflows skip packaging/D1/R2 when SQLite is unchanged. | `refresh-data.yml`, `refresh-bddk-bulletins.yml`, `refresh-evds-daily.yml` | pipeline |
| `update_monthly.py` | Incremental monthly BDDK bulletin (latest month). | `refresh.py` | pipeline |
| `update_weekly.py` | Rolling 13-week BDDK weekly refresh. | `refresh.py` | pipeline |
| `update_tbb_digital.py` | TBB quarterly digital-banking Excel → `tbb_digital_stats`. | `refresh.py` | pipeline |
| `update_kap_ownership.py` | KAP Genel Bilgi Formu ownership → `kap_ownership`. | `refresh.py` | pipeline |
| `update_tefas.py` | TEFAS fund-market daily / `--backfill`. | `refresh.py`; `backfill-tefas.yml` | pipeline |
| `update_nonbank.py` | BDDK non-bank monthly bulletin (leasing / factoring / financing) → `nonbank_balance_sheet`. | `refresh.py`; `backfill-nonbank.yml` | pipeline |
| `update_tbb_acquisition.py` | TBB monthly remote-vs-branch customer-acquisition stats → `tbb_acquisition_stats`. | `refresh.py` | pipeline |
| `update_tkbb_digital.py` | TKBB participation-bank quarterly digital stats (Turboard JSON API) → `tkbb_digital_stats`; incremental, auto-backfills an empty table. | `refresh.py` | pipeline |
| `update_tkbb_acquisition.py` | TKBB monthly remote-vs-branch acquisition (rolling 12-month window, accumulated) → `tkbb_acquisition_stats`. | `refresh.py` | pipeline |
| `update_tuik.py` | TÜİK veriportali Excel detail (GDP expenditure, PPI MIG) → `evds_series` as `TUIK.*` codes. | `refresh.py` | pipeline |
| `update_faaliyet.py` | Bank annual-report (faaliyet) franchise stats → `faaliyet_franchise`; `--backfill`. | `refresh.py`; `backfill-faaliyet.yml` | pipeline |
| `update_presentations.py` | IR investor-presentation decks (static URLs + auto-discovery) → `bank_earnings`. | `refresh-presentations-weekly.yml` | pipeline |
| `update_transcripts.py` | Earnings-call transcripts (8 listed banks with English calls) → `bank_call_transcripts`; `--json-dir` writes inspection dumps. | `refresh-transcripts-weekly.yml` (manual, no cron yet) | pipeline |
| `notify_new_bddk.py` | Positive Telegram ping when a weekly/monthly BDDK period newly lands; quiet otherwise. | `refresh-bddk-bulletins.yml` | pipeline |

## News / regulation lane
| Script | Purpose | Run by | Class |
|---|---|---|---|
| `sync_news.py` | KAP + TCMB + BDDK + press feeds → `news_items`. | `refresh-news-daily.yml` | pipeline |
| `summarize_regulations.py` | LLM (Kimi) weekly regulation briefing → `regulation_briefings`. Per-category calls grounded on the annual baseline; gates each section on `find_contradictions` (transition-aware) + the fact checklist (deterministic strip of superseded-value bullets, one pointed retry naming rule + source, never the value). | `summarize-regulations.yml` | pipeline |
| `ingest_policy_baseline.py` | Ingest TCMB annual Monetary-Policy PDF as briefing baseline. | by hand, ~annually | operational |
| `generate_read_headlines.py` | Free-LLM rewrite of each T1 tab's one-sentence lead; number-validated, shown only while its `det_hash` matches the page → `read_headlines`. | `generate-reads.yml` | pipeline |

## Audit lane — pipeline
One scheduled arrival path plus a manual diagnostic (same `bddk-audit` group). During filing
windows `refresh-audit.yml` runs daily: scrape → extract → derive/revalidate/build coverage
locally → **one** D1 push → snapshot; it stops after discovery when nothing changed.
`acquire-audit.yml` is manual-only acquisition without extraction.
| Script | Purpose | Run by | Class |
|---|---|---|---|
| `sync_audit_reports.py` | THE audit entry: scrape new PDFs → R2 (`--no-extract` = acquire) and/or extract pending → `bank_audit.db`. `--only-bank`, `--latest-period`, `--periods`, `--no-scrape`, `--force`, `--new-count-file`, `--result-file` (machine-readable quiet-run handoff). | `acquire-audit.yml` (manual scrape), `refresh-audit.yml` (scheduled/manual combined path) | pipeline |
| `build_bank_audit_stages.py` | Consolidate credit-quality rows → `bank_audit_stages`. | `refresh-audit.yml` | pipeline |
| `check_audit_quality.py` | 10 alert-only anomaly families (stale/balance/coverage/npl_drop/capital/liquidity/structure/ecl/pl_sign/free-provision); delta-alerts against the R2 baseline. | `refresh-audit.yml`, `backfill-audit.yml`, `reextract-statement.yml` | pipeline |
| `seed_audit_db.py` | Bootstrap `bank_audit.db` from the bulletin snapshot on first run. | both audit workflows (bootstrap) | pipeline |
| `sync_audit_expected.py` | Build `bank_audit_expected` (profile census ∪ R2 PDFs) + `bank_audit_statement_types` + `bank_audit_coverage` (the /admin coverage matrix spine). `--push` = full-rebuild D1 push, no R2 write. | `acquire-audit.yml`, `refresh-audit.yml`; by hand | pipeline |
| `watch_cross_period.py` | Cross-period unit watch — the only check that can see a reporting-unit change, since every in-filing identity scales out. Alert-only. | `refresh-audit.yml`; `audit-triage.yml` | pipeline |

## Audit lane — operational (backfills + manual corrections)
| Script | Purpose | Run by | Class |
|---|---|---|---|
| `backfill_audit_source_capture.py` | Download existing audit PDFs and add lossless source-line evidence + compact manifests for the 8 normalized/summary lanes, without rewriting analytical facts. Content-idempotent; revalidates touched partitions. | `backfill-audit-source-capture.yml`; by hand | operational |
| `check_capture_reconcile.py` | Reconcile stored analytical figures against the cells the filing printed, using the capture as an **external** anchor. Every per-partition validator is an internal identity, and a uniform unit change scales both sides equally — so this is the only check that sees a partition stored at the wrong reporting scale (the TEB 2026Q2 failure). Reads the declared unit off the captured text via `units.regex_unit`, so it needs no PDF. Reports `unit_scale` / `figures_absent` (errors) and `capture_incomplete` / `unit_unknown` (info); exits 1 on an error. Read-only. | by hand | diagnostic |
| `view_document_capture.py` | Render one captured filing to a standalone HTML page for review — each table as a grid, each footnote under the table it qualifies with the rows it links to. Reads `data/bank_audit_capture.db` only; writes one .html. `--list` shows captured partitions. Read-only. | by hand | diagnostic |
| `backfill_document_capture.py` | Capture EVERY table each filing prints — rows, inferred columns, cells — plus footnotes linked to the rows carrying their marker. Document-scoped, so tables with no parser are captured too; calls no analytical upsert. Raw ledger → `data/bank_audit_capture.db` + `data/audit_capture/*.jsonl` (local, gitignored) and R2 `state/bank_audit_capture.db.gz`; **only** `bank_audit_document_manifest` reaches D1. `--from-r2` streams each PDF then deletes it. | `backfill-document-capture.yml`; by hand | operational |
| `build_document_tables.py` | Derive the queryable per-table lane from the capture ledger → `data/bank_audit_tables.db` (own DB, never the audit snapshot): one row per section per filing (`bank_audit_document_sections`, title + role + page span + `source` = contents/banner/none), one per contents item (`_items`), one per captured table (`_tables` — section context, declared unit, and the grid as JSON with notes and every unplaced cell kept). Sectioning shared with the viewer via `src/audit_reports/document_sections.py`. Values as printed, signed, "-" stays text; per-partition DELETE+INSERT; read-only on the ledger. | by hand | operational |
| `build_capital_full.py` | The capital pilot — the first lane minted from the document layer instead of a PDF: assemble the full Basel III own-funds template (seed on the regulatory opener or the bare-header dialect, chain across contiguous pages, truncate at a second template copy) → `bank_audit_capital_full` in `data/bank_audit_tables.db` (local): every row typed, money scaled to canonical bin at mint, ratios never scaled, "-" stays NULL, ~29-role registry with the narrow `bank_audit_capital` as the external anchor. Default is a dry-run report (detection, per-anchor agreement, tier1=cet1+at1, CAR≈total/rwa, registry-growth list); `--write` stores. | by hand | operational |
| `build_lcr_full.py` | The LCR graduation — second lane minted from the document layer. BRSA numbers the template's rows (1–23) and the capture keeps the number as the row's first cell, so `template_row` is the cross-bank join key; the filing's TWO printed tables (current quarter + prior YEAR-END — the fx lane's documented BRSA prior-column convention) split on a number restart into `period_label` instances. Four value columns (unweighted/weighted × TL+FC/FC); money scales declared_unit→bin at mint, row 23 (the percent row) never scales, and a bare-integer ≥10000 there is ALBRK's three-decimal misparse repaired (ENPARA's genuine 34,221.52% keeps its decimals and is untouched). → `bank_audit_lcr_full` in `data/bank_audit_tables.db` (local, not D1). Dry-run reports anchors vs the narrow `bank_audit_liquidity` pair and the 23≈21/22 identity in two bands (row 23 is the average of WEEKLY ratios, so exactness is not owed); `--write` stores. | by hand | operational |
| `build_nsfr_full.py` | The NSFR graduation — third lane minted from the document layer, sibling of the LCR builder (BRSA numbers this template too, rows 1–34). Per-block column model: rowno column by majority, phantom all-None columns dropped, four maturity buckets in printed order, the weighted total ALWAYS rightmost. Row 14 carries `asf_total` (its label usually omits any "total" word); row 34 is the percent, never scaled, with the same integer-guarded three-decimal repair as the LCR. Current + prior-YEAR-END instances split on a number restart. → `bank_audit_nsfr_full` in `data/bank_audit_tables.db` (local, not D1). Dry-run reports anchors vs narrow `nsfr` and the asf/rsf identity; `--write` stores. | by hand | operational |
| `build_leverage_full.py` | The leverage-ratio graduation — fourth lane from the document layer, thin over `src/audit_reports/numbered_template.py` (the shared machinery the LCR and NSFR builders now run on too: signature detection by printed row number, per-block column model, wrap adoption, instance split, per-template percent-repair floor). Rows 1–15, current + prior-year-end columns; row 15 is the percent with a 1,000 floor ("9,127" = 9.127%). → `bank_audit_leverage_full` in `data/bank_audit_tables.db` (local, not D1). Anchored vs narrow `leverage_ratio` and the 13/14 identity. | by hand | operational |
| `build_rwa_full.py` | The RWA-overview graduation (Pillar 3 OV1, rows 1–25) — fifth lane from the document layer over `numbered_template.py`: the RWA decomposition by risk type in three printed columns (RWA current, RWA prior year-end, minimum capital = 8%). → `bank_audit_rwa_full` in `data/bank_audit_tables.db` (local, not D1). Anchored vs narrow `bank_audit_capital.total_rwa` AND the graduated `capital_full` RWA role (wide-vs-wide), with a 0.01% relative band because two separately printed tables round independently. | by hand | operational |
| `build_exposure_class_full.py` | The CR4 exposure-by-asset-class graduation (rows 1–18 × six columns: on/off-balance exposure before and after CCF/CRM, RWA, RWA density) — sixth lane from the document layer and the first **self-validating** one: three forms number the same asset-class rows, so a block is admitted by shape (six live columns) and an instance is STORED only if its total row's density = RWA / post-CRM exposure — the mint gate that proves the columns landed. → `bank_audit_exposure_class_full` in `data/bank_audit_tables.db` (local, not D1). No narrow lane holds any of this; the OV1 credit-risk RWA is the informational cross-anchor. | by hand | operational |
| `build_loan_type_full.py` | The loans-by-type graduation — the first NOTES-section family minted from the document layer (BRSA's cash-loans-by-type × credit-quality note, §5): eleven fixed rows (non-specialised + seven sub-types, specialised, other receivables, total) × four quality columns (standard; watch-list not-restructured / modified / refinanced), current + prior instances. Label registry TR+EN with wrapped-label merge; an instance is STORED only if the template's two identities hold (non-specialised = Σ sub-types; total = non-specialised + specialised + other). → `bank_audit_loan_type_full` in `data/bank_audit_tables.db` (local, not D1). No narrow lane holds any of it. | by hand | operational |
| `build_consumer_loan_full.py` | The consumer-loans graduation — second notes-section family: BRSA's consumer loans / retail credit cards / personnel loans / overdrafts by maturity note (~45 rows × short-term, medium-long-term, total), current + prior. Rows carry a `group_role` (currency group) and an `item_role` (housing, vehicle, general-purpose, instalment…) because item labels repeat under each group. Mint gate needs no registry: total = short + long must hold on ≥90% of value rows and on the grand total. → `bank_audit_consumer_loan_full` in `data/bank_audit_tables.db` (local, not D1). | by hand | operational |
| `build_derivative_full.py` | The derivatives graduation — third notes-section family: BRSA's derivative breakdown by instrument (forwards, swaps, futures, options, other, total) × (current TL, current FC, prior TL, prior FC). The same template prints several times per filing, so each instance carries a `context` (assets / liabilities / hedging_…) read off the block heading and contents item. Mint gate: total = Σ instruments on every column that prints a total. → `bank_audit_derivative_full` in `data/bank_audit_tables.db` (local, not D1). | by hand | operational |
| `build_securities_full.py` | The securities graduation — fourth notes-section family: BRSA's securities breakdown by instrument and listing (debt securities / investment funds / share certificates × quoted / unquoted; impairment or valuation adjustment; total) × (current, prior), one instance per measurement portfolio (`portfolio` = fvtpl / fvoci / amortised_cost / unknown, heading kept). Mint gate: group = quoted + unquoted, total = Σ groups ± adjustment — sign read off label and figure (a "(-)" label with a positive figure subtracts; HAYATK prints impairment already negative; GARAN's "Value Increase/Impairment Loss" adds). → `bank_audit_securities_full` in `data/bank_audit_tables.db` (local, not D1). | by hand | operational |
| `build_credit_quality_full.py` | The credit-quality graduation — BRSA's numbered 1–4 Pillar 3 CR1 form (loans / debt securities / off-balance-sheet receivables / total × defaulted gross, non-defaulted gross, allowances, net; current + prior year-end) over `numbered_template`. Shape filter: four value columns AND the loans row in row 1 (CR3 prints seven; any four-row table ending in "Total" would otherwise join). `row_live_cells` un-staggers CR1 where the capture merged it with CR2 into one grid. Mint gate: net = defaulted + non-defaulted − allowances on row 4; anchor: defaulted loans vs the narrow NPL-movement closing sum (III+IV+V). → `bank_audit_credit_quality_full` in `data/bank_audit_tables.db` (local, not D1). | by hand | operational |
| `build_defaulted_movement_full.py` | The defaulted-movement graduation — BRSA's numbered 1–6 Pillar 3 CR2 form (opening defaulted stock, newly defaulted, returned to performing, written off, other changes, closing; one or two columns) over `numbered_template`. Banks disagree on signs, so each instance is stored as printed with the `convention` under which its own arithmetic balanced (signed / deductions_3_4 / deductions_3_4_5) — the mint gate. Anchors: closing and opening vs CR1's defaulted stock on either perimeter (loans + debt, or incl. off-balance-sheet), closing vs the narrow NPL-movement sum. → `bank_audit_defaulted_movement_full` in `data/bank_audit_tables.db` (local, not D1). | by hand | operational |
| `build_risk_weight_full.py` | The risk-weight graduation — BRSA's Pillar 3 CR5 matrix, asset class × risk weight (0/10/20/25/35/50/75/100/150/200/250 %, others, total), stored LONG with `risk_weight`, `col_role` and a `secured_re` flag for the mortgage-secured twin columns. The weight header is the hard part: read from every header fragment at each column index (in-grid header rows, column labels, a "250" split as "25"/"0", a weight wrapped onto the line above) under a left-to-right non-decreasing rule, with the capture ledger's page text as last resort; roles and the total row are label-based (the 2016 template totals on row 17). Mint gate: total = Σ columns on the total row and ≥90% of rows, tolerance scaled to the declared unit. Anchor: grand total vs CR4 post-CRM on+off. → `bank_audit_risk_weight_full` in `data/bank_audit_tables.db` (local, not D1). | by hand | operational |
| `build_deposit_insurance_full.py` | The deposit-insurance graduation — the notes table of saving deposits covered by / exceeding the deposit-insurance limit (TL saving, FX with saving status, other with saving status, foreign-branch, off-shore, optional total and commercial rows) × (covered, exceeding) × (current, prior). Reads the column order off the labels (covered-first standard; HSBC prints period-major with a year header row, ANADOLU abbreviates rows to `DTH` / `Diğ.H.`), merges wrapped labels in both directions. Gate: a printed total must equal Σ rows; `total_check` records `holds` / `not_printed` (the regulator's template has no total row). → `bank_audit_deposit_insurance_full` in `data/bank_audit_tables.db` (local, not D1). | by hand | operational |
| `build_deposit_maturity_full.py` | The deposits-by-maturity graduation — the notes matrix of deposits by type × maturity band (demand, 7-day notice, ≤1m, 1–3m, 3–6m, 6–12m, 1y+, accumulating, total) and its same-shaped twin, interest paid on deposits by maturity, stored LONG with a label-registry `row_role` and a `band` per cell. Bands are read from every header fragment at and before each live column (one cell may name two bands; a `1.0` is a `1 month`), completed from the canonical order; a filing's blocks are streamed so a page-broken matrix keeps its total row; an unlabelled trailing prior-period total column is detected by which layout adds up. Gate: total = Σ bands on ≥90% of rows and the grand total. `measure` and `period_label` are decided jointly by the grand total against the narrow BS deposits line / P&L deposit-interest line (current, prior year-end, prior year same quarter). → `bank_audit_deposit_maturity_full` in `data/bank_audit_tables.db` (local, not D1). | by hand | operational |
| `build_section4_matrix_full.py` | The Section-4 matrices graduation — the three risk-management tables that share one row template (balance-sheet items, totals, gap, off-balance lines) under three column sets: `liquidity_gap` (remaining maturity incl. unallocated), `repricing` (rate-sensitivity incl. non-interest-bearing), `fx_position` (EUR / USD / other FC). Family read off the column vocabulary; bands via `src/audit_reports/band_matrix.py`; a filing's blocks streamed per family so a page-broken matrix re-joins; label-registry roles incl. the FVOCI wrap tail resolved by template order. Gate: total = Σ bands on ≥90% of rows and total assets. Anchors: total assets per bucket vs narrow `repricing`, per currency vs narrow `fx_position`, vs the balance sheet. → `bank_audit_section4_matrix_full` in `data/bank_audit_tables.db` (local, not D1). | by hand | operational |
| `build_sector_full.py` | The sector graduation — every notes table on BRSA's sector template (agriculture / industry / construction / services with their items, other, total), LONG, family by column shape: `risk_profile` (17 exposure classes + TL/FC/total, numbers from the in-grid header row or class names from the labels), `loans_currency` (TL, %, FC, % ± prior), `stage_ecl` (stage 2 / 3 / ECL — the narrow `loans_by_sector` table), `npl_provisions`, `two_period`. Sector registry in the narrow lane's vocabulary; an English "Manufacturing" group and a header-fragment group label are repaired by position. Gate: group = Σ items and total = Σ groups on the total/TL column. Anchor: `stage_ecl` cells vs the narrow lane. → `bank_audit_sector_full` in `data/bank_audit_tables.db` (local, not D1). | by hand | operational |
| `audit_narrow_vs_wide.py` | The narrow lanes audited by the wide ones: every narrow row (`bank_audit_capital`, `_liquidity`, `_npl_movement` cell by cell, `_loans_by_sector`, `_repricing`, `_fx_position`, and the P&L / BS / off-balance lines behind the breakdown notes) that a gated wide lane contradicts, named bank / period / kind / figure. Read-only on both databases; prints a per-lane count and writes the full list to `docs/knowledge/<date>-narrow-vs-wide-repair-list.md` (gitignored). The wide figure has the template's identity behind it, the narrow one none — so the list is the narrow lane's repair list. | by hand | operational |
| `build_tl_fc_note_full.py` | The TL/FC notes graduation — the small notes printed as items × (TL, FC) × (current, prior), nine families under a registry: interest on loans / from banks / on securities / on funds borrowed (nested under "to banks"), funds borrowed by source and by maturity, cash & CBRT, securities issued, subordinated debt (children under the latest head). Gate: total = Σ top-level rows and head = Σ children on the current TL and FC columns. Anchor: current TL+FC of the total vs the family's narrow P&L / BS line. Three families tried and dropped for want of an anchor (BS banks note, FVTPL by type, hedging by type). → `bank_audit_tl_fc_note_full` in `data/bank_audit_tables.db` (local, not D1). | by hand | operational |
| `build_npl_movement_full.py` | The NPL-movement graduation — the movement of non-performing loans by group (III / IV / V: opening, additions, transfers in / out, collections, write-offs, sold and its split, closing, provision, net), LONG per (row, group); the table behind the narrow `npl_movement` lane. Gate per group: net = closing − provision AND closing = opening + additions + transfers in − transfers out − collections − write-offs − sold, unregistered rows entering with the sign printed on their label. Anchor: each group's opening / closing / provision / net vs the narrow lane. → `bank_audit_npl_movement_full` in `data/bank_audit_tables.db` (local, not D1). | by hand | operational |
| `build_stage_movement_full.py` | The stage-movement graduation — the TFRS 9 movement tables by stage (stage 1 / 2 / 3 / total × opening, additions, derecognitions, sold, written off, transfers to stage 1/2/3, FX, closing) for gross loans and for ECL (`measure` from the heading), LONG over `band_matrix` with the stages as bands; three undigited "Aşama" labels are numbered in order, stacked current/prior grids split on the second opening row. Gate: total = Σ stages on ≥90% of rows AND closing = opening + Σ movements per stage under the printed sign convention (recorded). → `bank_audit_stage_movement_full` in `data/bank_audit_tables.db` (local, not D1). | by hand | operational |
| `build_two_period_note_full.py` | The two-period notes graduation — items × (current, prior) notes with a total, under a family registry with head/children: letters of guarantee by type, non-cash loans by type, trading income (gains / losses heads over capital-market, derivative, FX children; net total = gains − losses, 100% to the P&L line), and other operating expenses (personnel, termination reserve, impairments and depreciation by asset class, the "other operating expenses" head with lease / maintenance / advertising / other children, loss on sale, other). Gate: total = Σ top-level rows and head = Σ children. Anchor: the current total vs the narrow statement line (letters of guarantee 100%; expenses vs the P&L line or line + personnel, 49.5%; non-cash vs the guarantees head, 44%). → `bank_audit_two_period_note_full` in `data/bank_audit_tables.db` (local, not D1). | by hand | operational |
| `backfill_extraction.py` | Re-extract named banks from R2 → clear D1 partitions → push → snapshot. Shared D1/R2 helpers live in `scripts/audit_d1.py`. | `backfill-audit.yml`; by hand | operational |
| `audit_correct.py` | Unified manual-correction CLI: `overlay-statement` (hand-transcribed `manual_statements.json`), `override-cells` (`audit_overrides.json`), `reextract-pl`. Validate-to-0 → push one partition. | by hand | operational |
| `load_partition.py` | Impl behind `audit_correct overlay-statement`: load a hand-transcribed statement from `data/manual_statements.json` into one partition, validate, push. | via `audit_correct`; by hand | operational |
| `apply_overrides.py` | Impl behind `audit_correct override-cells`: apply curated cell fixes from `data/audit_overrides.json` (BS/OCI/capital/pl_rehier/… types), revalidate, push. | via `audit_correct`; by hand | operational |
| `reextract_statement.py` | Registry-routed re-extract of ONE statement lane; `--only-failing` uses the full relationship gate and `--require-passing` rolls back rejected source + derived + validation rows. Credit-quality rebuilds stages before acceptance; no-op tables are not re-stamped or pushed. | `reextract-statement.yml`; by hand | operational |
| `reextract_pl.py` | Re-extract ONLY `profit_loss` for ONE `(bank, period, kind)` partition — single-PDF repair, not a fleet tool (also exposed as the `audit_correct reextract-pl` sub-command). | by hand | operational |
| `revalidate_audit_db.py` | Recompute `bank_audit_validation` from stored rows for all 19 registered lanes, including cross-table and longitudinal checks; no PDF re-extraction. | by hand after a validator change | operational |
| `push_from_scratch.py` | Push pre-extracted rows from `fleet_scratch.db` → D1 (no re-extraction). | by hand (large repair) | operational |
| `discover_audit_urls.py` | Scan bank IR pages for new quarterly report URLs. | by hand, quarterly | operational |
| `compute_bank_metrics.py` | Derive a per-bank KPI snapshot from audit data. | by hand | operational |
| `fleet_evidence.py` | Dry-run full re-extraction to `fleet_scratch.db`; bucket improved/unchanged/regressed (the non-regression gate). Never writes prod/D1/R2. | by hand before a backfill | operational |
| `run_phase3_batches.py` | Gated batchwise re-extraction (aborts on regression). | by hand (large repair) | operational |
| `purge_partition.py` | Remove one `(bank, period[, kind])` in the one order that sticks: snapshot → local delete → D1 delete → re-upload snapshot → coverage re-sync. For extractions that validate green but are known wrong. | `purge-partition.yml`; by hand | operational |
| `repair_loans_zeros.py` | Re-derive the zeros `_save_loans`'s falsy-`or` chains discarded, from `raw_api_responses` on disk — fills NULLs only, refuses disagreements. | `repair-loans-zeros.yml` | operational |
| `triage_partitions.py` | Assign each failing partition a deterministic mechanical CAUSE from the PDF (`column_slip` / `dropped_cell` / `anchor_miss` / …), page + token evidence attached. | `audit-triage.yml`; by hand | operational |
| `measure_free_provision_change.py` | Corpus-wide diff of a `classify_free_provision` change against stored values; returns an artifact, writes nothing. | `measure-free-provision.yml` | operational |
| `backfill_prose.py` | Historical prose backfill over local PDFs → `data/bank_audit_prose.db` (merge + push recipe in OPERATIONS.md). | by hand | operational |
| `extract_audit_text.py` | Dump one filing's reconstructed text/lines for inspection. | by hand | diagnostic |
| `lint_document_capture.py` | Say what is wrong with one filing's document capture. | by hand | diagnostic |

## Analyst lane (`scripts/analyst/`)

| Script | Purpose | Run by | Class |
|---|---|---|---|
| `detect.py` | Deterministic detectors over the audit snapshot → `analyst_signals` + `analyst_basis_metadata`, staged into `data/analyst.db`. No LLM. | `analyst-daily.yml` | pipeline |
| `score_reports.py` | Structure/lead/coverage scoring over memo run artifacts (informational — the figure guard already gates). | `analyst-daily.yml` | pipeline |
| `prepare_filing_text.py` | Filing-page text pack for the V2 research loop's read-only tools. | `analyst-research.yml` | pipeline |
| `extract_stage_definitions.py` | Per-bank IFRS-9 stage definitions from the prose corpus → `web/app/lib/analyst/stage-definitions.ts` (generated module). | by hand | operational |
| `eval_research.py` | Analyst-V2 evaluation harness over `data/analyst_eval/cases.json`. | by hand | diagnostic |

## Audit lane — diagnostics (`scripts/diagnostics/`)
| Script | Purpose | Class |
|---|---|---|
| `profile_audit_corpus.py` | Profile every R2 PDF → `data/audit_profiles.json` (format census; feeds the coverage matrix's expected universe). | diagnostic |
| `catalog_audit_templates.py` | Catalog NPL/§4/§5 label variants per bank. | diagnostic |
| `summarize_audit_catalog.py` | Render the template catalog to summary + registry. | diagnostic |
| `generate_audit_census.py` | Render the census + drift into `docs/AUDIT_BANK_CATALOG.md`. | diagnostic |
| `diag_partition.py` | Dump one `(bank, period, kind)` statement + PDF line matches; show identity breaks. | diagnostic |
| `validate_discovery.py` | Check IR-page auto-discovery against the hand-maintained config. | diagnostic |
| `verify_stage_coverage.py` | Audit IFRS-9 stage coverage completeness. | diagnostic |
| `validate_presentation_discovery.py` | Check IR-deck auto-discovery (GARAN/AKBNK/YKBNK) against the static URL config. | diagnostic |

## Backfills (`scripts/backfills/`)
| Script | Purpose | Class |
|---|---|---|
| `backfill_credit_quality.py` | Re-extract the IFRS-9 credit-quality footnote fleet-wide after a fix. | operational backfill |
| `backfill_npl_history.py` | Re-extract NPL Stage-3 movement history (chunked by period). | operational backfill |

## Scratch (`scripts/scratch/`) — one-off benches + probes

Each answered a specific question and stays as the record of the method. All are
read-only on production: they pull PDFs into `data/_bench/` and write no D1/R2.
`test-openrouter.yml` is the only workflow that runs any of them.

| Script | The question it answered |
|---|---|
| `scratch_test_openrouter.py` | Does the `OPEN_ROUTER_API` secret work, and what does DeepSeek cost? |
| `scratch_dump_briefing.py` | Print the newest local `regulation_briefings` row so two providers' output can be compared. |
| `scratch_bench_unit_detection.py` | Can an LLM read a filing's reporting unit as well as the regex? (No — see PROJECT_STATE.) |
| `scratch_bench_vision_extract.py` | Can a vision model extract the statements a human had to correct? |
| `scratch_bench_text_cells.py` | Can a text LLM recover the cells a human had to correct? |
| `scratch_bench_validator_gate.py` | Would the validators CATCH a wrong LLM figure? (The 79.9% / 52.6% / 38.7% blind-spot measurement.) |
| `scratch_one_pdf_deepseek.py` | One text PDF, one model, every row checked against what we store. |
| `scratch_one_hard_row.py` | One page where the deterministic extractor failed — can any model read it? |
| `scratch_probe_absent_cause.py` | Is the 14% `npl_movement` ceiling real, or a matcher blind spot? |
| `scratch_probe_retrieval_ceiling.py` | What is the ceiling of the retrieval step, before any model is called? |
| `scratch_probe_drawn_pages.py` | How much of the corpus is drawn (vector outlines) rather than typed? |
| `scratch_probe_split_digits.py` | How widespread is digit-splitting in the audit text layer? |
| `scratch_probe_wrapped_cells.py` | How many hand corrections are the wrapped-cell shape? |
| `scratch_probe_stale_overrides.py` | Which hand corrections are now obsolete — already fixed by the extractor? |

## Archived (`scripts/archive/`) — done, kept for reference
`extract_all_audit_reports.py`, `scrape_all_banks.py` (local-PDF flow, replaced by R2-based
`sync_audit_reports`), `migrate_pdfs_to_r2.py` (one-time R2 migration), `reextract_all.py`
(superseded by `backfill_extraction --banks ALL`), `validate_pl_fix.py` / `audit_extraction.py`
(fix-verification), `generate_d1_migrations.py` (one-time D1 seed), the historical data
backfills `backfill_2020_2023.py` / `backfill_weekly_2020_2023.py` / `backfill_weekly_2y.py` /
`update_db_2026.py`, and the 2026-06 audit-repair one-offs: `_eq_failreport.py`
(equity-change failure listing), `ocr_statement.py` (easyocr experiment for image-only
statements — superseded by the manual-overlay path), `normalize_hierarchy_keys.py` (one-time
trailing-dot hierarchy-key migration; the loader now normalises on write), and
`load_partitions_batch.py` (batch variant of `load_partition` for the manual-transcription
campaign). Archived 2026-08-16, the frozen-lane cleanup trio:
`dedup_hierarchy_rows.py` (one-time removal of duplicate/junk hierarchy rows from the
frozen BS/P&L tables), its OCI sibling `clean_oci_header_rows.py` (page-artefact rows
in `bank_audit_oci`), and `normalize_roman_hierarchy.py` (one-time roman-hierarchy
normalization, companion to `loader._canon_hier`).
