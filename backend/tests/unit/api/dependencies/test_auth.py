from datetime import timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

import relaymaid.api.dependencies.auth as auth_module
from relaymaid.api.dependencies.auth import require_owner
from relaymaid.domain import AuthenticatedPrincipal, MembershipRole
from relaymaid.security.tokens import create_access_token

pytestmark = pytest.mark.anyio


async def test_require_owner_returns_same_principal() -> None:
    principal = AuthenticatedPrincipal(
        user_id=uuid4(),
        organization_id=uuid4(),
        email="owner@example.com",
        role=MembershipRole.OWNER,
    )
    assert await require_owner(principal) is principal


async def test_require_owner_rejects_viewer() -> None:
    principal = AuthenticatedPrincipal(
        user_id=uuid4(),
        organization_id=uuid4(),
        email="viewer@example.com",
        role=MembershipRole.VIEWER,
    )
    with pytest.raises(HTTPException) as error:
        await require_owner(principal)
    assert error.value.status_code == 403
    assert error.value.detail == "You do not have permission to perform this action"


@pytest.mark.parametrize("role", [None, "", "admin", "OWNER", "owner "])
async def test_require_owner_fails_closed_for_unexpected_roles(role: object) -> None:
    principal = AuthenticatedPrincipal(
        user_id=uuid4(),
        organization_id=uuid4(),
        email="invalid@example.com",
        role=cast(MembershipRole, role),
    )
    with pytest.raises(HTTPException) as error:
        await require_owner(principal)
    assert error.value.status_code == 403
    assert error.value.detail == "You do not have permission to perform this action"


@pytest.fixture
def auth_session(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(
        auth_module,
        "get_settings",
        lambda: SimpleNamespace(jwt_secret_token="unit-test-secret-for-authentication"),
    )
    monkeypatch.setattr(auth_module, "set_user_context", AsyncMock())
    monkeypatch.setattr(auth_module, "set_tenant_context", AsyncMock())
    return session


def credentials(
    *, expired: bool = False, wrong_secret: bool = False
) -> HTTPAuthorizationCredentials:
    token = create_access_token(
        user_id=uuid4(),
        organization_id=uuid4(),
        role=MembershipRole.OWNER,
        secret=(
            "incorrect-unit-test-signing-secret"
            if wrong_secret
            else "unit-test-secret-for-authentication"
        ),
        lifetime=timedelta(minutes=-1 if expired else 5),
    )
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.mark.parametrize(
    "failure", ["missing", "malformed", "expired", "wrong_signature"]
)
async def test_authentication_rejects_bad_credentials_before_database_access(
    auth_session: MagicMock,
    failure: str,
) -> None:
    supplied = None
    if failure == "malformed":
        supplied = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid")
    elif failure != "missing":
        supplied = credentials(
            expired=failure == "expired", wrong_secret=failure == "wrong_signature"
        )
    with pytest.raises(HTTPException) as error:
        await auth_module.get_current_principal(auth_session, supplied)
    assert error.value.status_code == 401
    assert error.value.detail == "Invalid or missing access token"
    assert error.value.headers == {"WWW-Authenticate": "Bearer"}
    auth_session.execute.assert_not_awaited()
    auth_module.set_user_context.assert_not_awaited()
    auth_module.set_tenant_context.assert_not_awaited()


async def test_authentication_rejects_when_no_active_membership_matches(
    auth_session: MagicMock,
) -> None:
    auth_session.execute.return_value.one_or_none.return_value = None
    with pytest.raises(HTTPException) as error:
        await auth_module.get_current_principal(auth_session, credentials())
    assert error.value.status_code == 401
    assert error.value.detail == "Invalid or missing access token"
    assert error.value.headers == {"WWW-Authenticate": "Bearer"}
    auth_session.execute.assert_awaited_once()


async def test_owner_claim_cannot_override_viewer_database_role(
    auth_session: MagicMock,
) -> None:
    auth_session.execute.return_value.one_or_none.return_value = SimpleNamespace(
        email="viewer@example.com",
        role=MembershipRole.VIEWER,
    )
    principal = await auth_module.get_current_principal(auth_session, credentials())
    with pytest.raises(HTTPException) as error:
        await require_owner(principal)
    assert principal.role is MembershipRole.VIEWER
    assert error.value.status_code == 403


@pytest.mark.parametrize(
    "failure_stage", ["set_user_context", "set_tenant_context", "query"]
)
async def test_authentication_does_not_swallow_database_errors(
    auth_session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    failure = RuntimeError("database unavailable")
    if failure_stage == "query":
        auth_session.execute.side_effect = failure
    else:
        monkeypatch.setattr(auth_module, failure_stage, AsyncMock(side_effect=failure))
    with pytest.raises(RuntimeError, match="database unavailable") as error:
        await auth_module.get_current_principal(auth_session, credentials())
    assert error.value is failure
    if failure_stage != "query":
        auth_session.execute.assert_not_awaited()
