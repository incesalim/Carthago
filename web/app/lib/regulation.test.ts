/**
 * Fixtures are the REAL strings from news_items in D1 (read 2026-07-12), not
 * invented prose. The parsers exist to survive the regulators' actual wording,
 * so the tests must be fed the regulators' actual wording.
 *
 * The most important test in this file is `unreadRules`: it pins the failure we
 * ship deliberately — the 23 May macroprudential release announces credit growth
 * limits and arrives WITHOUT its table, so the band must declare it missing
 * rather than quietly omit it.
 */
import { describe, expect, it } from "vitest";
import type { NewsItem } from "./news";
import {
  classifyInstrument,
  deriveCorridor,
  derivePolicyPath,
  deriveReserves,
  decisionLags,
  institutionOf,
  isBankInstitution,
  isInstrument,
  licences,
  meetingsHeld,
  parseBindingDate,
  parseBoardDecision,
  parseOvernight,
  parsePolicyRate,
  parseReserveChanges,
  parseTerminated,
  rateChanges,
  reserveCellLabel,
  unreadRules,
} from "./regulation";

// ── real bodies, verbatim from D1 ────────────────────────────────────────────

const MPC_HOLD =
  "Yaşar Fatih Karahan (Governor), Hatice Karahan, Fatma Özkul, Gazi İshak Kara.\n\n" +
  "The Monetary Policy Committee (the Committee) has decided to keep the policy rate " +
  "(the one-week repo auction rate) at 37 percent. The Committee has also maintained the " +
  "Central Bank overnight lending rate and the overnight borrowing rate at 40 percent and " +
  "35.5 percent, respectively.\n\nThe underlying trend of inflation…";

const MPC_CUT =
  "The Committee has decided to reduce the policy rate (the one-week repo auction rate) " +
  "from 38 percent to 37 percent. The Committee has also lowered the Central Bank " +
  "overnight lending rate and the overnight borrowing rate at 40 percent and 35.5 percent, " +
  "respectively.";

const MPC_2022 =
  "The Committee has decided to keep the policy rate (one-week repo auction rate) " +
  "constant at 14 percent.\n\nThe new variants and increasing…";

/** 2026-07-01 — the ONE recent macropru release that ships its table. */
const MACROPRU_WITH_TABLE =
  "The Central Bank of the Republic of Türkiye has decided to take the following " +
  "simplification steps to strengthen macrofinancial stability and support the monetary " +
  "transmission mechanism:\n\n" +
  "- The additional Turkish lira reserve requirement ratio for FX deposits/participation " +
  "funds, which was introduced in 2023 and is currently applied at 2.5%, has been terminated.\n" +
  "- Reserve requirement ratios applied to foreign currency deposits/participation funds " +
  "have been revised as follows:\n\n" +
  "| Foreign currency deposits/participation funds | Previous Ratio | New Ratio |\n" +
  "| --- | --- | --- |\n" +
  "| Demand deposits and deposits with maturities up to 1 month | 30% | 32% |\n" +
  "| With longer maturities | 26% | 28% |\n\n" +
  "The reserve requirements according to new ratios will be maintained on July 17, 2026.\n\n" +
  "For further information, please send an e-mail to basin@tcmb.gov.tr.";

/** 2026-05-23 — credit growth limits, and the table is simply NOT THERE (342 chars). */
const MACROPRU_NO_TABLE =
  "In view of loan growth developments, the Central Bank of the Republic of Türkiye has " +
  "introduced the following changes in the reserve requirements practice to support the " +
  "tight monetary policy stance and strengthen macrofinancial stability.\n\n" +
  "Growth Limits (For Eight Weeks)\n\n" +
  "For further information, please send an e-mail to basin@tcmb.gov.tr.";

function item(p: Partial<NewsItem> & { title: string; published_at: string }): NewsItem {
  return {
    source: "tcmb",
    external_id: p.title,
    ticker: null,
    category: null,
    summary: null,
    url: "https://tcmb.gov.tr/x",
    language: "en",
    body_text: null,
    ...p,
  } as NewsItem;
}

// ── classification ──────────────────────────────────────────────────────────

