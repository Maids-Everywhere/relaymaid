from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from anyio import to_thread
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relaymaid.db.models import Membership, User
from relaymaid.domain import MembershipRole
from relaymaid.security.passwords import verify_password
from relaymaid.security.tokens import create_access_token
from relaymaid.services.exceptions import InvalidCredentialsError


@dataclass(frozen=True, slots=True)
class AuthenticationResult:
    user_id: UUID
    organization_id: UUID
    email: str
    role: MembershipRole
    access_token: str


async def authenticate_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    token_secret: str,
    token_lifetime: timedelta,
) -> AuthenticationResult:
    user = await session.scalar(select(User).where(User.email == email))

    if user is None:
        raise InvalidCredentialsError

    password_matches = await to_thread.run_sync(
        verify_password, password, user.hashed_password
    )

    if not password_matches or not user.is_active:
        raise InvalidCredentialsError

    memberships = list(
        await session.scalars(select(Membership).where(Membership.user_id == user.id))
    )
    if len(memberships) != 1:
        raise InvalidCredentialsError

    membership = memberships[0]

    return AuthenticationResult(
        user_id=user.id,
        organization_id=membership.organization_id,
        email=user.email,
        role=membership.role,
        access_token=create_access_token(
            user_id=user.id,
            organization_id=membership.organization_id,
            role=membership.role,
            secret=token_secret,
            lifetime=token_lifetime,
        ),
    )
