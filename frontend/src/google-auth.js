// Google OAuth token management
// The credential (id_token) returned by @react-oauth/google is stored here
// and sent as a Bearer token on every API request.

let _credential = null;
let _listeners = [];

export function setCredential(credential) {
  _credential = credential;
  _listeners.forEach((fn) => fn(credential));
}

export function getCredential() {
  return _credential;
}

export function clearCredential() {
  _credential = null;
  sessionStorage.removeItem('g_credential');
  _listeners.forEach((fn) => fn(null));
}

// Persist across soft refreshes (session only — gone on tab close)
export function persistCredential(credential) {
  sessionStorage.setItem('g_credential', credential);
  setCredential(credential);
}

export function loadPersistedCredential() {
  const saved = sessionStorage.getItem('g_credential');
  if (saved) setCredential(saved);
  return saved;
}

// Subscribe to auth state changes (mirrors Supabase onAuthStateChange pattern)
export function onAuthChange(fn) {
  _listeners.push(fn);
  return () => { _listeners = _listeners.filter((l) => l !== fn); };
}

// Parse the Google id_token payload without verification (client-side only;
// the backend verifies the signature).
export function parseIdToken(credential) {
  try {
    const [, payload] = credential.split('.');
    return JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')));
  } catch {
    return null;
  }
}
