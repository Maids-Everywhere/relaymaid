from pathlib import Path

import pytest
from pydantic import ValidationError

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


def test_settings_read_jwt_secret_from_env_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("JWT_SECRET_TOKEN", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("JWT_SECRET_TOKEN=dotenv-secret\n")

    settings = Settings(_env_file=env_file)

    assert settings.jwt_secret_token == "dotenv-secret"


def test_environment_overrides_env_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("JWT_SECRET_TOKEN", "environment-secret")
    env_file = tmp_path / ".env"
    env_file.write_text("JWT_SECRET_TOKEN=dotenv-secret\n")

    settings = Settings(_env_file=env_file)

    assert settings.jwt_secret_token == "environment-secret"


@pytest.mark.parametrize("secret", [None, ""])
def test_settings_require_non_empty_jwt_secret(
    monkeypatch: pytest.MonkeyPatch,
    secret: str | None,
) -> None:
    for variable in (
        "JWT_SECRET_TOKEN",
        "RELAYMAID_JWT_SECRET_TOKEN",
        "jwt_secret_token",
    ):
        monkeypatch.delenv(variable, raising=False)
    if secret is not None:
        monkeypatch.setenv("JWT_SECRET_TOKEN", secret)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
