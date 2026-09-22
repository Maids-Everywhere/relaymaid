from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import jwt
import pytest

from relaymaid.config import Settings
from relaymaid.services.auth import create_access_token, decode_access_token
from relaymaid.services.exceptions import InvalidAccessTokenError


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


@pytest.mark.anyio
async def test_decode_access_token_returns_user_id() -> None:
    user_id = uuid4()
    secret = "test-secret-token-at-least-32-bytes"
    lifetime = timedelta(minutes=15)
    settings = Settings(jwt_secret_token=secret, jwt_lifetime=lifetime)

    with patch("relaymaid.services.auth.get_settings", return_value=settings):
        token = await create_access_token(user_id=user_id)
        decoded_user_id = await decode_access_token(access_token=token)

    assert decoded_user_id == user_id


@pytest.mark.anyio
async def test_decode_access_token_raises_for_invalid_token() -> None:
    with pytest.raises(InvalidAccessTokenError):
        await decode_access_token(access_token="not-a-valid-jwt")


@pytest.mark.anyio
async def test_decode_access_token_raises_for_invalid_sub() -> None:
    secret = "test-secret-token-at-least-32-bytes"
    lifetime = timedelta(minutes=15)
    settings = Settings(jwt_secret_token=secret, jwt_lifetime=lifetime)
    payload = {
        "sub": "not-a-uuid",
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int((datetime.now(UTC) + lifetime).timestamp()),
    }

    token = jwt.encode(payload, secret, algorithm="HS256")

    with (
        patch("relaymaid.services.auth.get_settings", return_value=settings),
        pytest.raises(InvalidAccessTokenError),
    ):
        await decode_access_token(access_token=token)


@pytest.mark.anyio
async def test_decode_access_token_raises_for_expired_token() -> None:
    secret = "test-secret-token-at-least-32-bytes"
    lifetime = timedelta(minutes=15)
    settings = Settings(jwt_secret_token=secret, jwt_lifetime=lifetime)
    expired_payload = {
        "sub": str(uuid4()),
        "iat": int((datetime.now(UTC) - timedelta(minutes=30)).timestamp()),
        "exp": int((datetime.now(UTC) - timedelta(minutes=1)).timestamp()),
    }

    token = jwt.encode(expired_payload, secret, algorithm="HS256")

    with (
        patch("relaymaid.services.auth.get_settings", return_value=settings),
        pytest.raises(InvalidAccessTokenError),
    ):
        await decode_access_token(access_token=token)
