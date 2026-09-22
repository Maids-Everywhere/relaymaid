from dataclasses import dataclass
from uuid import UUID

from relaymaid.domain.roles import MembershipRole


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    user_id: UUID
    organization_id: UUID
    email: str
    role: MembershipRole
