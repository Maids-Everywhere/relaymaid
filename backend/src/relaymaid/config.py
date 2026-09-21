import os
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Ensure .env from project root is loaded into environment variables early
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ENV_PATH = _PROJECT_ROOT / ".env"
if _ENV_PATH.exists():
    for _line in _ENV_PATH.read_text().splitlines():
        line = _line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            # don't override existing env vars
            os.environ.setdefault(k, v)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    environment: Literal["local", "test", "production"] = "local"

    # -------------- Database Section --------------
    model_config = SettingsConfigDict(
        # point to the absolute .env to ensure it's found when tests run
        env_file=str(_ENV_PATH),
        # read variables as-is from .env (no prefix)
        extra="allow",
    )

    database_url: str = (
        "postgresql+psycopg://relaymaid:relaymaid@postgres:5432/relaymaid"
    )
    redis_url: str = "redis://redis:6379/0"

    # -------------- JWT Section --------------
    jwt_lifetime: timedelta = timedelta(minutes=15)
    # read from JWT_SECRET_TOKEN in .env (project uses unprefixed .env keys)
    # pydantic will read the env var `JWT_SECRET_TOKEN` by default for
    # the `jwt_secret_token` field name, so no Field/env override is needed
    jwt_secret_token: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
