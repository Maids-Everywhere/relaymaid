from dataclasses import dataclass

from anyio import to_thread
from sqlalchemy.ext.asyncio import AsyncSession

from relaymaid.db.models import Membership, Organization, User
from relaymaid.domain import UserRole
from relaymaid.schemas import RegisterRequest
from relaymaid.security import hash_password


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    """Result of a registration operation.

    Attributes:
        user: The created ``User`` instance.
        organization: The created ``Organization`` instance.
        membership: The created ``Membership`` linking the user to the organization.
    """

    user: User
    organization: Organization
    membership: Membership


async def register_owner(
    session: AsyncSession, data: RegisterRequest
) -> RegistrationResult:
    """Register a new user and organization, assigning the user as owner.

    This creates and persists a new :class:`User`, a new :class:`Organization`,
    and a :class:`Membership` that assigns the user the ``UserRole.OWNER`` role.
    Objects are added to the provided ``AsyncSession`` and flushed so their
    primary keys are available before the membership is created.

    Args:
        session: SQLAlchemy :class:`AsyncSession` used to persist objects. The
            caller is responsible for committing or rolling back the transaction.
        data: :class:`RegisterRequest` containing ``email``, ``password``, and
            ``organization_name``.

    Returns:
        RegistrationResult: dataclass containing ``user``, ``organization``, and
        ``membership``.

    Raises:
        ValueError: If the email or organization name is already in use.
        SQLAlchemyError: May be propagated from session operations.
    """
    hashed_password = await to_thread.run_sync(
        hash_password, data.password.get_secret_value()
    )
    user = User(email=data.email, hashed_password=hashed_password)
    organization = Organization(name=data.organization_name)

    session.add_all([user, organization])
    await session.flush()

    membership = Membership(
        user_id=user.id, organization_id=organization.id, role=UserRole.OWNER
    )
    session.add(membership)
    await session.flush()

    return RegistrationResult(
        user=user, organization=organization, membership=membership
    )
