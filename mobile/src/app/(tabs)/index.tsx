/**
 * Overview — the brief.
 *
 * The website's home page is two layers: the computed brief, then the evidence
 * under it. The phone keeps layer one and drops layer two, because the evidence
 * layer is six multi-series charts and a scorecard grid that cannot be read at
 * this width. What survives is exactly what a brief is for: where the sector
 * stands, what moved, why, and what is flagged.
 *
 * Every figure arrives computed from the API. Nothing on this screen is derived
 * client-side — if a number needs new arithmetic it goes in web/app/lib so the
 * website and the app cannot print different values for the same metric.
 */
import { Link } from "expo-router";
import { View } from "react-native";

import { endpoints } from "../../api/client";
import type { Overview } from "../../api/types";
import { useResource } from "../../api/use-resource";
import { Sparkline } from "../../components/charts";
import {
  ErrorState,
  Loading,
  Screen,
  ScreenHeader,
  StaleNote,
} from "../../components/screen";
import { Delta, Figure, Hairline, Label, Row, Section, Text } from "../../components/ui";
import { num, pct, periodLabel, pp, signedPct, tl } from "../../format";
import { useTheme } from "../../theme";

export default function OverviewScreen() {
  const { colors, space } = useTheme();
  const { data, loading, refreshing, error, cachedAt, refresh } =
    useResource<Overview>("overview", endpoints.overview());

  if (loading && !data) return <Screen><Loading /></Screen>;
  if (!data) {
    return (
      <Screen>
        <ScreenHeader title="Overview" />
        <ErrorState message={error?.message ?? "No data."} onRetry={refresh} />
      </Screen>
    );
  }

  const activeFlags = data.flags.filter((f) => f.active);

  return (
    <Screen refreshing={refreshing} onRefresh={refresh}>
      <ScreenHeader
        title="Overview"
        record={`RECORD ${data.record.label} · VS ${data.record.vs}`}
      />
      <StaleNote cachedAt={cachedAt} error={error} />

      {/* ── The tape ──────────────────────────────────────────────────── */}
      {data.tape.length > 0 && (
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: space.md, paddingTop: space.md }}>
          {data.tape.map((t) => (
            <View key={t.label} style={{ flexDirection: "row", alignItems: "baseline", gap: 4 }}>
              <Label>{t.label}</Label>
              <Figure size={13}>{typeof t.value === "number" ? num(t.value, 2) : t.value}</Figure>
              {t.changePct != null && (
                <Delta value={t.changePct} format={(v) => signedPct(v, 1)} good="up" size={11} />
              )}
            </View>
          ))}
        </View>
      )}

      {/* ── Vitals ────────────────────────────────────────────────────── */}
      <Section title="The vitals" meta="trailing 13m">
        <View style={{ flexDirection: "row", flexWrap: "wrap" }}>
          {data.vitals.map((v, i) => (
            <View
              key={v.key}
              style={{
                width: "50%",
                paddingVertical: space.md,
                paddingRight: i % 2 === 0 ? space.md : 0,
                paddingLeft: i % 2 === 1 ? space.md : 0,
                borderBottomWidth: i < data.vitals.length - 2 ? 1 : 0,
                borderBottomColor: colors.hair,
                // A left rule on the right-hand column is the Desk's grid: the
                // cells are separated by a hairline, not by a gap.
                borderLeftWidth: i % 2 === 1 ? 1 : 0,
                borderLeftColor: colors.hair,
              }}
            >
              <Label>{v.label}</Label>
              <View style={{ flexDirection: "row", alignItems: "baseline", gap: 3, marginTop: 4 }}>
                <Figure size={22} weight="medium">{num(v.value, v.decimals)}</Figure>
                <Text size={12} tone="faint">{v.unit}</Text>
              </View>
              <View style={{ marginTop: space.xs }}>
                <Sparkline points={v.series} />
              </View>
              <View style={{ flexDirection: "row", gap: 4, marginTop: 2 }}>
                <Label>12m</Label>
                <Delta value={v.change12} format={(x) => pp(x, 1)} good={v.good} size={11} />
              </View>
            </View>
          ))}
        </View>
      </Section>

      {/* ── Levels ────────────────────────────────────────────────────── */}
      <Section title="Levels" meta="sector">
        <Row label="Total assets" value={tl(data.levels.totalAssets)} />
        <Row label="Assets y/y" value={pct(data.levels.assetsYoY, 1)} />
        <Row label="Loan growth y/y" value={pct(data.levels.loansYoY, 1)} />
        <Row label="Deposit growth y/y" value={pct(data.levels.depositsYoY, 1)} />
      </Section>

      {/* ── Movers ────────────────────────────────────────────────────── */}
      <Section title="Movers" meta={`${data.record.vs} → ${data.record.label}`}>
        {data.movers.map((m) => {
          const delta = m.curr != null && m.prev != null ? m.curr - m.prev : null;
          return (
            <Row
              key={m.key}
              label={m.label}
              note={m.note ?? undefined}
              right={
                <View style={{ alignItems: "flex-end" }}>
                  <View style={{ flexDirection: "row", alignItems: "baseline", gap: space.sm }}>
                    <Figure size={12} tone="faint">{num(m.prev, m.decimals)}</Figure>
                    <Figure size={15} weight="medium">{num(m.curr, m.decimals)}</Figure>
                  </View>
                  <Delta value={delta} format={(v) => pp(v, m.decimals)} good={m.good} size={11} />
                </View>
              }
            />
          );
        })}
      </Section>

      {/* ── Transmission ──────────────────────────────────────────────── */}
      <Section title="The backdrop → the banks" meta="computed">
        {data.transmission.map((t) => (
          <View key={t.key} style={{ paddingVertical: space.md }}>
            <View style={{ flexDirection: "row", alignItems: "baseline", gap: space.sm }}>
              <Figure size={15} weight="medium">{num(t.value, t.decimals)}</Figure>
              {t.unit ? <Text size={12} tone="faint">{t.unit}</Text> : null}
              <Label>{t.label}</Label>
            </View>
            <Text size={13} tone="muted" style={{ marginTop: 4 }}>
              {transmissionCopy(t)}
            </Text>
            <Hairline style={{ marginTop: space.md }} />
          </View>
        ))}
      </Section>

      {/* ── Flags ─────────────────────────────────────────────────────── */}
      <Section title="Flags" meta={`rule-based · ${activeFlags.length}`}>
        {activeFlags.length === 0 ? (
          <View style={{ paddingVertical: space.md }}>
            <Text size={13} tone="muted">
              NPL streak, capital drift, funding stretch and real returns are all below
              threshold.
            </Text>
          </View>
        ) : (
          activeFlags.map((f) => (
            <View key={f.code} style={{ paddingVertical: space.md }}>
              <Text weight="semibold" size={14} tone="warning">{FLAG_TITLES[f.code] ?? f.code}</Text>
              <Text size={13} tone="muted" style={{ marginTop: 2 }}>{flagCopy(f.code, f.operands)}</Text>
              {/* The rule is printed, always. A flag whose test is invisible is
                  an opinion; printed, it is a measurement. */}
              <Label style={{ marginTop: 6 }}>{f.rule}</Label>
              <Hairline style={{ marginTop: space.md }} />
            </View>
          ))
        )}
      </Section>

      {/* ── Standings ─────────────────────────────────────────────────── */}
      <Section title="Standings" meta={`car · ${periodLabel(data.standings.period)}`}>
        <Label tone="muted" style={{ paddingTop: space.md }}>Best capitalised</Label>
        {data.standings.best.map((r) => (
          <Link key={r.ticker} href={`/banks/${r.ticker}`} asChild>
            <View>
              <Row label={r.name} value={pct(r.car, 1)} />
            </View>
          </Link>
        ))}
        <Label tone="muted" style={{ paddingTop: space.lg }}>Thinnest buffer</Label>
        {data.standings.thinnest.map((r) => (
          <Link key={r.ticker} href={`/banks/${r.ticker}`} asChild>
            <View>
              <Row label={r.name} value={pct(r.car, 1)} />
            </View>
          </Link>
        ))}
      </Section>

      {/* ── Ahead ─────────────────────────────────────────────────────── */}
      <Section title="Ahead" meta="derived">
        {data.ahead.map((a) => (
          <Row
            key={a.kind}
            label={AHEAD_TITLES[a.kind] ?? a.kind}
            note={a.record ? `record ${a.record}` : undefined}
            right={<Figure size={13}>{a.when}</Figure>}
          />
        ))}
      </Section>

      <View style={{ paddingTop: space.xl }}>
        <Text size={12} tone="faint">
          {data.coverage.banks} banks · every figure computed from source series ·
          full depth at carthago.app
        </Text>
      </View>
    </Screen>
  );
}

