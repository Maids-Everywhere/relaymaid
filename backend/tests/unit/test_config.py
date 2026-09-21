import pytest

from relaymaid.config import Settings


def test_settings_use_relaymaid_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = "postgresql+psycopg://user:password@localhost:5432/test_db"
    monkeypatch.setenv("RELAYMAID_DATABASE_URL", database_url)
    monkeypatch.setenv("RELAYMAID_REDIS_URL", "redis://localhost:6379/1")

    settings = Settings()

    assert settings.database_url == database_url
    assert settings.redis_url == "redis://localhost:6379/1"


def test_settings_use_unprefixed_jwt_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET_TOKEN", "test-secret-token")

    settings = Settings()

    assert settings.jwt_secret_token == "test-secret-token"
