import { z } from "zod";

const envSchema = z.object({
  DATABASE_URL: z.string().default("postgresql://ledger:ledger@localhost:5432/ledger"),

  AUTH_PROVIDER: z.literal("google").default("google"),
  GOOGLE_CLIENT_ID: z.string().optional(),

  GROQ_API_KEY: z.string().optional(),
  GEMINI_API_KEY: z.string().optional(),
  COHERE_API_KEY: z.string().optional(),
  CEREBRAS_API_KEY: z.string().optional(),
  OPENROUTER_API_KEY: z.string().optional(),
  MISTRAL_API_KEY: z.string().optional(),

  CORS_ORIGINS: z
    .string()
    .default("http://localhost:5173,http://127.0.0.1:5173,https://ledger-beta-two.vercel.app"),

  ADVISOR_RATE_LIMIT: z.string().default("10/minute"),
  IMPORT_RATE_LIMIT: z.string().default("10/hour"),
  RECEIPT_RATE_LIMIT: z.string().default("20/hour"),
  CATEGORIZE_RATE_LIMIT: z.string().default("60/minute"),
  INSIGHTS_RATE_LIMIT: z.string().default("20/hour"),

  MAX_UPLOAD_MB: z.coerce.number().default(10),
  MAX_IMPORT_ROWS: z.coerce.number().default(5000),

  CATEGORIZATION_CONFIDENCE_THRESHOLD: z.coerce.number().default(0.85),
  INSIGHT_CACHE_TTL_HOURS: z.coerce.number().default(4),
  LLM_CACHE_TTL_SECONDS: z.coerce.number().default(3600),
  ANOMALY_IQR_MULTIPLIER: z.coerce.number().default(1.5),

  ENVIRONMENT: z.enum(["development", "production"]).default("development"),
  PORT: z.coerce.number().default(8000),
  WORKERS: z.string().default("1"),
  RUN_DB_BOOTSTRAP: z
    .string()
    .default("false")
    .transform((v) => v === "true"),
});

const parsed = envSchema.parse(process.env);

function normalizeDatabaseUrl(url: string): string {
  // Python's SQLAlchemy URL uses "postgresql+psycopg://"; postgres.js only
  // understands the bare "postgresql://" / "postgres://" scheme.
  return url.replace(/^postgresql\+psycopg:\/\//, "postgresql://");
}

export const config = {
  ...parsed,
  DATABASE_URL: normalizeDatabaseUrl(parsed.DATABASE_URL),
  corsOrigins: parsed.CORS_ORIGINS.split(",").map((o) => o.trim()).filter(Boolean),
};

function validateForProduction() {
  if (config.ENVIRONMENT === "production") {
    if (
      !config.GROQ_API_KEY &&
      !config.CEREBRAS_API_KEY &&
      !config.GEMINI_API_KEY &&
      !config.COHERE_API_KEY &&
      !config.OPENROUTER_API_KEY
    ) {
      console.warn("WARNING: No AI backend configured. Set at least one provider API key.");
    }
  }
}

validateForProduction();
