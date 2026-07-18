import { Hono } from "hono";

export const healthRoutes = new Hono();

// No auth, no DB — keep-alive target for Render free tier (matches /ping in
// backend/app/main.py, healthCheckPath in render.yaml).
healthRoutes.get("/ping", (c) => c.json({ pong: true }));
healthRoutes.get("/health", (c) => c.json({ ok: true, version: "1.4.0" }));
