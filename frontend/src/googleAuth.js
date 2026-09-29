import { API_BASE } from "./lib";

let reauthenticationPromise = null;

export async function createGoogleSession(credential) {
  const response = await fetch(`${API_BASE}/auth/session`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ credential }),
  });
  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("Google rejected this sign-in. Check that VITE_GOOGLE_CLIENT_ID matches the backend GOOGLE_CLIENT_ID, and use a verified Google account.");
    }
    if (response.status === 403) {
      throw new Error("This site is not authorized for Google sign-in. Check CORS_ORIGINS and the OAuth authorized JavaScript origins.");
    }
    throw new Error("Google authentication failed. Please try again.");
  }
  return response.json();
}

export async function loadGoogleSession() {
  const response = await fetch(`${API_BASE}/auth/session`, { credentials: "include" });
  return response.ok ? response.json() : null;
}

export async function clearGoogleSession() {
  const response = await fetch(`${API_BASE}/auth/session`, { method: "DELETE", credentials: "include" });
  if (!response.ok) throw new Error("Could not sign out. Please try again.");
  window.google?.accounts?.id?.disableAutoSelect();
}

export function reauthenticate() {
  if (reauthenticationPromise) return reauthenticationPromise;

  reauthenticationPromise = new Promise((resolve, reject) => {
    const google = window.google?.accounts?.id;
    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
    if (!google || !clientId) {
      reject(new Error("Google authentication is unavailable. Sign out and sign in again."));
      return;
    }
    let settled = false;
    const timer = window.setTimeout(() => finish(new Error("Google authentication timed out.")), 30000);
    function finish(error) {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      if (error) reject(error);
      else resolve();
    }
    google.initialize({
      client_id: clientId,
      callback: async ({ credential }) => {
        if (!credential) return finish(new Error("Google authentication was cancelled."));
        try {
          const response = await fetch(`${API_BASE}/auth/reauth`, {
            method: "POST", credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ credential }),
          });
          if (!response.ok) throw new Error("Google authentication failed. Sign out and sign in again.");
          finish();
        } catch (error) { finish(error); }
      },
    });
    google.prompt((notification) => {
      if (notification.isNotDisplayed() || notification.isSkippedMoment()) {
        finish(new Error("Google authentication is unavailable. Sign out and sign in again."));
      }
    });
  }).finally(() => {
    reauthenticationPromise = null;
  });
  return reauthenticationPromise;
}

export async function fetchWithReauth(path, options) {
  let response = await fetch(`${API_BASE}${path}`, { ...options, credentials: "include" });
  if (response.status === 428) {
    await reauthenticate();
    response = await fetch(`${API_BASE}${path}`, { ...options, credentials: "include" });
  }
  return response;
}
