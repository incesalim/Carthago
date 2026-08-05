import { afterEach, describe, expect, it, vi } from "vitest";
import { getEnv } from "./cf-env";
import { getTrafficSummary } from "./cf-analytics";

vi.mock("./cf-env", () => ({ getEnv: vi.fn() }));

const getEnvMock = vi.mocked(getEnv);

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("getTrafficSummary", () => {
  it("filters GraphQL with the site tag, never the browser beacon token", async () => {
    getEnvMock.mockResolvedValue({
      CF_ANALYTICS_TOKEN: "api-token",
      CF_ANALYTICS_SITE_TAG: "graphql-site-tag",
      CF_ANALYTICS_SITE_TOKEN: "browser-site-token",
      CF_ACCOUNT_TAG: "account-tag",
    });

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        data: {
          viewer: {
            accounts: [{ totals: [], byPath: [], byDay: [] }],
          },
        },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await getTrafficSummary(7);

    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const body = JSON.parse(String(request.body)) as {
      variables: { siteTag: string };
    };
    expect(body.variables.siteTag).toBe("graphql-site-tag");
    expect(String(request.body)).not.toContain("browser-site-token");
  });
});
