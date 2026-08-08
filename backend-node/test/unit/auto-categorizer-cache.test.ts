import { beforeEach, describe, expect, it } from "vitest";
import { categorizeSingle } from "../../src/services/auto-categorizer.js";
import { embeddingCache } from "../../src/services/embedding-cache.js";

describe("auto-categorizer cache", () => {
  beforeEach(() => {
    embeddingCache.clear();
  });

  it("reuses a similar cached categorization before falling back to AI", async () => {
    embeddingCache.put("ACME corp invoice 123", "Shopping", 0.99, "Acme");

    const result = await categorizeSingle("ACME corp invoice 456", "expense");

    expect(result.category).toBe("Shopping");
    expect(result.source).toBe("cache");
    expect(result.merchant).toBe("Acme");
    expect(result.confidence).toBeGreaterThanOrEqual(0.9);
  });

  it("still allows rule-based categorization to populate the cache", async () => {
    const result = await categorizeSingle("Netflix subscription renewal", "expense");

    expect(result.category).toBe("Subscriptions");
    expect(result.source).toBe("rules");

    const cached = embeddingCache.findSimilar("Netflix subscription renewal");
    expect(cached?.category).toBe("Subscriptions");
  });
});
