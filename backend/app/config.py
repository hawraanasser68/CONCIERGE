# Owner A — backend/app/config.py
#
# Single source of truth for all configuration.
# Read once at startup via get_settings(); cached for the process lifetime.
# All secrets are fetched from Vault at startup in lifespan.py — this file
# only holds the variables needed to REACH Vault and the DB.

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="forbid" — crashes on startup if an unknown env var is present.
    # Prevents silent misconfiguration from typos in variable names.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        case_sensitive=False,
    )

    # ── Database ──────────────────────────────────────────────────────────────
    # asyncpg driver — used by SQLAlchemy async engine
    database_url: str

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://redis:6379"

    # ── Vault ─────────────────────────────────────────────────────────────────
    # These two are needed to bootstrap Vault at startup.
    # All other secrets (signing keys, API keys, service tokens) come FROM Vault.
    vault_addr: str = "http://vault:8200"
    vault_token: str = "root"

    # ── OpenTelemetry ─────────────────────────────────────────────────────────
    # OTLP gRPC endpoint — Jaeger listens on port 4317
    otel_exporter_otlp_endpoint: str = "http://jaeger:4317"

    # ── App ───────────────────────────────────────────────────────────────────
    environment: str = "development"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Returns a cached Settings instance. Call this everywhere instead of Settings()."""
    return Settings()
