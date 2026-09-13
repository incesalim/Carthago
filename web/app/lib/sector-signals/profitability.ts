import { bridge, costIncome, engine, key, RECONCILE_TOLERANCE, type BsRow, type PnlRow } from "../profitability";
import { realRate } from "../real-terms";
import type { Pt } from "../capital";
import { signalState, signalText as text, type SectorSignal, type SignalFact } from "./types";

export interface ProfitabilitySignalInputs {
  roe: readonly Pt[];
  cpi: readonly { period_date: string; value: number | null }[];
  pnl: readonly PnlRow[];
  deposits: readonly BsRow[];
}
const finite = (value: number | null | undefined): value is number => value != null && Number.isFinite(value);
const fact = (key: string, en: string, tr: string, value: number | null | undefined, unit: SignalFact["unit"], asOf: string | null): SignalFact =>
  ({ key, label: text(en, tr), value: finite(value) ? value : null, unit, asOf });
const monthIndex = (period: string) => Number(period.slice(0, 4)) * 12 + Number(period.slice(5, 7));

/** Same 12-month mean of CPI year-on-year rates used on /profitability. */
export function profitabilityCpiAverage(input: ProfitabilitySignalInputs["cpi"]): Pt[] {
  const rows = [...input].sort((a, b) => a.period_date.localeCompare(b.period_date));
  const yoy: { period: string; value: number }[] = [];
  for (let i = 12; i < rows.length; i++) {
    const now = rows[i].value, previous = rows[i - 12].value;
    if (finite(now) && finite(previous) && previous > 0) {
      yoy.push({ period: rows[i].period_date.slice(0, 7), value: (now / previous - 1) * 100 });
    }
  }
  const average: Pt[] = [];
  for (let i = 11; i < yoy.length; i++) {
    let sum = 0;
    for (let j = i - 11; j <= i; j++) sum += yoy[j].value;
    average.push({ period: yoy[i].period, value: sum / 12 });
  }
  return average;
}

