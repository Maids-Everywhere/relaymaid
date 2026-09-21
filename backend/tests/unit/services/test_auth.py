from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import jwt
import pytest

from relaymaid.config import Settings
from relaymaid.services.auth import create_access_token


@pytest.mark.anyio
async def test_access_token_uses_utc_time() -> None:
    created_at = datetime(2026, 9, 21, 12, 30, tzinfo=UTC)
    lifetime = timedelta(minutes=15)
    secret = "test-secret-token-at-least-32-bytes"
    settings = Settings(jwt_secret_token=secret, jwt_lifetime=lifetime)

    with (
        patch("relaymaid.services.auth.get_settings", return_value=settings),
        patch("relaymaid.services.auth.datetime") as datetime_mock,
    ):
        datetime_mock.now.return_value = created_at
        token = await create_access_token(user_id=uuid4())

    datetime_mock.now.assert_called_once_with(UTC)
    payload = jwt.decode(
        token, secret, algorithms=["HS256"], options={"verify_exp": False}
    )
    assert payload["iat"] == int(created_at.timestamp())
    assert payload["exp"] == int((created_at + lifetime).timestamp())
