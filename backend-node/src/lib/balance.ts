import { sql } from "drizzle-orm";
import { db } from "../db/client.js";

/**
 * Port of backend/app/main.py's _get_balance_at (lines 209-290).
 *
 * Returns the true running balance for a user as of (but NOT including)
 * `asOfDate`, or the current balance if `asOfDate` is omitted.
 *
 * Implemented as a single SQL CTE rather than two round-tripped queries so
 * the anchor row's microsecond-precision created_at never passes through a
 * JS Date (which truncates to millisecond precision and would silently
 * break the tie-break ordering below).
 */
export async function getBalanceAt(
  userId: string,
  opts: { asOfDate?: string | null; excludeId?: string | null } = {}
): Promise<string | null> {
  const { asOfDate = null, excludeId = null } = opts;

  const rows = await db.execute<{ balance: string | null }>(sql`
    WITH anchor AS (
      SELECT id, date, created_at,
             COALESCE(stmt_seq, 2147483647) AS seq,
             running_balance
      FROM transactions
      WHERE user_id = ${userId}
        AND running_balance IS NOT NULL
        AND source <> 'cash'
        ${asOfDate ? sql`AND date < ${asOfDate}` : sql``}
        ${excludeId ? sql`AND id <> ${excludeId}` : sql``}
      ORDER BY date DESC, created_at DESC, stmt_seq DESC NULLS LAST
      LIMIT 1
    )
    SELECT (
      anchor.running_balance + COALESCE((
        SELECT SUM(CASE WHEN t.type = 'income' THEN t.amount ELSE -t.amount END)
        FROM transactions t, anchor
        WHERE t.user_id = ${userId}
          AND t.id <> anchor.id
          AND t.source <> 'cash'
          AND (
            t.date > anchor.date
            OR (t.date = anchor.date AND t.created_at > anchor.created_at)
            OR (t.date = anchor.date AND t.created_at = anchor.created_at
                AND COALESCE(t.stmt_seq, 2147483647) > anchor.seq)
          )
          ${asOfDate ? sql`AND t.date < ${asOfDate}` : sql``}
          ${excludeId ? sql`AND t.id <> ${excludeId}` : sql``}
      ), 0)
    )::text AS balance
    FROM anchor
  `);

  const row = rows[0] as { balance: string | null } | undefined;
  return row?.balance ?? null;
}
