import sys

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///./ledger_dev.db"

    # Auth
    auth_provider: str = "dev"
    supabase_jwks_url: str | None = None
    firebase_project_id: str | None = None

    # AI Providers (free tiers)
    groq_api_key: str | None = None
    gemini_api_key: str | None = None
    cohere_api_key: str | None = None
    cerebras_api_key: str | None = None
    openrouter_api_key: str | None = None
    mistral_api_key: str | None = None

    # Kept for .env compatibility — not actively used
    anthropic_api_key: str | None = None

    # Redis (optional — L2 cache, gracefully skipped if unavailable)
    redis_url: str = "redis://localhost:6379/0"

    # CORS — comma-separated or JSON list of allowed origins
    # Render sets env vars as plain strings, so support both formats:
    #   CORS_ORIGINS=https://my-app.vercel.app,https://my-app-preview.vercel.app
    cors_origins_raw: str = (
        "http://localhost:5173,"
        "http://127.0.0.1:5173,"
        "https://ledger-beta-two.vercel.app"
    )

    @property
    def cors_origins(self) -> list[str]:
        raw = self.cors_origins_raw.strip()
        if raw.startswith("["):  # JSON array format
            import json
            return json.loads(raw)
        return [o.strip() for o in raw.split(",") if o.strip()]

    # Rate limiting
    advisor_rate_limit: str = "10/minute"

    # Logging
    log_level: str = "info"

    # ── AI Intelligence Settings (v2) ─────────────────────────────────────────
    # Categorization confidence threshold below which LLM is called
    categorization_confidence_threshold: float = 0.85

    # Proactive insights cache TTL in hours (per user)
    insight_cache_ttl_hours: int = 4

    # LLM cache TTL in seconds
    llm_cache_ttl_seconds: int = 3600  # 1 hour

    # Anomaly detection sensitivity (IQR multiplier — higher = less sensitive)
    anomaly_iqr_multiplier: float = 1.5

    # ── Environment ─────────────────────────────────────────────────────────────
    environment: str = "development"
    debug: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_parse_none_str="",
        # Allow "cors_origins" in .env to map to cors_origins_raw
        populate_by_name=True,
    )

    def validate_for_production(self) -> None:
        """Call at startup. Hard-fails if unsafe config is used in production."""
        if self.environment == "production":
            if self.auth_provider == "dev":
                print(
                    "FATAL: AUTH_PROVIDER=dev is not allowed in production. "
                    "Set AUTH_PROVIDER=supabase or AUTH_PROVIDER=firebase.",
                    file=sys.stderr,
                )
                sys.exit(1)
            if not any([
                self.groq_api_key,
                self.cerebras_api_key,
                self.gemini_api_key,
                self.cohere_api_key,
                self.openrouter_api_key,
            ]):
                print(
                    "WARNING: No AI backend configured. Set at least one provider API key.",
                    file=sys.stderr,
                )
        elif self.auth_provider == "dev":
            print(
                "WARNING: Running with AUTH_PROVIDER=dev. "
                "Any Bearer token is accepted as a user ID. "
                "Never use this in production.",
                file=sys.stderr,
            )


settings = Settings()
settings.validate_for_production()
