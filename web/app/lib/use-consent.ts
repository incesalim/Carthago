"use client";

import { useSyncExternalStore } from "react";
import { readConsent, subscribeConsent, type Consent } from "./consent";

/**
 * Consent as what it actually is: an external store, read with the primitive
 * built for one.
 *
 * The obvious `useState` + `useEffect` version is a lint error here
 * (`react-hooks/set-state-in-effect`) and the rule is right — it renders once
 * with a guessed value, then again with the real one, and every consumer has to
 * handle the guess. `useSyncExternalStore` reads the store during render and
 * subscribes for changes, so there is no in-between state to design around.
 *
 * `readConsent` returns a string or null, never a fresh object, so it is a safe
 * snapshot: an unstable one would loop.
 */
export function useConsent(): Consent | null {
  return useSyncExternalStore(subscribeConsent, readConsent, () => null);
}

const noopSubscribe = () => () => {};

/**
 * False during SSR and the first client render, true afterwards.
 *
 * Consent UI must not exist in the server HTML: the answer lives in
 * localStorage, so the server would have to guess "undecided" and returning
 * visitors would see the banner flash before hydration removed it. A banner that
 * appears and vanishes is one that gets dismissed by accident.
 */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    noopSubscribe,
    () => true,
    () => false,
  );
}
