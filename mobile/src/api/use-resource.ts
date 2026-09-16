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
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, get } from "./client";

import { readCache, writeCache } from "./cache";
import { useCompatibility } from "./compatibility";

/** Cached payloads older than this are still SHOWN, but the screen says so. */
export const STALE_AFTER_MS = 6 * 60 * 60 * 1000; // 6h

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

export function useResource<T>(path: string): Resource<T> {
  const { online, recheck } = useCompatibility();
  const [dataPath, setDataPath] = useState(path);
  const [data, setData] = useState<T | null>(null);
  const [cachedAt, setCachedAt] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  // Guards a state update after unmount, and lets a new request supersede one
  // already in flight (rapid pull-to-refresh, or a tab switched away and back).
  const inflight = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const lastFetchedAt = useRef<number | null>(null);
  const lastFetchedPath = useRef<string | null>(null);

  const load = useCallback(
    async (isRefresh: boolean) => {
      inflight.current?.abort();
      const controller = new AbortController();
      inflight.current = controller;

      if (!online) {
        setLoading(false);
        setError(new ApiError("Offline — showing saved data where available.", 0, true));
        if (isRefresh) recheck();
        return;
      }
      if (isRefresh) setRefreshing(true);

      try {
        const fresh = await get<T>(path, controller.signal);
        if (!mounted.current || controller.signal.aborted) return;
        lastFetchedAt.current = Date.now();
        lastFetchedPath.current = path;
        setDataPath(path);
        setData(fresh);
        setCachedAt(null); // this copy IS from the network
        setError(null);
        void writeCache(path, fresh);
      } catch (err) {
        if (!mounted.current || controller.signal.aborted) return;
        const apiErr =
          err instanceof ApiError ? err : new ApiError("Something went wrong.", 0);
        // A failed refresh keeps whatever is on screen. Blanking good data
        // because a retry failed is strictly worse than showing it with a note.
        setError(apiErr);
        if (lastFetchedPath.current === path && lastFetchedAt.current) setCachedAt(lastFetchedAt.current);
      } finally {
        if (mounted.current && inflight.current === controller) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    },
    [path, online, recheck],
  );

  useEffect(() => {
    mounted.current = true;
    let active = true;
    const started = Date.now();

    void (async () => {
      const cached = await readCache<T>(path);
      if (!active) return;
      // A refresh may have completed while storage was being read.
      if (lastFetchedPath.current !== path || lastFetchedAt.current === null || lastFetchedAt.current < started) {
        setDataPath(path);
        setData(cached?.data ?? null);
        setCachedAt(cached?.cachedAt ?? null);
        setError(null);
        setLoading(cached === null);
      }
      await load(false);
    })();

    return () => {
      active = false;
      mounted.current = false;
      inflight.current?.abort();
    };
  }, [path, load]);

  const refresh = useCallback(() => void load(true), [load]);

  const current = dataPath === path;
  return { data: current ? data : null, loading: !current || loading, refreshing,
    error: current ? error : null, cachedAt: current ? cachedAt : null, refresh };
}