const FLAG_TITLES: Record<string, string> = {
  "real-roe": "Real returns",
  "npl-streak": "NPL streak",
  "car-drift": "Capital drift",
  "funding-stretch": "Funding stretch",
};

const AHEAD_TITLES: Record<string, string> = {
  mpc: "TCMB MPC — rate decision",
  "mpc-minutes": "TCMB MPC minutes",
  "inflation-report": "TCMB Inflation Report",
  fsr: "TCMB Financial Stability Report",
  "bddk-monthly": "BDDK monthly bulletin",
  "brsa-filings": "BRSA filings",
};

/**
 * Client-side COPY over server-side OPERANDS.
 *
 * The sentence is written here; every number in it came from the API. That
 * split is deliberate — prose belongs to the surface (the website's version has
 * inline route links this screen can't use), but a figure inside a sentence
 * must be the same figure the chart above it plots.
 */
function flagCopy(code: string, o: Record<string, number | null>): string {
  switch (code) {
    case "real-roe":
      return `ROE ${pct(o.roe, 1)} against ${pct(o.cpi, 1)} 12m-avg CPI: equity compounds a ${pct(Math.abs(o.real ?? 0), 1)} real loss.`;
    case "npl-streak":
      return `${num(o.streak, 0)} consecutive monthly rises (${pct(o.from, 2)} → ${pct(o.to, 2)}). Persistence is the signal, not the level.`;
    case "car-drift":
      return `Buffer ${pp(o.buffer, 1)} over the 12% minimum, drifting ${pp(o.drift12m, 1)} a year.`;
    case "funding-stretch":
      return `TL+FC loan/deposit ${pct(o.ldr, 1)}, above the ${num(o.line, 0)}% line — growth is leaning on non-deposit funding.`;
    default:
      return "";
  }
}

function transmissionCopy(t: Overview["transmission"][number]): string {
  const e = t.effect;
  switch (t.key) {
    case "cpi":
      return `ROE ${pct(e.nominal, 1)} ≈ ${signedPct(e.real, 1)} in real terms, deflated by ${e.deflatorBasis}.`;
    case "funding":
      return e.low24m != null
        ? `Deposits reprice first — NIM rebuilt from ${pct(e.low24m, 1)} to ${pct(e.nominal, 1)}; each policy move feeds the margin with a lag.`
        : `Deposits reprice first; each policy move feeds the margin with a lag.`;
    case "credit":
      return `Loan growth ${pct(e.nominal, 1)} nominal, deflated by ${e.deflatorBasis} ${pct(e.deflator, 1)}.`;
    case "usdtry":
      return "The lira's path sets the dollarization incentive — the FX share of deposits is the tell.";
    default:
      return "";
  }
}
