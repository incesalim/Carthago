/**
 * Task 3.1 — the memo prompt. The model receives DATA, not tables and not SQL:
 * every figure it may use is printed in the data block below, and the guard
 * later verifies the memo against exactly this rendering — what the model saw
 * is what the guard allows, one source of truth.
 *
 * The structure encodes the feasibility test's finding: the analyst gap is
 * asking the SECOND question of data already held. The decompositions that
 * answer it (coverage mix-vs-erosion, capital trajectory, FP history, core
 * margin) are precomputed upstream and REQUIRED reading in the instructions —
 * the model contextualizes derivations, it never performs them.
 */
import type { MetricChange } from "./comparator";
import type { PeerContext } from "./peers";
import type { AnalystSections } from "./sections";

export interface AnalystInput {
  sections: AnalystSections;
  peers: PeerContext;
  comparatives: MetricChange[];
}

const fmt = (v: number | string | null | undefined, suffix = ""): string =>
  v == null ? "n/a" : `${v}${suffix}`;

export interface StoryGate {
  story: string;
  live: boolean;
  reason: string;
}

/**
 * The deterministic editorial layer. The untuned GARAN run led with a
 * capital-composition story on a bank whose CAR−CET1 gap sits AT the class
 * median — the calibration banks' narrative transferred to a bank that does
 * not have it — while the genuinely strong finding (negative REAL returns)
 * went unused. Same cure as every other calibration failure: compute the
 * judgment and hand it over. A gate says which stories are LIVE for THIS
 * bank, with the numeric reason; the memo may only lead with a live one.
 * (insights.ts's rule, one level up: tone moves only when a threshold clears.)
 */
