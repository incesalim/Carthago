/**
 * Screen chrome: the scroll container, the page header, and the three states
 * every data screen has (loading, failed-with-nothing, showing-stale-data).
 *
 * Those states are here rather than in each screen because they are where a
 * data app is usually dishonest. The rules:
 *   • Never show a spinner over data we already have.
 *   • Never blank good data because a refresh failed.
 *   • Never show a figure from cache without saying when it was fetched.
 */
import type { ReactNode } from "react";
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { ago } from "../format";
import { useTheme } from "../theme";
import { Hairline, Label, Text } from "./ui";

export function Screen({
  children, refreshing, onRefresh,
}: {
  children: ReactNode;
  refreshing?: boolean;
  onRefresh?: () => void;
}) {
  const { colors, space } = useTheme();
  const insets = useSafeAreaInsets();

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.card }}
      contentContainerStyle={{
        paddingHorizontal: space.lg,
        // The tab bar floats over the content, so the last row needs clearance
        // or it sits permanently under it.
        paddingBottom: insets.bottom + space.xxl * 2,
      }}
      refreshControl={
        onRefresh ? (
          <RefreshControl
            refreshing={!!refreshing}
            onRefresh={onRefresh}
            tintColor={colors.faint}
          />
        ) : undefined
      }
    >
      {children}
    </ScrollView>
  );
}

/** The page head: title, and the record period the whole screen is "as of". */
export function ScreenHeader({
  title, record, right,
}: {
  title: string;
  record?: string;
  right?: ReactNode;
}) {
  const { space, type } = useTheme();
  return (
    <View style={{ paddingTop: space.md, paddingBottom: space.md }}>
      <View
        style={{
          flexDirection: "row",
          alignItems: "flex-end",
          justifyContent: "space-between",
        }}
      >
        <Text size={type.display} weight="semibold">{title}</Text>
        {right}
      </View>
      {record ? <Label style={{ marginTop: space.xs }}>{record}</Label> : null}
      <Hairline strong style={{ marginTop: space.md }} />
    </View>
  );
}

export function Loading() {
  const { colors, space } = useTheme();
  return (
    <View style={{ paddingVertical: space.xxl * 2, alignItems: "center" }}>
      <ActivityIndicator color={colors.faint} />
    </View>
  );
}

/** Shown only when there is NOTHING to display — never over existing data. */
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { colors, space } = useTheme();
  return (
    <View style={{ paddingVertical: space.xxl, gap: space.md }}>
      <Text tone="muted">{message}</Text>
      {onRetry && (
        <Pressable onPress={onRetry} hitSlop={12}>
          <Text weight="medium" style={{ color: colors.primary }}>Try again</Text>
        </Pressable>
      )}
    </View>
  );
}

/**
 * The provenance line. Prints when the copy on screen came from cache, and
 * separately when a refresh failed — so "these numbers are from Tuesday" is
 * always on screen rather than inferred from a stale-looking chart.
 */
export function StaleNote({
  cachedAt, error,
}: {
  cachedAt: number | null;
  error?: { message: string } | null;
}) {
  const { space } = useTheme();
  if (cachedAt == null && !error) return null;
  return (
    <View style={{ paddingTop: space.sm }}>
      {cachedAt != null && <Label tone="warning">Cached · fetched {ago(cachedAt)}</Label>}
      {error && <Label tone="faint">Couldn&apos;t refresh — {error.message}</Label>}
    </View>
  );
}
