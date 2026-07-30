/**
 * One bank.
 *
 * Scorecard → earnings quality → stages → franchise → that bank's KAP feed.
 *
 * The scorecard metric is SELECTABLE: tapping a row promotes it into the chart
 * at the top. One chart that changes beats ten stacked charts on a phone, and it
 * keeps the scrubbed value in a single place on screen.
 */
import { Stack, useLocalSearchParams } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { useMemo, useState } from "react";
import { Pressable, View } from "react-native";

import { endpoints } from "../../api/client";
import type { BankDetail, ScorecardMetric } from "../../api/types";
import { useResource } from "../../api/use-resource";
import { MetricChart, type ScrubPoint } from "../../components/charts";
import {
  ErrorState,
  Loading,
  Screen,
  ScreenHeader,
  StaleNote,
} from "../../components/screen";
import { Figure, Hairline, Label, Row, Section, Text } from "../../components/ui";
import { ago, metric as fmtMetric, num, pct, periodLabel, tl } from "../../format";
import { useTheme } from "../../theme";

export default function BankScreen() {
  const { ticker } = useLocalSearchParams<{ ticker: string }>();
  const { colors, space } = useTheme();

  const upper = (ticker ?? "").toUpperCase();
  const { data, loading, refreshing, error, cachedAt, refresh } = useResource<BankDetail>(
    `bank:${upper}`,
    endpoints.bank(upper),
  );

  const [selected, setSelected] = useState<string | null>(null);
  const [scrub, setScrub] = useState<ScrubPoint | null>(null);

  const active: ScorecardMetric | null = useMemo(() => {
    if (!data) return null;
    return (
      data.scorecard.find((m) => m.key === selected) ??
      // Default to ROE — the question a reader arrives with — falling back to
      // the first metric that actually has a value.
      data.scorecard.find((m) => m.key === "roe" && m.value != null) ??
      data.scorecard.find((m) => m.value != null) ??
      data.scorecard[0] ??
      null
    );
  }, [data, selected]);

  if (loading && !data) {
    return (
      <>
        <Stack.Screen options={{ title: upper }} />
        <Screen><Loading /></Screen>
      </>
    );
  }

  if (!data || !active) {
    return (
      <>
        <Stack.Screen options={{ title: upper }} />
        <Screen>
          <ScreenHeader title={upper} />
          <ErrorState message={error?.message ?? "No filings held."} onRetry={refresh} />
        </Screen>
      </>
    );
  }

  // While scrubbing, the headline shows the touched point, not the latest — so
  // there is exactly one number on screen claiming to be "the" value.
  const shown = scrub ? scrub.v : active.value;
  const shownPeriod = scrub ? scrub.t : data.period;

  return (
    <>
      <Stack.Screen options={{ title: data.ticker }} />
      <Screen refreshing={refreshing} onRefresh={refresh}>
        <ScreenHeader
          title={data.name}
          record={`${data.typeLabel ? data.typeLabel.toUpperCase() + " · " : ""}${periodLabel(data.period).toUpperCase()} · ${data.coverage.periodsHeld} QUARTERS HELD`}
        />
        <StaleNote cachedAt={cachedAt} error={error} />

        {data.peerExcluded && (
          <Text size={13} tone="warning" style={{ paddingTop: space.md }}>
            A central counterparty, not a lender — these ratios are computed against a
            clearing house&apos;s balance sheet and are excluded from peer rankings.
          </Text>
        )}

        {/* ── The selected metric ───────────────────────────────────────── */}
        <View style={{ paddingTop: space.lg }}>
          <Label tone="muted">{active.label}</Label>
          <View style={{ flexDirection: "row", alignItems: "baseline", gap: space.sm, marginTop: 4 }}>
            <Figure size={30} weight="medium">
              {fmtMetric(shown, active.unit, active.decimals)}
            </Figure>
            <Label>{periodLabel(shownPeriod)}</Label>
          </View>
          <View style={{ marginTop: space.md }}>
            <MetricChart
              points={active.series}
              zeroLine={active.key === "roe" || active.key === "roa"}
              onScrub={setScrub}
            />
          </View>
          {/* How the number was MADE, printed under it. */}
          {active.rule && <Label style={{ marginTop: space.sm }}>{active.rule}</Label>}
        </View>

        {/* ── Scorecard ─────────────────────────────────────────────────── */}
        <Section title="Scorecard" meta="tap to chart">
          {data.scorecard.map((m) => {
            const isActive = m.key === active.key;
            return (
              <View key={m.key}>
                <Pressable
                  onPress={() => { setSelected(m.key); setScrub(null); }}
                  style={({ pressed }) => ({
                    opacity: pressed ? 0.6 : 1,
                    flexDirection: "row",
                    alignItems: "center",
                    justifyContent: "space-between",
                    paddingVertical: space.md,
                  })}
                >
                  <View style={{ flexDirection: "row", alignItems: "center", gap: space.sm }}>
                    {/* Selection is a navy rule, not a fill — the Desk marks
                        state with a mark, not a background. */}
                    <View
                      style={{
                        width: 2,
                        height: 14,
                        backgroundColor: isActive ? colors.data : "transparent",
                      }}
                    />
                    <Text weight={isActive ? "medium" : "regular"}>{m.label}</Text>
                  </View>
                  <Figure weight={isActive ? "medium" : "regular"}>
                    {fmtMetric(m.value, m.unit, m.decimals)}
                  </Figure>
                </Pressable>
                <Hairline />
              </View>
            );
          })}
        </Section>

        {/* ── Earnings quality ──────────────────────────────────────────── */}
        {data.earningsQuality.freeProvision != null &&
          data.earningsQuality.freeProvision > 0 && (
            <Section title="Earnings quality" meta="free provision">
              <Row label="ROE, reported" value={pct(data.earningsQuality.roe, 1)} />
              <Row label="ROE, FP-adjusted" value={pct(data.earningsQuality.roeAdjusted, 1)} />
              <Row label="Free provision stock" value={tl(data.earningsQuality.freeProvision)} />
              <Text size={12} tone="faint" style={{ paddingTop: space.sm }}>
                Serbest karşılık is discretionary: building it depresses reported earnings,
                releasing it flatters them. The adjusted line strips both.
              </Text>
            </Section>
          )}

        {/* ── Stages ────────────────────────────────────────────────────── */}
        {data.stages && (
          <Section title="Loan stages" meta={`tfrs 9 · ${periodLabel(data.stages.period)}`}>
            <Row label="Stage 1" value={tl(data.stages.stage1)} note={`coverage ${pct(data.stages.coverage1, 2)}`} />
            <Row label="Stage 2" value={tl(data.stages.stage2)} note={`coverage ${pct(data.stages.coverage2, 2)}`} />
            <Row label="Stage 3" value={tl(data.stages.stage3)} note={`coverage ${pct(data.stages.coverage3, 2)}`} />
            <Row label="Total" value={tl(data.stages.total)} />
          </Section>
        )}

        {/* ── Franchise ─────────────────────────────────────────────────── */}
        {data.profile && (
          <Section title="Franchise" meta={periodLabel(data.profile.period)}>
            <Row label="Branches" value={num(data.profile.branchesTotal, 0)} />
            {data.profile.branchesForeign != null && data.profile.branchesForeign > 0 && (
              <Row label="— of which foreign" value={num(data.profile.branchesForeign, 0)} />
            )}
            <Row label="Personnel" value={num(data.profile.personnel, 0)} />
          </Section>
        )}

        {/* ── Disclosures ───────────────────────────────────────────────── */}
        {data.news.length > 0 && (
          <Section title="Disclosures" meta="kap">
            {data.news.slice(0, 8).map((n) => (
              <Row
                key={n.id}
                label={<Text size={14}>{n.title}</Text>}
                note={`${n.source.toUpperCase()} · ${ago(n.publishedAt)}`}
                onPress={() => void WebBrowser.openBrowserAsync(n.url)}
                right={null}
              />
            ))}
          </Section>
        )}

        <Pressable
          onPress={() => void WebBrowser.openBrowserAsync(data.web)}
          style={{ paddingTop: space.xl }}
        >
          <Text weight="medium" style={{ color: colors.primary }}>
            Full statements, ratios and history at carthago.app →
          </Text>
        </Pressable>
      </Screen>
    </>
  );
}