export function storyGates(input: AnalystInput): StoryGate[] {
  const { sections: s, peers } = input;
  const gates: StoryGate[] = [];
  const signals = s.comparability.signals_this_period;
  const has = (type: string, sub?: string) =>
    signals.some((x) => x.signal_type === type && (!sub || x.payload.includes(sub)));

  // Real terms — the story screens structurally miss in a 30%+ CPI regime.
  const roeReal = s.earnings.roe_real_pct;
  if (roeReal != null) {
    gates.push({
      story: "real_terms",
      live: roeReal < 0,
      reason:
        `ROE ${fmt(s.earnings.roe_ttm_pct)}% nominal = ${roeReal}% REAL against ` +
        `${fmt(s.macro.cpi_yoy_pct)}% CPI` +
        (s.earnings.assets_yoy_real_pct != null
          ? `; asset growth ${fmt(s.earnings.assets_yoy_pct)}% nominal = ${s.earnings.assets_yoy_real_pct}% real`
          : "") +
        (roeReal < 0
          ? " — the bank is SHRINKING its real equity; that outranks any nominal print"
          : " — real capital is being built"),
    });
  }

  // Capital composition — live on the detector signal or the level itself.
  const noncore = s.capital.noncore_share_of_car;
  const gap = s.capital.car_minus_cet1_pp;
  const gapMed = peers.medians.car_minus_cet1_pp;
  const capLive = has("divergence", "capital_composition") || (noncore != null && noncore >= 0.4);
  gates.push({
    story: "capital_composition",
    live: capLive,
    reason: capLive
      ? `non-core is ${fmt(noncore)} of CAR (gap ${fmt(gap)}pp vs class median ${fmt(gapMed)}pp)` +
        (has("divergence", "capital_composition") ? "; detector signal fired" : "")
      : `CAR−CET1 gap ${fmt(gap)}pp vs class median ${fmt(gapMed)}pp — unremarkable composition; ` +
        `do NOT manufacture a composition story (CET1 < CAR is true of every bank)`,
  });

  // NPL-vs-coverage concealment — the detector's call, with a data-level
  // fallback mirroring its thresholds (drop ≥10pp over the window while NPL
  // is flat/falling) so the gate holds even where analyst_signals is absent
  // (pre-freeze-lift D1, a local run without staging).
  const d = s.asset_quality.coverage_decomposition;
  const nplYoY = input.comparatives.find((c) => c.metric === "npl_ratio_pct")?.yoy.delta;
  const covFallback = d != null && d.total_fall_pp >= 10 && nplYoY != null && nplYoY <= 0.15;
  const covLive = has("divergence", "npl_coverage") || covFallback;
  gates.push({
    story: "npl_coverage_divergence",
    live: covLive,
    reason: covLive
      ? `NPL flat/falling while coverage fell materially` +
        (d ? ` (${d.total_fall_pp}pp over 4 quarters: ${d.mix_pp}pp mix, ${d.erosion_pp}pp erosion)` : "") +
        (has("divergence", "npl_coverage") ? "; detector signal fired" : "")
      : d
        ? `coverage moved ${d.total_fall_pp}pp over 4 quarters (mix ${d.mix_pp}pp, erosion ${d.erosion_pp}pp) — below the divergence threshold or NPL rising too; no concealment story`
        : "no divergence signal; no concealment story",
  });

  // Free provision — earnings-quality adjustment only where one exists.
  const fpEver = s.earnings.free_provision.history.some(
    (h) => h.release_pct_of_income != null && Math.abs(h.release_pct_of_income) >= 20,
  );
  const fpLive =
    fpEver ||
    s.governance.is_free_provision_qualified === true ||
    (s.earnings.free_provision.release_pct_of_ytd_income != null &&
      Math.abs(s.earnings.free_provision.release_pct_of_ytd_income) >= 20);
  gates.push({
    story: "free_provision",
    live: fpLive,
    reason: fpLive
      ? "a discretionary-reserve release has moved printed profit (see FP history) and/or the opinion is qualified over it — the printed series needs re-basing"
      : "no free provision held or disclosed — earnings carry no discretionary-reserve adjustment; say so in one sentence at most",
  });

  // Adverse peer deviations — where THIS bank leaves its class.
  const dev: string[] = [];
  const npl = s.asset_quality.npl_ratio_pct;
  if (npl != null && peers.medians.npl_ratio_pct != null && npl - peers.medians.npl_ratio_pct >= 1) {
    dev.push(`NPL ${npl}% vs class median ${peers.medians.npl_ratio_pct}%`);
  }
  const s2 = s.asset_quality.stage2_ratio_pct;
  if (s2 != null && peers.medians.stage2_ratio_pct != null && s2 - peers.medians.stage2_ratio_pct >= 2) {
    dev.push(`Stage-2 ${s2}% vs median ${peers.medians.stage2_ratio_pct}%`);
  }
  const cov = s.asset_quality.stage3_coverage_pct;
  if (cov != null && peers.medians.stage3_coverage_pct != null && peers.medians.stage3_coverage_pct - cov >= 5) {
    dev.push(`Stage-3 coverage ${cov}% vs median ${peers.medians.stage3_coverage_pct}%`);
  }
  const roe = s.earnings.roe_ttm_pct;
  if (roe != null && peers.medians.roe_ttm_pct != null && peers.medians.roe_ttm_pct - roe >= 5) {
    dev.push(`ROE ${roe}% vs median ${peers.medians.roe_ttm_pct}%`);
  }
  gates.push({
    story: "peer_deviation",
    live: dev.length > 0,
    reason: dev.length ? dev.join("; ") : "no adverse deviation ≥ threshold from the class medians",
  });

  // Comparability events — restatements, unit switches, opinion/perimeter moves.
  const events = signals.filter((x) => x.signal_type !== "divergence");
  gates.push({
    story: "comparability_events",
    live: events.length > 0,
    reason: events.length
      ? events.map((x) => `${x.signal_type} [${x.severity}]`).join("; ")
      : "no restatement, unit, opinion or perimeter signal this quarter",
  });

  return gates;
}

function lines(out: string[], title: string, rows: Record<string, unknown>): void {
  out.push(`## ${title}`);
  for (const [k, v] of Object.entries(rows)) {
    if (v === undefined) continue;
    out.push(`${k}: ${v === null ? "n/a" : String(v)}`);
  }
  out.push("");
}

