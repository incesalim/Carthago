/**
 * Data layer for the /digital tab — TBB quarterly digital-banking statistics
 * (sector-wide; no per-bank breakdown). Reads the tidy `tbb_digital_stats`
 * table populated by scripts/update_tbb_digital.py.
 *
 * Each chart is a small set of curated series, pinned by their natural key
 * (channel, segment, section_code, unit, metric_slug). Every slug below was
 * verified to span the full quarterly history (2019-Q1 → latest). Values are
 * stored in TBB's source units (thousand persons / thousand transactions /
 * billion TL); `digitalSeries` rescales to display units (millions, ₺ trillion).
 */
import { cachedAll } from "./db";
import type { TrendPoint } from "@/app/components/TrendChart";

export interface Spec {
  /** Series key used by TrendChart (legend order = array order). */
  code: string;
  channel: "digital" | "internet" | "mobile";
  segment: "individual" | "corporate" | "total";
  section: string;
  unit: "persons_thousands" | "count_thousands" | "volume_bn_try";
  slug: string;
}

const keyOf = (c: string, sg: string, sc: string, u: string, sl: string) =>
  `${c}|${sg}|${sc}|${u}|${sl}`;

/**
 * Fetch the given series as TrendChart points, rescaling each value by `scale`
 * (e.g. 1/1000 to turn thousands → millions, or billion TL → ₺ trillion). One
 * cached query covers every series in the chart.
 */
export async function digitalSeries(specs: Spec[], scale = 1): Promise<TrendPoint[]> {
  if (specs.length === 0) return [];
  const cond = specs
    .map(() => "(channel=? AND segment=? AND section_code=? AND unit=? AND metric_slug=?)")
    .join(" OR ");
  const binds = specs.flatMap((s) => [s.channel, s.segment, s.section, s.unit, s.slug]);
  const rows = await cachedAll<{
    period: string;
    channel: string;
    segment: string;
    section_code: string;
    unit: string;
    metric_slug: string;
    value: number | null;
  }>(
    `SELECT period, channel, segment, section_code, unit, metric_slug, value
       FROM tbb_digital_stats WHERE ${cond} ORDER BY period`,
    binds,
  );
  const codeFor = new Map(
    specs.map((s) => [keyOf(s.channel, s.segment, s.section, s.unit, s.slug), s.code]),
  );
  return rows.map((r) => ({
    period: r.period,
    bank_type_code:
      codeFor.get(keyOf(r.channel, r.segment, r.section_code, r.unit, r.metric_slug)) ?? "?",
    value: r.value == null ? null : r.value * scale,
  }));
}

/**
 * Per-series quarter-over-quarter change. Groups `points` by series
 * (`bank_type_code`), orders each by period, and emits value[t] − value[t−1] —
 * i.e. the net change that quarter. The first quarter of each series is dropped
 * (nothing to difference against). Used to turn the cumulative registered base
 * (a stock TBB reports) into "net new customers per quarter" (a flow it doesn't).
 */
export function quarterlyDeltas(points: TrendPoint[]): TrendPoint[] {
  const bySeries = new Map<string, TrendPoint[]>();
  for (const p of points) {
    if (!bySeries.has(p.bank_type_code)) bySeries.set(p.bank_type_code, []);
    bySeries.get(p.bank_type_code)!.push(p);
  }
  const out: TrendPoint[] = [];
  for (const series of bySeries.values()) {
    const sorted = [...series].sort((a, b) => a.period.localeCompare(b.period));
    for (let i = 1; i < sorted.length; i++) {
      const prev = sorted[i - 1].value;
      const cur = sorted[i].value;
      out.push({
        period: sorted[i].period,
        bank_type_code: sorted[i].bank_type_code,
        value: prev == null || cur == null ? null : cur - prev,
      });
    }
  }
  return out;
}

/**
 * Pivot long-form `TrendPoint[]` into the wide, one-row-per-period shape that
 * `StackedArea` and `BopFlowChart` expect. `xKey` is the period field name —
 * `"period"` for StackedArea, `"x"` for BopFlowChart. Rows are sorted by period.
 */
export function pivotWide(
  points: TrendPoint[],
  xKey: "period" | "x" = "period",
): Array<Record<string, string | number | null>> {
  const byPeriod = new Map<string, Record<string, string | number | null>>();
  for (const p of points) {
    if (!byPeriod.has(p.period)) byPeriod.set(p.period, { [xKey]: p.period });
    byPeriod.get(p.period)![p.bank_type_code] = p.value;
  }
  return Array.from(byPeriod.values()).sort((a, b) =>
    String(a[xKey]).localeCompare(String(b[xKey])),
  );
}

// Most series share this conversion: thousands → millions, or bn TL → trn TL.
export const SCALE_K_TO_M = 1 / 1000;
export const SCALE_BN_TO_TRN = 1 / 1000;

