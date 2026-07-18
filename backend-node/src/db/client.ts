import postgres from "postgres";
import { drizzle } from "drizzle-orm/postgres-js";
import { config } from "../config.js";
import * as schema from "./schema.js";

// prepare: false — Neon's PgBouncer runs in transaction-pooling mode, which
// does not support protocol-level prepared statements (mirrors Python's
// prepare_threshold=None in backend/app/db.py).
const client = postgres(config.DATABASE_URL, { prepare: false, max: 5, idle_timeout: 20 });

export const db = drizzle(client, { schema });
export { schema };
