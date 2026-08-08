import { createHmac } from "node:crypto";

export async function dispatchWebhook(url: string, payload: any, secret?: string): Promise<boolean> {
  if (!url) return false;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "User-Agent": "Leger-Webhook/1.0",
  };

  const body = JSON.stringify(payload);

  if (secret) {
    const signature = createHmac("sha256", secret).update(body).digest("hex");
    headers["X-Leger-Signature"] = `sha256=${signature}`;
  }

  try {
    const res = await fetch(url, {
      method: "POST",
      headers,
      body,
      // Webhooks should timeout relatively quickly to avoid blocking
      signal: AbortSignal.timeout(5000),
    });

    return res.ok;
  } catch (e) {
    console.warn(`Webhook dispatch to ${url} failed:`, e);
    return false;
  }
}
