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
