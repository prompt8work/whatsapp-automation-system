"""Settings from environment variables (or backend/.env locally). See backend/.env.example."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOCAL_JWT_SECRET = "local-dev-only-jwt-secret-do-not-use-in-prod"
_LOCAL_CRON_SECRET = "local-cron-secret"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["local", "test", "preview", "production"] = "local"
    log_level: str = "INFO"

    # Runtime connection: role app_rw, POOLED url in production.
    database_url: str = "postgresql+psycopg://app_rw:app_rw@localhost:5432/wa_platform"
    # Migrations: role app_owner, DIRECT (non-pooled) url.
    database_migration_url: str = (
        "postgresql+psycopg://app_owner:app_owner@localhost:5432/wa_platform"
    )

    # Auth (ARCHITECTURE §8.8). Generate secrets with:
    #   python -c "import secrets; print(secrets.token_urlsafe(48))"
    jwt_secret: SecretStr = SecretStr(_LOCAL_JWT_SECRET)
    access_token_minutes: int = 15
    refresh_token_days: int = 14

    # Shared secret Vercel Cron sends as `Authorization: Bearer <secret>`.
    cron_secret: SecretStr = SecretStr(_LOCAL_CRON_SECRET)

    # WhatsApp (ARCHITECTURE §7). "recording" logs outgoing messages instead of calling Meta -
    # the default locally and in tests; production uses "meta".
    whatsapp_sender: Literal["meta", "recording"] = "recording"
    meta_graph_api_version: str = "v23.0"
    meta_app_secret: SecretStr = SecretStr("")  # verifies X-Hub-Signature-256 on webhooks
    meta_verify_token: SecretStr = SecretStr("local-verify-token")  # webhook subscription check
    # Fernet key that encrypts per-number access tokens at rest. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    credentials_key: SecretStr = SecretStr("")

    # Dashboard origins allowed by CORS (local Vite dev server).
    cors_origins: list[str] = ["http://localhost:5173"]

    @property
    def is_local(self) -> bool:
        return self.environment in ("local", "test")

    @model_validator(mode="after")
    def _no_default_secrets_outside_local(self) -> Self:
        if not self.is_local:
            if self.jwt_secret.get_secret_value() == _LOCAL_JWT_SECRET:
                raise ValueError("Set JWT_SECRET for preview/production")
            if self.cron_secret.get_secret_value() == _LOCAL_CRON_SECRET:
                raise ValueError("Set CRON_SECRET for preview/production")
            if self.whatsapp_sender == "meta" and not (
                self.meta_app_secret.get_secret_value() and self.credentials_key.get_secret_value()
            ):
                raise ValueError(
                    "Set META_APP_SECRET and CREDENTIALS_KEY to use WHATSAPP_SENDER=meta"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
