import { Hono } from "hono";
import { cors } from "hono/cors";
import { config } from "./config.js";
import { authMiddleware } from "./auth.js";
import { HttpError } from "./lib/http-error.js";
import { healthRoutes } from "./routes/health.js";
import { profileRoutes } from "./routes/profile.js";
import { accountRoutes } from "./routes/accounts.js";
import { budgetRoutes } from "./routes/budgets.js";
import { transactionRoutes } from "./routes/transactions.js";
import { importsRoutes } from "./routes/imports.js";
import { categorizationRoutes } from "./routes/categorization.js";
import { chatRoutes } from "./routes/chat.js";
import { analyticsRoutes } from "./routes/analytics.js";
import { summaryRoutes } from "./routes/summary.js";
import { exportRoutes } from "./routes/export.js";

export const app = new Hono();

// CORS must wrap everything — including error responses — so a 500 still
// carries CORS headers (mirrors the outer ASGI CORSMiddleware wrap in
// backend/app/main.py). exposeHeaders fixes a real prod bug: Python's CORS
// config never exposed X-Conversation-Id, so the SSE advisor route's
// conversation id header was unreadable cross-origin.
app.use(
  "*",
  cors({
    origin: config.corsOrigins,
    allowHeaders: ["Content-Type", "Authorization"],
    exposeHeaders: ["X-Conversation-Id"],
  })
);

app.onError((err, c) => {
  if (err instanceof HttpError) {
    return c.json({ detail: err.message }, err.status as any);
  }
  console.error(err);
  return c.json({ detail: "Internal server error" }, 500);
});

app.route("/", healthRoutes);

// Everything below requires a Bearer token.
app.use("*", authMiddleware);
app.route("/", profileRoutes);
app.route("/", accountRoutes);
app.route("/", budgetRoutes);
app.route("/", transactionRoutes);
app.route("/", importsRoutes);
app.route("/", categorizationRoutes);
app.route("/", chatRoutes);
app.route("/", analyticsRoutes);
app.route("/", summaryRoutes);
app.route("/", exportRoutes);

