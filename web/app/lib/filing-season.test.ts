import { describe, expect, it } from "vitest";
import {
  deriveFilingSeason,
  priorPeriod,
  trackingWindow,
  type FilingSignals,
} from "./filing-season";

const at = (iso: string) => new Date(`${iso}T12:00:00Z`);

describe("trackingWindow", () => {
  it("tracks Q2 inside the July–August window", () => {
    const w = trackingWindow(at("2026-08-07"));
    expect(w.period).toBe("2026Q2");
    expect(w.priorPeriod).toBe("2026Q1");
    expect(w.open).toBe(true);
    expect(w.opensISO).toBe("2026-07-20");
    expect(w.closesISO).toBe("2026-08-20");
    expect(w.dayOfWindow).toBe(19);
  });

  it("keeps showing the last opened window between seasons", () => {
    const w = trackingWindow(at("2026-07-19"));
    expect(w.period).toBe("2026Q1");
    expect(w.open).toBe(false);
    expect(w.dayOfWindow).toBeNull();
  });

  it("crosses the year boundary to the prior Q3 window in early January", () => {
    const w = trackingWindow(at("2026-01-10"));
    expect(w.period).toBe("2025Q3");
    expect(w.open).toBe(false);
  });

  it("opens the Q4 window on Jan 20 and runs it through Mar 15 (annual filings)", () => {
    expect(trackingWindow(at("2026-01-20"))).toMatchObject({
      period: "2025Q4",
      open: true,
      dayOfWindow: 1,
    });
    expect(trackingWindow(at("2026-03-15")).open).toBe(true);
    expect(trackingWindow(at("2026-03-16")).open).toBe(false);
  });
});

describe("priorPeriod", () => {
  it("steps back one quarter, across years", () => {
    expect(priorPeriod("2026Q1")).toBe("2025Q4");
    expect(priorPeriod("2026Q3")).toBe("2026Q2");
  });
});

const WINDOW = trackingWindow(at("2026-08-07"));

function signals(partial: Partial<FilingSignals>): FilingSignals {
  return {
    banks: [],
    priorKinds: [],
    expected: [],
    extractions: [],
    results: [],
    ...partial,
  };
}

describe("deriveFilingSeason", () => {
  it("flags results-out-but-PDF-pending from the KAP evidence (the İş shape)", () => {
    const r = deriveFilingSeason(
      WINDOW,
      signals({
        banks: [{ ticker: "ISCTR", name: "İş Bankası" }],
        priorKinds: [
          { bank_ticker: "ISCTR", kind: "unconsolidated" },
          { bank_ticker: "ISCTR", kind: "consolidated" },
        ],
        results: [
          { ticker: "ISCTR", event_date: "2026-08-05", url: "https://kap.example/1" },
          { ticker: "ISCTR", event_date: "2026-08-06", url: "https://kap.example/2" },
        ],
      }),
    );
    expect(r.banks[0].status).toBe("results_only");
    expect(r.banks[0].resultsAt).toBe("2026-08-05");
    expect(r.banks[0].resultsUrl).toBe("https://kap.example/1");
    expect(r.banks[0].kinds.map((k) => k.state)).toEqual(["none", "none"]);
    expect(r.counts.results_only).toBe(1);
  });

  it("ranks extracted > partial > acquired, and a failed extraction stays acquired-level", () => {
    const r = deriveFilingSeason(
      WINDOW,
      signals({
        banks: [
          { ticker: "AAA", name: "A" },
          { ticker: "BBB", name: "B" },
          { ticker: "CCC", name: "C" },
          { ticker: "DDD", name: "D" },
        ],
        priorKinds: ["AAA", "BBB", "CCC", "DDD"].flatMap((t) => [
          { bank_ticker: t, kind: "unconsolidated" },
          { bank_ticker: t, kind: "consolidated" },
        ]),
        expected: [
          { bank_ticker: "BBB", kind: "consolidated", pdf_present: 1 },
          { bank_ticker: "CCC", kind: "unconsolidated", pdf_present: 1 },
        ],
        extractions: [
          { bank_ticker: "AAA", kind: "unconsolidated", success: 1 },
          { bank_ticker: "AAA", kind: "consolidated", success: 1 },
          { bank_ticker: "BBB", kind: "unconsolidated", success: 1 },
          { bank_ticker: "DDD", kind: "unconsolidated", success: 0 },
        ],
      }),
    );
    const by = Object.fromEntries(r.banks.map((b) => [b.ticker, b]));
    expect(by.AAA.status).toBe("extracted");
    expect(by.BBB.status).toBe("partial");
    expect(by.CCC.status).toBe("acquired");
    expect(by.DDD.status).toBe("acquired");
    expect(by.DDD.kinds.find((k) => k.kind === "unconsolidated")?.state).toBe("failed");
  });

  it("acquired evidence outranks a results filing; no evidence at all is 'none', not 'not published'", () => {
    const r = deriveFilingSeason(
      WINDOW,
      signals({
        banks: [
          { ticker: "EEE", name: "E" },
          { ticker: "FFF", name: "F" },
        ],
        priorKinds: [
          { bank_ticker: "EEE", kind: "unconsolidated" },
          { bank_ticker: "FFF", kind: "unconsolidated" },
        ],
        expected: [{ bank_ticker: "EEE", kind: "unconsolidated", pdf_present: 1 }],
        results: [{ ticker: "EEE", event_date: "2026-08-01", url: "u" }],
      }),
    );
    const by = Object.fromEntries(r.banks.map((b) => [b.ticker, b]));
    expect(by.EEE.status).toBe("acquired");
    expect(by.FFF.status).toBe("none");
    expect(by.FFF.resultsAt).toBeNull();
  });

  it("derives each bank's filing shape from the prior period, falling back to current, then both", () => {
    const r = deriveFilingSeason(
      WINDOW,
      signals({
        banks: [
          { ticker: "SOLO", name: "Solo-only bank" },
          { ticker: "CURR", name: "New bank seen this period" },
          { ticker: "BLANK", name: "Never seen" },
        ],
        priorKinds: [{ bank_ticker: "SOLO", kind: "unconsolidated" }],
        expected: [{ bank_ticker: "CURR", kind: "unconsolidated", pdf_present: 0 }],
      }),
    );
    const by = Object.fromEntries(r.banks.map((b) => [b.ticker, b]));
    expect(by.SOLO.kinds.map((k) => k.kind)).toEqual(["unconsolidated"]);
    expect(by.CURR.kinds.map((k) => k.kind)).toEqual(["unconsolidated"]);
    expect(by.BLANK.kinds.map((k) => k.kind)).toEqual(["unconsolidated", "consolidated"]);
    const total = Object.values(r.counts).reduce((a, b) => a + b, 0);
    expect(total).toBe(r.banks.length);
  });
});
