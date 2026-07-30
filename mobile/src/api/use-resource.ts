/**
 * `useResource` — fetch, cache, refresh. The one data hook every screen uses.
 *
 * Stale-while-revalidate against a persisted cache, because the alternative is
 * a spinner on every cold launch. The data behind these screens moves monthly
 * to quarterly, so a payload from yesterday is not "stale" in any sense the
 * reader cares about — showing it instantly and refreshing behind it is both
 * faster AND more accurate than an empty screen.
 *
 * What the cache is NOT allowed to do is lie about freshness. Every cached read
 * comes back with `cachedAt`, and screens print it whenever the copy on screen
 * did not come from this launch's network round trip. A figure with no date on
 * a finance screen is worse than no figure.
 *
 * No react-query. It is a good library and this is ~90 lines: one hook, one
 * cache, no mutations, no invalidation graph, no infinite queries.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, get } from "./client";

const PREFIX = "carthago:v1:";

/** Cached payloads older than this are still SHOWN, but the screen says so. */
export const STALE_AFTER_MS = 6 * 60 * 60 * 1000; // 6h

interface Envelope<T> {
  cachedAt: number;
  data: T;
}

export interface Resource<T> {
  data: T | null;
  /** True only while there is nothing to show — never during a refresh over
   *  existing data, which would flash the screen back to a spinner. */
  loading: boolean;
  refreshing: boolean;
  error: ApiError | null;
  /** When the shown copy was fetched; null if it came from this session. */
  cachedAt: number | null;
  refresh: () => void;
}

async function readCache<T>(key: string): Promise<Envelope<T> | null> {
  try {
    const raw = await AsyncStorage.getItem(PREFIX + key);
    return raw ? (JSON.parse(raw) as Envelope<T>) : null;
  } catch {
    // A corrupt or unreadable cache must never block a screen — fall through
    // to the network as if there were no cache at all.
    return null;
  }
}

async function writeCache<T>(key: string, data: T): Promise<void> {
  try {
    await AsyncStorage.setItem(
      PREFIX + key,
      JSON.stringify({ cachedAt: Date.now(), data } satisfies Envelope<T>),
    );
  } catch {
    /* out of space / storage disabled — the app still works, just not offline */
  }
}

export function useResource<T>(key: string, path: string): Resource<T> {
  const [data, setData] = useState<T | null>(null);
  const [cachedAt, setCachedAt] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  // Guards a state update after unmount, and lets a new request supersede one
  // already in flight (rapid pull-to-refresh, or a tab switched away and back).
  const inflight = useRef<AbortController | null>(null);
  const mounted = useRef(true);

  const load = useCallback(
    async (isRefresh: boolean) => {
      inflight.current?.abort();
      const controller = new AbortController();
      inflight.current = controller;

      if (isRefresh) setRefreshing(true);

      try {
        const fresh = await get<T>(path, controller.signal);
        if (!mounted.current || controller.signal.aborted) return;
        setData(fresh);
        setCachedAt(null); // this copy IS from the network
        setError(null);
        void writeCache(key, fresh);
      } catch (err) {
        if (!mounted.current || controller.signal.aborted) return;
        const apiErr =
          err instanceof ApiError ? err : new ApiError("Something went wrong.", 0);
        // A failed refresh keeps whatever is on screen. Blanking good data
        // because a retry failed is strictly worse than showing it with a note.
        setError(apiErr);
      } finally {
        if (mounted.current) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    },
    [key, path],
  );

  useEffect(() => {
    mounted.current = true;

    void (async () => {
      // Paint the cached copy first, then revalidate. The cached read is
      // skipped if the network already answered — which happens on a fast
      // connection and would otherwise overwrite fresh data with older data.
      const cached = await readCache<T>(key);
      if (mounted.current && cached) {
        setData((current) => {
          if (current !== null) return current;
          setCachedAt(cached.cachedAt);
          return cached.data;
        });
        setLoading(false);
      }
      await load(false);
    })();

    return () => {
      mounted.current = false;
      inflight.current?.abort();
    };
  }, [key, load]);

  const refresh = useCallback(() => void load(true), [load]);

  return { data, loading, refreshing, error, cachedAt, refresh };
}
