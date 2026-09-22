from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from relaymaid.domain import MembershipRole
from relaymaid.security.tokens import (
    InvalidAccessTokenError,
    create_access_token,
    decode_access_token,
)

SECRET = "test-secret-token-at-least-32-bytes"
LIFETIME = timedelta(minutes=15)


def test_access_token_uses_supplied_time() -> None:
    created_at = datetime(2026, 9, 21, 12, 30, tzinfo=UTC)
    organization_id = uuid4()
    token = create_access_token(
        user_id=uuid4(),
        organization_id=organization_id,
        role=MembershipRole.OWNER,
        secret=SECRET,
        lifetime=LIFETIME,
        created_at=created_at,
    )

    payload = jwt.decode(
        token, SECRET, algorithms=["HS256"], options={"verify_exp": False}
    )
    assert payload["iat"] == int(created_at.timestamp())
    assert payload["exp"] == int((created_at + LIFETIME).timestamp())
    assert payload["org"] == str(organization_id)
    assert payload["role"] == "owner"


def test_decode_access_token_returns_user_id() -> None:
    user_id = uuid4()
    organization_id = uuid4()
    token = create_access_token(
        user_id=user_id,
        organization_id=organization_id,
        role=MembershipRole.VIEWER,
        secret=SECRET,
        lifetime=LIFETIME,
    )
    claims = decode_access_token(access_token=token, secret=SECRET)

    assert claims.user_id == user_id
    assert claims.organization_id == organization_id
    assert claims.role is MembershipRole.VIEWER


def test_decode_access_token_raises_for_invalid_token() -> None:
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(access_token="not-a-valid-jwt", secret=SECRET)


def test_decode_access_token_raises_for_invalid_sub() -> None:
    payload = {
        "sub": "not-a-uuid",
        "org": str(uuid4()),
        "role": "owner",
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int((datetime.now(UTC) + LIFETIME).timestamp()),
    }

    token = jwt.encode(payload, SECRET, algorithm="HS256")

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(access_token=token, secret=SECRET)


def test_decode_access_token_raises_for_expired_token() -> None:
    expired_payload = {
        "sub": str(uuid4()),
        "org": str(uuid4()),
        "role": "owner",
        "iat": int((datetime.now(UTC) - timedelta(minutes=30)).timestamp()),
        "exp": int((datetime.now(UTC) - timedelta(minutes=1)).timestamp()),
    }

    token = jwt.encode(expired_payload, SECRET, algorithm="HS256")

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(access_token=token, secret=SECRET)