describe("classifyInstrument", () => {
  it("counts rate decisions and rule changes as instruments", () => {
    expect(classifyInstrument({ source: "tcmb", title: "Press Release on Interest Rates" })).toBe("rate");
    expect(classifyInstrument({ source: "tcmb", title: "Press Release on Macroprudential Framework" })).toBe("rule");
    expect(
      classifyInstrument({ source: "bddk", title: "(12.03.2026 - 11428) Siemens Finansman A.Ş.'ye faaliyet izni verilmesine ilişkin Kurul Kararı" }),
    ).toBe("board");
  });

  // The regression set: every one of these was counted as a "regulatory
  // instrument" by the page this replaces. The SSL certificate was its
  // headline "Latest decision".
  it("does NOT count housekeeping as regulation", () => {
    const noise = [
      "Press Release on the Replacement of the SSL Certificate of the CBRT Website",
      "Central Bank of the Republic of Türkiye and Hong Kong Monetary Authority Sign Memorandum of Understanding",
      "BDDK Bankacılık ve Finansal Piyasalar Dergisinin 39. sayısı yayımlanmıştır.",
      "Mart 2026 dönemi Üçer Aylık Temel Göstergeler yayımlanmıştır.",
      "Summary of the Monetary Policy Committee Meeting",
      "Press Release on Inflation Report 2026-II Briefing on May 14, 2026",
    ];
    for (const title of noise) {
      const kind = classifyInstrument({ source: "tcmb", title });
      expect(kind, title).toBe("other");
      expect(isInstrument(kind), title).toBe(false);
    }
  });

  it("keeps 'unclassified' as a real state rather than guessing", () => {
    expect(classifyInstrument({ source: "tcmb", title: "Press Release on Something Entirely New" })).toBe(
      "unclassified",
    );
  });
});

// ── the corridor ────────────────────────────────────────────────────────────

describe("policy corridor", () => {
  it("parses the hold phrasing", () => {
    expect(parsePolicyRate(MPC_HOLD)).toBe(37);
    expect(parseOvernight(MPC_HOLD)).toEqual({ lending: 40, borrowing: 35.5 });
  });

  it("parses the change phrasing — taking the NEW rate, not the old one", () => {
    expect(parsePolicyRate(MPC_CUT)).toBe(37); // "from 38 percent to 37 percent"
  });

  // REGRESSION. Bounding the match with [^.] to "stay in the sentence" looks
  // right and is a trap: 39.5 contains a full stop, so the match dies at the
  // decimal. It silently dropped 8 of 48 decisions — including 43→40.5,
  // 40.5→39.5, 42.5→46 and 8.5→15, five of the cycle's biggest moves.
  it("survives a DECIMAL in the old rate — the bug that ate a third of the cycle", () => {
    const cases: [string, number][] = [
      ["…decided to reduce the policy rate (the one-week repo auction rate) from 39.5 percent to 38 percent.", 38],
      ["…to reduce the policy rate (the one-week repo auction rate) from 40.5 percent to 39.5 percent.", 39.5],
      ["…to increase the policy rate (the one-week repo auction rate) from 42.5 percent to 46 percent.", 46],
      ["…to increase the policy rate (the one-week repo auction rate) from 8.5 percent to 15 percent.", 15],
      ["…to reduce the policy rate (one-week repo auction rate) from 10.5 percent to 9 percent. The weakening effects…", 9],
    ];
    for (const [body, expected] of cases) {
      expect(parsePolicyRate(`The Committee has decided ${body}`), body).toBe(expected);
    }
  });

  it("parses the 2022 'constant at' phrasing", () => {
    expect(parsePolicyRate(MPC_2022)).toBe(14);
  });

  it("returns null rather than a stale value when it cannot read the release", () => {
    expect(parsePolicyRate("The Committee met and discussed the outlook.")).toBeNull();
    expect(parseOvernight("The Committee met.")).toBeNull();
  });

  it("takes the corridor from the most recent readable rate decision", () => {
    const c = deriveCorridor([
      item({ title: "Press Release on Interest Rates", published_at: "2026-06-11", body_text: MPC_HOLD }),
      item({ title: "Press Release on Interest Rates", published_at: "2026-01-22", body_text: MPC_CUT }),
    ]);
    expect(c?.policy).toBe(37);
    expect(c?.lending).toBe(40);
    expect(c?.borrowing).toBe(35.5);
    expect(c?.decidedAt).toBe("2026-06-11");
  });
});

describe("policy path", () => {
  const items = [
    item({ title: "Press Release on Interest Rates", published_at: "2026-01-22", body_text: MPC_CUT }),
    item({ title: "Press Release on Interest Rates", published_at: "2026-06-11", body_text: MPC_HOLD }),
    item({ title: "Press Release on Interest Rates", published_at: "2022-01-20", body_text: MPC_2022 }),
    item({ title: "Summary of the Monetary Policy Committee Meeting", published_at: "2026-06-18", body_text: MPC_HOLD }),
  ];

  it("is sorted, and ignores the meeting SUMMARY (comms, not a decision)", () => {
    const path = derivePolicyPath(items);
    expect(path.map((p) => p.date)).toEqual(["2022-01-20", "2026-01-22", "2026-06-11"]);
  });

  it("counts holds since the last change", () => {
    // 14 → 37 (change) → 37 (hold) = one meeting held at the current rate
    expect(meetingsHeld(derivePolicyPath(items))).toBe(1);
    expect(rateChanges(derivePolicyPath(items)).map((p) => p.rate)).toEqual([14, 37]);
  });
});

