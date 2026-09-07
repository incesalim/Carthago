# Complete audit document corpus

Status: active implementation, begun 2026-09-06.

## Objective and scope

Preserve every table and every text passage in the registered bank audit-report
corpus, across banks, periods and reporting bases. Preserve source structure,
provenance and qualifications so tables can later become website time series
and narrative can support analyst research. Complete the registered corpus
first; expand to additional banks and earlier history afterward (user decision,
2026-09-06).

Existing task reports, successful jobs, extracted counts and internal accounting
identities are not evidence that the source was captured completely. Verify
against original PDFs and independently annotated source cases. No filing is
described as fully verified while any content region or required check remains
unresolved. Source contradictions are retained and flagged, never silently fixed
in the transcription layer.

The concurrent release-pipeline task owns the currently modified workflows,
`src/pipeline/`, release scripts and its migration. Keep this implementation
separate; do not stage or overwrite that task's changes.

## Verified starting observations

- Live R2 listing on 2026-09-06: 1,117 audit PDF objects, 38 banks,
  2022Q1 through 2026Q2. This counts acquired objects, not independently expected
  filings. The registered URL set and acquisition inventory must be reconciled.
- The local legacy capture has 1,095 filings. It cannot be accepted as the
  current corpus and does not store a PDF byte hash or extraction version.
- Routine `refresh-audit` captures a run-local ledger and discards it. The
  durable fleet ledger is written by a separate manual backfill. Detailed new
  filings therefore do not automatically accumulate in durable capture storage.
- The admin coverage matrix describes predefined analytical lanes. It does not
  establish whole-document capture coverage or show source-level verification.
- The legacy capture retains text lines and numerical table geometry; pure text
  tables and image/vector content require explicit handling. Successful numeric
  parsing does not establish preservation of all textual relationships.
- A source-verified QNB example preserves both printed percentages correctly
  but assigns an incorrect analytical role. Literal transcription and financial
  interpretation need separately testable contracts.

## Work sequence and acceptance

1. **Corpus inventory and immutable source identity.** Reconcile registered
   filings, acquisition objects and local inputs. Store original URL/object key,
   PDF SHA-256, byte count, bank/period/basis and revision association. Record
   missing sources and conflicting identities explicitly. Completeness must
   have a denominator independent of successful extraction.
2. **Independent source evidence and benchmark.** Preserve PyMuPDF source text
   and geometry without routing it through the existing table detector. Account
   for every text token, including duplicate occurrences, and every nontext
   region. Construct source-annotated real-PDF cases covering languages,
   rotation, wrapped and multi-page tables, prose, footnotes, text-only tables,
   outlines and scans. Verify the check itself with dropped/swapped content.
3. **Complete structured document representation.** Preserve document order,
   sections and nested headings; tables with row/column headers, original cell
   text and spans; paragraphs/lists; notes and references; page and bounding-box
   provenance; extraction method and explicit ambiguity. Keep residual content
   accessible. OCR/vision recovery must preserve source evidence and remain
   unverified until independently checked.
4. **Durable incremental processing.** Write per-source, versioned artifacts to
   R2; skip identical inputs and engine versions. Resume interrupted runs and
   retain failures. Rebuild searchable/structured views from those artifacts.
   Run fleet processing in Actions, keeping local execution to light probes
   and tests. A failed filing must not disappear behind a successful job total.
5. **Admin and analyst access.** Expose the expected/acquired/captured/verified
   distinction, stale versions, content gaps and source evidence in the admin
   panel. Provide queryable tables and structured prose with citations. Store
   large evidence in R2; limit D1 to useful indexes/status and approved derived
   data, with content comparison before writes.
6. **Corpus verification and series migration decision.** Run the independent
   checks across the registered corpus, investigate every unresolved class and
   publish an explicit readiness record. Verify new analytical questions against
   the source. Compare candidate series to current lanes by period, unit, basis
   and meaning; replace lanes only when the replacement has demonstrated the
   required coverage and correctness. Current serving lanes remain available
   during that comparison.

## Definition of done

Every expected filing has a traceable source or an evidenced acquisition gap.
Every acquired source version has durable, reproducible capture artifacts.
Every page's text and nontext content is accounted for. Every detected table,
paragraph and note is accessible with its source and structural context. Tests
exercise omission, duplication, misassociation, source changes and failed runs.
The admin view exposes unresolved work instead of collapsing it into a green
extraction status. Representative whole documents and new research questions
have been verified against rendered source pages, and remaining corpus issues
are enumerated. Completion is not inferred from a passing unit suite or a count
of detected tables.

## Execution record

- 2026-09-06: traced acquisition, capture, table derivation, prose, serving,
  admin coverage and workflow persistence. Confirmed first-stage scope with
  the user. Inspected live R2 object inventory read-only. Began independent
  inventory and source-evidence implementation.
- 2026-09-06: implemented immutable source evidence, source-bound candidate
  structure, per-filing R2 revision indexes and resumable publication. Candidate
  structure keeps all source text blocks, numeric table candidates, additional
  ruled text-only tables and nontext region references. Tests deliberately drop,
  duplicate, corrupt and swap content and interrupt uploads. None of these
  artifact-integrity checks certifies semantic completeness. Fleet publication,
  whole-document annotation and admin integration remain unfinished.
- 2026-09-06: visually verified QNB 2026Q1 solo PDF pages 45–46. Fixed the
  countercyclical-buffer role matcher to use the actual requirement row (0.01%),
  not a regulation reference inside the distinct 5.97% ratio. Added regression
  tests and reran the assembler; stored wide rows still require targeted rebuild.
- 2026-09-06: inspected the signed-in live admin panel. Its audit summary showed
  `Clean` while the lane matrix showed 39 error cells and all 1,117 prose cells
  unavailable. Changed the coarse summary wording to state its actual core
  extraction scope. The new corpus panel is still to be built.
- 2026-09-06: captured all 108 pages of QNB 2026Q1 solo into the new source
  representation; all typed text is conserved by the candidate lines. Source
  review of PDF page 47 found table rules made of thousands of raster dashes.
  Added candidate rule reconstruction and verified the resulting 23×3 mixed
  text table against the rendered PDF. Four independently annotated source
  cases pass; this is not a whole-document benchmark. Image/drawing review,
  table continuation and complete narrative semantics remain outstanding.