const sp = (
  code: string,
  channel: Spec["channel"],
  segment: Spec["segment"],
  section: string,
  unit: Spec["unit"],
  slug: string,
): Spec => ({ code, channel, segment, section, unit, slug });

// ── Adoption ───────────────────────────────────────────────────────────────

/** Active *individual* digital customers by how they bank (TBB's headline cut). */
export const CHANNEL_USE: Spec[] = [
  sp("mobile_only", "digital", "individual", "I", "persons_thousands",
     "aktif_bireysel_musteri_sayisi_sadece_mobil_bankacilik_kullanan"),
  sp("both", "digital", "individual", "I", "persons_thousands",
     "aktif_bireysel_musteri_sayisi_hem_internet_hem_mobil_bankacilik_kullanan"),
  sp("internet_only", "digital", "individual", "I", "persons_thousands",
     "aktif_bireysel_musteri_sayisi_sadece_internet_bankaciligi_kullanan"),
];
export const CHANNEL_USE_LABELS: Record<string, string> = {
  mobile_only: "Mobile only",
  both: "Both channels",
  internet_only: "Internet only",
};

/** Active customers on each channel (sector total) — mobile vs internet. */
export const ACTIVE_BY_CHANNEL: Spec[] = [
  sp("mobile", "mobile", "total", "I", "persons_thousands", "aktif_musteri_sayisi"),
  sp("internet", "internet", "total", "I", "persons_thousands", "aktif_musteri_sayisi"),
];
export const CHANNEL_LABELS: Record<string, string> = {
  mobile: "Mobile banking",
  internet: "Internet banking",
};

// ── Acquisition ──────────────────────────────────────────────────────────────

/**
 * Registered customer base by channel — TBB's "registered in the system &
 * logged in at least once" count (sector total). This is the cumulative
 * installed base; differencing it (see `quarterlyDeltas`) gives net new
 * customers per quarter. NB: a customer registered at N banks counts N times,
 * so this is a per-bank registered base summed across the sector, not a unique
 * head-count — read the *trend* and the *net adds*, not the absolute level.
 */
export const REGISTERED_BY_CHANNEL: Spec[] = [
  sp("mobile", "mobile", "total", "I", "persons_thousands",
     "sistemde_kayitli_en_az_bir_kez_login_olmus_musteri_sayisi"),
  sp("internet", "internet", "total", "I", "persons_thousands",
     "sistemde_kayitli_en_az_bir_kez_login_olmus_musteri_sayisi"),
];

/**
 * Product applications submitted through digital channels per quarter (TBB
 * section II) — the demand-side / top-of-funnel signal. Mobile only: internet
 * applications are now <0.5% of the total, so a mobile cut tells the real story
 * (and avoids a near-zero internet line). Loan vs credit-card applications.
 */
export const APPLICATIONS: Spec[] = [
  sp("loan", "mobile", "total", "II", "count_thousands", "kredi_basvurusu"),
  sp("card", "mobile", "total", "II", "count_thousands",
     "kredi_karti_ve_ek_kart_basvurusu"),
];
export const APPLICATION_LABELS: Record<string, string> = {
  loan: "Loan applications",
  card: "Card applications",
};

// ── Transactions ─────────────────────────────────────────────────────────────

/** Money-transfer grand total (III.1) — internet vs mobile, by unit. */
export const TRANSFER_VOLUME: Spec[] = [
  sp("mobile", "mobile", "total", "III.1", "volume_bn_try", "toplam"),
  sp("internet", "internet", "total", "III.1", "volume_bn_try", "toplam"),
];
export const TRANSFER_COUNT: Spec[] = [
  sp("mobile", "mobile", "total", "III.1", "count_thousands", "toplam"),
  sp("internet", "internet", "total", "III.1", "count_thousands", "toplam"),
];
/** Bill payments (III.2) count — internet vs mobile. */
export const BILL_COUNT: Spec[] = [
  sp("mobile", "mobile", "total", "III.2", "count_thousands", "fatura_odemeleri"),
  sp("internet", "internet", "total", "III.2", "count_thousands", "fatura_odemeleri"),
];

// ── Demographics (active individual digital customers) ───────────────────────

export const GENDER: Spec[] = [
  sp("erkek", "digital", "individual", "II", "persons_thousands", "erkek_toplam"),
  sp("kadin", "digital", "individual", "II", "persons_thousands", "kadin_toplam"),
];
export const GENDER_LABELS: Record<string, string> = { erkek: "Men", kadin: "Women" };

const AGE_GROUPS = ["0_17", "18_25", "26_35", "36_55", "56_65", "66"] as const;
export const AGE: Spec[] = AGE_GROUPS.map((g) =>
  sp(g, "digital", "individual", "III", "persons_thousands", `toplam_${g}_yas_grubu`),
);
export const AGE_LABELS: Record<string, string> = {
  "0_17": "0–17", "18_25": "18–25", "26_35": "26–35",
  "36_55": "36–55", "56_65": "56–65", "66": "66+",
};
