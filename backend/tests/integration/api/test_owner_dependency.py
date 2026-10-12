from collections.abc import AsyncIterator
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from relaymaid.api.dependencies.auth import OwnerPrincipal
from relaymaid.config import get_settings
from relaymaid.db.models import Membership, User
from relaymaid.domain import MembershipRole
from relaymaid.main import create_app
from relaymaid.security.tokens import create_access_token

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
async def owner_client(app_db_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.state.db_engine = app_db_engine
    app.state.db_session_factory = async_sessionmaker(
        app_db_engine, expire_on_commit=False
    )

    @app.get("/_test/owner")
    async def owner_only(principal: OwnerPrincipal) -> dict[str, str]:
        return {
            "user_id": str(principal.user_id),
            "organization_id": str(principal.organization_id),
            "role": principal.role.value,
        }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as request_client:
        yield request_client


@pytest.mark.parametrize("token", [None, "invalid-token"])
async def test_owner_endpoint_requires_authentication(
    owner_client: AsyncClient, token: str | None
) -> None:
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    response = await owner_client.get("/_test/owner", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "Invalid or missing access token"}


@pytest.mark.parametrize("token_role", list(MembershipRole))
@pytest.mark.parametrize("current_role", list(MembershipRole))
async def test_owner_endpoint_uses_current_membership_role(
    client: AsyncClient,
    owner_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    token_role: MembershipRole,
    current_role: MembershipRole,
) -> None:
    credentials = {"email": "owner-test@example.com", "password": "TestPassword12345"}
    response = await client.post(
        "/auth/register", json={**credentials, "organization_name": "Owner test"}
    )
    assert response.status_code == 201
    registration = response.json()
    membership_id = UUID(registration["membership_id"])
    async with session_factory.begin() as session:
        await session.execute(
            update(Membership)
            .where(Membership.id == membership_id)
            .values(role=token_role)
        )
    response = await client.post("/auth/login", json=credentials)
    assert response.status_code == 200
    token = response.json()["access_token"]

    # Change the database role after login to exercise stale JWT role claims.
    async with session_factory.begin() as session:
        await session.execute(
            update(Membership)
            .where(Membership.id == membership_id)
            .values(role=current_role)
        )
    response = await owner_client.get(
        "/_test/owner", headers={"Authorization": f"Bearer {token}"}
    )
    if current_role is MembershipRole.OWNER:
        assert response.status_code == 200
        assert response.json() == {
            "user_id": registration["user_id"],
            "organization_id": registration["organization_id"],
            "role": "owner",
        }
    else:
        assert response.status_code == 403
        assert response.json() == {
            "detail": "You do not have permission to perform this action"
        }


@pytest.mark.parametrize(
    "failure",
    [
        "expired_token",
        "wrong_signature",
        "unknown_user",
        "unknown_organization",
        "foreign_organization",
        "inactive_user",
        "removed_membership",
    ],
)
async def test_owner_endpoint_rejects_invalid_or_revoked_access(
    client: AsyncClient,
    owner_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    failure: str,
) -> None:
    credentials = {
        "email": "negative-owner@example.com",
        "password": "TestPassword12345",
    }
    response = await client.post(
        "/auth/register", json={**credentials, "organization_name": "Negative test"}
    )
    assert response.status_code == 201
    registration = response.json()
    response = await client.post("/auth/login", json=credentials)
    assert response.status_code == 200
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert (await owner_client.get("/_test/owner", headers=headers)).status_code == 200

    user_id = UUID(registration["user_id"])
    organization_id = UUID(registration["organization_id"])
    if failure == "inactive_user":
        async with session_factory.begin() as session:
            await session.execute(
                update(User).where(User.id == user_id).values(is_active=False)
            )
    elif failure == "removed_membership":
        async with session_factory.begin() as session:
            await session.execute(
                delete(Membership).where(
                    Membership.id == UUID(registration["membership_id"])
                )
            )
    else:
        if failure == "foreign_organization":
            response = await client.post(
                "/auth/register",
                json={
                    "email": "other-owner@example.com",
                    "password": "TestPassword12345",
                    "organization_name": "Other tenant",
                },
            )
            assert response.status_code == 201
            organization_id = UUID(response.json()["organization_id"])
        elif failure == "unknown_organization":
            organization_id = uuid4()
        elif failure == "unknown_user":
            user_id = uuid4()
        settings = get_settings()
        token = create_access_token(
            user_id=user_id,
            organization_id=organization_id,
            role=MembershipRole.OWNER,
            secret=(
                settings.jwt_secret_token + "-incorrect"
                if failure == "wrong_signature"
                else settings.jwt_secret_token
            ),
            lifetime=(
                timedelta(minutes=-1)
                if failure == "expired_token"
                else settings.jwt_lifetime
            ),
        )
        headers = {"Authorization": f"Bearer {token}"}

    response = await owner_client.get("/_test/owner", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "Invalid or missing access token"}
