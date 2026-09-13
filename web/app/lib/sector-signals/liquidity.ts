import type { EvdsRow } from "../metrics";
import type { Pt } from "../series";
import { reserveBuffer, RESERVE_CODES, FWD_YEARS_BACK } from "../reserves";
import { LDR_WEEKLY_TL } from "../ldr";
import { signalState, signalText as t, type SectorSignal, type SignalFact } from "./types";

export interface LiquiditySignalInput {
  privateLdr: Pt[];
  dollarization: Pt[];
  lcr: Pt[];
  nsfr: Pt[];
  evds: Record<string, EvdsRow[]>;
  forwards: EvdsRow[];
}
const value = (rows: Pt[]) => rows.at(-1)?.value ?? null;
const date = (rows: Pt[]) => rows.at(-1)?.period ?? null;
const known = (v: number | null | undefined): v is number => v != null && Number.isFinite(v);
const fact = (key: string, en: string, tr: string, value: number | null, asOf: string | null, unit: SignalFact["unit"] = "percent"): SignalFact => ({ key, label: t(en, tr), value, asOf, unit });
const missing = t("The observations needed to evaluate this condition are unavailable.", "Bu koşulu değerlendirmek için gereken gözlemler mevcut değil.");
const reserveSource = t("TCMB EVDS: weekly gross reserves TP.AB.TOPLAM; net reserves derived from (TP.BL054 − TP.BL122)/USD-TRY. Monthly forward/swap short position TP.DOVVARNC.K15 is carried from the nearest earlier published date, without interpolation.", "TCMB EVDS: haftalık brüt rezervler TP.AB.TOPLAM; net rezervler (TP.BL054 − TP.BL122)/USD-TL ile hesaplanır. Aylık vadeli döviz/swap kısa pozisyonu TP.DOVVARNC.K15, aradeğer üretmeden en yakın önceki yayımlanmış tarihten taşınır.");
const auditSource = t("BRSA unconsolidated audit reports, §4 liquidity disclosures, asset-weighted aggregate of reporting peer banks. Quarterly audited observations; not a live weekly sector ratio.", "BDDK konsolide olmayan denetim raporları, §4 likidite açıklamaları, veri yayımlayan emsal bankaların aktif ağırlıklı toplamı. Üç aylık denetlenmiş gözlemlerdir; güncel haftalık sektör oranı değildir.");

/** Preserve the date-based, on-or-before 364-day comparator of the original liquidity page. */
function yearAgo(rows: Pt[]): Pt | undefined {
  const last = date(rows);
  if (!last) return undefined;
  const cutoff = new Date(last);
  cutoff.setUTCDate(cutoff.getUTCDate() - 364);
  const cut = cutoff.toISOString().slice(0, 10);
  return rows.findLast((r) => r.period <= cut);
}

