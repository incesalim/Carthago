import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/app/lib/db", () => ({ allDirect: vi.fn() }));
vi.mock("@/app/lib/cf-env", () => ({
  getEnv: async () => ({}),
  envFlag: () => false,
}));

import { allDirect } from "@/app/lib/db";
import { GET } from "./route";

describe("series catalog pagination", () => {
  beforeEach(() => vi.mocked(allDirect).mockReset());

  it.each(["1e30", "9007199254740992", "Infinity", "-1", "1.5"])(
    "rejects invalid offset %s before querying D1",
    async (offset) => {
      const response = await GET(new Request(`https://carthago.app/api/v1/serieList?offset=${offset}`));
      expect(response.status).toBe(400);
      expect(await response.json()).toEqual({ error: "`offset` must be a non-negative safe integer." });
      expect(allDirect).not.toHaveBeenCalled();
    },
  );

  it.each([0, 500, Number.MAX_SAFE_INTEGER])("accepts safe offset %s", async (offset) => {
    vi.mocked(allDirect).mockResolvedValueOnce([]).mockResolvedValueOnce([{ n: 1000 }]);
    const response = await GET(new Request(`https://carthago.app/api/v1/serieList?offset=${offset}`));
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ meta: { total: 1000, count: 0, limit: 500, offset } });
    expect(allDirect).toHaveBeenNthCalledWith(1, expect.stringContaining("LIMIT ? OFFSET ?"), [500, offset]);
  });
});
