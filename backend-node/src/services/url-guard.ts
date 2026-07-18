export function isValidUrl(urlStr: string): boolean {
  if (!urlStr) return false;
  try {
    const url = new URL(urlStr);
    return ["http:", "https:"].includes(url.protocol);
  } catch (e) {
    return false;
  }
}

export function isSafeUrl(urlStr: string): boolean {
  if (!isValidUrl(urlStr)) return false;
  try {
    const url = new URL(urlStr);
    const host = url.hostname.toLowerCase();
    
    // Prevent SSRF against local/internal addresses
    if (
      host === "localhost" ||
      host === "127.0.0.1" ||
      host === "::1" ||
      host.endsWith(".local") ||
      host.startsWith("10.") ||
      host.startsWith("192.168.")
    ) {
      return false;
    }
    
    return true;
  } catch (e) {
    return false;
  }
}
