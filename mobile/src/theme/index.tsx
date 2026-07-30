/**
 * Theme access. One hook, `useTheme()`, returns the active palette plus the
 * scale constants — so no component ever reaches for a raw hex, which is the
 * only way light/dark parity survives more than a few screens.
 *
 * There is no theme TOGGLE. The website has one; a phone already has a
 * system-wide setting and an app that disagrees with it is the odd one out. If
 * a manual override is ever wanted, it belongs here (a context value seeded
 * from `useColorScheme()`), not scattered through the screens.
 */
import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useColorScheme } from "react-native";

import { dark, font, light, radius, space, type, type Palette } from "./tokens";

export interface Theme {
  colors: Palette;
  type: typeof type;
  space: typeof space;
  font: typeof font;
  radius: number;
  isDark: boolean;
}

const ThemeContext = createContext<Theme | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  // `useColorScheme()` returns null before the native module reports in. Light
  // is the right default: it matches the website's own default and the splash
  // screen, so a launch doesn't flash dark and snap back.
  const scheme = useColorScheme();
  const isDark = scheme === "dark";

  const value = useMemo<Theme>(
    () => ({ colors: isDark ? dark : light, type, space, font, radius, isDark }),
    [isDark],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): Theme {
  const t = useContext(ThemeContext);
  if (!t) throw new Error("useTheme() called outside <ThemeProvider>");
  return t;
}

export type { Palette };
export { dark, font, light, radius, space, type };
