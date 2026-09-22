from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import jwt
from anyio import to_thread
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relaymaid.config import get_settings
from relaymaid.db.models import User
from relaymaid.schemas.auth import LoginRequest
from relaymaid.security import verify_password
from relaymaid.services.exceptions import (
    InvalidAccessTokenError,
    InvalidCredentialsError,
)


@dataclass(frozen=True, slots=True)
class AuthorizationResult:
    user: User
    access_token: str


async def create_access_token(*, user_id: UUID) -> str:
    settings = get_settings()
    created_at = datetime.now(UTC)

    payload = {
        "sub": str(user_id),
        "iat": int(created_at.timestamp()),
        "exp": int((created_at + settings.jwt_lifetime).timestamp()),
    }

    return jwt.encode(payload, settings.jwt_secret_token, algorithm="HS256")


async def decode_access_token(*, access_token: str):
    try:
        payload = jwt.decode(
            access_token,
            get_settings().jwt_secret_token,
            algorithms="HS256",
            options={"require": ["sub", "iat", "exp"]},
        )
        return UUID(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, KeyError, TypeError) as exc:
        raise InvalidAccessTokenError from exc


async def authorize_user(
    session: AsyncSession, data: LoginRequest
) -> AuthorizationResult:
    user = await session.scalar(select(User).where(User.email == data.email))

    if user is None:
        raise InvalidCredentialsError

    password_matches = await to_thread.run_sync(
        verify_password, data.password.get_secret_value(), user.hashed_password
    )

    if not password_matches or not user.is_active:
        raise InvalidCredentialsError

    return AuthorizationResult(
        user=user,
        access_token=await create_access_token(user_id=user.id),
    )
