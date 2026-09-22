from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from relaymaid.domain import MembershipRole

JWT_ALGORITHM = "HS256"


class InvalidAccessTokenError(Exception):
    """Raised when an access token cannot be validated."""


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    user_id: UUID
    organization_id: UUID
    role: MembershipRole


def create_access_token(
    *,
    user_id: UUID,
    organization_id: UUID,
    role: MembershipRole,
    secret: str,
    lifetime: timedelta,
    created_at: datetime | None = None,
) -> str:
    issued_at = created_at or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "org": str(organization_id),
        "role": role.value,
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + lifetime).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_access_token(*, access_token: str, secret: str) -> AccessTokenClaims:
    try:
        payload = jwt.decode(
            access_token,
            secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "org", "role", "iat", "exp"]},
        )
        return AccessTokenClaims(
            user_id=UUID(payload["sub"]),
            organization_id=UUID(payload["org"]),
            role=MembershipRole(payload["role"]),
        )
    except (jwt.InvalidTokenError, ValueError, KeyError, TypeError) as exc:
        raise InvalidAccessTokenError from exc
