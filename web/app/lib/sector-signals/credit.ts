import { deflate, fxAdjustedGrowth, trailingRun, trailingRunVs, type Pt } from "../credit";
import { signalState, signalText as t, type SectorSignal, type SignalFact } from "./types";

export interface CreditSignalInput {
  nominal: Pt[];
  realConstantFx: Pt[];
  auto: Pt[];
  autoLevels: Pt[];
  cards: Pt[];
  generalPurpose: Pt[];
}

const value = (rows: Pt[]) => rows.at(-1)?.value ?? null;
const date = (rows: Pt[]) => rows.at(-1)?.period ?? null;
const available = (v: number | null) => v != null && Number.isFinite(v);
const fact = (key: string, en: string, tr: string, rows: Pt[], unit: SignalFact["unit"] = "percent"): SignalFact =>
  ({ key, label: t(en, tr), value: value(rows), unit, asOf: date(rows) });
const missing = t("The observations needed to evaluate this condition are unavailable.", "Bu koşulu değerlendirmek için gereken gözlemler mevcut değil.");

/** A short or interrupted positive run cannot establish that an eight-observation condition is clear. */
function runAvailable(rows: Pt[], predicate: (v: number, period: string) => boolean | null): boolean {
  let n = 0;
  for (let i = rows.length - 1; i >= 0; i--) {
    const row = rows[i];
    if (!available(row.value)) return false;
    const matches = predicate(row.value!, row.period);
    if (matches == null) return false;
    if (!matches || ++n >= 8) return true;
  }
  return false;
}

