import json
import sys
from urllib.parse import urlparse

from cryptography.fernet import Fernet
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///./ledger_dev.db"

    # Auth
    auth_provider: str = "dev"
    google_client_id: str | None = None
    webhook_encryption_keys: str = ""

    # AI Providers (free tiers)
    groq_api_key: str | None = None
    gemini_api_key: str | None = None
    cohere_api_key: str | None = None
    cerebras_api_key: str | None = None
    openrouter_api_key: str | None = None
    mistral_api_key: str | None = None

    # Kept for .env compatibility — not actively used
    anthropic_api_key: str | None = None

    # Upstash Redis REST API credentials. L2 cache is optional in development;
    # production startup requires both values for shared rate limits and budgets.
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""

    # CORS — comma-separated list of allowed origins.
    # Set CORS_ORIGINS on Render as:
    #   https://your-app.vercel.app,https://ledger-beta-two.vercel.app
    cors_origins: str = Field(
        default=("http://localhost:5173,http://127.0.0.1:5173,https://ledger-beta-two.vercel.app"),
        alias="CORS_ORIGINS",
    )

    def get_cors_origins(self) -> list[str]:
        """Parse CORS_ORIGINS string into a list. Supports comma-sep or JSON array."""
        raw = self.cors_origins.strip()
        if raw.startswith("["):
            origins = json.loads(raw)
        else:
            origins = raw.split(",")
        return [origin.strip().removesuffix("/") for origin in origins if origin.strip()]

    # Rate limiting (slowapi format, e.g. "10/minute", "5/hour"). These guard the
    # endpoints that burn CPU/RAM or free-tier AI provider quota on the single
    # 512MB Render worker.
    advisor_rate_limit: str = "10/minute"
    import_rate_limit: str = "10/hour"
    receipt_rate_limit: str = "20/hour"
    categorize_rate_limit: str = "60/minute"
    insights_rate_limit: str = "20/hour"

    # Statement-import bounds (protect the 512MB worker from huge uploads).
    max_upload_mb: int = 10
    max_import_rows: int = 5000

    # Logging
    log_level: str = "info"

    # ── AI Intelligence Settings (v2) ─────────────────────────────────────────
    # Categorization confidence threshold below which LLM is called
    categorization_confidence_threshold: float = 0.85

    # Proactive insights cache TTL in hours (per user)
    insight_cache_ttl_hours: int = 4

    # LLM cache TTL in seconds
    llm_cache_ttl_seconds: int = 3600  # 1 hour

    # AI provider safety controls. Empty policy values preserve the configured
    # adapter order; deployments can restrict providers globally or per task.
    ai_provider_allowlist: str = ""
    ai_task_provider_policy: str = ""
    ai_provider_timeout_seconds: float = 20.0
    ai_provider_max_attempts: int = 3
    # Open a provider circuit after repeated failures so a degraded upstream
    # does not consume every request's retry budget. The cooldown is short by
    # default; a later request probes the provider again automatically.
    ai_provider_circuit_failure_threshold: int = 3
    ai_provider_circuit_cooldown_seconds: float = 60.0
    # Request-equivalent quota guard. Zero disables the guard.
    ai_daily_request_budget: int = 0
    ai_provider_daily_request_budgets: str = ""
    ai_conversation_retention_days: int = 90
    # Fernet key used for portable encrypted backups. Generate with
    # `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`.
    backup_encryption_key: str | None = None
    backup_previous_encryption_keys: str = ""
    # JSON map such as {"Groq": "provider-configured-30d"}; unknown values
    # remain visible to users instead of being presented as guarantees.
    ai_provider_retention_policy: str = "{}"
    ai_provider_regions: str = "{}"

    # Anomaly detection sensitivity (IQR multiplier — higher = less sensitive)
    anomaly_iqr_multiplier: float = 1.5

    # ── Environment ─────────────────────────────────────────────────────────────
    environment: str = "development"
    debug: bool = False

    # Run create_all + ad-hoc column migrations at app import. entrypoint.sh already
    # performs the same DDL on container start, so this can be set to false in
    # production (RUN_DB_BOOTSTRAP=false) to skip redundant inspector round-trips on
    # every cold start. Defaults true so local/dev "just works".
    run_db_bootstrap: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )

    def validate_for_production(self) -> None:
        """Call at startup. Hard-fails if unsafe config is used in production."""
        if self.auth_provider not in {"google", "dev"}:
            print(
                f"FATAL: Unsupported AUTH_PROVIDER={self.auth_provider!r}. Use google or dev.",
                file=sys.stderr,
            )
            sys.exit(1)
        if self.environment == "production":
            origins = self.get_cors_origins()
            if not origins or any(
                urlparse(origin).scheme != "https" or not urlparse(origin).hostname or
                urlparse(origin).hostname in {"localhost", "127.0.0.1"} or
                urlparse(origin).path or urlparse(origin).query or urlparse(origin).fragment or
                urlparse(origin).username or urlparse(origin).password or "*" in origin
                for origin in origins
            ):
                print("FATAL: CORS_ORIGINS must contain only explicit HTTPS production origins.", file=sys.stderr)
                sys.exit(1)
            try:
                redis_url = urlparse(self.upstash_redis_rest_url)
                valid_rest_url = (
                    redis_url.scheme == "https"
                    and bool(redis_url.hostname)
                    and not redis_url.username
                    and not redis_url.password
                    and redis_url.path in {"", "/"}
                    and not redis_url.query
                    and not redis_url.fragment
                    and not any(char.isspace() for char in self.upstash_redis_rest_url)
                )
            except (TypeError, ValueError):
                valid_rest_url = False
            if not valid_rest_url or not self.upstash_redis_rest_token.strip():
                print(
                    "FATAL: UPSTASH_REDIS_REST_URL must be an HTTPS endpoint and UPSTASH_REDIS_REST_TOKEN must be set.",
                    file=sys.stderr,
                )
                sys.exit(1)
            if self.auth_provider != "google":
                print(
                    "FATAL: Production requires AUTH_PROVIDER=google.",
                    file=sys.stderr,
                )
                sys.exit(1)
            if self.auth_provider == "google" and not self.google_client_id:
                print(
                    "FATAL: GOOGLE_CLIENT_ID is required when AUTH_PROVIDER=google.",
                    file=sys.stderr,
                )
                sys.exit(1)
            if not self.webhook_encryption_keys:
                print("FATAL: WEBHOOK_ENCRYPTION_KEYS is required in production.", file=sys.stderr)
                sys.exit(1)
            if not self.backup_encryption_key:
                print("FATAL: BACKUP_ENCRYPTION_KEY is required in production.", file=sys.stderr)
                sys.exit(1)
            if self.backup_encryption_key in {key.strip() for key in self.webhook_encryption_keys.split(",")}:
                print("FATAL: Backup and webhook encryption keys must be separate.", file=sys.stderr)
                sys.exit(1)
            key_groups = (
                ("WEBHOOK_ENCRYPTION_KEYS", [key.strip() for key in self.webhook_encryption_keys.split(",")]),
                ("BACKUP_ENCRYPTION_KEY", [self.backup_encryption_key]),
                ("BACKUP_PREVIOUS_ENCRYPTION_KEYS", [key.strip() for key in self.backup_previous_encryption_keys.split(",") if key.strip()]),
            )
            for name, keys in key_groups:
                try:
                    for key in keys:
                        Fernet(key.encode())
                except (ValueError, TypeError):
                    print(f"FATAL: {name} must contain valid Fernet keys.", file=sys.stderr)
                    sys.exit(1)
            if not any(
                [
                    self.groq_api_key,
                    self.cerebras_api_key,
                    self.gemini_api_key,
                    self.cohere_api_key,
                    self.openrouter_api_key,
                ]
            ):
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
