export async function dispatchWebhook(url: string, payload: any, secret?: string): Promise<boolean> {
  if (!url) return false;
  
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "User-Agent": "Leger-Webhook/1.0"
  };
  
  if (secret) {
    // In a real implementation, you would compute an HMAC signature here
    // e.g. using crypto.createHmac
    headers["X-Leger-Signature"] = "stub_signature";
  }
  
  try {
    const res = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      // Webhooks should timeout relatively quickly to avoid blocking
      signal: AbortSignal.timeout(5000)
    });
    
    return res.ok;
  } catch (e) {
    console.warn(`Webhook dispatch to ${url} failed:`, e);
    return false;
  }
}