/** The deterministic data block — the ONLY source of figures for the memo. */
export function renderDataBlock(input: AnalystInput): string {
  const { sections: s, peers, comparatives } = input;
  const out: string[] = [];
  out.push(
    `# DATA — ${s.meta.bank_name} (${s.meta.bank_ticker}), ${s.meta.period}, ${s.meta.kind}`,
    `All amounts THOUSAND TL unless marked. Ratios in percent. n/a = not held (never zero).`,
    "",
  );

  lines(out, "Identity", {
    licence_class: s.business.licence_class,
    controlling_shareholder: s.governance.controlling_shareholder
      ? `${s.governance.controlling_shareholder} (${fmt(s.governance.controlling_share_pct, "%")})`
      : null,
    free_float_pct: s.business.ownership.free_float_pct,
    branches: s.business.profile.branches,
    personnel: s.business.profile.personnel,
    market_share_assets_pct: s.business.market_share.assets_pct,
    market_share_loans_pct: s.business.market_share.loans_pct,
    market_share_deposits_pct: s.business.market_share.deposits_pct,
    rank_by_assets: s.business.market_share.peer_rank_by_assets != null
      ? `${s.business.market_share.peer_rank_by_assets} of ${s.business.market_share.peer_count}`
      : null,
  });

  out.push("## STORY GATES — computed, binding. The headline and the lead of every section MUST come from a LIVE story; a DEAD story gets at most one 'notably absent' sentence.");
  for (const g of storyGates(input)) {
    out.push(`  ${g.live ? "LIVE" : "DEAD"} — ${g.story}: ${g.reason}`);
  }
  out.push("");

  lines(out, "Macro backdrop", {
    cbrt_funding_rate_pct: s.macro.funding_rate_pct,
    cpi_yoy_pct: s.macro.cpi_yoy_pct,
    usd_try: s.macro.usd_try,
    recent_regulation_categories: s.macro.regulation_categories.join(", ") || null,
  });

  lines(out, "Earnings", {
    total_assets: s.earnings.total_assets,
    assets_yoy_pct: s.earnings.assets_yoy_pct,
    assets_yoy_REAL_pct: s.earnings.assets_yoy_real_pct,
    net_income_ytd: s.earnings.net_income_ytd,
    net_income_quarterly: s.earnings.net_income_quarterly,
    net_income_ttm: s.earnings.net_income_ttm,
    roe_ttm_pct: s.earnings.roe_ttm_pct,
    roe_REAL_pct: s.earnings.roe_real_pct,
    roa_ttm_pct: s.earnings.roa_ttm_pct,
    operating_income_ttm: s.earnings.operating_income_ttm,
    net_fees_ytd: s.earnings.net_fees_ytd,
    opex_personnel_ytd: s.earnings.opex.personnel_ytd,
    opex_other_ytd: s.earnings.opex.other_ytd,
    cost_income_ttm_pct: s.earnings.opex.cost_income_ttm_pct,
  });

  out.push("## Free provision (discretionary reserve — the earnings-quality lens)");
  out.push(
    `stock_now: ${fmt(s.earnings.free_provision.stock)} · prior_year_end: ${fmt(s.earnings.free_provision.prior_year_end_stock)} · release_ytd: ${fmt(s.earnings.free_provision.release_ytd)} (${fmt(s.earnings.free_provision.release_pct_of_ytd_income, "%")} of YTD profit) · roe_ex_release_pct: ${fmt(s.earnings.free_provision.roe_ex_release_pct)}`,
  );
  out.push("history (period | stock | release_ytd | printed profit_ytd | release as % of printed | EX-RELEASE profit):");
  for (const h of s.earnings.free_provision.history) {
    if (h.stock == null && h.release_ytd == null) continue;
    const inflated =
      h.release_pct_of_income != null && h.release_pct_of_income >= 20
        ? "  <- printed profit inflated by the release; later YoY comparisons against this base are distorted"
        : "";
    out.push(
      `  ${h.period} | ${fmt(h.stock)} | ${fmt(h.release_ytd)} | ${fmt(h.net_income_ytd)} | ${fmt(h.release_pct_of_income, "%")} | ${fmt(h.income_ex_release)}${inflated}`,
    );
  }
  out.push("");

  out.push(`## Core margin — ${s.earnings.core_margin.label ?? "line not found"}`);
  out.push("quarterly (de-cumulated; the series is SEASONAL — read each quarter against the same quarter a year earlier, shown alongside):");
  {
    const byPeriod = new Map<string, number>();
    for (const c of s.earnings.core_margin.quarterly_series) {
      if (c.amount != null) byPeriod.set(c.period, c.amount);
    }
    for (const c of s.earnings.core_margin.quarterly_series) {
      if (c.amount == null) continue;
      const priorYear = `${Number(c.period.slice(0, 4)) - 1}${c.period.slice(4)}`;
      const base = byPeriod.get(priorYear);
      out.push(
        `  ${c.period}: ${c.amount}` +
          (base != null ? `  (same quarter a year earlier: ${base})` : ""),
      );
    }
  }
  out.push("");

  if (s.earnings.pl_movers.length) {
    out.push("## Biggest P&L movers (YTD vs prior-year YTD)");
    for (const m of s.earnings.pl_movers) {
      out.push(`  ${m.item_name}: ${m.prior_year_ytd} -> ${m.ytd} (${m.yoy_pct}%)`);
    }
    out.push("");
  }

  lines(out, "Asset quality", {
    gross_loans: s.asset_quality.gross_loans,
    npl_ratio_pct: s.asset_quality.npl_ratio_pct,
    stage2_ratio_pct: s.asset_quality.stage2_ratio_pct,
    stage3_coverage_pct: s.asset_quality.stage3_coverage_pct,
    stage2_coverage_pct: s.asset_quality.stage2_coverage_pct,
    zero_write_offs_every_stored_period: s.asset_quality.zero_write_offs_all_periods,
  });

  if (s.asset_quality.npl_by_bucket.length) {
    out.push("## NPL by BRSA group (III=substandard, IV=doubtful, V=loss)");
    for (const b of s.asset_quality.npl_by_bucket) {
      out.push(
        `  Group ${b.group}: gross ${fmt(b.gross)} · share ${fmt(b.share_pct, "%")} · coverage ${fmt(b.coverage_pct, "%")}`,
      );
    }
    out.push("");
  }

  const d = s.asset_quality.coverage_decomposition;
  if (d) {
    out.push("## Coverage-fall decomposition (PRECOMPUTED — cite, do not re-derive)");
    out.push(
      `  Stage-3 coverage fell ${d.total_fall_pp}pp (${d.coverage_then_pct}% at ${d.window_start} -> ${d.coverage_now_pct}%).`,
      `  Holding today's balances at ${d.window_start} within-bucket rates gives ${d.counterfactual_now_balances_then_rates_pct}%:`,
      `  ${d.mix_pp}pp of the fall is MIX (new NPL landing in lightly-provisioned buckets), ${d.erosion_pp}pp is genuine within-bucket erosion.`,
      "",
    );
  }

  if (s.asset_quality.npl_movement.length) {
    out.push("## NPL movement, YTD (group | opening | additions | collections | write_offs | sold | closing)");
    for (const m of s.asset_quality.npl_movement) {
      out.push(
        `  ${m.group} | ${fmt(m.opening)} | ${fmt(m.additions_ytd)} | ${fmt(m.collections_ytd)} | ${fmt(m.write_offs_ytd)} | ${fmt(m.sold_ytd)} | ${fmt(m.closing)}`,
      );
    }
    const adds = s.asset_quality.additions_quarterly.filter((a) => a.amount != null);
    if (adds.length) {
      out.push("quarterly additions (new NPL formation):");
      for (const a of adds) out.push(`  ${a.period} ${a.group}: ${a.amount}`);
    }
    out.push("");
  }

  lines(out, "Capital", {
    car_pct: s.capital.car_pct,
    cet1_pct: s.capital.cet1_pct,
    car_minus_cet1_pp: s.capital.car_minus_cet1_pp,
    noncore_share_of_regulatory_capital: s.capital.noncore_share_of_car,
    total_capital: s.capital.total_capital,
    cet1_capital: s.capital.cet1_capital,
    tier2_capital: s.capital.tier2_capital,
    rwa: s.capital.rwa,
    total_equity: s.capital.total_equity,
    equity_to_assets_pct: s.capital.equity_to_assets_pct,
  });
  out.push("capital trajectory (period | CET1 | CAR | gap pp | leverage):");
  for (const t of s.capital.trajectory) {
    out.push(`  ${t.period} | ${fmt(t.cet1)} | ${fmt(t.car)} | ${fmt(t.gap_pp)} | ${fmt(t.leverage)}`);
  }
  const rd = s.capital.ratio_drivers;
  if (rd.cet1_capital_qoq_pct != null || rd.rwa_qoq_pct != null) {
    out.push(
      "why the ratio moved (growth of numerator vs denominator): " +
        `CET1 capital QoQ ${fmt(rd.cet1_capital_qoq_pct, "%")} vs RWA QoQ ${fmt(rd.rwa_qoq_pct, "%")}; ` +
        `CET1 capital YoY ${fmt(rd.cet1_capital_yoy_pct, "%")} vs RWA YoY ${fmt(rd.rwa_yoy_pct, "%")}`,
    );
  }
  out.push("");

  lines(out, "Funding & liquidity", {
    deposits_total: s.funding.deposits_total,
    deposits_tl: s.funding.deposits_tl,
    deposits_fc: s.funding.deposits_fc,
    loan_deposit_ratio_pct: s.funding.ldr_pct,
    lcr_total_pct: s.funding.lcr_total_pct,
    lcr_fc_pct: s.funding.lcr_fc_pct,
    nsfr_pct: s.funding.nsfr_pct,
    leverage_pct: s.funding.leverage_pct,
  });

  lines(out, "FX position", {
    net_fx_position: s.currency.net_fx_position,
    net_on_balance: s.currency.net_on_balance,
    net_off_balance: s.currency.net_off_balance,
    fx_assets: s.currency.fx_assets,
    fx_liabilities: s.currency.fx_liabilities,
  });

  out.push("## Peer context — licence-class medians (" + peers.licence_class + `, n=${peers.peer_count})`);
  for (const [k, v] of Object.entries(peers.medians)) out.push(`  median_${k}: ${fmt(v)}`);
  out.push("");

  out.push("## Quarter-over-quarter / year-over-year");
  for (const c of comparatives) {
    if (c.now == null) continue;
    out.push(
      `  ${c.metric}: now ${c.now} · QoQ ${c.qoq.direction ?? "n/a"} ${fmt(c.qoq.delta)} · YoY ${c.yoy.direction ?? "n/a"} ${fmt(c.yoy.delta)}`,
    );
  }
  out.push("");

  out.push("## Comparability & audit");
  out.push(
    `  reporting_unit: ${fmt(s.comparability.reporting_unit)} (${s.comparability.unit_source}) · assurance: ${s.comparability.assurance_level} (${s.comparability.assurance_source}) · basis: ${s.comparability.consolidation_basis}`,
    `  opinion: ${fmt(s.comparability.opinion_type)} · category: ${fmt(s.comparability.opinion_category)} · auditor: ${fmt(s.comparability.auditor)} · qualified streak: ${s.comparability.qualified_streak} quarters`,
  );
  if (s.comparability.basis_text_lead) {
    out.push(`  auditor's basis text (verbatim lead): "${s.comparability.basis_text_lead}"`);
  }
  if (s.comparability.signals_this_period.length) {
    out.push("  detector signals fired this quarter:");
    for (const sig of s.comparability.signals_this_period) {
      out.push(`    [${sig.severity}] ${sig.signal_type}: ${sig.payload}`);
    }
  }
  out.push("");

  out.push("## NOT AVAILABLE (do not guess these — say 'not held' if relevant)");
  const gapSet = new Set<string>();
  for (const sec of [s.business, s.macro, s.earnings, s.asset_quality, s.currency, s.funding, s.capital, s.securities, s.comparability, s.governance, s.valuation]) {
    for (const g of sec._gaps) gapSet.add(g);
  }
  for (const g of gapSet) out.push(`  - ${g}`);

  return out.join("\n");
}

