/**
 * The four tabs.
 *
 * Four, not the website's ~30 routes. A phone's bottom bar holds five before the
 * labels truncate, and the site's routes collapse cleanly into the questions a
 * reader actually arrives with: how is the sector doing (Overview), how is this
 * bank doing (Banks), what is the backdrop (Economy), what just happened (News).
 * Everything else — /capital, /liquidity, /cross-bank, /regulation, /pipeline —
 * is depth that belongs on a laptop, and each screen links out to it.
 */
import Ionicons from "@expo/vector-icons/Ionicons";
import { Tabs } from "expo-router";

import { useTheme } from "../../theme";

export default function TabsLayout() {
  const { colors, font } = useTheme();

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.foreground,
        tabBarInactiveTintColor: colors.faint,
        tabBarStyle: {
          backgroundColor: colors.card,
          borderTopColor: colors.border,
        },
        tabBarLabelStyle: { fontFamily: font.mono, fontSize: 10, letterSpacing: 0.3 },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "OVERVIEW",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="pulse-outline" color={color} size={size} />
          ),
        }}
      />
      <Tabs.Screen
        name="banks"
        options={{
          title: "BANKS",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="business-outline" color={color} size={size} />
          ),
        }}
      />
      <Tabs.Screen
        name="economy"
        options={{
          title: "ECONOMY",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="stats-chart-outline" color={color} size={size} />
          ),
        }}
      />
      <Tabs.Screen
        name="news"
        options={{
          title: "NEWS",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="newspaper-outline" color={color} size={size} />
          ),
        }}
      />
    </Tabs>
  );
}
