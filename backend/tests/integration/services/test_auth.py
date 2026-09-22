from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from relaymaid.db.models import Membership, Organization, User
from relaymaid.domain import MembershipRole
from relaymaid.services.authentication import authenticate_user
from relaymaid.services.exceptions import InvalidCredentialsError
from relaymaid.services.registration import register_owner

EMAIL = "exist_user@example.com"
ORGANIZATION_NAME = "Clear Tests Corp."
VALID_PASSWORD = "superValidPassword4u"
INVALID_PASSWORD = "OOPSiFORGOTmyPASSWORD:("
TOKEN_SECRET = "test-secret-token-at-least-32-bytes"
TOKEN_LIFETIME = timedelta(minutes=15)


@pytest.fixture
async def dummy_user(db_session: AsyncSession) -> User:
    result = await register_owner(
        db_session,
        email=EMAIL,
        organization_name=ORGANIZATION_NAME,
        password=VALID_PASSWORD,
    )
    user = await db_session.get(User, result.user_id)

    assert user is not None
    return user


@pytest.mark.integration
@pytest.mark.anyio
async def test_user_authenticates_with_valid_credentials(
    db_session: AsyncSession, dummy_user: User
) -> None:
    result = await authenticate_user(
        db_session,
        email=EMAIL,
        password=VALID_PASSWORD,
        token_secret=TOKEN_SECRET,
        token_lifetime=TOKEN_LIFETIME,
    )

    assert result.user_id == dummy_user.id
    assert result.organization_id is not None
    assert result.email == dummy_user.email
    assert result.role.value == "owner"
    assert result.access_token


@pytest.mark.integration
@pytest.mark.anyio
async def test_user_authentication_rejects_wrong_password(
    db_session: AsyncSession, dummy_user: User
) -> None:
    assert dummy_user.__class__ is User  # Validate that user exists

    with pytest.raises(InvalidCredentialsError):
        await authenticate_user(
            db_session,
            email=EMAIL,
            password=INVALID_PASSWORD,
            token_secret=TOKEN_SECRET,
            token_lifetime=TOKEN_LIFETIME,
        )


@pytest.mark.integration
@pytest.mark.anyio
async def test_user_authentication_rejects_wrong_email(
    db_session: AsyncSession,
    dummy_user: User,
) -> None:
    assert dummy_user.__class__ is User  # Validate that user exists

    with pytest.raises(InvalidCredentialsError):
        await authenticate_user(
            db_session,
            email="missing_user@example.com",
            password=VALID_PASSWORD,
            token_secret=TOKEN_SECRET,
            token_lifetime=TOKEN_LIFETIME,
        )


@pytest.mark.integration
@pytest.mark.anyio
async def test_user_authentication_rejects_missing_account(
    db_session: AsyncSession,
) -> None:
    db_users_counts = await db_session.scalar(select(func.count()).select_from(User))
    assert db_users_counts == 0

    with pytest.raises(InvalidCredentialsError):
        await authenticate_user(
            db_session,
            email=EMAIL,
            password=VALID_PASSWORD,
            token_secret=TOKEN_SECRET,
            token_lifetime=TOKEN_LIFETIME,
        )


@pytest.mark.integration
@pytest.mark.anyio
async def test_authentication_requires_selection_for_multiple_memberships(
    db_session: AsyncSession,
    dummy_user: User,
) -> None:
    existing_membership = await db_session.scalar(
        select(Membership).where(Membership.user_id == dummy_user.id)
    )
    assert existing_membership is not None

    second_organization = Organization(name="Second Organization")
    db_session.add(second_organization)
    await db_session.flush()
    db_session.add(
        Membership(
            user_id=dummy_user.id,
            organization_id=second_organization.id,
            role=MembershipRole.VIEWER,
        )
    )
    await db_session.flush()

    with pytest.raises(InvalidCredentialsError):
        await authenticate_user(
            db_session,
            email=EMAIL,
            password=VALID_PASSWORD,
            token_secret=TOKEN_SECRET,
            token_lifetime=TOKEN_LIFETIME,
        )
