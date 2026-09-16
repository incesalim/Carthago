import { supported, type Handshake } from "./app-api-v1";

export type CompatibilityState = "ready" | "offline" | "upgrade" | "unavailable";

/** Pure decision boundary; I/O supplied by the launch gate and tests. */
export async function negotiate(deps: {
  fetch: () => Promise<Handshake>;
  save: (handshake: Handshake) => Promise<void>;
  previous: () => Promise<Handshake | null>;
  hasScreen: () => Promise<boolean>;
  offline: (error: unknown) => boolean;
  build: number;
}): Promise<CompatibilityState> {
  try {
    const handshake = await deps.fetch();
    await deps.save(handshake);
    return supported(handshake, deps.build) ? "ready" : "upgrade";
  } catch (error) {
    const previous = await deps.previous();
    if (previous && !supported(previous, deps.build)) return "upgrade";
    if (deps.offline(error) && previous && await deps.hasScreen()) return "offline";
    return "unavailable";
  }
}
