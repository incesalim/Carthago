import { deflate, type Pt } from "../credit";
import { LDR_PUBLISHED } from "../ldr";
import { signalState, signalText as t, type SectorSignal, type SignalFact } from "./types";

const MATURITY_KEYS = ["demand", "maturity_1m", "maturity_1_3m", "maturity_3_6m", "maturity_6_12m", "maturity_over_12m"] as const;
type MaturityRow = { period: string } & Partial<Record<(typeof MATURITY_KEYS)[number], number | null>>;
export interface DepositSignalInput {
  depositGrowth: Pt[];
  loanGrowth: Pt[];
  tl: Pt[];
  fx: Pt[];
  maturity: MaturityRow[];
  publishedLdr: Pt[];
  cpi: Map<string, number>;
}
const value = (rows: Pt[]) => rows.at(-1)?.value ?? null;
const date = (rows: Pt[]) => rows.at(-1)?.period ?? null;
const known = (v: number | null | undefined): v is number => v != null && Number.isFinite(v);
const fact = (key: string, en: string, tr: string, value: number | null, asOf: string | null, unit: SignalFact["unit"] = "percent"): SignalFact => ({ key, label: t(en, tr), value, asOf, unit });
const missing = t("The observations needed to evaluate this condition are unavailable.", "Bu koşulu değerlendirmek için gereken gözlemler mevcut değil.");
const weeklySource = t("BDDK weekly bulletin, sector total, TL and FX combined; 52-week annual growth.", "BDDK haftalık bülteni, sektör toplamı, TL ve YP birlikte; 52 haftalık yıllık büyüme.");

