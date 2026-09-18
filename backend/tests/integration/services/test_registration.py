from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import relaymaid.services.registration as registration_module
from relaymaid.db.models import Membership, Organization, User
from relaymaid.domain import UserRole
from relaymaid.schemas import RegisterRequest
from relaymaid.security import verify_password
from relaymaid.services import register_owner

EMAIL = "test@example.com"
PASSWORD = "testpassword123"
ORGANIZATION_NAME = "ACME"
REGISTER_REQUEST = RegisterRequest.model_validate(
    {"email": EMAIL, "password": PASSWORD, "organization_name": ORGANIZATION_NAME}
)


@pytest.mark.integration
@pytest.mark.anyio
async def test_register_owner_creates_related_records(db_session: AsyncSession):
    result = await register_owner(db_session, REGISTER_REQUEST)

    assert result.user.id is not None
    assert result.user.email == EMAIL
    assert result.user.is_active is True
    assert result.user.created_at is not None

    assert result.organization.id is not None
    assert result.organization.name == ORGANIZATION_NAME
    assert result.organization.created_at is not None

    assert result.membership.id is not None
    assert result.membership.user_id == result.user.id
    assert result.membership.organization_id == result.organization.id
    assert result.membership.role is UserRole.OWNER

    assert verify_password(
        PASSWORD,
        result.user.hashed_password,
    )


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
        role: UserRole,
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
            await register_owner(db_session, REGISTER_REQUEST)

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
