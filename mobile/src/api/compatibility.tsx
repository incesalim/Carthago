import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { AppState, Linking, Pressable, View } from "react-native";
import { Text } from "../components/ui";
import { useTheme } from "../theme";
import { ApiError, API_BASE, CLIENT_BUILD, endpoints, get } from "./client";
import { hasCachedScreen, readCache, writeCache } from "./cache";
import { type Handshake } from "./contract.generated";

import { negotiate, type CompatibilityState } from "./compatibility-state";
type State = "checking" | CompatibilityState;
const Compatibility = createContext({ online: false, recheck: () => {} });
export const useCompatibility = () => useContext(Compatibility);

export function CompatibilityGate({ children }: { children: ReactNode }) {
  const { colors } = useTheme();
  const [state, setState] = useState<State>("checking");
  const [attempt, setAttempt] = useState(0);
  const recheck = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      const next = await negotiate({
        fetch: () => get<Handshake>(endpoints.handshake(), controller.signal),
        save: (handshake) => writeCache(endpoints.handshake(), handshake),
        previous: async () => (await readCache<Handshake>(endpoints.handshake()))?.data ?? null,
        hasScreen: hasCachedScreen,
        offline: (error) => error instanceof ApiError && error.offline,
        build: CLIENT_BUILD,
      });
      if (!controller.signal.aborted) setState(next);
    })();
    return () => controller.abort();
  }, [attempt]);

  useEffect(() => {
    const listener = AppState.addEventListener("change", (next) => {
      if (next === "active") { setState("checking"); recheck(); }
    });
    return () => listener.remove();
  }, [recheck]);

  if (state === "ready" || state === "offline") {
    return <Compatibility.Provider value={{ online: state === "ready", recheck }}>{children}</Compatibility.Provider>;
  }
  return (
    <View style={{ flex: 1, justifyContent: "center", padding: 28, gap: 20, backgroundColor: colors.card }}>
      <Text weight="semibold" size={22}>{state === "checking" ? "Connecting to Carthago" : state === "upgrade" ? "Update Carthago to continue" : "Carthago is unavailable"}</Text>
      {state !== "checking" && <>
        <Text tone="muted">{state === "upgrade" ? "This version can no longer safely display the latest data. Install the latest app version, or use the website." : "Please check your connection and try again. No compatible saved data is available for this session."}</Text>
        <Pressable accessibilityRole="button" onPress={() => { setState("checking"); recheck(); }}><Text style={{ textDecorationLine: "underline" }}>Try again</Text></Pressable>
        <Pressable accessibilityRole="link" onPress={() => void Linking.openURL(API_BASE)}><Text style={{ color: colors.primary }}>Open carthago.app</Text></Pressable>
      </>}
    </View>
  );
}
