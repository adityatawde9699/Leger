const STORAGE_KEY = "google-session";

// How many milliseconds before expiry we attempt a silent refresh.
const REFRESH_BEFORE_EXPIRY_MS = 5 * 60 * 1000; // 5 minutes

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

/**
 * Returns how many ms until we should attempt a silent refresh.
 * Returns 0 if the session is already expired or within the refresh window.
 */
export function msUntilRefresh(session) {
  if (!session?.expires_at) return 0;
  return Math.max(0, session.expires_at - Date.now() - REFRESH_BEFORE_EXPIRY_MS);
}

/**
 * Attempts a silent Google One Tap re-authentication.
 * Resolves with a fresh session if Google can silently issue a new credential
 * (user is still signed into their Google account).
 * Rejects if silent re-auth is not possible (user must interact).
 */
export function silentlyRefreshGoogleSession(clientId) {
  return new Promise((resolve, reject) => {
    if (!window.google?.accounts?.id) {
      reject(new Error("Google Identity Services not loaded"));
      return;
    }

    window.google.accounts.id.initialize({
      client_id: clientId,
      callback: ({ credential, error }) => {
        if (error || !credential) {
          reject(new Error(error || "Silent re-auth returned no credential"));
          return;
        }
        try {
          const session = createGoogleSession(credential);
          saveGoogleSession(session);
          resolve(session);
        } catch (err) {
          reject(err);
        }
      },
    });

    // prompt() with a notification callback so we can detect
    // when Google says silent re-auth isn't possible.
    window.google.accounts.id.prompt((notification) => {
      if (notification.isNotDisplayed() || notification.isSkippedMoment()) {
        reject(new Error("Silent re-auth not available: " + (notification.getNotDisplayedReason?.() || notification.getSkippedReason?.() || "unknown")));
      }
    });
  });
}