// ── reserve ratios, and the rules we cannot read ────────────────────────────

describe("reserve requirements", () => {
  it("reads the before/after table, and keeps the header's currency with each row", () => {
    const group = "Foreign currency deposits/participation funds";
    expect(parseReserveChanges(MACROPRU_WITH_TABLE)).toEqual([
      { label: "Demand deposits and deposits with maturities up to 1 month", group, prev: 30, next: 32 },
      { label: "With longer maturities", group, prev: 26, next: 28 },
    ]);
  });

  it("treats a terminated ratio as a rule change", () => {
    const t = parseTerminated(MACROPRU_WITH_TABLE);
    expect(t).toHaveLength(1);
    expect(t[0].was).toBe(2.5);
  });

  it("reads the date the ratios start binding", () => {
    expect(parseBindingDate(MACROPRU_WITH_TABLE)).toBe("2026-07-17");
  });

  it("returns null when the release states no binding date — it does not invent one", () => {
    expect(parseBindingDate(MACROPRU_NO_TABLE)).toBeNull();
  });

  // THE CORE HONESTY TEST. TCMB ships most macropru releases without a table
  // (10 of the last 12). A band that silently omits an in-force rule is the
  // exact failure this page exists to attack.
  it("finds NOTHING in the 23 May growth-limits release — because there is nothing there", () => {
    expect(parseReserveChanges(MACROPRU_NO_TABLE)).toEqual([]);
    expect(parseTerminated(MACROPRU_NO_TABLE)).toEqual([]);
  });

  it("reports that release as an UNREAD RULE rather than dropping it", () => {
    const items = [
      item({ title: "Press Release on Macroprudential Framework", published_at: "2026-07-01", body_text: MACROPRU_WITH_TABLE }),
      item({ title: "Press Release on Macroprudential Framework", published_at: "2026-05-23", body_text: MACROPRU_NO_TABLE }),
    ];
    const unread = unreadRules(items, "2026-07-12");
    expect(unread).toHaveLength(1);
    expect(unread[0].publishedAt).toBe("2026-05-23");
    expect(unread[0].bodyLength).toBeLessThan(600); // the tell: the table is gone

    // …and the readable one still sets the regime.
    const state = deriveReserves(items);
    expect(state?.changes).toHaveLength(2);
    expect(state?.bindsOn).toBe("2026-07-17");
    expect(state?.terminated[0].was).toBe(2.5);
  });
});

// ── the clock ───────────────────────────────────────────────────────────────

describe("board decisions", () => {
  it("parses the decision date and number out of the title", () => {
    const d = parseBoardDecision(
      "(12.03.2026 - 11428) Siemens Finansman A.Ş.'ye faaliyet izni verilmesine ilişkin Kurul Kararı",
    );
    expect(d).toMatchObject({ decidedAt: "2026-03-12", decisionNo: 11428 });
    expect(d?.subject).toMatch(/^Siemens Finansman/);
  });

  it("returns null for the 570 of 603 titles that carry no prefix", () => {
    expect(parseBoardDecision("Mart 2026 dönemi Üçer Aylık Temel Göstergeler yayımlanmıştır.")).toBeNull();
  });

  // Enpara: decided 2024-08-15, reached the feed 2026-03-06. The page this
  // replaces would file that under "March 2026".
  it("measures the lag between the decision and its publication", () => {
    const rows = decisionLags([
      item({
        source: "bddk",
        title: "(15.08.2024 - 10945) Enpara Bank A.Ş.'ye faaliyet izni verilmesine ilişkin Kurul Kararı",
        published_at: "2026-03-06",
      }),
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0].decidedAt).toBe("2024-08-15");
    expect(rows[0].lagDays).toBe(568);
  });
});

