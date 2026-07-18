import type { Context, Next } from "hono";
import { createRemoteJWKSet, jwtVerify } from "jose";
import { config } from "./config.js";
import { db, schema } from "./db/client.js";
import { HttpError } from "./lib/http-error.js";

export interface UserContext {
  id: string;
  email: string | null;
}

let jwks: ReturnType<typeof createRemoteJWKSet> | null = null;
function getJwks() {
  if (!config.SUPABASE_JWKS_URL) {
    throw new HttpError(500, "SUPABASE_JWKS_URL not configured");
  }
  if (!jwks) jwks = createRemoteJWKSet(new URL(config.SUPABASE_JWKS_URL));
  return jwks;
}

// Google's public JWKS for verifying access tokens / id_tokens
const GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs";
let googleJwks: ReturnType<typeof createRemoteJWKSet> | null = null;
function getGoogleJwks() {
  if (!googleJwks) googleJwks = createRemoteJWKSet(new URL(GOOGLE_JWKS_URL));
  return googleJwks;
}

let firebaseAuthPromise: Promise<import("firebase-admin").auth.Auth> | null = null;
async function getFirebaseAuth() {
  if (!firebaseAuthPromise) {
    firebaseAuthPromise = (async () => {
      const admin = await import("firebase-admin");
      if (!admin.apps.length) admin.initializeApp();
      return admin.auth();
    })();
  }
  return firebaseAuthPromise;
}

function bearer(authorization: string | null | undefined): string {
  if (!authorization || !authorization.toLowerCase().startsWith("bearer ")) {
    throw new HttpError(401, "Missing Bearer token");
  }
  return authorization.slice(7).trim();
}

async function verifyToken(token: string): Promise<UserContext> {
  const provider = config.AUTH_PROVIDER;

  if (provider === "dev") {
    if (!token) throw new HttpError(401, "Token required even in dev mode");
    return { id: token, email: `${token}@dev.ledger.local` };
  }

  if (provider === "firebase") {
    try {
      const auth = await getFirebaseAuth();
      const decoded = await auth.verifyIdToken(token);
      return { id: decoded.uid, email: decoded.email ?? null };
    } catch (e) {
      throw new HttpError(401, `Firebase auth failed: ${(e as Error).message}`);
    }
  }

  if (provider === "supabase") {
    try {
      const { payload } = await jwtVerify(token, getJwks(), {
        algorithms: ["ES256", "RS256"],
      });
      if (!payload.sub) throw new Error("token missing sub");
      return { id: payload.sub, email: (payload.email as string) ?? null };
    } catch (e) {
      throw new HttpError(401, `Token invalid: ${(e as Error).message}`);
    }
  }

  if (provider === "google") {
    try {
      // Google access tokens can be verified via the tokeninfo endpoint.
      // This is simpler and more reliable than JWKS for access_tokens.
      const res = await fetch(
        `https://oauth2.googleapis.com/tokeninfo?access_token=${encodeURIComponent(token)}`
      );
      if (!res.ok) throw new Error("Token rejected by Google");
      const info = await res.json() as { sub: string; email?: string; aud?: string; error_description?: string };
      if (info.error_description) throw new Error(info.error_description);
      if (!info.sub) throw new Error("Token missing sub");
      // Optionally validate audience matches our client ID
      if (config.GOOGLE_CLIENT_ID && info.aud !== config.GOOGLE_CLIENT_ID) {
        throw new Error("Token audience mismatch");
      }
      return { id: info.sub, email: info.email ?? null };
    } catch (e) {
      throw new HttpError(401, `Google auth failed: ${(e as Error).message}`);
    }
  }

  throw new HttpError(500, `Unknown AUTH_PROVIDER: ${provider}`);
}

export async function authMiddleware(c: Context, next: Next) {
  const user = await verifyToken(bearer(c.req.header("authorization")));

  await db
    .insert(schema.users)
    .values({ id: user.id, email: user.email })
    .onConflictDoNothing({ target: schema.users.id });

  c.set("user", user);
  await next();
}

export function getUser(c: Context): UserContext {
  return c.get("user") as UserContext;
}