export function buildLiquiditySignals(input: LiquiditySignalInput): SectorSignal[] {
  const { privateLdr, dollarization, lcr, nsfr, evds, forwards } = input;
  const buffer = reserveBuffer(evds, forwards);
  const reserveDate = buffer.latest?.period ?? null;
  const latestBalanceDate = evds["TP.BL054"]?.at(-1)?.period_date ?? null;
  const forwardRows = forwards.length ? forwards : evds["TP.DOVVARNC.K15"] ?? [];
  const forward = reserveDate ? forwardRows.findLast((r) => r.period_date <= reserveDate) : undefined;
  // EvdsRow is typed numeric, but a runtime null must not become zero in subtraction.
  const completeReserve = reserveDate != null && ["TP.AB.TOPLAM", "TP.BL054", "TP.BL122", "TP.DK.USD.A"].every((code) =>
    known(evds[code]?.find((r) => r.period_date === reserveDate)?.value),
  ) && known(forward?.value);
  const b = completeReserve ? buffer.latest : null;
  const bufferCurrent = b != null && reserveDate === latestBalanceDate;
  const ownPct = b && known(b.own) && known(b.gross) && b.gross !== 0 && bufferCurrent ? b.own / b.gross * 100 : null;
  const swapPct = b && known(buffer.swapStock) && known(b.net) && b.net !== 0 && bufferCurrent ? buffer.swapStock / b.net * 100 : null;
  const forwardDate = forward?.period_date ?? null;
  const funding = evds["TP.APIFON3"]?.at(-1);
  const fund = known(funding?.value) ? funding.value / 1000 : null;
  const priv = value(privateLdr);
  const lcrNow = value(lcr);
  const nsfrNow = value(nsfr);
  const dollarNow = value(dollarization);
  const dollarBase = yearAgo(dollarization);
  const dollarDelta = known(dollarNow) && known(dollarBase?.value) ? dollarNow - dollarBase.value : null;
  const ownState = signalState(known(ownPct), ownPct != null && ownPct < 40);
  const swapState = signalState(known(swapPct), swapPct != null && swapPct > 25);
  const fundState = signalState(known(fund), fund != null && fund < 0);
  const privateState = signalState(known(priv), priv != null && priv > LDR_WEEKLY_TL.line);
  const lcrState = signalState(known(lcrNow), lcrNow != null && lcrNow < 100);
  const nsfrState = signalState(known(nsfrNow), nsfrNow != null && nsfrNow < 100);
  const dollarState = signalState(known(dollarDelta), dollarDelta != null && dollarDelta > 1);
  const reserveFact = (key: string, en: string, tr: string, bn: number | null, asOf = reserveDate) => fact(key, en, tr, known(bn) ? bn * 1000 : null, asOf, "USDmn");
  return [
    {
      id: "liquidity:thin-own-buffer", sector: "liquidity", state: ownState,
      title: t("Net reserves excluding swaps", "Swap hariç net rezervler"),
      summary: ownState === "unavailable" ? missing : ownState === "active"
        ? t("Net reserves excluding swaps are less than 40% of gross reserves. Gross reserves also include banks' FX held at the central bank and foreign exchange acquired through swaps.", "Swap hariç net rezervler brüt rezervlerin %40'ının altında. Brüt rezervler, bankaların merkez bankasında tuttuğu dövizi ve swap yoluyla alınan dövizi de içerir.")
        : t("Net reserves excluding swaps are at least 40% of gross reserves.", "Swap hariç net rezervler brüt rezervlerin en az %40'ına karşılık geliyor."),
      criterion: t("Net reserves excluding swaps divided by gross reserves is below 40%. Net reserves equal analytical-balance-sheet FX assets minus FX liabilities, converted at USD/TRY; the absolute monthly forward/swap short position is then deducted. Gross reserves must be nonzero.", "Swap hariç net rezervlerin brüt rezervlere oranının %40'ın altında olması. Net rezervler, analitik bilançodaki döviz varlıklarından döviz yükümlülüklerinin çıkarılıp USD/TL kuruyla dönüştürülmesiyle hesaplanır; ardından aylık vadeli döviz/swap kısa pozisyonunun mutlak değeri düşülür. Brüt rezerv sıfır olmamalıdır."),
      rule: "net_excl_swaps / gross < 40%", asOf: reserveDate, cadence: "mixed", source: reserveSource, href: "/liquidity#reserves",
      facts: [fact("own_share", "Net reserves excluding swaps / gross", "Swap hariç net rezerv / brüt rezerv", ownPct, reserveDate), reserveFact("own_reserves", "Net reserves excluding swaps", "Swap hariç net rezervler", b?.own ?? null), reserveFact("gross_reserves", "Gross reserves", "Brüt rezervler", b?.gross ?? null), reserveFact("net_reserves", "Net reserves including swaps", "Swap dahil net rezervler", b?.net ?? null), reserveFact("banks_fx", "Gross minus net reserves", "Brüt rezerv eksi net rezerv", b ? buffer.banksFx : null), reserveFact("swap_stock", "Monthly forward/swap short position", "Aylık vadeli döviz/swap kısa pozisyonu", b ? buffer.swapStock : null, forwardDate)],
    },
    {
      id: "liquidity:swap-dependence", sector: "liquidity", state: swapState,
      title: t("Swap funding within net reserves", "Net rezervlerde swap payı"),
      summary: swapState === "unavailable" ? missing : swapState === "active"
        ? t("The forward/swap short position exceeds 25% of net reserves. This is a liability with a maturity date; the monthly position is carried into the weekly reserve comparison.", "Vadeli döviz/swap kısa pozisyonu net rezervlerin %25'ini aşıyor. Bu kalem vadesi olan bir yükümlülüktür; aylık pozisyon haftalık rezerv karşılaştırmasına taşınır.")
        : t("The forward/swap short position does not exceed 25% of net reserves.", "Vadeli döviz/swap kısa pozisyonu net rezervlerin %25'ini aşmıyor."),
      criterion: t("The absolute forward/swap short position divided by derived net international reserves exceeds 25%. Net reserves must be nonzero. The monthly short position is the latest published observation on or before the reserve date.", "Vadeli döviz/swap kısa pozisyonunun mutlak değerinin hesaplanan net uluslararası rezervlere oranının %25'i aşması. Net rezerv sıfır olmamalıdır. Aylık kısa pozisyon, rezerv tarihinde veya öncesinde yayımlanmış son gözlemden alınır."),
      rule: "swaps / nir > 25%", asOf: reserveDate, cadence: "mixed", source: reserveSource, href: "/liquidity#reserves",
      facts: [fact("swap_share", "Forward/swap position / net reserves", "Vadeli döviz/swap pozisyonu / net rezerv", swapPct, reserveDate), reserveFact("swap_stock", "Monthly forward/swap short position", "Aylık vadeli döviz/swap kısa pozisyonu", b ? buffer.swapStock : null, forwardDate), reserveFact("net_reserves", "Net reserves including swaps", "Swap dahil net rezervler", b?.net ?? null)],
    },
    {
      id: "liquidity:tl-deficit", sector: "liquidity", state: fundState,
      title: t("Net central-bank lira funding", "Merkez bankası net TL fonlaması"),
      summary: fundState === "unavailable" ? missing : fundState === "active"
        ? t("Net CBRT funding is negative under this series' sign convention, indicating a system lira shortage funded at the central bank.", "Bu serinin işaret kuralına göre net TCMB fonlaması negatif; sistemde merkez bankasından karşılanan bir TL açığına işaret ediyor.")
        : t("Net CBRT funding is not negative under this series' sign convention; the negative-funding condition is not met.", "Bu serinin işaret kuralına göre net TCMB fonlaması negatif değil; negatif fonlama koşulu sağlanmıyor."),
      criterion: t("Daily net CBRT funding TP.APIFON3 is below zero. In this series, negative values indicate a lira shortage and borrowing from the CBRT; positive values indicate surplus liquidity deposited at the CBRT. Values are converted from TRY million to TRY billion.", "Günlük net TCMB fonlaması TP.APIFON3'ün sıfırın altında olması. Bu seride negatif değer TL açığını ve TCMB'den borçlanmayı; pozitif değer TCMB'ye yatırılan likidite fazlasını gösterir. Değerler milyon TL'den milyar TL'ye dönüştürülür."),
      rule: "net_cbrt_funding < 0", asOf: funding?.period_date ?? null, cadence: "daily",
      source: t("TCMB EVDS TP.APIFON3, daily net funding; original series sign convention.", "TCMB EVDS TP.APIFON3, günlük net fonlama; özgün serinin işaret kuralı."), href: "/liquidity#lira-funding",
      facts: [fact("net_funding", "Net CBRT funding", "Net TCMB fonlaması", fund, funding?.period_date ?? null, "TRYbn")],
    },
    {
      id: "liquidity:private-ldr", sector: "liquidity", state: privateState,
      title: t("Private banks' TL loan-to-deposit ratio", "Özel bankalarda TL kredi/mevduat oranı"),
      summary: privateState === "unavailable" ? missing : privateState === "active"
        ? t("Private banks' TL loan-to-deposit ratio exceeds the 95% research threshold. Additional lending can require additional funding. The 100% level is a separate reference; the monthly all-currency sector ratio is covered under Deposits.", "Özel bankaların TL kredi/mevduat oranı %95 araştırma eşiğini aşıyor. İlave kredi büyümesi ek fonlama gerektirebilir. %100 ayrı bir referans seviyedir; aylık TL ve YP toplam sektör oranı Mevduat kapsamında ele alınır.")
        : t("Private banks' weekly TL loan-to-deposit ratio does not exceed 95%.", "Özel bankaların haftalık TL kredi/mevduat oranı %95'i aşmıyor."),
      criterion: t("TL loans divided by TL deposits for domestic private and foreign banks combined exceeds 95%, using the BDDK weekly bulletin. This is a research threshold, distinct from the 100% reference and the monthly TL+FX sector ratio.", "BDDK haftalık bülteninde yerli özel ve yabancı bankalar birlikte ele alındığında, TL kredilerin TL mevduata oranının %95'i aşması. Bu bir araştırma eşiğidir; %100 referans seviyesinden ve aylık TL+YP sektör oranından farklıdır."),
      rule: LDR_WEEKLY_TL.rule, asOf: date(privateLdr), cadence: "weekly",
      source: t("BDDK weekly bulletin; TL loans / TL deposits, domestic private plus foreign banks.", "BDDK haftalık bülteni; TL kredi / TL mevduat, yerli özel ve yabancı bankalar birlikte."), href: "/liquidity#lira-funding",
      facts: [fact("private_tl_ldr", "Private TL loan/deposit", "Özel bankalar TL kredi/mevduat", priv, date(privateLdr)), fact("distance_to_100", "Distance below 100% reference", "%100 referansına kalan fark", priv != null ? 100 - priv : null, date(privateLdr), "pp")],
    },
    {
      id: "liquidity:lcr-floor", sector: "liquidity", state: lcrState,
      title: t("Liquidity coverage ratio", "Likidite karşılama oranı"),
      summary: lcrState === "unavailable" ? missing : lcrState === "active"
        ? t("The asset-weighted LCR of reporting banks is below the 100% regulatory benchmark at the latest audited quarter. This aggregate does not establish each bank's compliance.", "Veri yayımlayan bankaların aktif ağırlıklı LKO'su son denetlenmiş çeyrekte %100 düzenleyici referansın altında. Bu toplulaştırılmış oran her bankanın mevzuata uyumunu göstermez.")
        : t("The asset-weighted LCR of reporting banks is at least 100% at the latest available audited quarter.", "Veri yayımlayan bankaların aktif ağırlıklı LKO'su son mevcut denetlenmiş çeyrekte en az %100."),
      criterion: t("The quarterly asset-weighted liquidity coverage ratio of reporting banks is below 100%. Observations come from audited §4 disclosures and must not be treated as a current weekly sector measure.", "Veri yayımlayan bankaların üç aylık aktif ağırlıklı likidite karşılama oranının %100'ün altında olması. Gözlemler denetlenmiş §4 açıklamalarından gelir; güncel haftalık sektör ölçütü olarak yorumlanmamalıdır."),
      rule: "lcr < 100%", asOf: date(lcr), cadence: "quarterly", source: auditSource, href: "/liquidity#liquidity-ratios",
      facts: [fact("lcr", "Asset-weighted LCR", "Aktif ağırlıklı LKO", lcrNow, date(lcr))],
    },
    {
      id: "liquidity:nsfr-floor", sector: "liquidity", state: nsfrState,
      title: t("Net stable funding ratio", "Net istikrarlı fonlama oranı"),
      summary: nsfrState === "unavailable" ? missing : nsfrState === "active"
        ? t("The asset-weighted NSFR of reporting banks is below the 100% regulatory benchmark at the latest audited quarter. This aggregate does not establish each bank's compliance.", "Veri yayımlayan bankaların aktif ağırlıklı NİFO'su son denetlenmiş çeyrekte %100 düzenleyici referansın altında. Bu toplulaştırılmış oran her bankanın mevzuata uyumunu göstermez.")
        : t("The asset-weighted NSFR of reporting banks is at least 100% at the latest available audited quarter.", "Veri yayımlayan bankaların aktif ağırlıklı NİFO'su son mevcut denetlenmiş çeyrekte en az %100."),
      criterion: t("The quarterly asset-weighted net stable funding ratio of reporting banks is below 100%. Observations come from audited §4 disclosures and must not be treated as a current weekly sector measure.", "Veri yayımlayan bankaların üç aylık aktif ağırlıklı net istikrarlı fonlama oranının %100'ün altında olması. Gözlemler denetlenmiş §4 açıklamalarından gelir; güncel haftalık sektör ölçütü olarak yorumlanmamalıdır."),
      rule: "nsfr < 100%", asOf: date(nsfr), cadence: "quarterly", source: auditSource, href: "/liquidity#liquidity-ratios",
      facts: [fact("nsfr", "Asset-weighted NSFR", "Aktif ağırlıklı NİFO", nsfrNow, date(nsfr))],
    },
    {
      id: "liquidity:re-dollarization", sector: "liquidity", state: dollarState,
      title: t("Change in foreign-currency deposit share", "Yabancı para mevduat payındaki değişim"),
      summary: dollarState === "unavailable" ? missing : dollarState === "active"
        ? t("The sector FX deposit share has risen by more than 1 percentage point against the annual comparison date. The TL-equivalent share reflects exchange rates as well as deposit movements.", "Sektör YP mevduat payı yıllık karşılaştırma tarihine göre 1 yüzde puandan fazla arttı. TL karşılığıyla hesaplanan pay, mevduat hareketlerinin yanı sıra kurdan da etkilenir.")
        : t("The increase in sector FX deposit share does not exceed 1 percentage point against the annual comparison date.", "Sektör YP mevduat payındaki artış yıllık karşılaştırma tarihine göre 1 yüzde puanı aşmıyor."),
      criterion: t("The latest sector FX deposit share minus the share at the latest observation on or before 364 days earlier exceeds 1 percentage point. FX and total deposits use TL equivalents; this date-based comparison is distinct from the deposit page's 52-observation offset.", "Son sektör YP mevduat payından, 364 gün önceki tarihte veya öncesinde bulunan son gözlemin payı çıkarıldığında farkın 1 yüzde puanı aşması. YP ve toplam mevduat TL karşılığıyla kullanılır; tarihe dayalı bu karşılaştırma Mevduat sayfasındaki 52 gözlem geriye bakıştan farklıdır."),
      rule: "Δ52w(fc_share) > +1pp", asOf: date(dollarization), cadence: "weekly",
      source: t("BDDK weekly bulletin, sector FX deposits as a share of total deposits; TL equivalents.", "BDDK haftalık bülteni, sektör YP mevduatının toplam mevduattaki payı; TL karşılıkları."), href: "/liquidity#fx-funding",
      facts: [fact("fx_share", "Latest FX deposit share", "Son YP mevduat payı", dollarNow, date(dollarization)), fact("base_share", "Annual comparison FX share", "Yıllık karşılaştırma YP payı", dollarBase?.value ?? null, dollarBase?.period ?? null), fact("share_change", "Change in FX share", "YP payı değişimi", dollarDelta, date(dollarization), "pp")],
    },
  ];
}

export async function loadLiquiditySignals(): Promise<SectorSignal[]> {
  const { weeklyOwnershipRatio, weeklyDollarization, evdsMulti, evdsSeries } = await import("../metrics");
  const { sectorLiquidityRatios } = await import("../audit-ratios");
  const [ldr, dollarization, ratios, evds, forwards] = await Promise.all([
    weeklyOwnershipRatio("krediler", "1.0.1", "mevduat", "4.0.1", "TL"), weeklyDollarization(), sectorLiquidityRatios(),
    evdsMulti(["TP.APIFON3", ...RESERVE_CODES], 3), evdsSeries("TP.DOVVARNC.K15", FWD_YEARS_BACK),
  ]);
  return buildLiquiditySignals({ privateLdr: ldr.filter((r) => r.bank_type_code === "PRIVATE"), dollarization: dollarization.filter((r) => r.bank_type_code === "SECTOR"), lcr: ratios.filter((r) => r.bank_type_code === "LCR"), nsfr: ratios.filter((r) => r.bank_type_code === "NSFR"), evds, forwards });
}
