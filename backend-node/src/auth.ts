import type { Context, Next } from "hono";
import { config } from "./config.js";
import { db, schema } from "./db/client.js";
import { HttpError } from "./lib/http-error.js";

export interface UserContext {
  id: string;
  email: string | null;
}

function bearer(authorization: string | null | undefined): string {
  if (!authorization || !authorization.toLowerCase().startsWith("bearer ")) {
    throw new HttpError(401, "Missing Bearer token");
  }
  return authorization.slice(7).trim();
}

async function verifyToken(token: string): Promise<UserContext> {
  const provider = config.AUTH_PROVIDER;

  if (!token) {
    throw new HttpError(401, "Token required");
  }

  if (provider !== "google") {
    throw new HttpError(500, `Unsupported AUTH_PROVIDER: ${provider}`);
  }

  try {
    const res = await fetch(
      `https://oauth2.googleapis.com/tokeninfo?access_token=${encodeURIComponent(token)}`
    );
    if (!res.ok) throw new Error("Token rejected by Google");
    const info = await res.json() as { sub: string; email?: string; aud?: string; error_description?: string };
    if (info.error_description) throw new Error(info.error_description);
    if (!info.sub) throw new Error("Token missing sub");
    if (config.GOOGLE_CLIENT_ID && info.aud !== config.GOOGLE_CLIENT_ID) {
      throw new Error("Token audience mismatch");
    }
    return { id: info.sub, email: info.email ?? null };
  } catch (e) {
    throw new HttpError(401, `Google auth failed: ${(e as Error).message}`);
  }
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
