import { describe, expect, it } from "vitest";
import {
  MPC_DATES,
  aheadDates,
  dayLabel,
  mpcRunwayDays,
  nextMonthlyBulletinDue,
  nextMpc,
  rangeLabel,
} from "./ahead";

const at = (d: string) => new Date(`${d}T09:00:00Z`);

describe("MPC_DATES", () => {
  it("is sorted and well-formed — the CI freshness gate depends on it", () => {
    expect(MPC_DATES.every((d) => /^\d{4}-\d{2}-\d{2}$/.test(d))).toBe(true);
    expect([...MPC_DATES].sort()).toEqual([...MPC_DATES]);
  });
});

describe("nextMpc", () => {
  it("takes the next meeting on or after today", () => {
    // The day the hand-typed blocks said "JUL 23" — and were right, for nine days.
    expect(nextMpc(at("2026-07-14"))).toBe("2026-07-23");
    expect(nextMpc(at("2026-07-23"))).toBe("2026-07-23"); // the day itself still counts
    expect(nextMpc(at("2026-07-24"))).toBe("2026-09-10"); // …and rolls the day after
  });

  it("returns null rather than a past date once the table runs out", () => {
    // The page then OMITS the row. A schedule that has run out must not print
    // its last entry forever — that is the failure we are removing.
    expect(nextMpc(at("2099-01-01"))).toBeNull();
  });
});

describe("nextMonthlyBulletinDue", () => {
  it("expects the next month ~the 12th of month M+2, with its record name", () => {
    // Held May → the next record (June) is due ~12 Aug. This is what makes
    // holding May in mid-July FRESH rather than stale (admin-health / healthcheck).
    expect(nextMonthlyBulletinDue("2026-05")).toEqual({ date: "2026-08-12", record: "June" });
  });

  it("rolls the year", () => {
    expect(nextMonthlyBulletinDue("2026-11")).toEqual({ date: "2027-02-12", record: "December" });
    expect(nextMonthlyBulletinDue("2026-12")).toEqual({ date: "2027-03-12", record: "January" });
  });

  it("returns null on a malformed period", () => {
    expect(nextMonthlyBulletinDue("2026")).toBeNull();
    expect(nextMonthlyBulletinDue("")).toBeNull();
  });
});

describe("mpcRunwayDays", () => {
  it("measures what the CI gate fails on", () => {
    expect(mpcRunwayDays(at("2026-07-14"))).toBeGreaterThan(90);
    expect(mpcRunwayDays(at("2027-12-01"))).toBeLessThan(90);
  });
});

describe("aheadDates — the scraped TCMB calendar", () => {
  // release_calendar rows: D1 `kind` is snake_case.
  const events = [
    { kind: "mpc_decision", event_date: "2026-09-10" },
    { kind: "mpc_decision", event_date: "2026-07-23" },
    { kind: "mpc_minutes", event_date: "2026-07-30" },
    { kind: "inflation_report", event_date: "2026-08-14" },
    { kind: "financial_stability_report", event_date: "2026-11-20" },
  ];

  it("picks the next event of each kind from the scrape", () => {
    const a = aheadDates({ now: at("2026-07-24"), events });
    // The 2026-07-23 decision is past; the next is 2026-09-10.
    expect(a.mpc?.date).toBe("2026-09-10");
    expect(a.mpc?.rule).toBe("tcmb published calendar");
    expect(a["mpc-minutes"]?.date).toBe("2026-07-30");
    expect(a["inflation-report"]?.date).toBe("2026-08-14");
    expect(a.fsr?.date).toBe("2026-11-20");
  });

  it("falls back to MPC_DATES for the decision when the scrape is empty", () => {
    const a = aheadDates({ now: at("2026-07-14"), events: [] });
    expect(a.mpc?.date).toBe("2026-07-23"); // from MPC_DATES
    expect(a.mpc?.rule).toBe("tcmb calendar (fallback list)");
    // The report kinds have no fallback — no scrape, no row.
    expect(a["inflation-report"]).toBeUndefined();
    expect(a.fsr).toBeUndefined();
  });

  it("omits a kind whose only events are in the past", () => {
    const a = aheadDates({
      now: at("2027-01-01"),
      events: [{ kind: "inflation_report", event_date: "2026-08-14" }],
    });
    expect(a["inflation-report"]).toBeUndefined();
  });
});

describe("aheadDates — the BDDK monthly bulletin", () => {
  it("derives the record month and its publication date", () => {
    // Live D1 at the time of writing: the last monthly record is May 2026. The
    // hand-typed row said "AUG ~12 · June record" — the rule reproduces it exactly.
    const a = aheadDates({ now: at("2026-07-14"), latestMonthly: "2026-05" });
    expect(a["bddk-monthly"]?.when).toBe("AUG ~12");
    expect(a["bddk-monthly"]?.record).toBe("June");
    expect(a["bddk-monthly"]?.date).toBe("2026-08-12");
  });

  it("rolls the record and the publication across a year boundary", () => {
    const a = aheadDates({ now: at("2027-01-20"), latestMonthly: "2026-11" });
    expect(a["bddk-monthly"]?.record).toBe("December");
    expect(a["bddk-monthly"]?.date).toBe("2027-02-12");
  });

  it("says nothing when the record is unknown", () => {
    expect(aheadDates({ now: at("2026-07-14"), latestMonthly: null })["bddk-monthly"]).toBeUndefined();
  });
});

describe("aheadDates — the BRSA filing window", () => {
  it("projects the next quarter's window from the observed lag", () => {
    // Observed in D1: the five Q1-2026 KAP filings landed 35–38 days after
    // quarter-end. Q2 ends 30 Jun → the window is early August, NOT the
    // "AUG–SEP" that was typed in.
    const a = aheadDates({
      now: at("2026-07-14"),
      latestAudit: "2026Q1",
      filingLag: { loDays: 35, hiDays: 38, n: 5 },
    });
    expect(a["brsa-filings"]?.record).toBe("Q2");
    expect(a["brsa-filings"]?.date).toBe("2026-08-04");
    expect(a["brsa-filings"]?.when).toBe("AUG 4–7");
    expect(a["brsa-filings"]?.rule).toContain("n=5");
  });

  it("rolls Q4 into the next year", () => {
    const a = aheadDates({
      now: at("2027-01-05"),
      latestAudit: "2026Q4",
      filingLag: { loDays: 35, hiDays: 38, n: 5 },
    });
    expect(a["brsa-filings"]?.record).toBe("Q1");
    expect(a["brsa-filings"]?.date).toBe("2027-05-05"); // Q1 ends 31 Mar + 35d
  });

  it("prints no window when too few filings back it", () => {
    // A window we cannot support is a window we do not print.
    const a = aheadDates({
      now: at("2026-07-14"),
      latestAudit: "2026Q1",
      filingLag: { loDays: 35, hiDays: 38, n: 2 },
    });
    expect(a["brsa-filings"]).toBeUndefined();
    expect(aheadDates({ now: at("2026-07-14"), latestAudit: "2026Q1" })["brsa-filings"]).toBeUndefined();
  });
});

describe("labels", () => {
  it("formats a day and a window", () => {
    expect(dayLabel("2026-07-23")).toBe("JUL 23");
    expect(rangeLabel("2026-08-04", "2026-08-07")).toBe("AUG 4–7");
    expect(rangeLabel("2026-08-30", "2026-09-02")).toBe("AUG 30 – SEP 2");
  });
});