/** The three original credit conditions; no presentation or database dependencies. */
export function buildCreditSignals(input: CreditSignalInput): SectorSignal[] {
  const { nominal, realConstantFx, auto, autoLevels, cards, generalPurpose } = input;
  const realNow = value(realConstantFx);
  const autoNow = value(auto);
  const realRun = trailingRun(realConstantFx, (v) => v < 0);
  const autoRun = trailingRun(auto, (v) => v < 0);
  const unsecuredRun = Math.min(
    trailingRunVs(cards, nominal, (v, other) => v > other),
    trailingRunVs(generalPurpose, nominal, (v, other) => v > other),
  );
  const nominalByDate = new Map(nominal.map((r) => [r.period, r.value]));
  const outruns = (v: number, period: string) => {
    const other = nominalByDate.get(period) ?? null;
    return available(other) ? v > other! : null;
  };
  const unsecuredAvailable = date(cards) === date(generalPurpose) &&
    runAvailable(cards, outruns) && runAvailable(generalPurpose, outruns);
  const realState = signalState(available(realNow), realRun > 0 && realNow! < 0);
  const autoState = signalState(runAvailable(auto, (v) => v < 0), autoRun >= 8 && autoNow != null && autoNow < 0);
  const unsecuredState = signalState(unsecuredAvailable, unsecuredRun >= 8);
  const weeklySource = t("BDDK weekly bulletin; sector total, annual growth over 52 weeks. Runs count consecutive published observations within the fetched history.", "BDDK haftalık bülteni; sektör toplamı, 52 haftalık yıllık büyüme. Süreler, alınan veri aralığındaki ardışık yayımlanmış gözlemleri sayar.");
  const runFact = (key: string, en: string, tr: string, n: number, asOf: string | null, known: boolean): SignalFact =>
    ({ key, label: t(en, tr), value: known ? n : null, unit: "weeks", asOf });
  return [
    {
      id: "credit:real_credit_contraction", sector: "credit", state: realState,
      title: t("Real credit contraction", "Reel kredi daralması"),
      summary: realState === "unavailable" ? missing : realState === "active"
        ? t("Credit is contracting after currency and price effects are removed. The latest nominal rate includes both effects and can have a later observation date.", "Kur ve fiyat etkileri arındırıldığında krediler daralıyor. Son nominal büyüme bu iki etkiyi de içerir ve daha ileri bir gözlem tarihine ait olabilir.")
        : t("The latest available real, constant-currency annual growth rate is not negative.", "Son hesaplanabilir reel, sabit kurla yıllık kredi büyümesi negatif değil."),
      criterion: t("Real, constant-currency 52-week growth is below zero in the latest observation. The FX book is held at the base-period USD/TRY rate, assuming all FX is USD; the result is deflated using (1 + growth)/(1 + annual CPI) − 1. Only published monthly CPI is used, so the real series may lag weekly nominal data.", "Son gözlemde reel, sabit kurla 52 haftalık büyümenin sıfırın altında olması. YP portföyü, tamamının ABD doları olduğu varsayımıyla baz dönem USD/TL kurunda tutulur; sonuç (1 + büyüme)/(1 + yıllık TÜFE) − 1 formülüyle fiyat etkisinden arındırılır. Yalnızca yayımlanmış aylık TÜFE kullanıldığından reel seri haftalık nominal veriden geride kalabilir."),
      rule: `real_fxadj(52w) < 0 for ${realRun}w`, asOf: date(realConstantFx), cadence: "mixed",
      source: t("BDDK weekly credit bulletin; TCMB USD/TRY; TÜİK monthly CPI via EVDS. Weekly real observations use their calendar month's published CPI; no nowcast.", "BDDK haftalık kredi bülteni; TCMB USD/TL; EVDS üzerinden TÜİK aylık TÜFE. Haftalık reel gözlemde ilgili takvim ayının yayımlanmış TÜFE verisi kullanılır; tahminle tamamlama yapılmaz."),
      href: "/credit#growth",
      facts: [fact("real_growth", "Real, constant-currency growth", "Reel, sabit kurla büyüme", realConstantFx), fact("nominal_growth", "Latest nominal growth", "Son nominal büyüme", nominal), runFact("negative_run", "Consecutive negative observations", "Ardışık negatif gözlem", realRun, date(realConstantFx), realState !== "unavailable")],
    },
    {
      id: "credit:auto_contraction", sector: "credit", state: autoState,
      title: t("Vehicle loan contraction", "Taşıt kredilerinde daralma"),
      summary: autoState === "unavailable" ? missing : autoState === "active"
        ? available(value(autoLevels))
          ? t("Vehicle loans have contracted for at least eight consecutive published weekly observations. The outstanding balance provides the scale needed to assess its contribution to total credit growth; a small book limits that contribution.", "Taşıt kredileri en az sekiz ardışık yayımlanmış haftalık gözlemde daraldı. Kredi stoku, toplam kredi büyümesine etkisini değerlendirmek için ölçeği gösterir; küçük bir stok bu etkiyi sınırlar.")
          : t("Vehicle loans have contracted for at least eight consecutive published weekly observations. The outstanding balance is unavailable, so the size of its contribution to total credit growth cannot be assessed here.", "Taşıt kredileri en az sekiz ardışık yayımlanmış haftalık gözlemde daraldı. Kredi stoku mevcut olmadığından toplam kredi büyümesine etkisinin boyutu burada değerlendirilemiyor.")
        : t("The condition of negative annual vehicle loan growth for at least eight consecutive observations is not met.", "Taşıt kredilerinde yıllık büyümenin en az sekiz ardışık gözlemde negatif olması koşulu sağlanmıyor."),
      criterion: t("Annual vehicle loan growth is below zero for at least eight consecutive published weekly observations; the latest annual rate must also be negative.", "Taşıt kredilerinde yıllık büyümenin en az sekiz ardışık yayımlanmış haftalık gözlemde sıfırın altında olması; son yıllık büyüme de negatif olmalıdır."),
      rule: `auto_yoy < 0 for ${autoRun}w`, asOf: date(auto), cadence: "weekly", source: weeklySource, href: "/credit#retail",
      facts: [fact("growth", "Vehicle loan growth", "Taşıt kredisi büyümesi", auto), runFact("negative_run", "Consecutive negative observations", "Ardışık negatif gözlem", autoRun, date(auto), autoState !== "unavailable"), { ...fact("loan_book", "Vehicle loan balance", "Taşıt kredisi stoku", autoLevels, "TRYbn"), value: value(autoLevels) == null ? null : value(autoLevels)! / 1000 }],
    },
    {
      id: "credit:unsecured_retail_hot", sector: "credit", state: unsecuredState,
      title: t("Unsecured retail credit growth", "Teminatsız bireysel kredi büyümesi"),
      summary: unsecuredState === "unavailable" ? missing : unsecuredState === "active"
        ? t("Retail cards and general-purpose loans have both outgrown sector credit for at least eight consecutive observations. Asset-quality data provides the related portfolio-risk context.", "Bireysel kredi kartları ve ihtiyaç kredileri en az sekiz ardışık gözlemde sektör kredilerinden hızlı büyüdü. Portföy riski, aktif kalitesi verileriyle birlikte değerlendirilir.")
        : t("The combined condition of both products outgrowing sector credit for eight consecutive observations is not met.", "Her iki ürünün de sekiz ardışık gözlemde sektör kredilerinden hızlı büyümesi koşulu sağlanmıyor."),
      criterion: t("Both retail card and general-purpose loan annual growth exceed sector annual credit growth for at least eight consecutive published weekly observations. Each comparison uses the same observation date; the shorter of the two runs determines the condition.", "Bireysel kredi kartları ile ihtiyaç kredilerinin yıllık büyümesinin en az sekiz ardışık yayımlanmış haftalık gözlemde sektörün yıllık kredi büyümesini aşması. Her karşılaştırma aynı gözlem tarihini kullanır; iki süreden kısa olanı esas alınır."),
      rule: `cards_yoy > sector AND gpl_yoy > sector for ${unsecuredRun}w`, asOf: date(cards), cadence: "weekly", source: weeklySource, href: "/credit#retail",
      facts: [fact("cards_growth", "Retail card growth", "Bireysel kredi kartı büyümesi", cards), fact("general_purpose_growth", "General-purpose loan growth", "İhtiyaç kredisi büyümesi", generalPurpose), fact("sector_growth", "Sector credit growth", "Sektör kredi büyümesi", nominal), runFact("outperformance_run", "Consecutive observations for both products", "İki ürün için ardışık gözlem", unsecuredRun, date(cards), unsecuredState !== "unavailable")],
    },
  ];
}

