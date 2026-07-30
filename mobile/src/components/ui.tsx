/**
 * The Desk's primitives, in React Native.
 *
 * The system's rules, enforced here so screens can't break them by accident:
 *   • Hierarchy from weight and size in one family — never a second typeface.
 *   • Every FIGURE is mono. That is what makes a column of numbers line up, and
 *     it's the single most recognisable thing about the website.
 *   • Hairlines, not boxes. A `Card` here draws a rule, not a border with a
 *     shadow — the sheet is the background, so a box on it is a second sheet.
 *   • Blue is links and routes ONLY. No blue headings, no blue accents.
 */
import type { ReactNode } from "react";
import {
  Pressable,
  StyleSheet,
  Text as RNText,
  View,
  type StyleProp,
  type TextStyle,
  type ViewStyle,
} from "react-native";

import { useTheme } from "../theme";

type Tone = "default" | "muted" | "faint" | "positive" | "negative" | "warning";

function useToneColor(tone: Tone): string {
  const { colors } = useTheme();
  switch (tone) {
    case "muted": return colors.mutedForeground;
    case "faint": return colors.faint;
    case "positive": return colors.positive;
    case "negative": return colors.negative;
    case "warning": return colors.warning;
    default: return colors.foreground;
  }
}

/** Body copy. */
export function Text({
  children, tone = "default", size, weight = "regular", style, numberOfLines,
}: {
  children: ReactNode;
  tone?: Tone;
  size?: number;
  weight?: "regular" | "medium" | "semibold";
  style?: StyleProp<TextStyle>;
  numberOfLines?: number;
}) {
  const { font, type } = useTheme();
  const color = useToneColor(tone);
  const family =
    weight === "semibold" ? font.sansSemibold
    : weight === "medium" ? font.sansMedium
    : font.sans;
  return (
    <RNText
      numberOfLines={numberOfLines}
      style={[
        {
          color,
          fontFamily: family,
          fontSize: size ?? type.body,
          // Native's default line height is tight for a 15px UI face; the
          // website's body copy sits at ~1.5 and the app should match.
          lineHeight: Math.round((size ?? type.body) * 1.45),
        },
        style,
      ]}
    >
      {children}
    </RNText>
  );
}

/**
 * A small-caps mono label — the Desk's section and field marker.
 *
 * The website tracks these at 0.07em over 8.5px. At the 11px floor this app
 * uses, that same tracking reads loose, so it is retuned rather than copied.
 */
export function Label({
  children, tone = "faint", style,
}: {
  children: ReactNode;
  tone?: Tone;
  style?: StyleProp<TextStyle>;
}) {
  const { font, type } = useTheme();
  const color = useToneColor(tone);
  return (
    <RNText
      style={[
        {
          color,
          fontFamily: font.mono,
          fontSize: type.caption,
          letterSpacing: 0.5,
          textTransform: "uppercase",
        },
        style,
      ]}
    >
      {children}
    </RNText>
  );
}

/** Every number on screen. Mono, tabular, so columns align. */
export function Figure({
  children, size, tone = "default", weight = "regular", style,
}: {
  children: ReactNode;
  size?: number;
  tone?: Tone;
  weight?: "regular" | "medium";
  style?: StyleProp<TextStyle>;
}) {
  const { font, type } = useTheme();
  const color = useToneColor(tone);
  return (
    <RNText
      style={[
        {
          color,
          fontFamily: weight === "medium" ? font.monoMedium : font.mono,
          fontSize: size ?? type.heading,
          fontVariant: ["tabular-nums"],
        },
        style,
      ]}
    >
      {children}
    </RNText>
  );
}

export function Heading({ children, style }: { children: ReactNode; style?: StyleProp<TextStyle> }) {
  const { type } = useTheme();
  return <Text size={type.title} weight="semibold" style={style}>{children}</Text>;
}

/** The 1px rule that replaces a border. `strong` = the sheet edge; default = an
 *  inner row divider, one step quieter. */
export function Hairline({ strong = false, style }: { strong?: boolean; style?: StyleProp<ViewStyle> }) {
  const { colors } = useTheme();
  return (
    <View
      style={[
        { height: StyleSheet.hairlineWidth, backgroundColor: strong ? colors.border : colors.hair },
        style,
      ]}
    />
  );
}

/** A titled block: mono label, optional meta on the right, then content. */
export function Section({
  title, meta, action, children, style,
}: {
  title: string;
  meta?: string;
  action?: ReactNode;
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  const { space } = useTheme();
  return (
    <View style={[{ marginTop: space.xl }, style]}>
      <View
        style={{
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: space.sm,
        }}
      >
        <Label tone="muted">{title}</Label>
        {action ?? (meta ? <Label>{meta}</Label> : null)}
      </View>
      <Hairline strong />
      {children}
    </View>
  );
}

/** A label/value line — the Desk's densest unit, used for every list. */
export function Row({
  label, value, note, onPress, right,
}: {
  label: ReactNode;
  value?: ReactNode;
  note?: ReactNode;
  onPress?: () => void;
  right?: ReactNode;
}) {
  const { space } = useTheme();
  const body = (
    <View
      style={{
        flexDirection: "row",
        alignItems: "center",
        justifyContent: "space-between",
        paddingVertical: space.md,
        gap: space.md,
      }}
    >
      <View style={{ flex: 1, gap: 2 }}>
        {typeof label === "string" ? <Text>{label}</Text> : label}
        {note ? (typeof note === "string" ? <Text size={12} tone="faint">{note}</Text> : note) : null}
      </View>
      {right ?? (typeof value === "string" ? <Figure>{value}</Figure> : value)}
    </View>
  );

  return (
    <>
      {onPress ? (
        // 0.6 rather than the platform default: the Desk's hover is text-only,
        // and a full-row grey flash is app-chrome the system doesn't have.
        <Pressable onPress={onPress} style={({ pressed }) => ({ opacity: pressed ? 0.6 : 1 })}>
          {body}
        </Pressable>
      ) : (
        body
      )}
      <Hairline />
    </>
  );
}

/** Signed delta in the data tones. `good` inverts the colouring for metrics
 *  where down is the improvement (NPL), and disables it where neither
 *  direction is a verdict (loan/deposit, asset growth). */
export function Delta({
  value, format, good = "up", size,
}: {
  value: number | null;
  format: (v: number | null) => string;
  good?: "up" | "down" | "neutral";
  size?: number;
}) {
  const tone: Tone =
    value == null || good === "neutral" || value === 0
      ? "faint"
      : (value > 0) === (good === "up")
        ? "positive"
        : "negative";
  return <Figure size={size ?? 12} tone={tone}>{format(value)}</Figure>;
}