export const ANALYST_SYSTEM_PROMPT = `You are the in-house bank analyst for a Turkish banking-sector data platform.
Write ONE credit-analyst memo for the bank/quarter in the DATA block, in English.

ABSOLUTE RULES
- Every figure you write MUST appear in the DATA block. You know no numbers of
  your own. Never compute a new number (no additions, ratios or growth rates of
  your own) — the derived numbers you need are already in the DATA block.
- NULL/"n/a" means NOT HELD, never zero. If something material is listed under
  NOT AVAILABLE, say it is not held rather than guessing.
- No investment advice: never say buy/sell/long/short, no price targets.
- Amounts are thousand TL; you may express them as ₺bn by quoting the exact
  stored figure alongside (e.g. "7,000,000 thousand TL (₺7.0bn)").

WHAT MAKES THIS A MEMO, NOT A SCREEN
The DATA block opens with STORY GATES — a computed verdict on which analytical
stories are LIVE for this bank. They are binding editorial rulings, not hints:
the headline must state a LIVE story; a DEAD story may appear only as a single
"notably absent" sentence (a clean bank's cleanliness IS worth one line). Do
not import a story from banks in general — if the gate says the capital
composition is unremarkable, it is unremarkable HERE regardless of how often
that story is true elsewhere.

Headline ratios conceal composition. Your job is the SECOND question:
- If CAR and CET1 diverge, the composition of capital IS the story — use the
  trajectory table and say which is binding.
- If the NPL ratio and Stage-3 coverage diverge, use the PRECOMPUTED
  mix-vs-erosion decomposition and the NPL-movement table (formation,
  collections, write-offs — and SAY IT when write-offs are zero: nothing is
  being cleared) — never guess the cause when it is computed.
- READ THE FP HISTORY TABLE, not just the latest quarter. If any quarter in it
  shows a large release_ytd against that quarter's net_income_ytd, the PRINTED
  profit history is not comparable to itself: a year-over-year "collapse" or
  "surge" measured against an inflated base is an artifact of the release, not
  the business. Say which printed comparisons are distorted and by which
  release. Quote the release and that quarter's printed profit side by side.
- The core-margin quarterly series is the underlying earnings line. Read it
  against the printed bottom line — a margin that halved or rebuilt while the
  headline moved the other way is exactly the finding a screen misses. Compare
  LIKE quarters (Q1 against earlier Q1s): the series is seasonal, and a
  Q4-to-Q1 step is not a collapse.
- Judge growth in REAL terms (the deflated figures are provided).
- Use peer medians to say whether a level is the bank or the sector.

STRUCTURE (markdown, ≤ 900 words)
Line 1: "# " + a one-sentence headline stating the single most important fact.
Then exactly these sections:
"## What changed" — 2-3 paragraphs: the quarter's movements that matter, with QoQ/YoY and peer context.
"## What it means" — 2-3 paragraphs: the causal chain, built from the decompositions, movement tables and the auditor's words.
"## What to watch" — 2-4 bullets: forward indicators tied to LIVE stories. A
falsification threshold must be a figure that appears in the DATA block (the
current value, a peer median, a window-start value) — if no held figure makes
a sensible threshold, state the indicator and its direction WITHOUT a number.
This is where invented figures die: never project a level the data does not contain.
"## Comparability caveats" — bullets: reporting unit, assurance level, consolidation basis, opinion status and streak, restatement/detector signals, and any NOT-AVAILABLE item a reader must know about.

Output ONLY the memo itself, starting directly with the "# " headline line.
Never narrate your process, restate these instructions, or think out loud —
text that is not the memo is discarded wholesale.`;

export function buildMemoMessages(input: AnalystInput): { system: string; user: string } {
  return {
    system: ANALYST_SYSTEM_PROMPT,
    user: renderDataBlock(input),
  };
}
