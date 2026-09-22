from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from relaymaid.db.dependencies import DatabaseSession
from relaymaid.db.models import User
from relaymaid.services.auth import decode_access_token
from relaymaid.services.exceptions import InvalidAccessTokenError

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    session: DatabaseSession,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing access token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise unauthorized

    try:
        user_id = await decode_access_token(access_token=credentials.credentials)
    except InvalidAccessTokenError as exc:
        raise unauthorized from exc

    user = await session.scalar(
        select(User).where(
            User.id == user_id,
            User.is_active.is_(True),
        )
    )

    if user is None:
        raise unauthorized

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
