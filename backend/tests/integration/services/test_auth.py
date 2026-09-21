import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from relaymaid.db.models import User
from relaymaid.schemas.auth import LoginRequest, RegisterRequest
from relaymaid.services.auth import authorize_user
from relaymaid.services.exceptions import InvalidCredentialsError
from relaymaid.services.registration import register_owner

EMAIL = "exist_user@example.com"
ORGANIZATION_NAME = "Clear Tests Corp."
VALID_PASSWORD = "superValidPassword4u"
INVALID_PASSWORD = "OOPSiFORGOTmyPASSWORD:("


@pytest.fixture
async def dummy_user(db_session: AsyncSession) -> User:
    register_request = RegisterRequest.model_validate(
        {
            "email": EMAIL,
            "organization_name": ORGANIZATION_NAME,
            "password": VALID_PASSWORD,
        }
    )

    registration_result = await register_owner(db_session, register_request)

    return registration_result.user


@pytest.mark.integration
@pytest.mark.anyio
async def test_user_authorizes_with_valid_credentials(
    db_session: AsyncSession, dummy_user: User
):
    login_request = LoginRequest.model_validate(
        {"email": EMAIL, "password": VALID_PASSWORD}
    )

    auth_result = await authorize_user(db_session, login_request)
    auth_user = auth_result.user

    assert auth_user.id == dummy_user.id
    assert auth_user.created_at == dummy_user.created_at
    assert auth_user.email == dummy_user.email
    assert auth_user.is_active == dummy_user.is_active
    assert auth_result.access_token is not None


@pytest.mark.integration
@pytest.mark.anyio
async def test_user_authorizes_with_wrong_password(
    db_session: AsyncSession, dummy_user: User
):
    assert dummy_user.__class__ is User  # Validate that user exists

    login_request = LoginRequest.model_validate(
        {"email": EMAIL, "password": INVALID_PASSWORD}
    )

    with pytest.raises(InvalidCredentialsError):
        await authorize_user(db_session, login_request)


@pytest.mark.integration
@pytest.mark.anyio
async def test_user_authorizes_wrong_email(db_session: AsyncSession, dummy_user: User):
    assert dummy_user.__class__ is User  # Validate that user exists

    login_request = LoginRequest.model_validate(
        {"email": "missing_user@example.com", "password": VALID_PASSWORD}
    )

    with pytest.raises(InvalidCredentialsError):
        await authorize_user(db_session, login_request)


@pytest.mark.integration
@pytest.mark.anyio
async def test_user_authorizes_no_account(db_session: AsyncSession):
    db_users_counts = await db_session.scalar(select(func.count()).select_from(User))
    assert db_users_counts == 0

    login_request = LoginRequest.model_validate(
        {"email": EMAIL, "password": VALID_PASSWORD}
    )

    with pytest.raises(InvalidCredentialsError):
        await authorize_user(db_session, login_request)
