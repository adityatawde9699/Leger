import sys
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///./ledger_dev.db"

    # Auth
    auth_provider: str = "dev"
    supabase_jwks_url: str | None = None
    firebase_project_id: str | None = None

    # AI — Cloud
    anthropic_api_key: str | None = None

    # AI — Local (llama.cpp server)
    llama_server_url: str = "http://127.0.0.1:8080"
    llama_enabled: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # CORS — comma-separated list of allowed origins
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Rate limiting
    advisor_rate_limit: str = "10/minute"

    # Environment
    environment: str = "development"
    debug: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_parse_none_str="",
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
            if not self.anthropic_api_key and not self.llama_enabled:
                print(
                    "WARNING: No AI backend configured. "
                    "Set ANTHROPIC_API_KEY or LLAMA_ENABLED=true.",
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
