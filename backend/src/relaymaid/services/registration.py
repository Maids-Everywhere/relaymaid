from dataclasses import dataclass
from uuid import UUID, uuid4

from anyio import to_thread
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from relaymaid.db.models import Membership, Organization, User
from relaymaid.domain import MembershipRole
from relaymaid.security.passwords import hash_password
from relaymaid.services.exceptions import EmailAlreadyExistsError
from relaymaid.db.tenant_context import set_user_context, set_tenant_context


def get_constraint_name(exc: IntegrityError) -> str | None:
    diagnostic = getattr(exc.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None)


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    user_id: UUID
    organization_id: UUID
    membership_id: UUID
    email: str
    role: MembershipRole


async def register_owner(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    organization_name: str,
) -> RegistrationResult:
    """Register an organization and its first owner in the current transaction."""
    hashed_password = await to_thread.run_sync(hash_password, password)
    user_uuid = uuid4()
    organization_uuid = uuid4()
    user = User(id=user_uuid, email=email, hashed_password=hashed_password)
    organization = Organization(id=organization_uuid, name=organization_name)

    await set_user_context(session=session, user_id=user_uuid)
    await set_tenant_context(session=session, organization_id=organization_uuid)

    session.add_all([user, organization])
    try:
        await session.flush()
    except IntegrityError as exc:
        if get_constraint_name(exc) == "uq_users_email":
            raise EmailAlreadyExistsError from exc
        raise

    membership = Membership(
        user_id=user.id,
        organization_id=organization.id,
        role=MembershipRole.OWNER,
    )
    session.add(membership)
    await session.flush()

    return RegistrationResult(
        user_id=user.id,
        organization_id=organization.id,
        membership_id=membership.id,
        email=user.email,
        role=membership.role,
    )
