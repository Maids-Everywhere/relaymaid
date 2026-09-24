from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from relaymaid.api.dependencies.database import DatabaseSession
from relaymaid.config import get_settings
from relaymaid.db.models import Membership, User
from relaymaid.domain import AuthenticatedPrincipal
from relaymaid.security.tokens import InvalidAccessTokenError, decode_access_token
from relaymaid.db.tenant_context import set_tenant_context, set_user_context

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_principal(
    session: DatabaseSession,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> AuthenticatedPrincipal:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing access token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise unauthorized

    try:
        claims = decode_access_token(
            access_token=credentials.credentials,
            secret=get_settings().jwt_secret_token,
        )
    except InvalidAccessTokenError as exc:
        raise unauthorized from exc

    await set_user_context(session=session, user_id=claims.user_id)

    await set_tenant_context(session=session, organization_id=claims.organization_id)

    principal_row = (
        await session.execute(
            select(User.email, Membership.role)
            .join(Membership, Membership.user_id == User.id)
            .where(
                User.id == claims.user_id,
                Membership.organization_id == claims.organization_id,
                User.is_active.is_(True),
            )
        )
    ).one_or_none()

    if principal_row is None:
        raise unauthorized

    return AuthenticatedPrincipal(
        user_id=claims.user_id,
        organization_id=claims.organization_id,
        email=principal_row.email,
        role=principal_row.role,
    )


CurrentPrincipal = Annotated[AuthenticatedPrincipal, Depends(get_current_principal)]
