import { capitalStack, detectStep, type Pt } from "../capital";
import { CAR_TARGET, CET1_MIN, CET1_TARGET } from "../capital-thresholds";
import type { BankCapitalRow } from "../audit-ratios";
import { signalState, signalText as text, type SectorSignal, type SignalFact } from "./types";

export interface CapitalSignalInputs {
  car: readonly Pt[];
  capitalRatios: readonly (Pt & { bank_type_code: string })[];
  banks: { period: string | null; rows: readonly BankCapitalRow[] };
  equityGrowth: readonly Pt[];
  assetGrowth: readonly Pt[];
}

const finite = (value: number | null | undefined): value is number =>
  value != null && Number.isFinite(value);
const fact = (key: string, en: string, tr: string, value: number | null | undefined, unit: SignalFact["unit"], asOf: string | null): SignalFact =>
  ({ key, label: text(en, tr), value: finite(value) ? value : null, unit, asOf });

/** The five original capital rules, independently evaluable without D1 or React. */
export function evaluateCapitalSignals(input: CapitalSignalInputs): SectorSignal[] {
  const car = input.car.at(-1);
  const carDate = car?.period ?? null;
  const buffer = finite(car?.value) ? car.value - CAR_TARGET : null;
  const step = detectStep(input.car, { window: 13, k: 3 });
  const carWindow = input.car.slice(-13);
  const monthIndex = (period: string) => Number(period.slice(0, 4)) * 12 + Number(period.slice(5, 7));
  const stepAvailable = step != null && carWindow.every((row, i) => finite(row.value) &&
    (i === 0 || monthIndex(row.period) - monthIndex(carWindow[i - 1].period) === 1));
  const stack = capitalStack(input.capitalRatios).at(-1) ?? null;
  const auditDate = input.capitalRatios.map(row => row.period).sort().at(-1) ?? null;
  const stackAvailable = stack != null && stack.period === auditDate;
  const hybrids = stack ? stack.at1 + stack.t2 : null;
  const auditBuffer = stack ? stack.car - CAR_TARGET : null;
  const disclosed = input.banks.rows.filter(row => finite(row.cet1));
  const thin = disclosed.filter(row => row.cet1! < CET1_TARGET).length;
  const belowTotalTarget = disclosed.filter(row => row.cet1! < CAR_TARGET).length;
  // An observed bank below the threshold proves the existential rule. Missing
  // CET1 values may never prove that the entire register is clear.
  const bankAvailable = input.banks.period != null && disclosed.length > 0 &&
    (thin > 0 || disclosed.length === input.banks.rows.length);
  const eq = input.equityGrowth.at(-1);
  const assets = input.assetGrowth.at(-1);
  const gap = finite(eq?.value) && finite(assets?.value) ? eq.value - assets.value : null;
  const growthAvailable = gap != null && eq?.period === assets?.period;
  const monthly = text(
    "BDDK monthly bulletin, published sector ratios. Monthly observations are separate from audited quarterly capital figures.",
    "BDDK aylık bülteni, yayımlanan sektör oranları. Aylık gözlemler, bağımsız denetimden geçmiş üç aylık sermaye verilerinden ayrıdır.",
  );
  const audited = text(
    "BRSA quarterly financial statements of reporting banks. Sector ratios use summed capital divided by summed risk-weighted assets; compare the buffer and instruments on this same audited basis.",
    "Veri açıklayan bankaların BDDK formatındaki üç aylık finansal tabloları. Sektör oranları toplam sermayenin toplam risk ağırlıklı varlıklara bölünmesiyle hesaplanır; tampon ve sermaye araçları aynı denetlenmiş veri esasına göre karşılaştırılır.",
  );
  const missing = text("Required observations are unavailable; the criterion cannot be evaluated.", "Gerekli gözlemler mevcut değil; ölçüt değerlendirilemiyor.");

  return [
    {
      id: "capital:structural-break", sector: "capital", state: signalState(stepAvailable, !!step?.isBreak),
      title: text("Capital-ratio level shift", "Sermaye yeterlilik oranında seviye değişimi"),
      summary: !stepAvailable ? missing : step!.isBreak
        ? text("A monthly capital-ratio change exceeds the comparison threshold. A twelve-month trend spanning this observation would largely describe the level shift.", "Sermaye yeterlilik oranındaki aylık değişim karşılaştırma eşiğini aşıyor. Bu gözlemi içeren on iki aylık eğilim, büyük ölçüde seviye değişimini yansıtır.")
        : text("The largest monthly change does not meet the level-shift criterion.", "En büyük aylık değişim, seviye değişimi ölçütünü karşılamıyor."),
      criterion: text("Among up to 13 published monthly readings, the largest absolute change must exceed three times the mean absolute change of the other months; that mean must be positive.", "En fazla 13 yayımlanmış aylık gözlemdeki en büyük mutlak değişim, diğer ayların ortalama mutlak değişiminin üç katını aşmalıdır; karşılaştırma ortalaması pozitif olmalıdır."),
      rule: "|Δ1m| > 3 × mean(|Δ1m|, 13m)", asOf: carDate, cadence: "monthly", source: monthly, href: "/capital#adequacy",
      facts: [
        fact("largest-move", "Largest monthly change", "En büyük aylık değişim", stepAvailable ? step?.delta : null, "pp", step?.period ?? null),
        fact("typical-move", "Mean absolute change in other months", "Diğer aylardaki ortalama mutlak değişim", stepAvailable ? step?.typical : null, "pp", carDate),
        fact("comparison-multiple", "Threshold multiple", "Eşik çarpanı", 3, "ratio", carDate),
        fact("window", "Maximum observation window", "Azami gözlem aralığı", 13, "months", carDate),
      ],
    },
    {
      id: "capital:hybrid-buffer", sector: "capital", state: signalState(stackAvailable, hybrids != null && auditBuffer != null && hybrids > auditBuffer),
      title: text("Capital-buffer composition", "Sermaye tamponunun bileşimi"),
      summary: !stackAvailable ? missing : hybrids! > auditBuffer!
        ? text("Additional Tier 1 and Tier 2 exceed the audited buffer above the total-capital target. Common equity alone is below that total-capital target; this describes composition, not a CET1 breach.", "İlave ana sermaye ve katkı sermaye, toplam sermaye hedefi üzerindeki denetlenmiş tamponu aşıyor. Çekirdek sermaye tek başına toplam sermaye hedefinin altında; bu bir bileşim tespitidir, çekirdek sermaye ihlali değildir.")
        : text("Additional Tier 1 and Tier 2 do not exceed the audited buffer above the total-capital target.", "İlave ana sermaye ve katkı sermaye, toplam sermaye hedefi üzerindeki denetlenmiş tamponu aşmıyor."),
      criterion: text(`AT1 + Tier 2 > audited total capital ratio − ${CAR_TARGET}%. The ${CAR_TARGET}% level is BDDK's total-capital target, not the statutory minimum.`, `İlave ana sermaye + katkı sermaye > denetlenmiş toplam sermaye oranı − %${CAR_TARGET}. %${CAR_TARGET}, BDDK'nın toplam sermaye hedefidir; yasal asgari oran değildir.`),
      rule: `at1 + tier2 > car_audited − ${CAR_TARGET}`, asOf: auditDate, cadence: "quarterly", source: audited, href: "/capital#composition",
      facts: [
        fact("at1", "Additional Tier 1", "İlave ana sermaye", stack?.at1, "pp", stack?.period ?? auditDate),
        fact("tier2", "Tier 2", "Katkı sermaye", stack?.t2, "pp", stack?.period ?? auditDate),
        fact("instruments", "AT1 + Tier 2", "İlave ana sermaye + katkı sermaye", hybrids, "pp", stack?.period ?? auditDate),
        fact("audited-car", "Audited total capital ratio", "Denetlenmiş toplam sermaye oranı", stack?.car, "percent", stack?.period ?? auditDate),
        fact("audited-buffer", "Audited buffer above target", "Hedef üzerindeki denetlenmiş tampon", auditBuffer, "pp", stack?.period ?? auditDate),
        fact("cet1", "Common equity Tier 1 ratio", "Çekirdek sermaye oranı", stack?.cet1, "percent", stack?.period ?? auditDate),
        fact("car-target", "BDDK total-capital target", "BDDK toplam sermaye hedefi", CAR_TARGET, "percent", auditDate),
      ],
    },
    {
      id: "capital:thin-cet1", sector: "capital", state: signalState(bankAvailable, thin > 0),
      title: text("Common-equity conservation buffer", "Çekirdek sermaye koruma tamponu"),
      summary: !bankAvailable ? text("The disclosed CET1 observations do not establish a complete comparison; missing bank ratios cannot be treated as clear.", "Açıklanan çekirdek sermaye oranları tam bir karşılaştırma sağlamıyor; eksik banka oranları eşik aşılmamış gibi değerlendirilemez.") : thin > 0
        ? text("At least one reporting bank is below the common-equity conservation-buffer threshold. Entering the buffer restricts distributions; the hard minimum is a separate threshold. Additional systemic-bank buffers are excluded because BDDK designations are unavailable.", "En az bir veri açıklayan banka, çekirdek sermaye koruma tamponu eşiğinin altında. Tampona girilmesi dağıtımları kısıtlar; yasal asgari oran ayrı bir eşiktir. BDDK sınıflandırmaları mevcut olmadığından sistemik bankalara ait ek tamponlar teste dahil değildir.")
        : text("All banks in the available register disclose CET1 at or above the conservation-buffer threshold. CET1 below the total-capital target is a composition observation, since AT1 and Tier 2 also meet that target. Additional systemic-bank buffers are not tested.", "Mevcut listedeki tüm bankalar, koruma tamponu eşiğinde veya üzerinde çekirdek sermaye açıklıyor. Çekirdek sermayenin toplam sermaye hedefinin altında olması bir bileşim tespitidir; ilave ana sermaye ve katkı sermaye de bu hedefe dahildir. Sistemik bankalara ait ek tamponlar test edilmiyor."),
      criterion: text(`At least one disclosed CET1 ratio < ${CET1_TARGET}% (${CET1_MIN}% minimum + 2.5 percentage points conservation buffer). This test alone does not classify a statutory breach.`, `En az bir açıklanan çekirdek sermaye oranı < %${CET1_TARGET} (%${CET1_MIN} asgari oran + 2,5 yüzde puan koruma tamponu). Bu test tek başına yasal ihlal sınıflandırması yapmaz.`),
      rule: `count(cet1 < ${CET1_TARGET}%) > 0`, asOf: input.banks.period, cadence: "quarterly", source: audited, href: "/capital#banks",
      facts: [
        fact("below-cet1-target", "Banks below CET1 buffer threshold", "Çekirdek sermaye tamponu eşiğinin altındaki bankalar", disclosed.length ? thin : null, "count", input.banks.period),
        fact("banks", "Banks in register", "Listedeki banka sayısı", input.banks.rows.length, "count", input.banks.period),
        fact("disclosed", "Banks disclosing CET1", "Çekirdek sermaye açıklayan bankalar", disclosed.length, "count", input.banks.period),
        fact("missing", "Banks with missing CET1", "Çekirdek sermaye oranı eksik bankalar", input.banks.rows.length - disclosed.length, "count", input.banks.period),
        fact("below-total-target", "Banks with CET1 below total-capital target", "Çekirdek sermayesi toplam sermaye hedefinin altındaki bankalar", disclosed.length ? belowTotalTarget : null, "count", input.banks.period),
        fact("cet1-target", "CET1 buffer threshold", "Çekirdek sermaye tamponu eşiği", CET1_TARGET, "percent", input.banks.period),
        fact("cet1-minimum", "Statutory CET1 minimum", "Yasal asgari çekirdek sermaye oranı", CET1_MIN, "percent", input.banks.period),
        fact("conservation-buffer", "Conservation buffer", "Sermaye koruma tamponu", CET1_TARGET - CET1_MIN, "pp", input.banks.period),
        fact("total-target", "Total-capital target", "Toplam sermaye hedefi", CAR_TARGET, "percent", input.banks.period),
      ],
    },
    {
      id: "capital:generation-gap", sector: "capital", state: signalState(growthAvailable, gap != null && gap < 0),
      title: text("Equity growth relative to assets", "Özkaynak büyümesinin aktiflerle karşılaştırması"),
      summary: !growthAvailable ? text("Equity and asset growth are not both available for the same latest month.", "Özkaynak ve aktif büyümesi aynı son ay için birlikte mevcut değil.") : gap! < 0
        ? text("Assets are growing faster than the equity supporting the balance sheet.", "Aktifler, bilançoyu taşıyan özkaynaklardan daha hızlı büyüyor.")
        : text("Equity growth is at least as high as asset growth.", "Özkaynak büyümesi aktif büyümesine eşit veya daha yüksek."),
      criterion: text("Annual equity growth minus annual asset growth < 0 percentage points.", "Yıllık özkaynak büyümesi eksi yıllık aktif büyümesi < 0 yüzde puan."),
      rule: "equity_yoy − assets_yoy < 0", asOf: eq?.period ?? assets?.period ?? null, cadence: "monthly", source: monthly, href: "/capital#leverage",
      facts: [
        fact("equity-growth", "Annual equity growth", "Yıllık özkaynak büyümesi", eq?.value, "percent", eq?.period ?? null),
        fact("asset-growth", "Annual asset growth", "Yıllık aktif büyümesi", assets?.value, "percent", assets?.period ?? null),
        fact("growth-gap", "Equity growth minus asset growth", "Özkaynak büyümesi eksi aktif büyümesi", growthAvailable ? gap : null, "pp", eq?.period ?? null),
      ],
    },
    {
      id: "capital:thin-buffer", sector: "capital", state: signalState(buffer != null, buffer != null && buffer < 2),
      title: text("Buffer above the capital target", "Sermaye hedefi üzerindeki tampon"),
      summary: buffer == null ? missing : buffer < 2
        ? text("The published sector capital ratio is less than two percentage points above BDDK's target.", "Yayımlanan sektör sermaye yeterlilik oranının BDDK hedefine farkı iki yüzde puandan az.")
        : text("The published sector capital ratio is at least two percentage points above BDDK's target.", "Yayımlanan sektör sermaye yeterlilik oranının BDDK hedefine farkı en az iki yüzde puan."),
      criterion: text(`Published sector CAR − ${CAR_TARGET}% < 2 percentage points. This compares with the target, not the statutory minimum.`, `Yayımlanan sektör sermaye yeterlilik oranı − %${CAR_TARGET} < 2 yüzde puan. Karşılaştırma yasal asgari oranla değil, hedef oranla yapılır.`),
      rule: `car − ${CAR_TARGET} < 2pp`, asOf: carDate, cadence: "monthly", source: monthly, href: "/capital#adequacy",
      facts: [fact("car", "Published capital adequacy ratio", "Yayımlanan sermaye yeterlilik oranı", car?.value, "percent", carDate), fact("buffer", "Buffer above target", "Hedef üzerindeki tampon", buffer, "pp", carDate), fact("target", "BDDK target", "BDDK hedefi", CAR_TARGET, "percent", carDate), fact("threshold", "Buffer threshold", "Tampon eşiği", 2, "pp", carDate)],
    },
  ];
}

export async function loadCapitalSignals(): Promise<SectorSignal[]> {
  const metrics = await import("../metrics");
  const audited = await import("../audit-ratios");
  const sector = [metrics.BANK_TYPES.SECTOR];
  const [car, capitalRatios, banks, equityGrowth, assetGrowth] = await Promise.all([
    metrics.ratioCar(sector), audited.sectorCapitalRatios(), audited.perBankCapital(),
    metrics.equityYoY(sector), metrics.totalAssetsYoY(sector),
  ]);
  return evaluateCapitalSignals({ car, capitalRatios, banks, equityGrowth, assetGrowth });
}
