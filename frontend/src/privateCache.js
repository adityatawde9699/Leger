// Authenticated API responses must never persist on the device. Earlier builds let the
// service worker cache /api responses in "api-cache"; this removes that cache on startup
// and whenever the session ends, so financial data does not outlive a sign-out.
const LEGACY_API_CACHES = ["api-cache"];

export async function clearCachedApiData() {
  if (typeof window === "undefined" || !("caches" in window)) return;
  try {
    await Promise.all(LEGACY_API_CACHES.map((name) => window.caches.delete(name)));
  } catch {
    // Cache Storage can be unavailable (private mode, blocked storage); nothing to clear then.
  }
}
