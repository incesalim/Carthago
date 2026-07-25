import { afterEach, describe, expect, it, vi } from "vitest";
import { CONSENT_KEY, clearConsent, readConsent, writeConsent } from "./consent";

/**
 * Consent is the one preference on this site where the failure directions are
 * not symmetric: reading it wrong and loading Google Analytics for someone who
 * declined is a privacy failure, while reading it wrong the other way just loses
 * a page view. So every path that cannot produce a definite "granted" must
 * return null, and null must mean off.
 */

type Store = Map<string, string>;

/** Install a fake `window` with a working (or hostile) localStorage. */
function withWindow(opts: { store?: Store; throws?: boolean } = {}) {
  const store = opts.store ?? new Map<string, string>();
  const localStorage = {
    getItem: (k: string) => {
      if (opts.throws) throw new Error("storage disabled");
      return store.has(k) ? store.get(k)! : null;
    },
    setItem: (k: string, v: string) => {
      if (opts.throws) throw new Error("quota exceeded");
      store.set(k, v);
    },
    removeItem: (k: string) => {
      if (opts.throws) throw new Error("storage disabled");
      store.delete(k);
    },
  };
  const events: string[] = [];
  (globalThis as { window?: unknown }).window = {
    localStorage,
    dispatchEvent: (e: Event) => {
      events.push(e.type);
      return true;
    },
  };
  return { store, events };
}

afterEach(() => {
  delete (globalThis as { window?: unknown }).window;
  vi.unstubAllGlobals();
});

describe("readConsent", () => {
  it("is null on the server — nothing to read, so nothing loads", () => {
    expect(readConsent()).toBeNull();
  });

  it("returns only the two values it recognises", () => {
    const { store } = withWindow();
    store.set(CONSENT_KEY, "granted");
    expect(readConsent()).toBe("granted");
    store.set(CONSENT_KEY, "denied");
    expect(readConsent()).toBe("denied");
  });

  it("treats anything else as unanswered, not as consent", () => {
    const { store } = withWindow();
    for (const junk of ["true", "yes", "1", "GRANTED", "", "null"]) {
      store.set(CONSENT_KEY, junk);
      expect(readConsent()).toBeNull();
    }
  });

  it("fails CLOSED when storage throws (private mode, storage disabled)", () => {
    withWindow({ throws: true });
    expect(readConsent()).toBeNull();
  });
});

describe("writeConsent / clearConsent", () => {
  it("persists the choice and notifies listeners", () => {
    const { store, events } = withWindow();
    writeConsent("granted");
    expect(store.get(CONSENT_KEY)).toBe("granted");
    expect(events).toHaveLength(1);
  });

  it("clearing forgets the answer, so the banner returns", () => {
    const { store } = withWindow();
    writeConsent("denied");
    clearConsent();
    expect(store.has(CONSENT_KEY)).toBe(false);
    expect(readConsent()).toBeNull();
  });

  it("never throws out of a click handler when storage refuses", () => {
    withWindow({ throws: true });
    expect(() => writeConsent("granted")).not.toThrow();
    expect(() => clearConsent()).not.toThrow();
  });

  it("does nothing on the server rather than crashing the render", () => {
    expect(() => writeConsent("granted")).not.toThrow();
    expect(() => clearConsent()).not.toThrow();
  });
});
