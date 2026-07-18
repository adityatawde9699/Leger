import { serve } from "@hono/node-server";
import { config } from "./config.js";
import { app } from "./app.js";
import { bootstrap } from "./db/bootstrap.js";

async function main() {
  if (config.RUN_DB_BOOTSTRAP) {
    await bootstrap();
  }

  const server = serve({ fetch: app.fetch, port: config.PORT }, (info) => {
    console.log(`ledger-api-node listening on :${info.port}`);
  });

  const shutdown = () => {
    server.close(() => process.exit(0));
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

main().catch((err) => {
  console.error("Fatal startup error", err);
  process.exit(1);
});