- 2026-09-06: Actions sample [34026793864](https://github.com/incesalim/Carthago/actions/runs/34026793864)
  preserved QNB 2026Q1 consolidated and solo: 218 pages, with original PDFs,
  evidence and candidate structure in eight R2 objects. Independently downloaded
  and verified the stored bytes and source accounting; the four annotated solo
  cases pass, while consolidated remains unannotated. CI exposed an unnecessary
  SDK import in offline storage tests; removed that dependency and tested the
  adapter with the SDK unavailable.
- 2026-09-06: identical replay [34027268957](https://github.com/incesalim/Carthago/actions/runs/34027268957)
  passed and left all ten stored objects unchanged, including ETag, byte count
  and modification time. Added a compact corpus catalog and private admin page
  viewer. Python-produced wire fixtures test exact page-byte compatibility with
  the Worker reader, plus dropped/changed pages, wrong sources and auth gating.
  Deployed at `8020250c` after green CI. Live admin checks confirmed source-bound
  page streaming, the QNB page-47 23×3 table, preserved prose and blocked anonymous
  downloads. Broader source-format verification remains pending.
- 2026-09-06: added resume receipts that bind already-verified bytes to their
  storage object versions; changed sources, engines, annotations, missing or
  changed artifacts and failed attempts invalidate reuse. Added full-byte replay
  and automatic corpus follow-up after the existing acquisition workflows.
  Cloud receipt replay [34029395716](https://github.com/incesalim/Carthago/actions/runs/34029395716)
  passed: both QNB filings reused object-version receipts, and all 15 stored
  objects remained unchanged. The first structure fleet was stopped after new
  source probes exposed two structural defects. Source-only fleet
  [34029735843](https://github.com/incesalim/Carthago/actions/runs/34029735843)
  is running while structure repairs are verified.
- 2026-09-06: source probes found Akbank 2026Q1 solo page 6's single-row
  ownership table was undetected, and Garanti 2022Q4 consolidated page 4's
  pension-table left border was pulled into its text by global snapping of the
  auditor logo's vector paths. Added conservative rule filtering and cell-width
  underline candidates. Independent annotations fail on the prior outputs and
  pass on the repaired pages. Also verified TOMK 2024Q1 page 7's wrapped director
  responsibilities. Seven selected source cases across four filings now pass;
  this still does not constitute whole-document semantic verification.
- 2026-09-06: Albaraka 2026Q1 solo PDF page 3 stores four titled audit passages
  and the signature in a single physical text block. Added source-line paragraph
  segmentation, heading candidates, explicit table-text membership and retained
  running furniture. Four manually transcribed full-paragraph digests check the
  qualifications, negations, repeated figures and heading associations against
  their source regions. Source accounting also rejects reordered, dropped or
  duplicated prose. The admin can show these candidates alongside raw blocks.
  Cloud probes and broader narrative/reading-order verification remain pending.
- 2026-09-06: cloud probes at `e842211c` passed Akbank, Garanti, QNB and TOMK's selected
  cases. The Albaraka whole-report probe correctly failed all four paragraph
  checks: larger cover typography leaked into the auditor opinion's heading
  path. The wording itself was intact. Reproduced the failure from the retained
  cloud artifact and corrected heading scope to the page, with document section
  context retained separately. The unchanged source annotations then pass.
  Cross-page paragraph/heading continuation remains an explicit later task;
  relative font size alone is insufficient evidence for that relationship.
- 2026-09-06: Albaraka replay `34031695563` passes all four unchanged paragraph
  annotations; independently checked its downloaded artifact. Across the cloud
  probes, all seven selected table cases and four prose cases now pass.
- 2026-09-06: stopped source-only fleet `34029735843` after 242 successful named
  outcomes. A further Akbank page-9 source check found that default page clipping
  truncates image replacement text (PDF ActualText), including the final footnote.
  Replacement geometry can also glue a heading to the preceding amount. Original
  PDFs remain intact. Source evidence now preserves an unbounded text view, a
  separate literal-glyph word view when they differ, and PDF-declared structure
  with source-span links and image regions. Native `Table` tags can be column
  strips, so they remain source metadata rather than assumed visual tables.
  Two new source cases gate both source-only capture and structured capture;
  their changes invalidate source receipts independently of table cases.
  The new evidence engine needs cloud validation before the fleet resumes.
- 2026-09-06: read-only source-format probes on FIBA 2025Q3 and ISCTR 2025Q1
  completed. They flag 40 unreadable pages in each FIBA filing and five in ISCTR
  consolidated (none in solo). These are detector flags, not a completed source
  review. Original images/vectors are preserved; OCR recovery and independent
  transcription checks remain outstanding.
- 2026-09-06: source-fidelity cloud probes at `9b1d9b84` pass all 13 selected
  table, prose and source-text cases. Published sample `34033192250` covers four
  Akbank/Albaraka filings and 374 pages. Independently downloaded their originals,
  evidence and structure: source/acquisition bytes, committed engine hashes,
  page accounting and all matching annotations pass. Live admin checks show the
  separated Albaraka opinion and complete Akbank footnote; the catalog correctly
  reports 238 stale captures among 242 preserved sources and zero fully verified
  filings. Added four stable filing groups for full Actions runs; tests verify
  exhaustive/disjoint assignment, global limit handling, explicit empty groups
  and safe catalog merging after three competing writers. This changes execution
  only; the source and structure engine fingerprints remain unchanged.
- 2026-09-06: CI for `b4fd60c9` passed. Bounded sample replay `34034349723`
  reused all four filings; independently checked all 21 source/corpus object
  versions were unchanged. Full run `34034440123` is active in four disjoint
  groups. The catalog retains its full 1,117-filing denominator and zero fully
  verified status while stale captures are replaced.
- 2026-09-06: visually confirmed FIBA 2025Q3 solo page 10's vector-only balance
  sheet and ISCTR 2025Q1 consolidated page 11's raster balance sheet. Full-page
  OCR recovered all 12 selected total-assets tokens in their correct regions.
  An isolated-cell probe read FIBA's 37.237.474 as 37.137.474; both disagreement
  and the row's arithmetic expose the error. Borders also become punctuation.
  Added separate, image-bearing OCR observations with pinned model and runtime
  identities, source-pixel verification and complete retained word/span checks.
  Local source probes and 12 token-region annotations pass, without approving
  cell signs, wording or whole tables. The workflow exposes only bounded,
  read-only OCR probes at this stage; cloud verification and production recovery
  integration remain outstanding.
- 2026-09-06: OCR cloud probes `34035657812` (FIBA) and `34035660589` (ISCTR)
  pass. Independently downloaded their originals, native evidence, OCR PDFs and
  observations; pixel/source retention and the 12 selected token-region checks
  pass. Comparing Windows and Actions outputs exposes differences outside those
  selected cases, including amounts. Raw OCR is retained as an observation.
- 2026-09-06: a vector-outline prototype on FIBA page 10 uses 24 transcribed
  numeric words and two dash styles as source anchors. It reconstructs 47 numeric
  rows (182 numbers, 100 dashes), with all 38 fully numeric TP+FC=total identities
  passing. On held-out page 11 it reads 274 entries and leaves eight parenthesized
  amounts unresolved, preserving the signs' uncertainty. Twelve independently
  transcribed deposit/total-liability region checks pass. Added a bounded,
  read-only outline probe with a source-rebuilt atlas and tests for reference
  mismatches, ambiguous glyphs, moved/changed words, and partial negative reads.
  The 26 selected word/region/abstention checks pass locally. Cloud validation,
  parentheses and additional fonts/characters remain outstanding; this does not
  certify complete table or prose semantics.
- 2026-09-06: outline cloud probe `34037621029` passes. Independently downloaded
  its original, source evidence, atlas and observations: the rebuilt atlas is
  identical and all 26 selected checks pass. Extended source seeds to learn only
  parentheses and a decimal comma; numeric templates remain from page 10. Eight
  previously unresolved page-11 negatives now require their exact signs. Twenty
  page-13 P&L values were visually transcribed before testing. All 46 selected
  words pass locally. One apparent miss was a test-region ambiguity caused by a
  whole-page background path: requiring whole-path containment resolves it
  without relaxing glyph matching. Cloud replay and durable recovery integration
  remain outstanding.
- 2026-09-06: punctuation replay `34038991010` and an independent download/source
  reconstruction pass all 46 selected outline checks. Implemented separate
  recovery publication, per-page history/failures, source-linked OCR lines and
  raw OCR/outline comparisons. Added a manual Actions recovery workflow and a
  private admin reader/viewer. Tests inject changed words, lost lines, source and
  page mismatches, missing/corrupt storage, interrupted uploads and false approval;
  repeated identical publication writes nothing. Production recovery, source
  classification coverage and broader table/prose associations remain pending.
- 2026-09-06: published recovery samples `34039939707` (three FIBA pages) and
  `34039941630` (one ISCTR page) pass. Independent R2 downloads reproduce original
  hashes, pixels, OCR observations, outline atlas/readings and annotations. Live
  admin displays both, including FIBA's 21/4/2 raw-reader differences; anonymous
  access returns 403. Source review confirms one material disagreement: interest
  received from banks is 717.417, which OCR read as 7.417. The outline read is
  correct; added a source regression without teaching new glyphs. Replaced the
  inherited selector's double-rotated page bounds with explicit display geometry
  and image-region word counts, tested at all four rotations. Changed recovery
  views now rebuild from retained raw observations without repeating OCR.
- 2026-09-06: refinement replay `34040563636` reuses all three selected OCR
  observations. Unchanged replay `34040764985` reuses them and leaves all 12
  checked object versions unchanged. Started full recovery `34040878532` in
  four groups, alongside the native capture fleet. Implemented a candidate
  table view from retained source pixels, thin vertical rules and repeated
  amount baselines. Local FIBA/ISCTR probes yield 47×8, 47×8, 64×6 and 48×8
  grids. All 59 method/region checks (53 annotated source locations) pass; tests
  deliberately swap/drop/duplicate/move source cells, alter image pixels and
  preserve unresolved signs and OCR `o` without inventing numeric zeros.
  Full raw observations remain accessible; table semantics and cloud layout
  validation are still outstanding.

- 2026-09-06: read-only recovery table probes `34042466701` (FIBA pages
  10/11/13) and `34042468735` (ISCTR page 11) pass at `7cd0cf88`; CI and
  deployment pass. Independent downloaded source-pixel, raw observation,
  source-built atlas and grid reconstruction checks pass all 59 selected
  cell associations. Windows NumPy 1.26.4 and Actions 2.5.2 produce identical
  grids; this cross-runtime check is recorded separately from engine identity.
  Whole-table interpretation and unannotated content remain unverified.
- 2026-09-06: added recovery filing receipts after byte readback of original,
  page artifacts and recovery index. Changed source versions, page failures,
  code/runtime/models, per-filing annotations or retained artifact versions
  invalidate the shortcut. Explicit and automatic page scopes are separate.
  Tests confirm a no-op replay reads only the receipt, recovery index and object metadata,
  writes nothing and runs no PDF processing; explicit byte recheck reuses raw
  OCR. These receipts still require a cloud replay proof before automatic
  recovery follow-up. The native and raw-recovery full runs remain active.

- 2026-09-06: independently rendered Akbank 2026Q1 solo page 9 confirms that
  replacement labels can inherit the preceding amount's text cursor. Literal
  glyphs alone fix numeric geometry but lose the image labels. A candidate view
  now uses only unique image/text siblings under a native Span, retains all
  original references and rejects ambiguous links. Native clipped image bounds
  must fit the observed image region. The selected page has 82 pairs and an
  86-row/six-value-column alternative. Three source-transcribed rows (18 values)
  and the complete footnote position pass, alongside the previous two page-9
  source cases. Unit tests reject changed/missing/duplicate associations and
  confirm display coordinates are transformed only once at all four rotations.
  Candidate structure and the admin table reader are integrated locally; source
  evidence stays unchanged. Cloud validation/publication remain pending.

- 2026-09-06: the four `5f6fd48` source-positioning cloud samples pass, as do
  CI and deployment. Independent downloaded bytes/source accounting verify
  543 retained pages and all 17 selected cases. Seven source pages are freshly
  observed from their original PDFs; the 82 Akbank page-9 position candidates
  and its alternative table rebuild identically. The cloud structure hash is
  checked against the committed files; local line-ending differences are
  recorded separately. Publishing sample `34045487439` is queued behind the
  native fleet. Completed native groups 0/1/2 independently match 840 expected
  filings and 87,258 pages, with no omitted, duplicate, unexpected or failed
  outcomes. Group 3 and the older raw-recovery fleet remain active.

- 2026-09-06: inspected the existing wrong-PDF helper: it tests only whether
  the cover contains the year and does not use the bank or quarter. Added a
  separate read-only source review with bank/date/basis claims and source span
  references, exact PDF/evidence/structure byte and page checks, suspicious-text
  signals and recovery gaps. Tests catch wrong quarters within the same year,
  wrong banks/bases, competing claims, missing pages and changed source bytes.
  Five retained original covers support their expected identity; a synthetic
  damaged-font example is flagged without treating ordinary numbers as bad
  text. The workflow quality mode never writes source or serving data. Fleet
  quality review remains pending.

- 2026-09-06: all four native groups completed and independently reconcile
  1,117 sources/116,503 pages without omissions, duplicates, unexpected outcomes
  or failures. Published Akbank/Albaraka positioned views match the independent
  probes byte-for-byte and pass live-admin review. Full read-only quality review
  34047832643 is active; three completed groups byte-verify 850 filings.
- 2026-09-06: independent BDDK register comparison across all 38 existing banks
  and 2022Q1–2026Q2 found 45 missing explicit URL bindings, including 29 PDFs not
  yet acquired. Corrected the registry to 1,146 filings without changing any
  existing URL. Opened official VakıfBank, Türkiye Kalkınma, Ziraat Dinamik and
  Takasbank source probes; the latter has a readable 78-page original and a
  damaged text layer. Added a separate optional missing-source acquisition step
  within the corpus workflow. It preserves original transport and PDF bytes,
  rejects ambiguous archive selection or conflicting cover identity, verifies
  conditional source creation, and leaves existing acquisitions unchanged.
  Eighteen acquisition tests cover failures, races, scope and no-write replay.
  Cloud publication and acquisition of the 29 gaps remain pending.

- 2026-09-06: full quality run 34047832643 completed. All four group reports
  independently match the original 1,117 acquired bindings and source hashes;
  both PDF copies and retained artifacts verify for all 116,503 pages. Leading
  source text supports 1,050 identities; 59 unresolved and eight ambiguous
  cases remain for review. These checks certify stored bytes and named source
  claims, not every printed character or table meaning.

- 2026-09-06: missing-source publishing sample 34049005525 passes. Takasbank and
  VakıfBank 2022Q1 newly acquired PDFs match separate official downloads; the
  existing VakıfBank solo acquisition retains its earlier hash/version. R2
  transport/manifest/PDF/evidence/structure bytes independently verify across
  292 selected pages. There are now 1,119 acquired filings and 27 registered
  gaps. Added an acquisition-before-capture job dependency so parallel groups
  cannot freeze different acquisition inventories while sources are arriving.

- 2026-09-06: expanded acquisition in 34049704430 names all 1,146 registered
  outcomes: 1,119 unchanged, 25 newly acquired, two held for review. Independent
  inspection explains both: Ziraat Dinamik has a Java-wrapped PDF inside a ZIP;
  Anadolubank has a 96-page report and a one-page signed responsibility statement.
  Added nested-wrapper provenance and exact filename/hash-bound reviewed archive
  selection. Unselected PDF members stay named/hashed with text capture pending.
  Publishing repairs remain queued work after the ongoing full native run.
- 2026-09-06: repaired artificial spaces at font-span boundaries in source
  identity review and added Ziraat's source-corroborated legal name. Reviewed
  Emlak, Vakıf Katılım and Ziraat covers now resolve; a contradictory Halkbank
  cover stays ambiguous. The old heuristic missed all four inspected damaged-text
  Takasbank pages. Nontext control-character signals now flag each, and automatic
  recovery selection includes these signals while preserving native observations.
  Tests cover controls, ordinary Turkish text, split font spans, explicit/automatic
  receipt scopes and a real PDF whose text layer contains control glyphs.

- Still required for source provenance: older `source_url` metadata is a registry
  lookup, not a fresh HTTP byte comparison. Stored-copy byte checks and opening
  identity claims do not establish that an older acquisition matches the current
  official published revision. Add an independent origin comparison and retain
  named mismatches/unavailable sources without overwriting historical originals.

- 2026-09-06: cloud source-identity repair sample supports all four selected
  covers; exact committed review-code hashes checked. Independently verified
  Takasbank's official PDF bytes, rendered pixels and raw recovery observations
  for pages 1/13. Its borderless balance sheet had no recovery table. Added a
  conservative amount-alignment fallback, preserving physical continuation rows
  and empty cells; 16 independently transcribed source amount regions pass.
  Added complete text-region comparisons and physical OCR blocks with table
  membership. Three of four source passages match; `İstanbul` versus OCR
  `Istanbul` stays explicitly different in the quality record and admin view.
  Recognition, whole-table structure and semantic coverage remain unapproved.

- 2026-09-06: independently reviewed all eight automatically ambiguous source
  identities against rendered originals. Five are contextual bank/prior-period
  mentions; three English covers contain genuine consolidated/unconsolidated
  contradictions while their auditor introductions identify consolidated reports.
  Added revision-bound contextual reviews with exact source span/text/geometry
  witnesses. They supplement automatic findings and cannot approve content or
  silently clear source contradictions. Local checks of all eight originals pass;
  cloud probes at `77c37cea` independently verify all eight reviews in 12 filings.
  Five covers now have automatic support after source font-span joins; three
  genuine cover contradictions remain explicit.

- 2026-09-06: completed the original raw-recovery fleet: 1,117 source bindings,
  184 filings with 741 selected pages and 289,865 OCR words; 933 filings with no
  image/outline pages flagged. Independent reconciliation matches every source
  hash against the verified native run. This does not establish selector recall.
  Published six FIBA/ISCTR/Takasbank sample pages; independently rechecked R2
  original/artifact bytes, pixels, observations and 75 selected table-cell checks.
  All three unchanged filing replays use receipts; 25 object versions are identical.
- 2026-09-06: introduced a separate source-bound embedded-font reading for empty
  Unicode maps. Unique source font/glyph/origin/fallback bindings retain raw text
  and alternatives; partial maps, duplicate bindings and ambiguous non-whitespace
  characters abstain. Source probes recover 60/1,571 Takasbank characters on
  pages 1/13 and pass all four independently transcribed complete text regions.
  The dotted İstanbul source reading is recovered while the OCR discrepancy stays
  visible. Tests cover real embedded fonts, subset-name truncation, four rotations,
  valid/partial/absent maps, ambiguous positions and mutated packets. Integrated
  derived-cache/receipt identity and admin alternatives; cloud probe pending.

- 2026-09-06: cloud font probe `34055586894` exactly matches source bytes,
  source pixels, retained OCR, the independently rebuilt font view and all four
  full text regions. Raw OCR is reused. Published packets at `34055751819` match
  that verified probe; CI/deploy at `0b43b2ef` pass.
- 2026-09-06: configured recovery after completed source capture. It downloads
  that same-repository run's reports, retains a manifest of successfully published
  filing/PDF hashes and names read-only/failed exclusions. Quality-only reports
  trigger no recovery. Workers process only the manifest, retain missing outcomes
  and reject changed PDFs before recovery or receipt reuse. Four or fewer filings
  stay one job; larger scopes use four stable groups. Tests cover scope omission,
  duplicate/conflicting bindings, changed source receipts and missing acquisitions.
  Automatic cloud execution remains pending; no D1 or analytical-lane writes.

- 2026-09-06: a live quality-only capture and automatic follow-up pass with an
  empty retained scope and recovery skipped; manual recovery still works. The
  positive publishing follow-up awaits the larger capture. Added independent
  official-origin comparison with exact downloaded/acquired byte checks, retained
  transport and PDF revisions, separate indexes, source identity findings and
  named unavailable/different outcomes. Matching wrong-period bytes still fail.
  Mutation, publication readback, grouped-scope and CLI tests pass; cloud source
  comparison pending. No acquired PDF or analytical row is replaced.

- 2026-09-06: independently verified four cloud origin probes at `2d0bbf2`: exact
  transport/PDF bytes, selected archive members, wrapper provenance, first-three
  page spans, committed implementation hashes and current acquisition bytes or
  absence. FIBA/Takasbank match; the two queued acquisition repairs stay missing.
  FIBA published transport/receipt/index matches the probe; the original object
  version is unchanged. Dispatched the full registered origin review. Added an
  authenticated admin comparison reader with receipt/artifact checksums, immutable
  filing/source bindings, explicit differences and links to retained source bytes.
  Python-produced wire tests exercise corrupt bytes, reminted wrong bindings,
  nonexistent comparisons and anonymous access; 719 web tests pass.

- 2026-09-06: the origin admin is deployed and independently checked for FIBA
  exact-byte agreement and Anadolubank's missing acquisition/pending signed PDF.
  Added separate archive-member document capture: verify every member against
  the retained transport, retain native source/structure in an isolated index,
  and recover every page with pinned OCR, physical text blocks and source-pixel
  table candidates. Tests reject dropped/invented members, altered primary or
  attachment bytes, changed source relationships and cross-filing index access.
  Primary index bytes survive; repeated native capture performs no new writes.
  Visually transcribed two headings and both complete responsibility statements
  from Anadolubank's one-page signed source for independent cloud comparisons.
  Cloud capture and related-document admin text access remain pending.

- 2026-09-06: completed all 1,146 registered native captures. Independently
  reconciled 1,144 expanded outcomes plus the two repaired source-bound archive
  acquisitions, totaling 119,772 pages. Every old source hash remains unchanged.
  Both repaired originals and all 175 retained pages match their official sources.
  Automatic recovery's live retained scope matches exactly 1,144 successful PDF
  hashes, with the two missing rows explicitly excluded and all four workers
  started; repair follow-ups follow separately. Full quality/origin reviews run.
- 2026-09-06: independently verified and published the separate one-page signed
  declaration: source/archive bytes, native image, OCR source pixels, 155 raw words
  and geometry, candidate layout and committed engine hashes. Two of four source
  regions match, while A.Ş./A.S. and ile/ve discrepancies remain explicit. Added
  an origin/member-bound admin reader and separate page/recovery access; unknown
  members, wrong archive/report bindings and corrupt receipts are rejected.
  Publication replay reuses raw OCR and leaves eight object versions, including
  the primary filing index, unchanged. The complete web suite passes 732 tests;
  live attachment-reader deployment checks remain pending.

- 2026-09-07: tightened the attachment reader after an independent mutation
  review: a valid parent-report revision substituted under an otherwise correct
  attachment relationship must fail. The reader now binds its PDF hash directly
  to the origin's raw member hash. Wrapped attachments need an explicit wrapper
  byte binding before admin access; the signed declaration is an ordinary PDF.

- 2026-09-07: all four current quality groups pass for 1,146 sources and 119,772
  pages; independently reconciled every PDF hash, copy and retained artifact.
  Native identities: 1,140 supported, three unresolved and three ambiguous.
  Visually inspected both scanned Kalkınma annual covers and the damaged-font
  Takasbank cover. Added three PDF/page/region-bound visual transcription reviews,
  separately labelled from native evidence; mutation checks reject changed pages,
  images, transcriptions, invalid regions and invented native references. The
  transcription itself remains a reviewer assertion. Cloud execution pending.
- 2026-09-07: live admin attachment view independently shows the 96-page primary
  report, separate one-page declaration, source links, eight OCR blocks and both
  A.S./A.Ş. and ve/ile disagreements. CI/deploy at `979b169` and 733 web tests pass.

- 2026-09-07: all three visual identity cloud reviews at `cbe9d3e` pass and match
  independently inspected original witnesses, registry and review engine hashes.
  CI `34061081094` and deploy `34061185039` pass; automatic unresolved findings
  remain explicit. No transcription claim is presented as native text evidence.
- 2026-09-07: visually reviewed QNB original pages 47–48 as a multi-page table
  case. The debt-instrument columns 1/2 continue under an explicit title despite
  changed widths. Added source-bound heading/header context, unambiguous grid
  spans and continuation candidates, preserving all cells and physical fragments.
  Tests reject swapped identifiers, missing markers/source words, intervening or
  competing tables, shifted/overlapping grid cells and changed context packets.
  The admin supports merged slots and prior-fragment navigation. A new independent
  continuation annotation fails on the old structure and passes on the new view;
  cloud capture/publication remain pending.

- 2026-09-07: QNB table-context cloud probe `34061799667` passes. Independent
  checks verify original bytes, all 108 retained pages, fresh source pages 47–48,
  five source annotations, context derived from the earlier retained structure
  and exact committed structure-engine hashes. Publication/live context pending.
- 2026-09-07: added read-only rendered-source review packs to the existing capture
  workflow. Each selected page has a named outcome and PDF/PNG/pixel/geometry
  binding. Whole-document rendering is limited to one filing in Actions; local
  probes remain at most four pages. No OCR or inferred text is used for the
  rendered originals. Tests cover rotation, exact pixels, changed source bytes,
  invalid/omitted selections and a middle-page failure followed by successful
  later rendering. Cloud whole-document preparation pending.

- 2026-09-07: QNB publication `34062058387` matches the independently verified
  source/structure probe; full-byte replay leaves all five object versions
  unchanged. Live table-context inspection awaits renewal of the expired admin
  session. No authentication bypass or serving-data change was introduced.
- 2026-09-07: TOMK 2023Q3 whole-source review pack `34062146313` passes source,
  engine and all 51 PNG byte checks, four fresh original-pixel probes and full
  native/structure retention checks. Visually reviewed pages 1–12. Found footer
  order, separate bullet markers and fragmented signatory roles; numerical
  statement rows are retained but their ruled header/body fragments need logical
  association. Added a complete physical-table source benchmark for all 40 slots
  in the shareholder table, both merged date headings and the unit statement.
  Local mutation checks reject dropped/duplicated slots/rows, swapped periods,
  identical values with the wrong source, changed units and unaccounted source
  words. It approves neither the whole report nor financial interpretation.
- 2026-09-07: fresh-origin group 1 completed with five byte-different PDFs,
  33 unavailable/non-PDF downloads and one pre-repair Anadolubank observation.
  Independently opened Albaraka/Eximbank paired covers; acquired copies explicitly
  identify English translations, while current BDDK copies are Turkish. Preserve
  both editions and investigate remaining differences. Capture-time registered
  locators are not retroactive download provenance. Full origin/recovery fleets
  and later Anadolubank comparison remain outstanding.

- 2026-09-07: independently reconciled all 1,146 origin outcomes: 973 byte matches,
  11 differences, 161 unavailable/non-PDF sources and one historical absence.
  The repaired Anadolu consolidated follow-up matches and preserves history.
  Identified ICBC certificate failures, Ziraat Katılım challenge HTML, Halkbank
  DOCX-only transport and Anadolu solo's separate signed PDF. The latter's
  86-page primary member matches acquired bytes and now has an exact selection.
- 2026-09-07: completed the visual inventory pass across all 51 TOMK pages. This
  is not full cell/paragraph certification. Found the missed prior FX table and
  conflicting source capital/liquidity values, retained in the internal review.
  The complete40slot shareholder case is published and independently verified.
  Added separate source lines inside tall ruled body cells, preserving original
  columns/headers, literal note references and EPS unit wording. Full source-word
  accounting and corruption tests pass; three independently read profit/loss
  lines are added to the cloud benchmark. Admin toggle and cloud validation pending.

- 2026-09-07: source-line cloud probe `34064705881` independently verifies all 51
  retained native pages and rebuilt line views, with four source cases passing.
  Repaired page 30's missed prior FX table by matching segmented column borders;
  the complete six-slot case preserves USD/EURO headings and literal TL units.
  Full Python suite and targeted mutation checks pass; cloud publication pending.
- 2026-09-07: Anadolu solo origin follow-up `34064708288` matches acquired bytes;
  receipt, archive and exact committed engine independently verified. Signed
  attachment probe `34064863416` retains all 150 OCR words/positions and original
  pixels. Five independently transcribed full regions expose two disagreements,
  including a changed regulatory reference. Retain both readings; publication pending.

- 2026-09-07: FX/source-line probe `34065765217` passes all five cases; publication
  and replay `34065945594` match independently checked bytes and leave all four
  object versions unchanged. Anadolu solo attachment publication/replay
  `34065766786` preserves all eight versions and both source wording disagreements.
- 2026-09-07: added a separate whitespace-partition reading view. TOMK pages 2
  and 4 now order the letter before its footer, link seven list markers and retain
  six signatory columns with their split role text. Original narrative/span
  inventories remain unchanged; ambiguous geometry is explicit. Two page-layout
  source cases and corruption tests pass. Admin reference-integrity fallback and
  all 738 web tests pass; cloud validation and authenticated display pending.

- 2026-09-07: reading-layout cloud probe `34066499398` independently passes all
  seven cases; all 51 native pages and prior structure fields are unchanged.
  New views were rebuilt from retained source references. 44 other pages retain
  unresolved layout areas; the selected prose cases do not certify them.
- 2026-09-07: traced ICBC's source-download failures to the already-vendored
  GlobalSign intermediate. Verified the live hostname/chain normally and matched
  2026Q2 solo bytes to acquisition. Exact-host downloader support and failure
  tests pass; cloud comparison across all 36 registered ICBC filings pending.

- 2026-09-07: ICBC follow-up `34066751096` matches all 36 acquired PDFs and
  supports their opening-page identities. Every receipt/current index and old
  acquisition hash independently reconciles. Fresh byte agreement now covers
  1,011 filings; prior unavailable observations remain in history.
- 2026-09-07: TOMK reading-view publication/replay `34066695808` preserves the
  seven-case probe exactly and leaves all four checked object versions unchanged.
- 2026-09-07: inventoried 14 Takasbank activity-report attachments. Independently
  checked two complete 12-page native/structure artifacts, all OCR word positions,
  four original-page pixel samples and both covers. The June 2022 archive contains
  a March 2022 report; June 2026's member matches its quarter. Added immutable
  related-identity receipts and admin source-period conflict display, preserving
  archive context separately. Python and 745 web tests pass; cloud rollout pending.

- 2026-09-07: added three source-bound open content notes from the TOMK whole-page
  visual inventory (seven exact passages). Source and private-reader checks reject
  substituted wording, occurrences, pages, geometry and unsupported approval.
  Benchmark receipts retain the notes separately from structure; admin and private
  analyst JSON expose original passages. No figure is corrected by these notes.
  Cloud receipt publication and deployed UI checks remain pending.

- 2026-09-07: all registered recovery selection outcomes reconciled: 1,144 in
  `34058889360` plus explicit ZIRAATD/Anadolu checks `34069911174` / `34069912704`.
  Total 1,146 filings; 1,153 selected pages in 210 filings; 441,179 OCR words;
  936 filings not flagged. Two earlier follow-up IDs held empty scope reports,
  not repair outcomes; the explicit checks correct that gap. This is selection
  and retention coverage, not recognition or whole-document correctness.
- 2026-09-07: all 14 Takasbank archive associations published and independently
  reconciled to original/native/structure/identity bytes; 13 distinct PDFs, 168
  associated pages and 37,216 OCR words. The 2022Q2 archive/source-period conflict
  remains. Replay preserves 31 object versions. Both Anadolu declaration identity
  receipts are backfilled without restamping prior artifacts; native image-only
  identity remains unresolved. All 16 currently identified related associations
  are captured, with known recognition disagreements retained.
- 2026-09-07: TOMK open content notes pass cloud probe `34069764376`; all 51 native
  and structured pages remain byte-identical. Publication/replay `34069966411`
  passes independent receipt checks and preserves all four object versions.
  Deployed admin review awaits the user renewing the expired session.
- 2026-09-07: four bounded BDDK alternate-origin probes match literal official
  listing rows and independently inspected covers. AKTIF/VAKBN/ZIRAATK 2026Q2
  solo match acquisitions; ATBANK differs despite identical rendered covers.
  Full alternate-revision comparison and source-bound publication remain open.

- 2026-09-07: implemented a separate BDDK listing witness for alternate-origin
  comparisons. The current search form and 1,142 exact registered filing rows
  were independently observed; four real rows form the regression fixture.
  Publication binds literal bank name, period, basis, URL, listing response and
  downloaded bytes, retaining prior observations. Python checks, 771 web tests,
  lint and type checks pass. Cloud verification remains pending.

- 2026-09-07: read-only BDDK probe `34071549110` has the expected three exact
  matches and ATBANK revision difference. All original/transport/listing bytes,
  exact Git implementation hashes and leading-page identity observations pass
  independent comparison with the four source probes. The lean CI environment
  exposed an unnecessary HTML-library import; the built-in parser replacement
  matches all 1,142 registered listing rows and requires no CI dependency change.


- 2026-09-07: BDDK publication `34072061577` independently verifies 21 unique
  retained objects, immutable receipt histories and unchanged acquisition/main
  native bindings for all four source probes. Only VAKBN/ZIRAATK add new filing
  agreements; ATBANK retains both a bank-site match and different regulator PDF.
  The broader 72-filing VAKBN/ZIRAATK comparison `34072441306` reports 67 matches,
  three different PDFs and two non-PDF responses; independent readback is in progress.
- 2026-09-07: implemented capture of an exact observed different PDF into a
  separate edition index, with native/structure reuse and named selected recovery
  outcomes. Source-bound history, transport, archive/PDF/listing bytes and local
  replacement rejection have regression coverage. Admin readers retain all origin
  observations, historical attachment access and separate edition access. Python
  focused tests and all 788 web tests pass; cloud capture/readback and live UI
  verification remain pending. Acquired filing indexes are never switched.


- 2026-09-07: all 72 regulator-origin outcomes from `34072441306` independently
  reconcile across 359 stored objects and unchanged acquisition/main native
  bindings. Published observation rollup: 1,069 filings with any byte agreement,
  15 with a different PDF, one overlapping filing and 63 with neither outcome.
- 2026-09-07: independently unpacked both ZIRAATK 2025Q3 downloads. Their nested
  ZIPs contain exact acquired PDFs; the old parser's non-PDF status was a wrapper
  failure. Added narrow two-level ZIP handling with full member witnesses,
  spanning-marker retention and rejection of ambiguous/truncated containers.
  Both real-source byte checks and targeted regression tests pass; cloud follow-up pending.
- 2026-09-07: edition probe `34073988169` independently verifies ATBANK's complete
  88-page native/structure artifact, exact committed engines and four fresh page
  observations. Source original matches the independent regulator download.
  CI/deployment at `53e18f8` pass; publication `34074261461` is running.


- 2026-09-07: nested-wrapper follow-up `34074341718` matches both ZIRAATK PDFs.
  Independent comparison checks all 11 retained objects against the manually
  unpacked source chain, exact Git engines and unchanged acquisition/main native
  bindings. Published origin coverage is now 1,071 agreements, 15 different PDFs
  (one overlap) and 61 filings with neither outcome.
- 2026-09-07: ATBANK edition publication/replay `34074261461` matches the complete
  independently checked probe and leaves all seven object versions unchanged.
  All remaining 14 observed editions have verified source-byte/transport bindings
  and individual Actions captures in progress; no main filing is switched.
- 2026-09-07: added exact registered-filing scopes to origin follow-ups, with
  duplicate/unknown/ambiguous/truncation rejection before source access. Twenty
  command tests pass. The 61 remaining source comparisons will use this explicit
  scope instead of repeating complete bank histories.


- 2026-09-07: independently inspected TOMK's page-16 cash-flow source. The native
  grid merges current/prior amount columns across one short missing divider.
  A separate header/rule-supported projection now preserves all 49 source lines,
  including unassociated dashes, without changing physical cells. Three exact
  source-row annotations, conservation and ambiguity/mutation checks pass. Only
  this page's line view changes among all 51 retained TOMK pages. Full Python,
  788 web tests, lint and type checks pass; cloud publication remains pending.

- 2026-09-07: all 61 exact source follow-ups in `34074745326` independently
  reconcile across 288 objects: 14 matches, 30 different PDFs and 17 unresolved
  sources. Current origin coverage is 1,085 agreements, 45 different-PDF filings,
  one overlap and 17 with neither outcome. The first 15 editions independently
  reconcile across 1,624 pages; the next 30 reconcile across 2,811 pages. Combined:
  4,435 pages, 11,193,374 native characters, 83,154 physical text blocks, 11,073
  table candidates, 46 selected recovery pages and 18,862 OCR words. Original
  acquisition and main-index versions remain unchanged. Artifact accounting and
  recovery-byte checks do not approve full semantic content.
- 2026-09-07: independently verified cash-flow probe `34075540385` against all
  51 native pages and prior structure: only page 16's line view changes. All 13
  source cases pass. Publication/replay `34075859884` matches the probe and
  preserves all six observed object versions on replay, including the prior
  structure artifact and acquisition. Three open source-content notes remain.
- 2026-09-07: independently inventoried 14 two-PDF regulator archives. Eight
  Anadolubank primary members exactly match acquired PDFs. Visually checked all
  six TSKB financial-report covers against their bank, period and basis; each is
  a different PDF from the acquisition. Added exact URL/transport/member-bound
  selections, acquired-byte or literal-cover witnesses, and mutation tests.
  Neither filename guesses nor another URL's override select the report.
  Fourteen additional responsibility-statement attachments need separate capture;
  the 14 selected origin observations await cloud verification/publication.
- 2026-09-07: source-selection publication `34076924747` independently reconciles
  all 14 filings and 71 stored objects: eight matches, six different PDFs, all
  source identities supported, all original/main object versions unchanged.
  Current published origin coverage is 1,093 agreements, 51 different-PDF filings,
  one overlap and three with neither outcome. Six TSKB editions and 14 additional
  signed attachments have independently verified source bindings and are being
  captured separately in Actions.
- 2026-09-07: independent probes of the official bank listings and linked PDFs
  resolve the last three source paths locally. AKTIF 2025Q3 solo exactly matches
  the acquisition. EXIM 2025Q3 solo and HALKB 2026Q2 solo have different PDF bytes;
  their rendered covers match bank, period and basis. Corrected only those two
  registered locators and retained their previous URLs/listing review context.
  The denominator stays 1,146; acquired PDFs and main indexes are untouched.
  Cloud source-origin proof and the two new edition captures remain pending.

- 2026-09-07: final origin publication `34077439751` independently verifies all
  three remaining sources and 15 retained objects. All 1,146 registered filings
  now have an official PDF comparison: 1,094 have a byte agreement, 53 an observed
  different PDF, one overlaps and zero have neither. All 53 observed editions
  independently reconcile: 5,378 pages, 13,623,066 native characters, 102,888
  blocks, 13,024 table candidates, 47 selected recovery pages and 19,190 OCR words.
  No main filing or acquired PDF is replaced.
- 2026-09-07: all 14 new archive declarations pass independent byte/source checks:
  14 pages, 3,689 native characters and 2,026 OCR words. Four native identities
  are supported and ten remain unresolved. The observed attachment count is now
  30 associations. Recovery artifact checks do not certify recognition accuracy.
- 2026-09-07: TOMK page 15's vertically spanning label cell now exposes one group
  of 19 source lines across 17 columns, keeping the closing balance once and all
  original cells intact. Four independent source cases, whole-word conservation,
  ambiguity mutations and admin rendering checks pass locally. Only this page's
  line view changes across the retained 51-page report. Cloud verification and
  publication remain pending; table meanings and header-note links are unverified.

- 2026-09-07: equity probe `34078794091` independently verifies all 51 unchanged
  native pages, exact committed engine and 17 source cases. Publication/replay
  `34078940748` matches the probe and leaves all seven observed object versions
  unchanged. CI/deploy at `b9c89ad` pass; authenticated UI review remains pending.
- 2026-09-07: independently transcribed the complete page-39 deferred-tax table.
  Added a separate alternative from repeated segmented rules and complete native
  header blocks. All 40 slots, 69 source word occurrences, both grouped headings,
  blank net-row positions and printed units pass the full-table benchmark; the
  prior fragments fail it. Only page 39 gains this alternative across TOMK's 51
  pages. Whole-table omission, swapped repeated values, invented zeroes, shifted
  columns, truncated headings and changed units are rejected. Full Python, 791
  web tests, lint/type and mobile checks pass. Cloud verification remains pending.

- 2026-09-07: deferred-tax probe `34079635094` independently verifies all 51
  original/native pages, unchanged earlier tables and prose, committed engine
  and 18 source cases. Publication/replay `34079793061` matches the probe and
  preserves all eight observed object versions. CI/deploy at `e8fafbd` pass.
- 2026-09-07: independently matched all six equity-column numbers to the six
  complete source explanations on page 15, retaining the wrapped final paragraph.
  Added source-linked table-note candidates and an exact occurrence/paragraph
  benchmark. Missing, ambiguous, duplicated or shifted associations remain
  unlinked or fail validation. Only page 15 gains the relationship across the
  retained 51 pages. Admin rendering preserves full text and column references;
  cloud verification/publication and authenticated display remain pending.

- 2026-09-07: note-link probe `34080486986` independently verifies all 51 native
  pages, unchanged prior structure, six complete source explanations and 19
  cases. Publication/replay `34080668719` matches the probe and leaves all nine
  checked object versions unchanged. CI/deploy at `22cc62b` pass.
- 2026-09-07: independently transcribed the four page-38 asset tables and checked
  all 121 slots, merged period headings, units and the source investment-fund
  qualification. The retained ruled candidates already match; no extractor
  change is needed. Added four full-table cases and omission, repeated-occurrence,
  invented-zero and unit mutations. The benchmark now has 23 cases; cloud
  verification of those additional cases remains pending.

- 2026-09-07: asset-table probe `34081259589` independently verifies 23 source
  cases with byte-identical original, native and complete structure. Publication
  and replay `34081464245` change only the review receipt and preserve all nine
  checked object versions on replay. CI/deploy at `43ca082` pass.
- 2026-09-07: independently reviewed TOMK's contents, inserted statement divider,
  body banners and footer numbering. The old section starts misplaced four
  boundaries and clipped wrapped titles. Added a separate source-bound navigation
  view with all seven correct section ranges, 57 complete contents entries and
  45 footer observations. Five source contents disagreements remain visible;
  repeated divider titles, ambiguous folios and missing banners are not guessed.
  A 24th source case covers full navigation and mutation tests check omissions,
  truncation, wrong occurrences, erased conflicts and paragraph section context.
  All prior tables and literal prose fields remain unchanged in the local
  projection. Cloud rebuild, publication and authenticated display remain pending.

- 2026-09-07: navigation probe `34087256653` independently reproduces the local
  source review and all 24 cases, preserving 51 native pages and every prior table
  and literal prose field. Publication/replay `34087462722` preserves history and
  all ten checked object versions on replay. CI/deploy at `10e5cae` pass. The admin
  session still requests sign-in after refresh; authenticated display is pending.

- 2026-09-07: independently reviewed seven body starts and selected contents in
  GARAN 2022Q4 consolidated and ALBRK 2026Q1 consolidated. Added numbered-heading
  and CHAPTER support, preserving wrapped titles and the separate Page-No column.
  The selected benchmarks retain 69/61 contents entries, 11 complete selected
  titles and 14 source footer bindings. Missing, moved, dotted, repeated or
  incomplete evidence abstains; GARAN solo's differing source titles remain
  unresolved. Fresh checks on eight original pages preserve every older native
  field; five added evidence fields are recorded separately. The admin displays
  literal contents section headings as well as body headings. Full Python and
  796 web tests pass locally. Cloud verification/publication remain pending;
  no whole-report semantic verification is claimed.

- 2026-09-07: cross-bank cloud probes at `544ee1e` reproduce the selected source
  navigation and all 282 native pages; previous table fields remain intact.
  Independent comparison then caught ALBRK prose fragmented by speculative table
  headers. Publication is held. Excluding those alternatives from narrative
  segmentation restores the complete shareholder paragraph; aligned Roman
  headings prevent III from becoming IV's parent through minor font differences.
  A source paragraph case and interference/sibling tests cover the finding.
  Pure projections preserve all tables and pass 28 cases across TOMK, GARAN and
  ALBRK; fresh cloud verification remains pending.

- 2026-09-07: corrected probes `34090776777` (TOMK), `34090773185` (GARAN) and
  `34090769895` (ALBRK) exactly match independent local projections, 333 retained
  native pages and 28 selected source cases. Twelve fresh page/pixel checks pass;
  prior table fields, text blocks and ordered prose spans are preserved.
  Publications/replays `34091220078`, `34091216355`, `34091212337` retain history
  and all 27 checked object versions on repeat runs. CI/deploy at `36fde33` pass.
  Authenticated admin display remains pending. Original TOMK pages 26–29 have
  been inspected for the next full-grid/continuation review; no link is approved
  merely from adjacency or a repeated period heading.

- 2026-09-07: additional probes `34092256559`, `34092260814`, `34092264952`,
  `34092268623` independently verify the remaining 17 registered source cases.
  All seven annotated reports now pass 45 selected cases across 692 native pages.
  Original/native R2 bytes and fresh source-page inventories/pixels match.
  Akbank's replacement-text render comparison uses a separate fresh document
  handle; extracting before rendering changes the in-memory image cache without
  changing PDF bytes. Some navigation remains unresolved, and no whole filing
  is semantically certified. The next step is a registered-corpus candidate
  refresh retaining history and every unverified state, with no D1 publication.

- 2026-09-07: registered-corpus candidate refresh `34092888903` is running in
  four Actions groups at observed head `fe7b669` (same code as the later docs-only
  commit `f99e4ce`). Scope is all registered filings, both filing bases, no new
  acquisition and no D1 writes. Completion and independent reconciliation are
  pending; source and semantic completeness are not inferred from dispatch.

- 2026-09-07: changed execution priority to shared, measured content defects.
  The retained registered quality review names line/source mismatches in 347
  reports and table-cell/source mismatches in 213 reports; these are baseline
  counts, not current post-repair results. Reproduced a coordinate-system defect
  in rotated ruled-table detection and a symmetric baseline window that includes
  preceding-line words. Fixed both. Original Garanti page 19 now passes a complete
  OCI table case: unit, period headers, merged slots and every one of 16 source
  rows with both value columns. The old artifact fails that same case. Regression
  tests exercise 0/90/180/270-degree PDF encodings and closely spaced baselines.
  Cancelled old-engine fleet refresh 34092888903; partial outputs remain retained.
  New capture reports/indexes carry named per-page structural diagnostics for
  corpus-wide repair ranking. Corrected cloud publication and fleet reconciliation
  remain pending; no complete-report approval is inferred from this table check.
