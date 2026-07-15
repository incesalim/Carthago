import { describe, expect, it } from "vitest";
import {
  classifyKap,
  foldTr,
  isOffshore,
  ratingAgency,
  glossKap,
  type ActCategory,
} from "./kap-actions";

/**
 * These fixtures are REAL (title, summary) pairs from the live KAP feed, one per
 * bucket the classifier must get right. The point of the test is automation
 * safety: the page derives every figure from `classifyKap` at request time, so a
 * silent regression here would silently corrupt the page. In particular it locks
 * the two failure modes that matter — a coupon-payment notice must NOT read as an
 * issuance, and an unrecognised filing must NOT be suppressed as routine.
 */
const CASES: { title: string; summary: string; want: ActCategory; note: string }[] = [
  {
    title: "Pay Dışında Sermaye Piyasası Aracı İşlemlerine İlişkin Bildirim (Faiz İçeren)",
    summary: "Yurtdışı Piyasalara Tahvil İhracı SPK Onayı",
    want: "funding",
    note: "offshore bond approval",
  },
  {
    title: "Pay Dışında Sermaye Piyasası Aracı İşlemlerine İlişkin Bildirim (Faiz İçeren)",
    summary: "TRSSKBKA2716 ISIN kodlu sermaye benzeri tahvilin yüz üçüncü kupon ödemesi yapılmıştır.",
    want: "routine",
    note: "coupon payment on a sub-debt — must NOT read as issuance",
  },
  {
    title: "Özel Durum Açıklaması (Genel)",
    summary: "Yurt Dışında Yapılacak Katkı Sermaye Nitelikli Borçlanma Aracı İhracı Hakkında",
    want: "funding",
    note: "Tier-2 issuance filed under the generic material-event form",
  },
  {
    title: "Özel Durum Açıklaması (Genel)",
    summary: "Sendikasyon Kredisi Hakkında",
    want: "funding",
    note: "syndicated loan is wholesale funding",
  },
  {
    title: "Sermaye Artırımı - Azaltımı İşlemlerine İlişkin Bildirim",
    summary: "Bankamızın Bedelli Sermaye Artırımı İşlemine İlişkin SPK Başvurusu",
    want: "capital",
    note: "cash rights issue",
  },
  {
    title: "Özel Durum Açıklaması (Genel)",
    summary:
      "Bankalarda İyi Ücretlendirme Uygulamalarına İlişkin Rehber kapsamında geri alınan paylar",
    want: "capital",
    note: "share buyback",
  },
  {
    title: "Kar Payı Dağıtım İşlemlerine İlişkin Bildirim",
    summary: "2025 yılı kar dağıtımı hakkında",
    want: "capital",
    note: "dividend",
  },
  {
    title: "Kredi Derecelendirmesi",
    summary: "Fitch Ratings Derecelendirme Notları",
    want: "rating",
    note: "credit rating",
  },
  {
    title: "Kurumsal Yönetim İlkelerine Uyum Derecelendirmesi",
    summary: "Kurumsal Yönetim Derecelendirme Sözleşmesi hakkında",
    want: "governance",
    note: "corporate-governance compliance rating is NOT a credit rating",
  },
  {
    title: "Finansal Rapor",
    summary: "",
    want: "results",
    note: "quarterly financial report (often has no summary)",
  },
  {
    title: "Özel Durum Açıklaması (Genel)",
    summary: "Takipteki Kredi Alacakları Portföyünün Satışı",
    want: "material",
    note: "NPL portfolio sale",
  },
  {
    title: "Özel Durum Açıklaması (Genel)",
    summary: "ABD'de Bankamız Aleyhinde Açılan Ceza Davası ve OFAC Süreçleri",
    want: "material",
    note: "OFAC / litigation",
  },
  {
    title: "Özel Durum Açıklaması (Genel)",
    summary: "Yönetim Kurulu Üyesi Değişikliği",
    want: "governance",
    note: "board change",
  },
  {
    title: "Şirket Genel Bilgi Formu",
    summary: "",
    want: "routine",
    note: "company-information boilerplate",
  },
  {
    title: "Fiyat Tespit Raporuna İlişkin Analist Raporu (Halka Arz)",
    summary: "Beta Enerji ve Teknoloji A.Ş. Fiyat Tespit Raporu",
    want: "routine",
    note: "third-party IPO the bank underwrote — not the bank's own act",
  },
  {
    title: "Özel Durum Açıklaması (Genel)",
    summary: "Süresi İçinde Kaydileştirilmeyen Paylarla İlgili Duyuru",
    want: "routine",
    note: "dematerialisation notice",
  },
];

describe("classifyKap", () => {
  for (const c of CASES) {
    it(`${c.want} ← ${c.note}`, () => {
      expect(classifyKap(c.title, c.summary)).toBe(c.want);
    });
  }

  it("never throws on empty / null input, and defaults to the visible bucket", () => {
    expect(classifyKap("", null)).toBe("material");
    expect(classifyKap("Some entirely novel KAP form type", "unrecognised subject")).toBe(
      "material",
    );
  });
});

describe("foldTr", () => {
  it("folds Turkish diacritics and dotted-İ so keywords match", () => {
    expect(foldTr("İhraç Şğüöç")).toBe("ihrac sguoc");
    expect(foldTr("Yurtdışı")).toBe("yurtdisi");
  });
});

describe("isOffshore", () => {
  it("flags foreign-market funding, not domestic", () => {
    expect(isOffshore("Yurtdışı Piyasalara Tahvil İhracı")).toBe(true);
    expect(isOffshore("GMTN Programı Çerçevesinde Türkiye Dışında")).toBe(true);
    expect(isOffshore("Nitelikli Yatırımcılara Yapılan Tahvil İhracı")).toBe(false);
  });
});

describe("ratingAgency", () => {
  it("names the agency from the filing", () => {
    expect(ratingAgency("Moody's Kredi Derecelendirme Notu Güncellemesi", "")).toBe("Moody's");
    expect(ratingAgency("JCR Eurasia Kredi Derecelendirme Notları", "")).toBe("JCR Eurasia");
    expect(ratingAgency("no agency here", "")).toBeNull();
  });
});

describe("glossKap", () => {
  it("glosses an offshore GMTN issue in English and appends the CMB-approval note", () => {
    const g = glossKap(
      {
        ticker: "VAKBN",
        published_at: "2026-07-13",
        title: "Pay Dışında Sermaye Piyasası Aracı İşlemlerine İlişkin Bildirim",
        summary: "GMTN Programı Çerçevesinde Türkiye Dışında Sürdürülebilir Borçlanma Aracı İhracı SPK Onayı",
        url: "x",
        external_id: "1",
      },
      "funding",
    );
    expect(g).toMatch(/GMTN/);
    expect(g).toMatch(/CMB approval/);
  });

  it("falls back to the Turkish subject when no rule matches", () => {
    const g = glossKap(
      {
        ticker: "AKBNK",
        published_at: "2026-07-01",
        title: "Özel Durum Açıklaması (Genel)",
        summary: "Bir konu hakkında açıklama",
        url: "x",
        external_id: "2",
      },
      "material",
    );
    expect(g).toBe("Bir konu hakkında açıklama");
  });
});
