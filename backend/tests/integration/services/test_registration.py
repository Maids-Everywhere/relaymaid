from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import relaymaid.services.registration as registration_module
from relaymaid.db.models import Membership, Organization, User
from relaymaid.domain import MembershipRole
from relaymaid.security.passwords import verify_password
from relaymaid.services.exceptions import EmailAlreadyExistsError
from relaymaid.services.registration import register_owner

EMAIL = "test@example.com"
PASSWORD = "testpassword123"
ORGANIZATION_NAME = "ACME"


@pytest.mark.integration
@pytest.mark.anyio
async def test_register_owner_creates_related_records(
    db_session: AsyncSession,
) -> None:
    result = await register_owner(
        db_session,
        email=EMAIL,
        password=PASSWORD,
        organization_name=ORGANIZATION_NAME,
    )

    user = await db_session.get(User, result.user_id)
    organization = await db_session.get(Organization, result.organization_id)
    membership = await db_session.get(Membership, result.membership_id)

    assert user is not None
    assert user.email == EMAIL
    assert user.is_active is True
    assert user.created_at is not None

    assert organization is not None
    assert organization.name == ORGANIZATION_NAME
    assert organization.created_at is not None

    assert membership is not None
    assert membership.user_id == user.id
    assert membership.organization_id == organization.id
    assert result.role is MembershipRole.OWNER

    assert verify_password(PASSWORD, user.hashed_password)


@pytest.mark.integration
@pytest.mark.anyio
async def test_register_owner_raises_when_email_already_exists(
    db_session: AsyncSession,
) -> None:
    registration_data = {
        "email": EMAIL,
        "password": PASSWORD,
        "organization_name": ORGANIZATION_NAME,
    }
    await register_owner(db_session, **registration_data)

    with pytest.raises(EmailAlreadyExistsError):
        await register_owner(db_session, **registration_data)


@pytest.mark.integration
@pytest.mark.anyio
async def test_registration_rolls_back_when_membership_fails(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def create_broken_membership(
        *,
        user_id: UUID,
        organization_id: UUID,
        role: MembershipRole,
    ) -> Membership:
        del user_id

        return Membership(
            user_id=uuid4(),
            organization_id=organization_id,
            role=role,
        )

    monkeypatch.setattr(
        registration_module,
        "Membership",
        create_broken_membership,
    )

    with pytest.raises(IntegrityError):
        async with db_session.begin():
            await register_owner(
                db_session,
                email=EMAIL,
                password=PASSWORD,
                organization_name=ORGANIZATION_NAME,
            )

    user_count = await db_session.scalar(
        select(func.count()).select_from(User).where(User.email == EMAIL)
    )
    organization_count = await db_session.scalar(
        select(func.count())
        .select_from(Organization)
        .where(Organization.name == ORGANIZATION_NAME)
    )
    membership_count = await db_session.scalar(
        select(func.count()).select_from(Membership)
    )

    assert user_count == 0
    assert organization_count == 0
    assert membership_count == 0