/** The original five deposit rules; missing maturity buckets never become zero. */
export function buildDepositsSignals(input: DepositSignalInput): SectorSignal[] {
  const { depositGrowth, loanGrowth, tl, fx, maturity, publishedLdr, cpi } = input;
  const m = maturity.at(-1);
  const maturityKnown = !!m && MATURITY_KEYS.every((k) => known(m[k]));
  const total = maturityKnown ? MATURITY_KEYS.reduce((n, k) => n + m[k]!, 0) : null;
  const share = (key: (typeof MATURITY_KEYS)[number]) => total != null && total > 0 ? m![key]! * 100 / total : null;
  const demand = share("demand");
  const term1 = share("maturity_1m");
  const term13 = share("maturity_1_3m");
  const term = term1 != null && term13 != null ? term1 + term13 : null;
  const reprice = demand != null && term != null ? demand + term : null;
  const loans = value(loanGrowth);
  const deposits = value(depositGrowth);
  const gap = known(loans) && known(deposits) && date(loanGrowth) === date(depositGrowth) ? loans - deposits : null;
  const real = deflate(depositGrowth, cpi);
  const realNow = value(real);
  const realDate = date(real);
  const nominalAtReal = depositGrowth.find((r) => r.period === realDate)?.value ?? null;
  const realCpi = realDate ? cpi.get(realDate.slice(0, 7)) ?? null : null;
  const tlByDate = new Map(tl.map((r) => [r.period, r.value]));
  const fxShare: Pt[] = [];
  for (const row of fx) {
    const tlValue = tlByDate.get(row.period);
    if (!known(tlValue) || !known(row.value) || tlValue + row.value <= 0) continue;
    fxShare.push({ period: row.period, value: row.value * 100 / (tlValue + row.value) });
  }
  const fxNow = value(fxShare);
  const fxBase = fxShare.at(-53);
  const latestFxAvailable = date(fxShare) === date(fx) && date(fxShare) === date(tl);
  const fxDelta = latestFxAvailable && known(fxNow) && known(fxBase?.value) ? fxNow - fxBase.value : null;
  const ldr = value(publishedLdr);
  const repriceState = signalState(known(reprice), reprice != null && reprice > 85);
  const gapState = signalState(known(gap), gap != null && gap > 3);
  const realState = signalState(known(realNow), realNow != null && realNow < 0);
  const dollarState = signalState(known(fxDelta), fxDelta != null && fxDelta > 1);
  const ldrState = signalState(known(ldr), ldr != null && ldr > LDR_PUBLISHED.line);
  return [
    {
      id: "deposits:reprice-cliff", sector: "deposits", state: repriceState,
      title: t("Short-term deposit repricing", "Mevduatta kısa vadeli yeniden fiyatlama"),
      summary: repriceState === "unavailable" ? missing : repriceState === "active"
        ? t("Demand deposits and deposits maturing within three months exceed 85% of the maturity distribution. This short repricing horizon can transmit policy-rate changes quickly to funding costs.", "Vadesiz ve üç ay içinde vadesi dolan mevduat, vade dağılımının %85'ini aşıyor. Kısa yeniden fiyatlama süresi, politika faizi değişikliklerinin fonlama maliyetlerine hızlı yansımasına neden olabilir.")
        : t("Demand deposits and maturities up to three months do not exceed the 85% threshold.", "Vadesiz ve üç aya kadar vadeli mevduatın payı %85 eşiğini aşmıyor."),
      criterion: t("The combined share of demand deposits, maturities up to one month and maturities from one to three months exceeds 85%. The denominator is the sum of all six published maturity buckets; an undisclosed bucket prevents evaluation.", "Vadesiz, bir aya kadar vadeli ve bir–üç ay vadeli mevduatın toplam payının %85'i aşması. Payda, yayımlanmış altı vade diliminin toplamıdır; herhangi bir dilim eksikse değerlendirme yapılmaz."),
      rule: "share(demand + ≤3m) > 85%", asOf: m?.period ?? null, cadence: "monthly",
      source: t("BDDK monthly deposit maturity table, TOPLAM MEVDUAT, currency=TL reporting basis; demand and all maturity buckets.", "BDDK aylık mevduat vade tablosu, TOPLAM MEVDUAT, currency=TL raporlama esası; vadesiz ve tüm vade dilimleri."),
      href: "/deposits#maturity",
      facts: [fact("repricing_share", "Demand and up to three months", "Vadesiz ve üç aya kadar vadeli", reprice, m?.period ?? null), fact("demand_share", "Demand deposit share", "Vadesiz mevduat payı", demand, m?.period ?? null), fact("term_share", "Term deposits up to three months", "Üç aya kadar vadeli mevduat payı", term, m?.period ?? null)],
    },
    {
      id: "deposits:funding-gap", sector: "deposits", state: gapState,
      title: t("Loan and deposit growth gap", "Kredi ve mevduat büyümesi farkı"),
      summary: gapState === "unavailable" ? missing : gapState === "active"
        ? t("Annual loan growth exceeds annual deposit growth by more than 3 percentage points, increasing the need for funding beyond deposit growth.", "Yıllık kredi büyümesi, yıllık mevduat büyümesini 3 yüzde puandan fazla aşıyor; mevduat artışının ötesinde fonlama ihtiyacı doğuruyor.")
        : t("The annual loan-minus-deposit growth gap does not exceed 3 percentage points.", "Yıllık kredi büyümesi ile mevduat büyümesi arasındaki fark 3 yüzde puanı aşmıyor."),
      criterion: t("52-week loan growth minus 52-week deposit growth exceeds 3 percentage points, using sector totals on the same weekly observation date.", "Aynı haftalık gözlem tarihindeki sektör toplamlarıyla, 52 haftalık kredi büyümesinden 52 haftalık mevduat büyümesi çıkarıldığında farkın 3 yüzde puanı aşması."),
      rule: "loans_52w − deposits_52w > 3pp", asOf: date(depositGrowth), cadence: "weekly", source: weeklySource, href: "/deposits#growth",
      facts: [fact("loan_growth", "Annual loan growth", "Yıllık kredi büyümesi", loans, date(loanGrowth)), fact("deposit_growth", "Annual deposit growth", "Yıllık mevduat büyümesi", deposits, date(depositGrowth)), fact("growth_gap", "Loan minus deposit growth", "Kredi büyümesi eksi mevduat büyümesi", gap, date(depositGrowth), "pp")],
    },
    {
      id: "deposits:real-base", sector: "deposits", state: realState,
      title: t("Real deposit growth", "Reel mevduat büyümesi"),
      summary: realState === "unavailable" ? missing : realState === "active"
        ? t("The deposit base is contracting in purchasing-power terms at the latest observation for which monthly CPI is published.", "Aylık TÜFE'nin yayımlandığı son hesaplanabilir gözlemde mevduat tabanı satın alma gücü bakımından daralıyor.")
        : t("The latest calculable annual deposit growth after CPI adjustment is not negative.", "TÜFE ile arındırılmış son hesaplanabilir yıllık mevduat büyümesi negatif değil."),
      criterion: t("Real annual deposit growth is below zero. The calculation is 100 × [(1 + nominal growth/100)/(1 + annual CPI/100) − 1], rather than subtracting the rates. The original rule is retained as shorthand. Only published CPI for the observation's month is used; no nowcast, so real and latest nominal dates can differ.", "Reel yıllık mevduat büyümesinin sıfırın altında olması. Hesaplama, oranların farkı yerine 100 × [(1 + nominal büyüme/100)/(1 + yıllık TÜFE/100) − 1] formülünü kullanır. Özgün kural kısa gösterim olarak korunmuştur. Yalnızca gözlem ayının yayımlanmış TÜFE'si kullanılır; tahminle tamamlama yapılmadığından reel veri ile son nominal verinin tarihleri farklı olabilir."),
      rule: "deposits_52w − cpi_yoy < 0", asOf: realDate, cadence: "mixed",
      source: t("BDDK weekly deposit growth; TÜİK monthly CPI (TP.TUKFIY2025.GENEL) via TCMB EVDS; exact Fisher deflation.", "BDDK haftalık mevduat büyümesi; TCMB EVDS üzerinden TÜİK aylık TÜFE (TP.TUKFIY2025.GENEL); Fisher formülüyle arındırma."),
      href: "/deposits#growth",
      facts: [fact("real_growth", "Real annual deposit growth", "Reel yıllık mevduat büyümesi", realNow, realDate), fact("matched_nominal_growth", "Nominal growth at real observation", "Reel veri tarihinde nominal büyüme", nominalAtReal, realDate), fact("annual_cpi", "Published annual CPI", "Yayımlanmış yıllık TÜFE", realCpi, realDate?.slice(0, 7) ?? null), fact("latest_nominal_growth", "Latest nominal deposit growth", "Son nominal mevduat büyümesi", deposits, date(depositGrowth))],
    },
    {
      id: "deposits:dollarization", sector: "deposits", state: dollarState,
      title: t("Foreign-currency deposit share", "Yabancı para mevduat payı"),
      summary: dollarState === "unavailable" ? missing : dollarState === "active"
        ? t("The FX share of deposits has increased by more than 1 percentage point over the comparison window. The TL-equivalent share reflects exchange-rate valuation as well as deposit movements.", "YP mevduat payı karşılaştırma döneminde 1 yüzde puandan fazla arttı. TL karşılığıyla hesaplanan pay, mevduat hareketlerinin yanı sıra kur değerlemesinden de etkilenir.")
        : t("The increase in the FX share of deposits does not exceed 1 percentage point over the comparison window.", "YP mevduat payındaki artış karşılaştırma döneminde 1 yüzde puanı aşmıyor."),
      criterion: t("FX deposits divided by TL plus FX deposits, in TL equivalents, increases by more than 1 percentage point against 52 published observations earlier. This preserves the original row-offset comparison; with missing weeks it need not span exactly 364 days.", "TL karşılığıyla YP mevduatın TL ve YP mevduat toplamına oranının, 52 yayımlanmış gözlem önceye göre 1 yüzde puandan fazla artması. Özgün gözlem sırasına dayalı karşılaştırma korunur; eksik haftalar varsa dönem tam 364 gün olmayabilir."),
      rule: "Δ52w(fx_share) > +1pp", asOf: date(fxShare), cadence: "weekly", source: weeklySource, href: "/deposits#currency",
      facts: [fact("fx_share", "Latest FX deposit share", "Son YP mevduat payı", fxNow, date(fxShare)), fact("base_share", "FX share 52 observations earlier", "52 gözlem önceki YP payı", fxBase?.value ?? null, fxBase?.period ?? null), fact("share_change", "Change in FX share", "YP payı değişimi", fxDelta, date(fxShare), "pp")],
    },
    {
      id: "deposits:funding-stretch", sector: "deposits", state: ldrState,
      title: t("All-currency loan-to-deposit ratio", "TL ve YP toplam kredi/mevduat oranı"),
      summary: ldrState === "unavailable" ? missing : ldrState === "active"
        ? t("The published sector loan-to-deposit ratio exceeds 100%, indicating lending beyond the deposit base. The weekly private-bank TL-only measure has a separate 95% research threshold on Liquidity.", "Yayımlanmış sektör kredi/mevduat oranı %100'ü aşıyor; kredi stoku mevduat tabanının üzerinde. Özel bankaların haftalık, yalnızca TL üzerinden hesaplanan oranı Likidite kapsamında ayrı %95 araştırma eşiğiyle değerlendirilir.")
        : t("The published all-currency sector loan-to-deposit ratio does not exceed 100%.", "Yayımlanmış TL ve YP toplam sektör kredi/mevduat oranı %100'ü aşmıyor."),
      criterion: t("The BDDK published monthly sector loan-to-deposit ratio, including TL and foreign currencies, exceeds 100%. This is distinct from the weekly TL-only private-bank ratio.", "BDDK'nın yayımladığı, TL ve yabancı paraları içeren aylık sektör kredi/mevduat oranının %100'ü aşması. Bu ölçüt, özel bankaların haftalık ve yalnızca TL üzerinden hesaplanan oranından farklıdır."),
      rule: LDR_PUBLISHED.rule, asOf: date(publishedLdr), cadence: "monthly",
      source: t("BDDK published monthly sector ratio; loans and deposits, TL and foreign currencies combined.", "BDDK yayımlanmış aylık sektör oranı; kredi ve mevduatta TL ve yabancı paralar birlikte."),
      href: "/deposits#loan-funding", facts: [fact("published_ldr", "Published TL+FX loan/deposit", "Yayımlanmış TL+YP kredi/mevduat", ldr, date(publishedLdr))],
    },
  ];
}

export async function loadDepositsSignals(): Promise<SectorSignal[]> {
  const { weeklyGrowth, weeklySeries, depositMaturityMix, ratioLdr, WEEKLY_BANK_TYPES, BANK_TYPES } = await import("../metrics");
  const { cpiYoYByMonth } = await import("../real-terms");
  const sector = [WEEKLY_BANK_TYPES.SECTOR];
  const [depositGrowth, loanGrowth, tl, fx, maturity, publishedLdr, cpi] = await Promise.all([
    weeklyGrowth("mevduat", "4.0.1", "TOTAL", 52, sector, 104),
    weeklyGrowth("krediler", "1.0.1", "TOTAL", 52, sector, 104),
    weeklySeries("mevduat", "4.0.1", "TL", sector, 156),
    weeklySeries("mevduat", "4.0.1", "FX", sector, 156),
    depositMaturityMix(BANK_TYPES.SECTOR), ratioLdr([BANK_TYPES.SECTOR]), cpiYoYByMonth(),
  ]);
  return buildDepositsSignals({ depositGrowth, loanGrowth, tl, fx, maturity, publishedLdr, cpi });
}
