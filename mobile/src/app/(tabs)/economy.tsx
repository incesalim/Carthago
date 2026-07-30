/**
 * Economy — the backdrop.
 *
 * Same pattern as the bank screen: a headline band, then one selectable chart.
 * The website's /economy tab plots twenty series across five sections; here they
 * are a list you promote into the chart, because twenty small charts on a phone
 * is a scroll nobody finishes.
 */
import { useMemo, useState } from "react";
import { Pressable, View } from "react-native";

import { endpoints } from "../../api/client";
import type { Economy } from "../../api/types";
import { useResource } from "../../api/use-resource";
import { MetricChart, type ScrubPoint } from "../../components/charts";
import {
  ErrorState,
  Loading,
  Screen,
  ScreenHeader,
  StaleNote,
} from "../../components/screen";
import { Figure, Hairline, Label, Section, Text } from "../../components/ui";
import { num, periodLabel } from "../../format";
import { useTheme } from "../../theme";

/** Series shown, in reading order, with the decimals each deserves. A rate to
 *  two decimals is false precision; USD/TRY to one is useless. */
const SERIES: { key: string; label: string; decimals: number; zeroLine?: boolean }[] = [
  { key: "cpiYoY", label: "CPI, y/y", decimals: 1 },
  { key: "cpiMoM", label: "CPI, m/m", decimals: 2, zeroLine: true },
  { key: "exp12m", label: "Inflation expectation, 12m", decimals: 1 },
  { key: "fundingMonthly", label: "TCMB funding cost", decimals: 1 },
  { key: "realRate", label: "Real funding rate, ex-ante", decimals: 1, zeroLine: true },
  { key: "gdpGrowth", label: "GDP, y/y", decimals: 1, zeroLine: true },
  { key: "ipGrowth", label: "Industrial production, y/y", decimals: 1, zeroLine: true },
  { key: "unemployment", label: "Unemployment", decimals: 1 },
  { key: "usdtry", label: "USD/TRY", decimals: 2 },
  { key: "reer", label: "Real effective exchange rate", decimals: 1 },
  { key: "ca12m", label: "Current account, 12m", decimals: 1, zeroLine: true },
  { key: "budgetPctGdp", label: "Budget balance, 12m", decimals: 1, zeroLine: true },
];

export default function EconomyScreen() {
  const { colors, space } = useTheme();
  const { data, loading, refreshing, error, cachedAt, refresh } =
    useResource<Economy>("economy", endpoints.economy());

  const [selected, setSelected] = useState("cpiYoY");
  const [scrub, setScrub] = useState<ScrubPoint | null>(null);

  const active = useMemo(
    () => SERIES.find((s) => s.key === selected) ?? SERIES[0],
    [selected],
  );

  if (loading && !data) return <Screen><Loading /></Screen>;
  if (!data) {
    return (
      <Screen>
        <ScreenHeader title="Economy" />
        <ErrorState message={error?.message ?? "No data."} onRetry={refresh} />
      </Screen>
    );
  }

  const points = data.series[active.key] ?? [];
  const latest = points.at(-1);
  const shown = scrub ? scrub.v : (latest?.v ?? null);
  const shownAt = scrub ? scrub.t : (latest?.t ?? null);

  return (
    <Screen refreshing={refreshing} onRefresh={refresh}>
      <ScreenHeader title="Economy" record={data.source.toUpperCase()} />
      <StaleNote cachedAt={cachedAt} error={error} />

      {/* ── The selected series ───────────────────────────────────────── */}
      <View style={{ paddingTop: space.lg }}>
        <Label tone="muted">{active.label}</Label>
        <View style={{ flexDirection: "row", alignItems: "baseline", gap: space.sm, marginTop: 4 }}>
          <Figure size={30} weight="medium">{num(shown, active.decimals)}</Figure>
          <Text size={13} tone="faint">{data.units[active.key] ?? ""}</Text>
          <Label>{periodLabel(shownAt)}</Label>
        </View>
        <View style={{ marginTop: space.md }}>
          <MetricChart points={points} zeroLine={active.zeroLine} onScrub={setScrub} />
        </View>
      </View>

      {/* ── The series list ───────────────────────────────────────────── */}
      <Section title="Series" meta="tap to chart">
        {SERIES.map((s) => {
          const isActive = s.key === active.key;
          const last = data.series[s.key]?.at(-1)?.v ?? null;
          return (
            <View key={s.key}>
              <Pressable
                onPress={() => { setSelected(s.key); setScrub(null); }}
                style={({ pressed }) => ({
                  opacity: pressed ? 0.6 : 1,
                  flexDirection: "row",
                  alignItems: "center",
                  justifyContent: "space-between",
                  paddingVertical: space.md,
                })}
              >
                <View style={{ flexDirection: "row", alignItems: "center", gap: space.sm, flex: 1 }}>
                  <View
                    style={{
                      width: 2,
                      height: 14,
                      backgroundColor: isActive ? colors.data : "transparent",
                    }}
                  />
                  <Text weight={isActive ? "medium" : "regular"}>{s.label}</Text>
                </View>
                <View style={{ flexDirection: "row", alignItems: "baseline", gap: 4 }}>
                  <Figure weight={isActive ? "medium" : "regular"}>{num(last, s.decimals)}</Figure>
                  <Label>{data.units[s.key] ?? ""}</Label>
                </View>
              </Pressable>
              <Hairline />
            </View>
          );
        })}
      </Section>

      <Text size={12} tone="faint" style={{ paddingTop: space.xl }}>
        Source: {data.source}. Series are trimmed for the phone — full history and the
        derivation notes are on carthago.app/economy.
      </Text>
    </Screen>
  );
}
