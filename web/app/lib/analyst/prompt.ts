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
  /** Editorial precedence, 1 = leads. Bank-specific distortions outrank
   *  regime-wide conditions: a printed series that is not comparable to
   *  itself (FP) or a data-integrity event beats a concealment divergence,
   *  which beats peer deviation, which beats negative real returns — the
   *  last is true of much of the sector at 30%+ CPI and so carries the
   *  least bank-specific information. Every LIVE story still gets its own
   *  paragraph; rank only decides the HEADLINE. */
  rank: number;
}

/**
 * A detector signal rendered as a sentence a reader cannot invert. The GARAN
 * deep-dive read `discontinued_ops direction:"appeared"` as "a NEW line of
 * business was added" — the exact opposite of a disposal-in-progress. Raw
 * payloads invite that; each known signal now explains itself.
 */
export function signalSentence(sig: { signal_type: string; payload: string }): string {
  try {
    const p = JSON.parse(sig.payload) as Record<string, unknown>;
    if (sig.signal_type === "perimeter_change" && p.subtype === "discontinued_ops") {
      return p.direction === "appeared"
        ? `a DISCONTINUED-OPERATIONS result of ${fmt(p.current_amount as number)} appeared in the P&L (prior quarter: none). This means the bank is EXITING a business — a disposal or held-for-sale reclassification — NOT adding a new one; continuing-operations comparisons against earlier quarters carry this perimeter break.`
        : `the discontinued-operations line ceased (prior ${fmt(p.prior_amount as number)}) — an exited business has left the accounts; the perimeter break now sits in the PRIOR-year comparatives.`;
    }
    if (sig.signal_type === "perimeter_change" && p.subtype === "cons_gap") {
      return `the consolidated/unconsolidated asset gap moved ${fmt(p.move as number)} — the group perimeter changed (a subsidiary bought, sold or newly consolidated).`;
    }
    if (sig.signal_type === "unit_change") {
      return `the reporting unit SWITCHED (QoQ total-assets ratio ${fmt(p.ratio as number)}) — figures across this boundary are on different scales and must not be compared as printed.`;
    }
    if (sig.signal_type === "cross_period_mismatch") {
      return `this filing's stored prior column disagrees with what the earlier filing itself reported (${fmt(p.lane as string)}.${fmt(p.metric as string)}, ${fmt(p.pct_diff as number)}% apart${p.documented ? " — a documented restatement" : ""}); history was restated or a prior column is defective.`;
    }
    if (sig.signal_type === "opinion_change") {
      return `the audit opinion moved (${fmt(p.subtype as string)}): ${sig.payload}`;
    }
  } catch {
    /* fall through to the raw payload */
  }
  return sig.payload;
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
      rank: 6,
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
      rank: 3,
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
      rank: 4,
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
      rank: 2,
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
      rank: 5,
    live: dev.length > 0,
    reason: dev.length ? dev.join("; ") : "no adverse deviation ≥ threshold from the class medians",
  });

  // Comparability events — restatements, unit switches, opinion/perimeter moves.
  const events = signals.filter((x) => x.signal_type !== "divergence");
  gates.push({
    story: "comparability_events",
      rank: 1,
    live: events.length > 0,
    reason: events.length
      ? events.map((x) => `[${x.severity}] ${signalSentence(x)}`).join(" · ")
      : "no restatement, unit, opinion or perimeter signal this quarter",
  });

  // Live first, then by editorial precedence — the first entry is the LEAD.
  return gates.sort((a, b) => Number(b.live) - Number(a.live) || a.rank - b.rank);
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

  out.push("## STORY GATES — computed, binding, in editorial order. The headline states the LEAD story; EVERY live story gets its own paragraph; a DEAD story gets at most one 'notably absent' sentence.");
  let leadMarked = false;
  for (const g of storyGates(input)) {
    const tag = g.live ? (leadMarked ? "LIVE" : "LEAD") : "DEAD";
    if (g.live) leadMarked = true;
    out.push(`  ${tag} — ${g.story}: ${g.reason}`);
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
    out.push("## NPL movement, YTD (group | opening | additions | transfers_in | transfers_out | collections | write_offs | sold | closing) — transfers are BETWEEN groups, so the table foots per group");
    for (const m of s.asset_quality.npl_movement) {
      out.push(
        `  ${m.group} | ${fmt(m.opening)} | ${fmt(m.additions_ytd)} | ${fmt(m.transfers_in_ytd)} | ${fmt(m.transfers_out_ytd)} | ${fmt(m.collections_ytd)} | ${fmt(m.write_offs_ytd)} | ${fmt(m.sold_ytd)} | ${fmt(m.closing)}`,
      );
    }
    // The TOTAL row is precomputed so the model never sums rows itself —
    // an across-groups collections total it derived by hand was the one real
    // invention of the AKBNK run.
    const tot = (f: (m: (typeof s.asset_quality.npl_movement)[number]) => number | null) => {
      let sum = 0;
      let any = false;
      for (const m of s.asset_quality.npl_movement) {
        const v = f(m);
        if (v != null) {
          sum += v;
          any = true;
        }
      }
      return any ? sum : null;
    };
    out.push(
      `  TOTAL | ${fmt(tot((m) => m.opening))} | ${fmt(tot((m) => m.additions_ytd))} | ${fmt(tot((m) => m.transfers_in_ytd))} | ${fmt(tot((m) => m.transfers_out_ytd))} | ${fmt(tot((m) => m.collections_ytd))} | ${fmt(tot((m) => m.write_offs_ytd))} | ${fmt(tot((m) => m.sold_ytd))} | ${fmt(tot((m) => m.closing))}`,
    );
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

  if (peers.rows.length) {
    out.push("## Named peer table — the class by assets, each bank's own filed figures");
    out.push("  ticker | total_assets | CAR | CET1 | NPL% | Stage2% | Stage3 cov% | ROE ttm%");
    for (const r of peers.rows) {
      out.push(
        `  ${r.bank_ticker} | ${fmt(r.total_assets)} | ${fmt(r.car)} | ${fmt(r.cet1)} | ` +
          `${fmt(r.npl_ratio_pct)} | ${fmt(r.stage2_ratio_pct)} | ${fmt(r.stage3_coverage_pct)} | ${fmt(r.roe_ttm_pct)}`,
      );
    }
    out.push("");
  }

  const sec = s.macro.sector;
  if (sec.as_of) {
    out.push(`## Sector aggregates — BDDK monthly data, ${sec.as_of} (system-wide, code 10001)`);
    out.push(
      `  sector_total_assets: ${fmt(sec.total_assets_million_tl)} MILLION TL · this bank's share: ${fmt(sec.bank_share_of_sector_assets_pct, "%")}`,
      `  sector_roe: ${fmt(sec.roe_pct, "%")} · sector_npl_ratio: ${fmt(sec.npl_ratio_pct, "%")} · sector_car: ${fmt(sec.car_pct, "%")} · sector_nim_on_avg_assets: ${fmt(sec.nim_pct, "%")}`,
      "",
    );
  }

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
    out.push("  detector signals fired this quarter (our own detectors over the stored rows — not regulator notices):");
    for (const sig of s.comparability.signals_this_period) {
      out.push(`    [${sig.severity}] ${sig.signal_type}: ${signalSentence(sig)}`);
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
stories are LIVE for this bank, in editorial order. They are binding rulings,
not hints: the headline must state the story marked LEAD; EVERY other LIVE
story must receive at least one dedicated paragraph of its own in the body
sections — dropping a live story is as wrong as inventing a dead one. A DEAD story may appear only as a single "notably absent"
sentence (a clean bank's cleanliness IS worth one line). Do not import a
story from banks in general — if the gate says the capital composition is
unremarkable, it is unremarkable HERE regardless of how often that story is
true elsewhere.

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

STRUCTURE — a FULL research report, 2,500–4,000 words of substance, markdown.
Line 1: "# " + a one-sentence headline stating the LEAD story.
Then a short "Analyst verdict" paragraph (3-5 sentences — the whole thesis).
Then EXACTLY these sections, in order. Markdown tables are encouraged wherever
the data block gives you a table (scorecard, buckets, trajectory, peers) —
every cell a figure from the data block, "n/a" where not held.

"## First-read scorecard" — a table: the 8-12 defining metrics of the quarter
(assets, net income, ROE nominal AND real, NIM-proxy or margin line, NPL,
Stage-2, coverage, CAR/CET1, LDR), each with the figure, the QoQ/YoY move,
and one short interpretation.
"## What changed" — 3-5 paragraphs: the quarter's movements that matter, every
LIVE story present, peer and sector context inline.
"## Earnings and earnings quality" — margin/core-margin trend (like-quarter
comparisons), fees/opex/cost-income, the free-provision position and its
history (re-base distorted comparisons where the history shows releases),
real-terms verdict.
"## Balance sheet, funding and liquidity" — assets, deposits (TL/FC split),
LDR, LCR/NSFR/leverage.
"## Asset quality" — the deep dive: stages, BRSA buckets with shares and
per-bucket coverage, the PRECOMPUTED mix-vs-erosion decomposition, the NPL
movement reconciliation (opening → additions → collections → write-offs/sales
→ closing), quarterly formation, sector NPL comparison.
"## Capital" — ratios vs peers and sector, the trajectory table, WHY the
ratio moved (the capital-vs-RWA growth figures), equity/assets, leverage.
"## Currency position" — the net FX position, on/off-balance split, by
currency.
"## Macro and regulation" — the funding rate, CPI, USDTRY, sector aggregates,
recent regulation categories; what they mean for THIS bank's mix.
"## Peer comparison" — the named-peer table rendered as markdown, then 2-3
paragraphs of directional reading (who leads on what; where this bank sits;
respect the stage-definition caveat).
"## What the auditor said" — assurance level and its meaning (a review is
negative assurance, narrower than an audit), opinion status and streak, the
verbatim basis text if qualified, detector signals. For a clean opinion say
plainly that no qualification exists and what a review does NOT cover.
"## What to watch" — 4-6 bullets tied to LIVE stories. A falsification
threshold must be a figure that appears in the DATA block (current value,
peer median, window-start value) — if no held figure makes a sensible
threshold, state the indicator and its direction WITHOUT a number. This is
where invented figures die: never project a level the data does not contain.
"## What this report cannot see" — an honest register of the NOT AVAILABLE
list: name the missing dataset AND what question it would answer (e.g. market
pricing is deliberately not carried, so no P/B or P/E is computed here).
"## Bottom line" — 2-3 paragraphs: the thesis restated with its strongest
numbers, what is franchise vs cycle vs accounting artifact, and the single
condition that would change the read.

Output ONLY the report itself, starting directly with the "# " headline line.
Never narrate your process, restate these instructions, or think out loud —
text that is not the report is discarded wholesale.`;

const SKELETON_REMINDER = `
────────────────────────────────────────────
REMINDER — output the FULL report now, 2,500–4,000 words, starting with the
"# " headline, then the Analyst verdict paragraph, then EXACTLY these
sections in order (every one present; use markdown tables where the data
gives you a table):
## First-read scorecard
## What changed
## Earnings and earnings quality
## Balance sheet, funding and liquidity
## Asset quality
## Capital
## Currency position
## Macro and regulation
## Peer comparison
## What the auditor said
## What to watch
## What this report cannot see
## Bottom line
A short four-section memo is a FAILED output.`;

export function buildMemoMessages(input: AnalystInput): { system: string; user: string } {
  return {
    system: ANALYST_SYSTEM_PROMPT,
    // The skeleton repeats at the TAIL of the user message: on long prompts
    // the free models follow the most recent instruction far more reliably
    // than one buried mid-system-prompt (the 435-word collapse of run
    // 30906921912 is the measurement).
    user: renderDataBlock(input) + "\n" + SKELETON_REMINDER,
  };
}
