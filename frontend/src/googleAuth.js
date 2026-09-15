const STORAGE_KEY = "google-session";

function decodeIdToken(token) {
  const parts = token.split(".");
  if (parts.length !== 3) throw new Error("Google returned an invalid ID token.");

  const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
  const padded = payload.padEnd(Math.ceil(payload.length / 4) * 4, "=");
  return JSON.parse(decodeURIComponent(
    atob(padded)
      .split("")
      .map((char) => `%${char.charCodeAt(0).toString(16).padStart(2, "0")}`)
      .join("")
  ));
}

function isValidGoogleClaims(claims) {
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
  const issuerIsGoogle = claims.iss === "accounts.google.com" || claims.iss === "https://accounts.google.com";
  return Boolean(
    claims.sub &&
    claims.exp * 1000 > Date.now() &&
    claims.aud === clientId &&
    issuerIsGoogle
  );
}

export function createGoogleSession(credential) {
  const claims = decodeIdToken(credential);
  if (!isValidGoogleClaims(claims)) {
    throw new Error("Google returned an expired or invalid credential.");
  }

  return {
    access_token: credential,
    expires_at: claims.exp * 1000,
    user: {
      id: claims.sub,
      email: claims.email,
      name: claims.name,
      picture: claims.picture,
    },
  };
}

export function saveGoogleSession(session) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function loadGoogleSession() {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (!saved) return null;

  try {
    const session = JSON.parse(saved);
    const claims = decodeIdToken(session.access_token || "");
    if (!isValidGoogleClaims(claims)) throw new Error("Expired session");
    return session;
  } catch {
    localStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function clearGoogleSession() {
  localStorage.removeItem(STORAGE_KEY);
  window.google?.accounts?.id?.disableAutoSelect();
}
