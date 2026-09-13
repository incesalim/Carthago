import type { Pt } from "../capital";
import type { RollForwardYear, StageLadder } from "../credit-risk";
import { deflate, growthSeries, risingRun } from "../series";
import { signalState, signalText as text, type SectorSignal, type SignalFact } from "./types";

export interface AssetQualitySignalInputs {
  npl: readonly Pt[];
  grossNpl: readonly Pt[];
  loans: readonly Pt[];
  cpiYoY: Map<string, number>;
  ladder: StageLadder | null;
  roll: readonly RollForwardYear[];
}
const finite = (value: number | null | undefined): value is number => value != null && Number.isFinite(value);
const fact = (key: string, en: string, tr: string, value: number | null | undefined, unit: SignalFact["unit"], asOf: string | null): SignalFact =>
  ({ key, label: text(en, tr), value: finite(value) ? value : null, unit, asOf });
const monthIndex = (period: string) => Number(period.slice(0, 4)) * 12 + Number(period.slice(5, 7));

/** The four original research rules; weekly, monthly and annual audit bases stay distinct. */
export function evaluateAssetQualitySignals(input: AssetQualitySignalInputs): SectorSignal[] {
  const { ladder } = input;
  const stageRatio = ladder && finite(ladder.stage3Share) && ladder.stage3Share > 0 ? ladder.stage2Share / ladder.stage3Share : null;
  const stageAvailable = ladder != null && finite(stageRatio) && [ladder.stage2Bn, ladder.stage3Bn, ladder.cov2, ladder.cov3].every(finite);
  const stageActive = stageAvailable && stageRatio! >= 2 && ladder!.cov2 < ladder!.cov3 / 5;
  const annual = input.roll.at(-1);
  const prior = input.roll.at(-2);
  const formationMultiple = annual && prior && prior.additions > 0 ? annual.additions / prior.additions : null;
  const formationAvailable = annual != null && prior != null && finite(formationMultiple) &&
    [annual.additions, annual.exits, annual.net, annual.collectionShare].every(finite) &&
    Number(annual.year) - Number(prior.year) === 1;
  const formationActive = formationAvailable && formationMultiple! >= 1.5 && annual!.net > 0;
  const annualDate = annual ? `${annual.year}Q4` : null;
  const priorDate = prior ? `${prior.year}Q4` : null;
  const stockReal = deflate(growthSeries([...input.grossNpl]), input.cpiYoY).at(-1);
  const loanReal = deflate(growthSeries([...input.loans]), input.cpiYoY).at(-1);
  const stockAvailable = finite(stockReal?.value) && finite(loanReal?.value) && stockReal.period === loanReal.period;
  const stockThreshold = finite(loanReal?.value) ? 3 * Math.max(loanReal.value, 0.1) : null;
  const stockActive = stockAvailable && stockReal!.value! > stockThreshold!;
  const monthlyNpl = input.npl.map(row => ({ ...row, period: row.period.slice(0, 7) }))
    .sort((a, b) => a.period.localeCompare(b.period));
  const published = monthlyNpl.at(-1);
  const uninterrupted: Pt[] = [];
  for (let i = monthlyNpl.length - 1; i >= 0; i--) {
    const row = monthlyNpl[i];
    if (!finite(row.value) || (uninterrupted.length > 0 && monthIndex(uninterrupted[0].period) - monthIndex(row.period) !== 1)) break;
    uninterrupted.unshift(row);
  }
  const streakAvailable = uninterrupted.length >= 7;
  const run = streakAvailable ? risingRun(uninterrupted) : null;
  const runStart = run != null ? uninterrupted.at(-1 - run) : null;
  const missing = text("Required observations are unavailable; the criterion cannot be evaluated.", "Gerekli gözlemler mevcut değil; ölçüt değerlendirilemiyor.");

  return [
    {
      id: "asset-quality:watchlist_thinly_covered", sector: "asset-quality", state: signalState(stageAvailable, stageActive),
      title: text("Stage 2 size and provision coverage", "İkinci aşama kredilerin büyüklüğü ve karşılık oranı"),
      summary: !stageAvailable ? missing : stageActive
        ? text("Stage 2 is at least twice Stage 3, while its coverage is below one-fifth of Stage 3 coverage. Stage 2 is a watchlist classification, not an impaired-loan classification; lower coverage is expected. Migration scenarios size a possible cost, not a current provisioning shortfall.", "İkinci aşama krediler üçüncü aşamanın en az iki katı; karşılık oranı ise üçüncü aşama karşılık oranının beşte birinden düşük. İkinci aşama yakın izleme sınıfıdır, donuk alacak sınıfı değildir; daha düşük karşılık oranı beklenir. Geçiş senaryoları mevcut karşılık açığını değil, olası maliyeti ölçer.")
        : text("The combined Stage 2 size and coverage criterion is not met. The two stages remain distinct classifications with different expected coverage.", "İkinci aşama büyüklüğü ve karşılık oranına ilişkin birleşik ölçüt karşılanmıyor. İki aşama, beklenen karşılık oranları farklı olan ayrı sınıflardır."),
      criterion: text("Stage 2 / Stage 3 ≥ 2 and Stage 2 coverage < Stage 3 coverage / 5. Both balances and coverage ratios use the same audited reporting-bank sample.", "İkinci aşama / üçüncü aşama ≥ 2 ve ikinci aşama karşılık oranı < üçüncü aşama karşılık oranı / 5. Bakiyeler ve karşılık oranları aynı denetlenmiş banka örneklemini kullanır."),
      rule: "stage2 / stage3 >= 2 AND cov2 < cov3 / 5", asOf: ladder?.period ?? null, cadence: "quarterly",
      source: text("BRSA quarterly staging and expected-credit-loss disclosures; aggregate of reporting banks. Stage 2 and Stage 3 shares and coverages are calculated on the same audited basis, not divided by the monthly published NPL ratio.", "BDDK formatındaki üç aylık kredi aşaması ve beklenen kredi zararı açıklamaları; veri açıklayan bankaların toplamı. İkinci ve üçüncü aşama payları ile karşılık oranları aynı denetlenmiş veri esasındadır; aylık yayımlanan takipteki alacak oranına bölünmez."), href: "/asset-quality#stages",
      facts: [
        fact("stage2-balance", "Stage 2 balance", "İkinci aşama bakiye", ladder?.stage2Bn, "TRYbn", ladder?.period ?? null), fact("stage3-balance", "Stage 3 balance", "Üçüncü aşama bakiye", ladder?.stage3Bn, "TRYbn", ladder?.period ?? null),
        fact("stage-ratio", "Stage 2 / Stage 3", "İkinci aşama / üçüncü aşama", stageRatio, "ratio", ladder?.period ?? null), fact("stage2-coverage", "Stage 2 provision coverage", "İkinci aşama karşılık oranı", ladder?.cov2, "percent", ladder?.period ?? null), fact("stage3-coverage", "Stage 3 provision coverage", "Üçüncü aşama karşılık oranı", ladder?.cov3, "percent", ladder?.period ?? null),
        fact("reporting-banks", "Reporting banks", "Veri açıklayan bankalar", ladder?.n, "count", ladder?.period ?? null),
      ],
    },
    {
      id: "asset-quality:formation_doubling", sector: "asset-quality", state: signalState(formationAvailable, formationActive),
      title: text("Annual non-performing loan formation", "Yıllık takipteki alacak oluşumu"),
      summary: !formationAvailable ? missing : formationActive
        ? text("Annual NPL additions are at least 1.5 times the prior year and exceed exits. The exit composition separates collections from write-offs and sales; the comparison does not assume that all exits are collections.", "Yıllık takipteki alacak girişleri önceki yılın en az 1,5 katı ve çıkışları aşıyor. Çıkış bileşimi tahsilatları silme ve satışlardan ayırır; tüm çıkışların tahsilat olduğu varsayılmaz.")
        : text("The combined criterion of at least 1.5 times prior-year additions and positive net formation is not met.", "Önceki yılın en az 1,5 katı giriş ve pozitif net oluşumdan oluşan birleşik ölçüt karşılanmıyor."),
      criterion: text("Current annual NPL additions / prior-year additions ≥ 1.5, and additions − exits > 0. The prior-year additions must be positive.", "Güncel yıllık takipteki alacak girişleri / önceki yıl girişleri ≥ 1,5 ve girişler − çıkışlar > 0. Önceki yıl girişleri pozitif olmalıdır."),
      rule: "formation_current / formation_prior >= 1.5 AND net_formation > 0", asOf: annualDate, cadence: "quarterly",
      source: text("BRSA audited NPL movement tables, Q4 cumulative flows only: full calendar-year additions, collections, write-offs and sales. Each year is the aggregate of its reporting banks; the sample may differ between years.", "BDDK formatındaki denetlenmiş takipteki alacak hareket tabloları, yalnızca dördüncü çeyrek birikimli akımları: tam takvim yılı girişleri, tahsilatları, silmeleri ve satışları. Her yıl kendi veri açıklayan bankalarının toplamıdır; örneklem yıllar arasında değişebilir."), href: "/asset-quality#flows",
      facts: [
        fact("additions", "Annual additions", "Yıllık girişler", annual?.additions, "TRYbn", annualDate), fact("prior-additions", "Prior-year additions", "Önceki yıl girişleri", prior?.additions, "TRYbn", priorDate), fact("formation-multiple", "Additions / prior-year additions", "Girişler / önceki yıl girişleri", formationMultiple, "ratio", annualDate),
        fact("exits", "Annual exits", "Yıllık çıkışlar", annual?.exits, "TRYbn", annualDate), fact("net-formation", "Net formation", "Net oluşum", annual?.net, "TRYbn", annualDate), fact("collections", "Collections", "Tahsilatlar", annual?.collections, "TRYbn", annualDate), fact("collection-share", "Collections as share of exits", "Tahsilatların çıkışlardaki payı", annual?.collectionShare, "percent", annualDate), fact("write-offs", "Write-offs", "Aktiften silmeler", annual?.writeOffs, "TRYbn", annualDate), fact("sales", "NPL sales", "Takipteki alacak satışları", annual?.sold, "TRYbn", annualDate), fact("disposal-share", "Write-offs and sales as share of exits", "Silme ve satışların çıkışlardaki payı", annual?.disposalShare, "percent", annualDate),
        fact("reporting-banks", "Current-year reporting banks", "Güncel yıl veri açıklayan bankalar", annual?.n, "count", annualDate), fact("prior-reporting-banks", "Prior-year reporting banks", "Önceki yıl veri açıklayan bankalar", prior?.n, "count", priorDate),
      ],
    },
    {
      id: "asset-quality:stock_compounding", sector: "asset-quality", state: signalState(stockAvailable, stockActive),
      title: text("Real growth of non-performing loans", "Takipteki alacakların reel büyümesi"),
      summary: !stockAvailable ? missing : stockActive
        ? text("CPI-deflated NPL stock growth exceeds the defined comparison with real loan-book growth. Both rates are measured on the same published CPI basis.", "TÜFE'den arındırılmış takipteki alacak stoku büyümesi, reel kredi büyümesiyle tanımlanan karşılaştırma eşiğini aşıyor. İki oran aynı yayımlanmış TÜFE esasına göre ölçülür.")
        : text("CPI-deflated NPL stock growth does not exceed the defined comparison with real loan-book growth.", "TÜFE'den arındırılmış takipteki alacak stoku büyümesi, reel kredi büyümesiyle tanımlanan karşılaştırma eşiğini aşmıyor."),
      criterion: text("Real NPL-stock growth > 3 × max(real loan-book growth, 0.1%). The 0.1% floor is part of the original condition, including when real loan growth is negative.", "Reel takipteki alacak stoku büyümesi > 3 × maks(reel kredi büyümesi, %0,1). Reel kredi büyümesi negatifken de kullanılan %0,1 tabanı, özgün koşulun bir parçasıdır."),
      rule: "npl_stock_real > 3 * max(loan_book_real, 0.1)", asOf: stockReal?.period ?? null, cadence: "mixed",
      source: text("BDDK weekly NPL and loan stocks; annual growth uses actual elapsed days. Fisher deflation uses published monthly TCMB EVDS/TÜİK CPI only. Real series may lag the weekly nominal record; missing CPI is not estimated. The two real-growth observations must share a date.", "BDDK haftalık takipteki alacak ve kredi stokları; yıllık büyümede fiili gün farkı kullanılır. Fisher düzeltmesi yalnızca yayımlanmış aylık TCMB EVDS/TÜİK TÜFE verisini kullanır. Reel seriler haftalık nominal veriden geride kalabilir; eksik TÜFE tahmin edilmez. İki reel büyüme gözlemi aynı tarihe ait olmalıdır."), href: "/asset-quality#npl",
      facts: [fact("real-npl-growth", "Real NPL-stock growth", "Takipteki alacak stokunun reel büyümesi", stockReal?.value, "percent", stockReal?.period ?? null), fact("real-loan-growth", "Real loan-book growth", "Kredi stokunun reel büyümesi", loanReal?.value, "percent", loanReal?.period ?? null), fact("comparison-threshold", "Three times floored real loan growth", "Taban uygulanmış reel kredi büyümesinin üç katı", stockThreshold, "percent", loanReal?.period ?? null)],
    },
    {
      id: "asset-quality:npl_ratio_streak", sector: "asset-quality", state: signalState(streakAvailable, run != null && run >= 6),
      title: text("Consecutive rises in the published NPL ratio", "Yayımlanan takipteki alacak oranında ardışık artış"),
      summary: !streakAvailable ? text("Seven consecutive monthly observations are required to assess six consecutive rises; missing months cannot establish a clear result.", "Altı ardışık artışı değerlendirmek için yedi ardışık aylık gözlem gerekir; eksik aylar eşik aşılmamış sonucunu vermez.") : run! >= 6
        ? text("The published NPL ratio has risen for at least six consecutive months. The sequence's starting and latest values are shown; direction remains informative even when the ratio's level is low.", "Yayımlanan takipteki alacak oranı en az altı aydır aralıksız artıyor. Dizinin başlangıç ve son değerleri gösterilir; oranın seviyesi düşükken de yönü bilgi taşır.")
        : text("The published NPL ratio has not risen for six consecutive months.", "Yayımlanan takipteki alacak oranı altı ay boyunca aralıksız artmış değil."),
      criterion: text("At least six consecutive positive month-to-month changes in the published sector NPL ratio.", "Yayımlanan sektör takipteki alacak oranında en az altı ardışık pozitif aylık değişim."),
      rule: "npl_ratio_consecutive_monthly_rises >= 6", asOf: published?.period ?? null, cadence: "monthly",
      source: text("BDDK monthly published sector NPL ratio. This is distinct from the weekly stock-implied ratio and the audited Stage 2/Stage 3 measures.", "BDDK'nın yayımladığı aylık sektör takipteki alacak oranı. Haftalık stoklardan türetilen oran ile denetlenmiş ikinci/üçüncü aşama ölçülerinden farklıdır."), href: "/asset-quality#npl",
      facts: [fact("rising-months", "Consecutive monthly rises", "Ardışık aylık artış sayısı", run, "months", published?.period ?? null), fact("start-ratio", "Ratio before the current rising sequence", "Mevcut artış dizisinden önceki oran", runStart?.value, "percent", runStart?.period ?? null), fact("latest-ratio", "Latest published NPL ratio", "Son yayımlanan takipteki alacak oranı", published?.value, "percent", published?.period ?? null), fact("threshold", "Required consecutive rises", "Gerekli ardışık artış sayısı", 6, "months", published?.period ?? null)],
    },
  ];
}

export async function loadAssetQualitySignals(): Promise<SectorSignal[]> {
  const metrics = await import("../metrics");
  const risk = await import("../credit-risk");
  const { cpiYoYByMonth } = await import("../real-terms");
  const { NPL_ITEMS, LOAN_ITEMS } = await import("../asset-quality");
  const sector = [metrics.WEEKLY_BANK_TYPES.SECTOR];
  const [npl, grossNpl, loans, cpiYoY, ladder, roll] = await Promise.all([
    metrics.ratioNpl([metrics.BANK_TYPES.SECTOR]),
    metrics.weeklySeries("takipteki_alacaklar", NPL_ITEMS.TOTAL, "TOTAL", sector, 156),
    metrics.weeklySeries("krediler", LOAN_ITEMS.TOTAL, "TOTAL", sector, 156),
    cpiYoYByMonth(), risk.stageLadder(), risk.nplRollForwardAnnual(),
  ]);
  return evaluateAssetQualitySignals({ npl, grossNpl, loans, cpiYoY, ladder, roll });
}
