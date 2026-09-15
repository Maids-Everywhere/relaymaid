from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="RELAYMAID_",
        extra="ignore",
    )

    environment: Literal["local", "test", "production"] = "local"
    database_url: str = (
        "postgresql+psycopg://relaymaid:relaymaid@postgres:5432/relaymaid"
    )
    redis_url: str = "redis://redis:6379/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
