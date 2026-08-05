import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getEnv } from "@/app/lib/cf-env";
import Beacon from "./Beacon";

vi.mock("@/app/lib/cf-env", () => ({ getEnv: vi.fn() }));

const getEnvMock = vi.mocked(getEnv);

afterEach(() => {
  vi.clearAllMocks();
});

describe("Beacon", () => {
  it("embeds the public site token, not the GraphQL site tag", async () => {
    getEnvMock.mockResolvedValue({
      CF_ANALYTICS_SITE_TAG: "graphql-site-tag",
      CF_ANALYTICS_SITE_TOKEN: "browser-site-token",
    });

    const element = (await Beacon()) as ReactElement<{
      type?: string;
      "data-cf-beacon"?: string;
    }>;

    expect(element.props.type).toBe("module");
    expect(JSON.parse(element.props["data-cf-beacon"] ?? "null")).toEqual({
      token: "browser-site-token",
    });
  });

  it("does not mistake a site tag for a beacon token", async () => {
    getEnvMock.mockResolvedValue({ CF_ANALYTICS_SITE_TAG: "graphql-site-tag" });
    expect(await Beacon()).toBeNull();
  });
});
