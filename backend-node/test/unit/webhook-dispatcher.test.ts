import { createHmac } from "node:crypto";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { dispatchWebhook } from "../../src/services/webhook-dispatcher.js";

describe("dispatchWebhook", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns false when the url is empty", async () => {
    await expect(dispatchWebhook("", { ok: true })).resolves.toBe(false);
  });

  it("sends a signed payload when a secret is provided", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);

    const payload = { event: "account.created", id: "evt_123" };
    const secret = "webhook-secret";
    const expectedBody = JSON.stringify(payload);
    const expectedSignature = createHmac("sha256", secret).update(expectedBody).digest("hex");

    await expect(dispatchWebhook("https://example.com/webhook", payload, secret)).resolves.toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "https://example.com/webhook",
      expect.objectContaining({
        method: "POST",
        body: expectedBody,
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          "User-Agent": "Leger-Webhook/1.0",
          "X-Leger-Signature": `sha256=${expectedSignature}`,
        }),
      }),
    );
  });

  it("omits the signature header when no secret is provided", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);

    await expect(dispatchWebhook("https://example.com/webhook", { ok: true })).resolves.toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
      headers: expect.not.objectContaining({
        "X-Leger-Signature": expect.any(String),
      }),
    });
  });
});