export async function loadCreditSignals(): Promise<SectorSignal[]> {
  const { weeklyGrowth, weeklySeries, evdsSeries, WEEKLY_BANK_TYPES } = await import("../metrics");
  const { cpiYoYByMonth } = await import("../real-terms");
  const sector = [WEEKLY_BANK_TYPES.SECTOR];
  const [nominal, tl, fx, auto, autoLevels, cards, generalPurpose, usd, cpi] = await Promise.all([
    weeklyGrowth("krediler", "1.0.1", "TOTAL", 52, sector, 104),
    weeklySeries("krediler", "1.0.1", "TL", sector, 156),
    weeklySeries("krediler", "1.0.1", "FX", sector, 156),
    weeklyGrowth("krediler", "1.0.5", "TOTAL", 52, sector, 104),
    weeklySeries("krediler", "1.0.5", "TOTAL", sector, 156),
    weeklyGrowth("krediler", "1.0.8", "TOTAL", 52, sector, 104),
    weeklyGrowth("krediler", "1.0.6", "TOTAL", 52, sector, 104),
    evdsSeries("TP.DK.USD.A", 4), cpiYoYByMonth(),
  ]);
  return buildCreditSignals({ nominal, realConstantFx: deflate(fxAdjustedGrowth(tl, fx, usd), cpi), auto, autoLevels, cards, generalPurpose });
}
