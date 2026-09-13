import { cpiFromIndex, streak, type Pt } from "../desk";
import { realRate } from "../real-terms";
import { LDR_PUBLISHED } from "../ldr";
import { CAR_TARGET } from "../capital-thresholds";
import { signalState, signalText as text, type SectorSignal, type SignalFact } from "./types";

export interface OverviewSignalInputs {
  roe: Pt[];
  cpiAverage: Pt[];
  npl: Pt[];
  car: Pt[];
  ldr: Pt[];
}

const finite = (value: number | null | undefined): value is number => typeof value === "number" && Number.isFinite(value);
const monthly = (rows: Pt[]): Pt[] => rows.map(row => ({ period: row.period.slice(0, 7), value: finite(row.value) ? row.value : null }))
  .sort((a, b) => a.period.localeCompare(b.period));
const latest = (rows: Pt[]) => rows.at(-1);
function monthBefore(period: string, months: number) {
  const [year, month] = period.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1 - months, 1));
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
}

/** Keep a missing CPI month from changing a positional 12-month calculation. */
export function overviewCpiAverage(raw: { period_date: string; value: number | null }[]): Pt[] {
  const levels = new Map(raw.map(row => [row.period_date.slice(0, 7), row.value]));
  const computed = new Map(cpiFromIndex(raw.filter((row): row is { period_date: string; value: number } => finite(row.value))).avg12.map(row => [row.period, row.value]));
  return [...levels.keys()].sort().map(period => ({
    period,
    value: Array.from({ length: 24 }, (_, offset) => monthBefore(period, offset)).every(month => {
      const level = levels.get(month);
      return finite(level) && level > 0;
    })
      ? computed.get(period) ?? null : null,
  }));
}

