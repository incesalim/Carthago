/**
 * Root layout: fonts, theme, navigation shell.
 *
 * The splash is held until the fonts resolve. Instrument Sans and Plex Mono are
 * not decoration here — the mono face is what aligns every column of figures,
 * so a first paint in the system font would reflow the entire screen a beat
 * later. Holding the splash for the load is the lesser of the two.
 */
// Per-weight SUBPATH imports, not the package root. Importing from the root
// pulls every weight and italic the family ships — measured at ~2.5MB of TTFs
// in the export manifest for the five faces this app actually registers, all of
// which lands in the binary. The subpaths cost nothing and ship only these.
import { IBMPlexMono_400Regular } from "@expo-google-fonts/ibm-plex-mono/400Regular";
import { IBMPlexMono_500Medium } from "@expo-google-fonts/ibm-plex-mono/500Medium";
import { InstrumentSans_400Regular } from "@expo-google-fonts/instrument-sans/400Regular";
import { InstrumentSans_500Medium } from "@expo-google-fonts/instrument-sans/500Medium";
import { InstrumentSans_600SemiBold } from "@expo-google-fonts/instrument-sans/600SemiBold";
import { useFonts } from "expo-font";
import { Stack } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";
import { useColorScheme } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { ThemeProvider } from "../theme";
import { dark, light } from "../theme/tokens";

void SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const scheme = useColorScheme();
  const isDark = scheme === "dark";
  const colors = isDark ? dark : light;

  const [fontsLoaded, fontError] = useFonts({
    InstrumentSans_400Regular,
    InstrumentSans_500Medium,
    InstrumentSans_600SemiBold,
    IBMPlexMono_400Regular,
    IBMPlexMono_500Medium,
  });

  useEffect(() => {
    // Hide on ERROR too. A font that fails to fetch — a captive portal, a bad
    // cache — must not leave the user staring at a splash screen forever; the
    // fallback family is ugly, an app that never opens is broken.
    if (fontsLoaded || fontError) void SplashScreen.hideAsync();
  }, [fontsLoaded, fontError]);

  if (!fontsLoaded && !fontError) return null;

  return (
    <SafeAreaProvider>
      <ThemeProvider>
        <StatusBar style={isDark ? "light" : "dark"} />
        <Stack
          screenOptions={{
            headerShadowVisible: false,
            headerStyle: { backgroundColor: colors.card },
            headerTintColor: colors.primary,
            headerTitleStyle: {
              color: colors.foreground,
              fontFamily: "InstrumentSans_600SemiBold",
              fontSize: 16,
            },
            contentStyle: { backgroundColor: colors.card },
          }}
        >
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen name="banks/[ticker]" options={{ title: "" }} />
        </Stack>
      </ThemeProvider>
    </SafeAreaProvider>
  );
}