describe("licensing register", () => {
  const lags = decisionLags([
    item({
      source: "bddk",
      title: "(15.08.2024 - 10945) Enpara Bank A.Ş.'ye faaliyet izni verilmesine ilişkin Kurul Kararı",
      published_at: "2026-03-06",
    }),
    item({
      source: "bddk",
      title: "(31.10.2024 - 10979) FUPS Bank A.Ş.'ye faaliyet izni verilmesine ilişkin Kurul Kararı",
      published_at: "2026-03-06",
    }),
  ]);
  const banks = [
    { ticker: "ENPARA", name: "Enpara Bank" },
    { ticker: "AKBNK", name: "Akbank" },
  ];

  it("pulls the institution out of the decision subject", () => {
    expect(institutionOf("Enpara Bank A.Ş.'ye faaliyet izni verilmesine ilişkin Kurul Kararı")).toBe(
      "Enpara Bank",
    );
  });

  it("matches a licensed bank we cover, and flags one we do not", () => {
    const rows = licences(lags, banks);
    expect(rows).toHaveLength(2);

    const enpara = rows.find((r) => r.institution.startsWith("Enpara"));
    expect(enpara?.ticker).toBe("ENPARA");
    expect(enpara?.decision.lagDays).toBe(568);

    // FUPS is absent from `banks` ON PURPOSE (licensed Oct-2024, zero reports
    // filed). The detector must surface it — the caller decides gap vs watch.
    const fups = rows.find((r) => r.institution.startsWith("FUPS"));
    expect(fups?.ticker).toBeNull();
  });

  it("needs no alias for a bank it has never seen — an unmatched name IS the signal", () => {
    const rows = licences(lags, [{ ticker: "AKBNK", name: "Akbank" }]);
    expect(rows.every((r) => r.ticker === null)).toBe(true);
  });

  // BDDK licenses banks, leasing houses, factoring firms, asset managers and
  // e-money issuers from ONE numbered sequence. Without this filter the
  // "licensed but not covered" flag fires on Real Varlık Yönetim and Pratik
  // Finansman — institutions that will never be in the bank universe because
  // they are not banks. A flag that cries wolf 21 times is worse than no flag.
  it("keeps NON-BANKS out of the bank register", () => {
    expect(isBankInstitution("Enpara Bank")).toBe(true);
    expect(isBankInstitution("Marin Yatırım Bankası")).toBe(true);
    expect(isBankInstitution("Adil Katılım Bankası")).toBe(true);
    expect(isBankInstitution("Ziraat Dinamik Banka")).toBe(true);

    expect(isBankInstitution("Real Varlık Yönetim")).toBe(false);
    expect(isBankInstitution("Pratik Finansman")).toBe(false);
    expect(isBankInstitution("Tuna Faktoring")).toBe(false);
    expect(isBankInstitution("Ziraat Finansal Kiralama")).toBe(false);
    expect(isBankInstitution("Parolapara Elektronik Para ve Ödeme Hizmetleri")).toBe(false);

    const mixed = decisionLags([
      item({
        source: "bddk",
        title: "(13.06.2025 - 11226) Galata Varlık Yönetim A.Ş.'ye faaliyet izni verilmesine ilişkin Kurul Kararı",
        published_at: "2026-03-13",
      }),
      item({
        source: "bddk",
        title: "(26.02.2026 - 11424) İktisat Katılım Bankası A.Ş.'ye faaliyet izni verilmesine ilişkin Kurul Kararı",
        published_at: "2026-03-18",
      }),
    ]);
    const rows = licences(mixed, banks);
    expect(rows).toHaveLength(1);
    expect(rows[0].institution).toMatch(/İktisat/);
  });

  // A permission to ESTABLISH a bank is not a licence to OPERATE one, and a
  // revocation is neither. The first cut labelled all three "operating licence
  // granted", which is simply false for two of them.
  it("tells the three kinds of licensing decision apart", () => {
    const rows = licences(
      decisionLags([
        item({
          source: "bddk",
          title: "(12.03.2026 - 11432) Fuzul Katılım Bankası A.Ş. ünvanlı bir katılım bankası kurulmasına izin verilmesi",
          published_at: "2026-03-18",
        }),
        item({
          source: "bddk",
          title: "(12.03.2026 - 11433) SLM Yatırım Bankası A.Ş.'nin kuruluş izninin iptaline ilişkin Kurul Kararı",
          published_at: "2026-03-18",
        }),
        item({
          source: "bddk",
          title: "(26.02.2026 - 11424) İktisat Katılım Bankası A.Ş.'ye faaliyet izni verilmesine ilişkin Kurul Kararı",
          published_at: "2026-03-18",
        }),
      ]),
      [],
    );
    const byNo = new Map(rows.map((r) => [r.decision.decisionNo, r.kind]));
    expect(byNo.get(11432)).toBe("establishment");
    expect(byNo.get(11433)).toBe("revocation");
    expect(byNo.get(11424)).toBe("operating");
  });
});

describe("reserve cell labels", () => {
  // "Demand deposits … up to 1 month" alone reads as a LIRA ratio. It is not
  // one — the table's header says foreign currency, and the label must too.
  it("carries the currency from the table header into the cell label", () => {
    const [short, long] = parseReserveChanges(MACROPRU_WITH_TABLE);
    expect(reserveCellLabel(short)).toBe("FX deposits · ≤1 month");
    expect(reserveCellLabel(long)).toBe("FX deposits · longer maturities");
  });
});
