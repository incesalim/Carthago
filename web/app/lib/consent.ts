/**
 * Analytics consent — the stored answer to "may we load Google Analytics".
 *
 * Client-side only, and deliberately small. Two rules the rest of the code
 * depends on:
 *
 *  1. **Absence is refusal.** No stored value means GA does not load. Consent is
 *     opt-IN, so an undecided visitor is treated exactly like one who declined;
 *     the banner is the only thing that distinguishes them.
 *  2. **This is not itself tracking.** The preference lives in localStorage
 *     under one key, never leaves the browser, and carries no identifier — so
 *     storing it needs no consent of its own (it is the "strictly necessary"
 *     kind: remembering that you were asked).
 *
 * Cloudflare Web Analytics is NOT gated by this. It sets no cookie and stores no
 * per-visitor identifier, so it raises no consent question — see /privacy.
 */

export type Consent = "granted" | "denied";

export const CONSENT_KEY = "carthago:analytics-consent";

/** Fired on the window when the choice changes, so listeners re-render. */
export const CONSENT_EVENT = "carthago:consent";

/**
 * Subscribe to changes for `useSyncExternalStore`. Listens to both our own event
 * (this tab) and `storage` (another tab), so accepting in one tab does not leave
 * a stale banner in the next.
 */
export function subscribeConsent(onChange: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(CONSENT_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(CONSENT_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

/**
 * The stored choice, or null when the visitor has not answered.
 *
 * Returns null on the server and whenever storage is unavailable (private
 * modes, storage disabled, quota errors). Null means no GA — failing closed is
 * the only safe direction for a consent read.
 */
export function readConsent(): Consent | null {
  if (typeof window === "undefined") return null;
  try {
    const v = window.localStorage.getItem(CONSENT_KEY);
    return v === "granted" || v === "denied" ? v : null;
  } catch {
    return null;
  }
}

/** Record a choice and notify listeners in this tab. */
export function writeConsent(value: Consent): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(CONSENT_KEY, value);
  } catch {
    // Storage refused: the choice can't persist, so it holds for this page only.
    // Better than throwing inside a click handler on a page of charts.
  }
  window.dispatchEvent(new CustomEvent(CONSENT_EVENT, { detail: value }));
}

/**
 * Forget the choice, which puts the banner back. The withdrawal path on
 * /privacy — a consent you cannot take back is not a consent.
 */
export function clearConsent(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(CONSENT_KEY);
  } catch {
    /* nothing to clear if storage is unavailable */
  }
  window.dispatchEvent(new CustomEvent(CONSENT_EVENT, { detail: null }));
}
