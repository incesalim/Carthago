/**
 * Banks — the index.
 *
 * Size-ranked at one common quarter, searchable by name or ticker. The list
 * carries four figures per row; the rest of the scorecard is one tap away.
 *
 * FlatList rather than mapping inside the shared <Screen> scroller: this is ~38
 * rows today and grows with every bank onboarded, and a plain map renders every
 * row on every keystroke of the filter.
 */
import { router } from "expo-router";
import { useDeferredValue, useMemo, useState } from "react";
import { FlatList, Pressable, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { endpoints } from "../../api/client";
import type { BankList, BankRow } from "../../api/types";
import { useResource } from "../../api/use-resource";
import { ErrorState, Loading, ScreenHeader, StaleNote } from "../../components/screen";
import { Figure, Hairline, Label, Text } from "../../components/ui";
import { pct, periodLabel, tl } from "../../format";
import { useTheme } from "../../theme";

export default function BanksScreen() {
  const { colors, font, space, type } = useTheme();
  const insets = useSafeAreaInsets();
  const { data, loading, refreshing, error, cachedAt, refresh } =
    useResource<BankList>("banks", endpoints.banks());

  const [query, setQuery] = useState("");
  // Keeps typing responsive while the (long) list re-filters behind it.
  const deferred = useDeferredValue(query);

  const rows = useMemo(() => {
    if (!data) return [];
    const q = deferred.trim().toLocaleLowerCase("tr");
    if (!q) return data.rows;
    return data.rows.filter(
      (r) =>
        r.name.toLocaleLowerCase("tr").includes(q) ||
        r.ticker.toLocaleLowerCase("tr").includes(q),
    );
  }, [data, deferred]);

  if (loading && !data) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.card, paddingHorizontal: space.lg }}>
        <Loading />
      </View>
    );
  }

  if (!data) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.card, paddingHorizontal: space.lg }}>
        <ScreenHeader title="Banks" />
        <ErrorState message={error?.message ?? "No data."} onRetry={refresh} />
      </View>
    );
  }

  return (
    <View style={{ flex: 1, backgroundColor: colors.card }}>
      <FlatList
        data={rows}
        keyExtractor={(r) => r.ticker}
        contentContainerStyle={{
          paddingHorizontal: space.lg,
          paddingBottom: insets.bottom + space.xxl * 2,
        }}
        refreshing={refreshing}
        onRefresh={refresh}
        ListHeaderComponent={
          <>
            <ScreenHeader
              title="Banks"
              record={`${data.count} BANKS · ${periodLabel(data.period).toUpperCase()}`}
            />
            <StaleNote cachedAt={cachedAt} error={error} />
            <TextInput
              value={query}
              onChangeText={setQuery}
              placeholder="Search"
              placeholderTextColor={colors.faint}
              autoCorrect={false}
              autoCapitalize="characters"
              style={{
                marginTop: space.md,
                marginBottom: space.sm,
                paddingVertical: space.sm,
                color: colors.foreground,
                fontFamily: font.mono,
                fontSize: type.small,
                borderBottomWidth: 1,
                borderBottomColor: colors.border,
              }}
            />
          </>
        }
        ListEmptyComponent={
          <Text tone="muted" style={{ paddingVertical: space.xl }}>
            No bank matches “{query}”.
          </Text>
        }
        renderItem={({ item }) => (
          <BankListRow row={item} onPress={() => router.push(`/banks/${item.ticker}`)} />
        )}
      />
    </View>
  );
}

/**
 * One row: identity on the left, four figures on the right.
 *
 * The figures are labelled per row rather than by a column header. A header row
 * would be denser, but it strands anyone who scrolls past it — and on a phone
 * that is everyone after four rows.
 */
function BankListRow({ row, onPress }: { row: BankRow; onPress: () => void }) {
  const { space } = useTheme();

  return (
    <>
      <Pressable
        onPress={onPress}
        style={({ pressed }) => ({ opacity: pressed ? 0.6 : 1, paddingVertical: space.md })}
      >
        <View style={{ flexDirection: "row", alignItems: "center", gap: space.md }}>
          <View style={{ flex: 1, gap: 2 }}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: space.sm }}>
              <Text weight="medium" size={15}>{row.name}</Text>
              {/* Takasbank is a CCP. Its ratios are real but answer a different
                  question, so the row says so rather than letting a reader rank
                  a clearing house against lenders. */}
              {row.peerExcluded && <Label tone="warning">CCP</Label>}
            </View>
            <View style={{ flexDirection: "row", gap: space.sm }}>
              <Label>{row.ticker}</Label>
              {row.typeLabel ? <Label tone="faint">{row.typeLabel}</Label> : null}
            </View>
          </View>

          <View style={{ alignItems: "flex-end" }}>
            <Figure size={15} weight="medium">{tl(row.totalAssets)}</Figure>
            <View style={{ flexDirection: "row", gap: space.md, marginTop: 3 }}>
              <Stat label="ROE" value={pct(row.roe, 1)} />
              <Stat label="NPL" value={pct(row.npl, 2)} />
              <Stat label="CAR" value={pct(row.car, 1)} />
            </View>
          </View>
        </View>
      </Pressable>
      <Hairline />
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ alignItems: "flex-end" }}>
      <Label>{label}</Label>
      <Figure size={12}>{value}</Figure>
    </View>
  );
}