/** Retains the original five rules; absent P&L fields cannot become zero inputs. */
export function evaluateProfitabilitySignals(input: ProfitabilitySignalInputs): SectorSignal[] {
  const pnl = [...input.pnl].sort((a, b) => key(a).localeCompare(key(b)));
  const latestPnl = pnl.at(-1);
  const pnlDate = latestPnl ? key(latestPnl) : null;
  const cpi = [...input.cpi].sort((a, b) => a.period_date.localeCompare(b.period_date));
  const cpiAverages = profitabilityCpiAverage(cpi);
  const availableCpi = new Map(cpiAverages.filter(average => {
    const end = cpi.findIndex(row => row.period_date.slice(0, 7) === average.period);
    const window = cpi.slice(Math.max(0, end - 23), end + 1);
    return window.length === 24 && window.every((row, i) => finite(row.value) && row.value > 0 &&
      (i === 0 || monthIndex(row.period_date) - monthIndex(window[i - 1].period_date) === 1));
  }).map(row => [row.period, row.value]));
  const cpiDate = cpi.at(-1)?.period_date.slice(0, 7) ?? null;
  const cpiValue = cpiDate ? availableCpi.get(cpiDate) ?? null : null;
  const roe = input.roe.at(-1);
  const roeValue = finite(roe?.value) ? roe.value : null;
  const roeComparisonDate = roe?.period && cpiDate ? [roe.period, cpiDate].sort()[0] : roe?.period ?? cpiDate;
  const roeComparison = input.roe.find(row => row.period === roeComparisonDate);
  const roeCpi = roeComparisonDate ? availableCpi.get(roeComparisonDate) ?? null : null;
  const real = realRate(roeComparison?.value, roeCpi);

  const deposits = [...input.deposits].sort((a, b) => key(a).localeCompare(key(b)));
  const fundingCompleteAt = (period: string) => {
    const row = pnl.find(row => key(row) === period);
    const depositIndex = deposits.findIndex(row => key(row) === period);
    const window = depositIndex < 0 ? [] : deposits.slice(Math.max(0, depositIndex - 12), depositIndex + 1);
    return row != null && finite(row.dep_int) && finite(row.net) && window.length > 0 &&
      window.every(row => [row.demand, row.time_dep, row.total_dep, row.equity].every(finite));
  };
  const fundingRows = engine(pnl, deposits).filter(row => fundingCompleteAt(row.period));
  const funding = fundingRows.find(row => row.period === pnlDate) ?? null;
  const fundingComparisonDate = pnlDate && cpiDate ? [pnlDate, cpiDate].sort()[0] : pnlDate ?? cpiDate;
  const fundingComparison = fundingRows.find(row => row.period === fundingComparisonDate);
  const fundingCpi = fundingComparisonDate ? availableCpi.get(fundingComparisonDate) ?? null : null;
  const ciRows = costIncome(pnl);
  const ciComplete = latestPnl != null && [latestPnl.nii, latestPnl.fees, latestPnl.opex].every(finite);
  const ci = ciComplete ? ciRows.find(row => row.period === pnlDate) ?? null : null;
  const ciPrior = ciRows.at(-13) ?? null;
  const ciPriorPnl = ciPrior ? pnl.find(row => key(row) === ciPrior.period) : null;
  const ciPriorValue = ciPriorPnl && [ciPriorPnl.nii, ciPriorPnl.fees, ciPriorPnl.opex].every(finite) ? ciPrior!.value : null;
  const priorPnl = latestPnl?.month === 1 ? latestPnl : pnl.find(row => latestPnl && row.year === latestPnl.year && row.month === latestPnl.month - 1);
  const bridgeFields = ["nii", "prov", "fees", "opex", "other", "tax", "net"] as const;
  const bridgeComplete = latestPnl != null && priorPnl != null && bridgeFields.every(field => finite(latestPnl[field]) && finite(priorPnl[field]));
  const reconciled = bridgeComplete ? bridge(pnl) : null;
  const fundingGap = fundingComparison && fundingCpi != null ? fundingComparison.blended - fundingCpi : null;

  const missing = text("Required observations are unavailable; the criterion cannot be evaluated.", "Gerekli gözlemler mevcut değil; ölçüt değerlendirilemiyor.");
  const fundingSource = text(
    "BDDK monthly sector income statement and deposit balance sheet. YTD amounts are annualized by 12/month; deposit and equity balances use the existing average of up to 13 observations. Pricing demand deposits is an illustrative cost calculation, excluding servicing costs and behavioral responses, not a forecast.",
    "BDDK aylık sektör gelir tablosu ve mevduat bilançosu. Yılbaşından itibaren biriken tutarlar 12/ay ile yıllıklandırılır; mevduat ve özkaynak bakiyelerinde mevcut en fazla 13 gözlemin ortalaması kullanılır. Vadesiz mevduata faiz ödenmesi; hizmet maliyetlerini ve davranışsal tepkileri içermeyen örnek bir maliyet hesabıdır, tahmin değildir.",
  );
  const cpiSource = text(
    "BDDK published annualized sector ROE and TCMB EVDS/TÜİK CPI (TP.TUKFIY2025.GENEL). Inflation is the arithmetic mean of 12 monthly year-on-year CPI rates; Fisher deflation is (1 + ROE)/(1 + CPI) − 1. The comparison uses the latest common observation month. Separately dated latest readings are retained as context.",
    "BDDK'nın yayımladığı yıllıklandırılmış sektör özkaynak kârlılığı ve TCMB EVDS/TÜİK TÜFE serisi (TP.TUKFIY2025.GENEL). Enflasyon, 12 aylık yıllık TÜFE değişimlerinin aritmetik ortalamasıdır; Fisher düzeltmesi (1 + özkaynak kârlılığı)/(1 + TÜFE) − 1 biçimindedir. Karşılaştırma son ortak gözlem ayını kullanır. Serilerin son değerleri, kendi tarihleriyle ayrıca korunur.",
  );

  return [
    {
      id: "profitability:free-funding", sector: "profitability", state: signalState(funding != null, funding != null && funding.ratio > 1),
      title: text("Dependence on demand-deposit funding", "Vadesiz mevduat fonlamasına bağımlılık"),
      summary: !funding ? missing : funding.ratio > 1
        ? text("Pricing demand deposits at the sector's paid-deposit rate would cost more than annualized sector net profit. Returns are sensitive to the funding mix under this illustrative assumption.", "Vadesiz mevduata sektörün faiz ödenen mevduat oranı uygulanması, yıllıklandırılmış sektör net kârından yüksek bir maliyet doğuruyor. Bu örnek varsayım altında getiri, fonlama bileşimine duyarlı.")
        : text("The illustrative annual cost of pricing demand deposits does not exceed annualized sector net profit.", "Vadesiz mevduata faiz ödenmesinin örnek yıllık maliyeti, yıllıklandırılmış sektör net kârını aşmıyor."),
      criterion: text("Demand deposits priced at the paid-deposit rate / annualized net profit > 1.", "Faiz ödenen mevduat oranıyla fiyatlanan vadesiz mevduat maliyeti / yıllıklandırılmış net kâr > 1."),
      rule: "demand_book_at_paid_rate / net_profit > 1", asOf: pnlDate, cadence: "monthly", source: fundingSource, href: "/profitability#funding-cost",
      facts: [
        fact("paid-rate", "Rate paid on interest-bearing deposits", "Faiz ödenen mevduata uygulanan oran", funding?.paidOnTime, "percent", pnlDate),
        fact("funding-value", "Illustrative annual cost", "Örnek yıllık maliyet", funding?.worth, "TRYtrn", pnlDate),
        fact("annual-profit", "Annualized net profit", "Yıllıklandırılmış net kâr", funding?.profit, "TRYtrn", pnlDate),
        fact("cost-profit-ratio", "Illustrative cost / profit", "Örnek maliyet / kâr", funding?.ratio, "ratio", pnlDate),
        fact("demand-share", "Demand-deposit share", "Vadesiz mevduat payı", funding?.demandShare, "percent", pnlDate),
      ],
    },
    {
      id: "profitability:real-roe", sector: "profitability", state: signalState(real != null, real != null && real < 0),
      title: text("Inflation-adjusted return on equity", "Enflasyondan arındırılmış özkaynak kârlılığı"),
      summary: real == null ? missing : real < 0
        ? text("Published ROE is negative in real terms after Fisher deflation with average CPI.", "Yayımlanan özkaynak kârlılığı, ortalama TÜFE ile Fisher düzeltmesi sonrasında reel olarak negatif.")
        : text("Published ROE is non-negative in real terms after Fisher deflation with average CPI.", "Yayımlanan özkaynak kârlılığı, ortalama TÜFE ile Fisher düzeltmesi sonrasında reel olarak sıfır veya pozitif."),
      criterion: text("(1 + ROE)/(1 + 12-month-average CPI) − 1 < 0. Inputs are rates; the result is a real percentage rate, not a percentage-point gap.", "(1 + özkaynak kârlılığı)/(1 + 12 aylık ortalama TÜFE) − 1 < 0. Girdiler oran olarak kullanılır; sonuç yüzde puan farkı değil, reel yüzde oranıdır."),
      rule: "(1+roe)/(1+cpi_12m_avg) − 1 < 0", asOf: roeComparisonDate, cadence: "monthly", source: cpiSource, href: "/profitability#returns",
      facts: [fact("roe", "ROE in comparison month", "Karşılaştırma ayındaki özkaynak kârlılığı", roeComparison?.value, "percent", roeComparisonDate), fact("average-cpi", "12-month-average CPI in comparison month", "Karşılaştırma ayındaki 12 aylık ortalama TÜFE", roeCpi, "percent", roeComparisonDate), fact("real-roe", "Fisher-deflated ROE", "Fisher düzeltmeli reel özkaynak kârlılığı", real, "percent", roeComparisonDate), fact("latest-roe", "Latest published ROE", "Son yayımlanan özkaynak kârlılığı", roeValue, "percent", roe?.period ?? null), fact("latest-average-cpi", "Latest 12-month-average CPI inflation", "Son 12 aylık ortalama TÜFE enflasyonu", cpiValue, "percent", cpiDate)],
    },
    {
      id: "profitability:cost-income", sector: "profitability", state: signalState(ci != null, ci != null && ci.value > 50),
      title: text("Cost-to-income ratio", "Gider / gelir oranı"),
      summary: !ci ? missing : ci.value > 50
        ? text("Operating expenses consume more than half of income. The prior-year comparison is shown separately; the threshold alone does not establish a rising trend.", "Faaliyet giderleri gelirin yarısından fazlasını tüketiyor. Önceki yıl karşılaştırması ayrıca gösterilir; tek başına bu eşik yükseliş eğilimi kanıtlamaz.")
        : text("Operating expenses consume at most half of income.", "Faaliyet giderleri gelirin en fazla yarısını tüketiyor."),
      criterion: text("Non-interest expenses / (net interest income + non-interest income) > 50%.", "Faiz dışı giderler / (net faiz geliri + faiz dışı gelirler) > %50."),
      rule: "cost_income > 50%", asOf: pnlDate, cadence: "monthly", source: text("BDDK monthly cumulative-YTD sector income statement. The current and 12-observation-prior ratios use the same costIncome calculation.", "BDDK aylık, yılbaşından itibaren birikimli sektör gelir tablosu. Güncel oran ve 12 gözlem önceki oran aynı gider/gelir hesabını kullanır."), href: "/profitability#margins",
      facts: [fact("cost-income", "Current cost / income", "Güncel gider / gelir", ci?.value, "percent", pnlDate), fact("cost-income-prior", "Cost / income, 12 observations earlier", "12 gözlem önce gider / gelir", ciPriorValue, "percent", ciPrior?.period ?? null), fact("threshold", "Comparison threshold", "Karşılaştırma eşiği", 50, "percent", pnlDate)],
    },
    {
      id: "profitability:savers-below-cpi", sector: "profitability", state: signalState(fundingGap != null, fundingGap != null && fundingGap < 0),
      title: text("Deposit funding cost relative to inflation", "Mevduat fonlama maliyetinin enflasyonla karşılaştırması"),
      summary: fundingGap == null ? missing : fundingGap < 0
        ? text("The blended deposit cost is below average inflation. The nominal gap supports the margin; it is not itself a calculation of depositors' real returns.", "Ortalama mevduat maliyeti, ortalama enflasyonun altında. Nominal fark faiz marjını destekler; bu fark tek başına mevduat sahibinin reel getirisi hesabı değildir.")
        : text("The blended deposit cost is at least as high as average inflation. Their difference is a nominal percentage-point comparison.", "Ortalama mevduat maliyeti, ortalama enflasyona eşit veya daha yüksek. Aralarındaki fark nominal yüzde puan karşılaştırmasıdır."),
      criterion: text("Blended deposit cost − 12-month-average CPI < 0 percentage points.", "Ortalama mevduat maliyeti − 12 aylık ortalama TÜFE < 0 yüzde puan."),
      rule: "blended_deposit_cost − cpi_12m_avg < 0", asOf: fundingComparisonDate, cadence: "monthly",
      source: text(`${fundingSource.en} CPI uses 12-month-average inflation in the latest common observation month. Latest separate readings remain as dated context.`, `${fundingSource.tr} TÜFE için son ortak gözlem ayındaki 12 aylık ortalama enflasyon kullanılır. Serilerin ayrı son değerleri, tarihleriyle birlikte korunur.`), href: "/profitability#funding-cost",
      facts: [fact("blended-cost", "Blended deposit cost in comparison month", "Karşılaştırma ayındaki ortalama mevduat maliyeti", fundingComparison?.blended, "percent", fundingComparisonDate), fact("average-cpi", "12-month-average CPI in comparison month", "Karşılaştırma ayındaki 12 aylık ortalama TÜFE", fundingCpi, "percent", fundingComparisonDate), fact("nominal-gap", "Deposit cost minus inflation", "Mevduat maliyeti eksi enflasyon", fundingGap, "pp", fundingComparisonDate), fact("latest-blended-cost", "Latest blended deposit cost", "Son ortalama mevduat maliyeti", funding?.blended, "percent", pnlDate), fact("latest-average-cpi", "Latest 12-month-average CPI inflation", "Son 12 aylık ortalama TÜFE enflasyonu", cpiValue, "percent", cpiDate)],
    },
    {
      id: "profitability:pnl-reconcile", sector: "profitability", state: signalState(reconciled != null, reconciled != null && !reconciled.reconciles),
      title: text("Income-statement reconciliation", "Gelir tablosu mutabakatı"),
      summary: !reconciled ? text("The current or preceding monthly statement lacks an input required for reconciliation. An absent disclosure is not a zero amount.", "Güncel veya önceki aylık tabloda mutabakat için gerekli bir girdi eksik. Açıklanmayan tutar sıfır kabul edilmez.") : !reconciled.reconciles
        ? text("The income bridge differs from reported net profit beyond tolerance and is withheld. A changed source-line mapping is one possible explanation and requires investigation.", "Gelir köprüsü ile açıklanan net kâr arasındaki fark toleransı aştığı için grafik gösterilmiyor. Kaynak satır eşlemesindeki değişiklik olası açıklamalardan biridir ve incelenmelidir.")
        : text("The income bridge agrees with reported net profit within the stated tolerance.", "Gelir köprüsü, belirtilen tolerans içinde açıklanan net kâr ile tutarlı."),
      criterion: text(`Absolute difference between bridge total and reported monthly net profit > TRY ${RECONCILE_TOLERANCE} trillion.`, `Köprü toplamı ile açıklanan aylık net kâr arasındaki mutlak fark > ${RECONCILE_TOLERANCE.toString().replace(".", ",")} trilyon TL.`),
      rule: "|bridge − reported_net| > ₺0.001trn", asOf: pnlDate, cadence: "monthly", source: text("BDDK monthly cumulative-YTD sector income statement. January is taken directly; later months subtract the immediately preceding month. The fixed source-line mapping is checked against reported net profit before displaying the bridge.", "BDDK aylık, yılbaşından itibaren birikimli sektör gelir tablosu. Ocak doğrudan alınır; sonraki aylarda bir önceki ay çıkarılır. Köprü gösterilmeden önce sabit kaynak satır eşlemesi, açıklanan net kâr ile kontrol edilir."), href: "/profitability#income",
      facts: [
        fact("computed-profit", "Bridge total", "Köprü toplamı", reconciled?.computed, "TRYtrn", pnlDate), fact("reported-profit", "Reported monthly net profit", "Açıklanan aylık net kâr", reconciled?.net, "TRYtrn", pnlDate), fact("gap", "Bridge minus reported profit", "Köprü eksi açıklanan kâr", reconciled?.gap, "TRYtrn", pnlDate), fact("tolerance", "Absolute reconciliation tolerance", "Mutlak mutabakat toleransı", RECONCILE_TOLERANCE, "TRYtrn", pnlDate),
      ],
    },
  ];
}

export async function loadProfitabilitySignals(): Promise<SectorSignal[]> {
  const metrics = await import("../metrics");
  const [roe, cpi, pnl, deposits] = await Promise.all([
    metrics.ratioRoe([metrics.BANK_TYPES.SECTOR]), metrics.evdsSeries("TP.TUKFIY2025.GENEL", 10),
    metrics.sectorPnl(), metrics.sectorDepositMix(),
  ]);
  return evaluateProfitabilitySignals({ roe, cpi, pnl, deposits });
}