/** Four legacy overview rules, with explicit availability and observation dates. */
export function evaluateOverviewSignals(input: OverviewSignalInputs): SectorSignal[] {
  const roe = monthly(input.roe), cpi = monthly(input.cpiAverage), npl = monthly(input.npl), car = monthly(input.car), ldr = monthly(input.ldr);
  const source = text("BDDK monthly bulletin; published banking-sector ratios.", "BDDK aylık bülteni; yayımlanan bankacılık sektörü oranları.");
  const unavailable = text("The observations needed to evaluate this criterion are not available.", "Bu ölçütü değerlendirmek için gereken gözlemler mevcut değil.");
  const fact = (key: string, en: string, tr: string, value: number | null | undefined, unit: SignalFact["unit"], asOf: string | null): SignalFact => ({ key, label: text(en, tr), value: finite(value) ? value : null, unit, asOf });

  // Both inputs are monthly. Compare the exact common month; an older CPI
  // observation must not silently substitute for a missing common-month value.
  const roeDate = latest(roe)?.period ?? null, cpiDate = latest(cpi)?.period ?? null;
  const realDate = roeDate && cpiDate ? [roeDate, cpiDate].sort()[0] : roeDate ?? cpiDate;
  const roePoint = roe.find(row => row.period === realDate), cpiPoint = cpi.find(row => row.period === realDate);
  const realRoe = realRate(roePoint?.value ?? null, cpiPoint?.value ?? null);
  const realAvailable = finite(realRoe);

  const nplDate = latest(npl)?.period ?? null;
  const nplWindow: Pt[] = [];
  for (let i = npl.length - 1; i >= 0; i--) {
    const row = npl[i];
    if (!finite(row.value) || (nplWindow.length > 0 && row.period !== monthBefore(nplWindow[0].period, 1))) break;
    nplWindow.unshift(row);
  }
  const nplAvailable = nplWindow.length >= 7;
  const nplRun = nplAvailable ? streak(nplWindow, "up") : null;
  const nplStart = nplRun != null ? nplWindow.at(-1 - nplRun) : undefined;
  const nplNow = latest(npl)?.value ?? null;

  const carPoint = latest(car), carDate = carPoint?.period ?? null;
  const carPrior = carDate ? car.find(row => row.period === monthBefore(carDate, 12)) : undefined;
  const carChange = finite(carPoint?.value) && finite(carPrior?.value) ? carPoint.value - carPrior.value : null;
  const carBuffer = finite(carPoint?.value) ? carPoint.value - CAR_TARGET : null;
  const ldrPoint = latest(ldr), ldrDate = ldrPoint?.period ?? null;

  return [
    {
      id: "overview:real-roe", sector: "overview", state: signalState(realAvailable, realAvailable && realRoe < 0),
      title: text("Real return on equity", "Reel özkaynak kârlılığı"),
      summary: !realAvailable ? unavailable : realRoe < 0
        ? text("Annualized return on equity is negative after adjustment for 12-month-average CPI inflation.", "Yıllıklandırılmış özkaynak kârlılığı, 12 aylık ortalama TÜFE enflasyonu ile düzeltildiğinde negatif.")
        : text("Annualized return on equity is at or above 12-month-average CPI inflation.", "Yıllıklandırılmış özkaynak kârlılığı, 12 aylık ortalama TÜFE enflasyonu düzeyinde veya üzerinde."),
      criterion: text("Fisher-adjusted ROE is below zero: (1 + ROE/100) ÷ (1 + 12-month-average CPI/100) − 1 < 0. Both inputs use the same month.", "Fisher yöntemiyle düzeltilmiş özkaynak kârlılığı sıfırın altında: (1 + ROE/100) ÷ (1 + 12 aylık ortalama TÜFE/100) − 1 < 0. İki girdi aynı aya aittir."),
      rule: "(1+roe)/(1+cpi_12m_avg) − 1 < 0", asOf: realDate, cadence: "monthly",
      source: text("BDDK published annualized sector ROE; TÜİK CPI via TCMB EVDS. Deflator is the arithmetic average of 12 monthly year-on-year CPI rates, aligned to the ROE month.", "BDDK yayımlanmış yıllıklandırılmış sektör ROE oranı; TCMB EVDS üzerinden TÜİK TÜFE. Deflatör, ROE ayıyla eşleştirilen 12 aylık yıllık TÜFE oranlarının aritmetik ortalamasıdır."),
      href: "/profitability#returns", facts: [
        fact("roe", "Annualized ROE", "Yıllıklandırılmış ROE", roePoint?.value, "percent", roePoint?.period ?? realDate),
        fact("cpi-average", "12-month-average CPI", "12 aylık ortalama TÜFE", cpiPoint?.value, "percent", cpiPoint?.period ?? realDate),
        fact("real-roe", "Fisher-adjusted ROE", "Fisher yöntemiyle reel ROE", realRoe, "percent", realDate),
      ],
    },
    {
      id: "overview:npl-streak", sector: "overview", state: signalState(nplAvailable, nplRun != null && nplRun >= 6),
      title: text("Consecutive NPL-ratio increases", "Takipteki kredi oranında ardışık artış"),
      summary: !nplAvailable ? unavailable : nplRun != null && nplRun >= 6
        ? text("The sector NPL ratio has risen for at least six consecutive months. Quarterly Stage 2 disclosures provide additional context.", "Sektörün takipteki kredi oranı en az altı ay üst üste yükseldi. Üç aylık ikinci aşama kredi açıklamaları ek bağlam sağlar.")
        : text("The latest uninterrupted rise in the sector NPL ratio is shorter than six months.", "Sektörün takipteki kredi oranındaki son kesintisiz artış dönemi altı aydan kısa."),
      criterion: text("At least six consecutive strictly positive monthly changes in the sector NPL ratio. Seven consecutive monthly observations are required; 3% is a level comparison, not the trigger.", "Sektörün takipteki kredi oranında en az altı ardışık aylık artış. Yedi ardışık aylık gözlem gerekir; %3 düzey karşılaştırmasıdır, tetikleme eşiği değildir."),
      rule: "consecutive_rise(npl) ≥ 6m", asOf: nplDate, cadence: "monthly", source, href: "/asset-quality#npl",
      facts: [
        fact("consecutive-rises", "Consecutive monthly increases", "Ardışık aylık artış", nplRun, "months", nplDate),
        fact("npl-start", "NPL ratio at start of the run", "Artış dönemi başındaki takipteki kredi oranı", nplStart?.value, "percent", nplStart?.period ?? null),
        fact("npl-current", "Latest NPL ratio", "Son takipteki kredi oranı", nplNow, "percent", nplDate),
        fact("level-reference", "NPL level reference", "Takipteki kredi oranı düzey referansı", 3, "percent", nplDate),
      ],
    },
    {
      id: "overview:car-drift", sector: "overview", state: signalState(carChange != null, carChange != null && carChange < -0.5),
      title: text("Annual change in capital adequacy", "Sermaye yeterliliğinde yıllık değişim"),
      summary: carChange == null ? unavailable : carChange < -0.5
        ? text("The sector capital adequacy ratio has declined by more than 0.5 percentage points over twelve months.", "Sektör sermaye yeterlilik oranı on iki ayda 0,5 yüzde puandan fazla geriledi.")
        : text("The twelve-month change in the sector capital adequacy ratio is at or above −0.5 percentage points.", "Sektör sermaye yeterlilik oranının on iki aylık değişimi −0,5 yüzde puan düzeyinde veya üzerinde."),
      criterion: text("The latest capital adequacy ratio minus the same month's ratio one year earlier is below −0.5 percentage points. The buffer is separately measured against the 12% BDDK target.", "Son sermaye yeterlilik oranı ile bir yıl önce aynı ayın oranı arasındaki fark −0,5 yüzde puanın altında. Sermaye tamponu ayrıca BDDK'nın %12 hedef oranına göre ölçülür."),
      rule: "Δcar_12m < −0.5pp", asOf: carDate, cadence: "monthly", source, href: "/capital#adequacy",
      facts: [
        fact("car-current", "Latest capital adequacy ratio", "Son sermaye yeterlilik oranı", carPoint?.value, "percent", carDate),
        fact("car-prior", "Capital adequacy ratio one year earlier", "Bir yıl önceki sermaye yeterlilik oranı", carPrior?.value, "percent", carPrior?.period ?? null),
        fact("car-change", "Twelve-month change", "On iki aylık değişim", carChange, "pp", carDate),
        fact("capital-buffer", "Buffer over the 12% target", "%12 hedef üzerindeki tampon", carBuffer, "pp", carDate),
      ],
    },
    {
      id: "overview:funding-stretch", sector: "overview", state: signalState(finite(ldrPoint?.value), finite(ldrPoint?.value) && ldrPoint.value > LDR_PUBLISHED.line),
      title: text("Loan-to-deposit ratio, all currencies", "Kredi/mevduat oranı, tüm para birimleri"),
      summary: !finite(ldrPoint?.value) ? unavailable : ldrPoint.value > LDR_PUBLISHED.line
        ? text("The published sector loan-to-deposit ratio exceeds 100%. The weekly TL-only funding ratio is a separate measure.", "Yayımlanmış sektör kredi/mevduat oranı %100'ü aşıyor. Haftalık TL kredi/mevduat oranı ayrı bir ölçüdür.")
        : text("The published sector loan-to-deposit ratio is at or below 100%.", "Yayımlanmış sektör kredi/mevduat oranı %100 düzeyinde veya altında."),
      criterion: text("BDDK's published monthly sector loan-to-deposit ratio, including TL and foreign currency, is above 100%.", "BDDK'nın yayımladığı, TL ve yabancı para kalemlerini içeren aylık sektör kredi/mevduat oranı %100'ün üzerinde."),
      rule: LDR_PUBLISHED.rule, asOf: ldrDate, cadence: "monthly",
      source: text(LDR_PUBLISHED.basis, "BDDK yayımlanmış sektör oranı; aylık, tüm para birimleri."), href: "/deposits#loan-funding",
      facts: [
        fact("loan-deposit", "Published loan-to-deposit ratio, TL+FC", "Yayımlanmış kredi/mevduat oranı, TL+YP", ldrPoint?.value, "percent", ldrDate),
        fact("reference", "Comparison threshold", "Karşılaştırma eşiği", LDR_PUBLISHED.line, "percent", ldrDate),
      ],
    },
  ];
}

export async function loadOverviewSignals(): Promise<SectorSignal[]> {
  const { ratioRoe, ratioNpl, ratioCar, ratioLdr, evdsSeries, BANK_TYPES } = await import("../metrics");
  const sector = [BANK_TYPES.SECTOR];
  const [roe, npl, car, ldr, cpi] = await Promise.all([
    ratioRoe(sector), ratioNpl(sector), ratioCar(sector), ratioLdr(sector), evdsSeries("TP.TUKFIY2025.GENEL", 10),
  ]);
  return evaluateOverviewSignals({ roe, npl, car, ldr, cpiAverage: overviewCpiAverage(cpi) });
}
