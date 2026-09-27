from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ENV_PATH = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Runtime application settings."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH),
        env_prefix="RELAYMAID_",
        extra="ignore",
    )

    environment: Literal["local", "test", "production"] = "local"

    database_url: str
    redis_url: str = "redis://redis:6379/0"

    jwt_lifetime: timedelta = timedelta(minutes=15)
    jwt_secret_token: str = Field(
        min_length=1,
        validation_alias=AliasChoices(
            "RELAYMAID_JWT_SECRET_TOKEN",
            "JWT_SECRET_TOKEN",
            "jwt_secret_token",
        ),
    )


class MigrationSettings(BaseSettings):
    """Privileged settings used only by Alembic."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH),
        env_prefix="RELAYMAID_",
        extra="ignore",
    )

    migration_database_url: str


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_migration_settings() -> MigrationSettings:
    return MigrationSettings()