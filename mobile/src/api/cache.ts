import AsyncStorage from "@react-native-async-storage/async-storage";
import { API_BASE } from "./client";
import { cacheKey, decodeCache, encodeCache, type CacheEnvelope } from "./contract.generated";

export async function readCache<T>(path: string): Promise<CacheEnvelope<T> | null> {
  try {
    const raw = await AsyncStorage.getItem(cacheKey(API_BASE, path));
    return raw ? decodeCache<T>(API_BASE, path, raw) : null;
  } catch { return null; }
}
export async function writeCache<T>(path: string, data: T): Promise<void> {
  try { await AsyncStorage.setItem(cacheKey(API_BASE, path), encodeCache(API_BASE, path, data)); }
  catch { /* Storage failure does not invalidate a checked network response. */ }
}
export async function hasCachedScreen(): Promise<boolean> {
  const prefix = cacheKey(API_BASE, "/api/app/v1/");
  try {
    const keys = (await AsyncStorage.getAllKeys()).filter((key) => key.startsWith(prefix));
    for (const key of keys) {
      const path = "/api/app/v1/" + key.slice(prefix.length);
      if (await readCache(path)) return true;
    }
  } catch { /* No readable cache. */ }
  return false;
}
