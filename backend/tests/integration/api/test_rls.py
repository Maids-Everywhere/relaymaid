from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import relaymaid.services.registration as registration_module
from relaymaid.api.dependencies.auth import CurrentPrincipal
from relaymaid.api.dependencies.database import DatabaseSession
from relaymaid.config import get_settings
from relaymaid.db.models import Membership, Organization, User
from relaymaid.domain import MembershipRole
from relaymaid.main import create_app
from relaymaid.security.tokens import create_access_token

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
PASSWORD = "TestPassword12345"


@pytest.fixture
async def rls_probe_client(app_db_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.state.db_engine = app_db_engine
    app.state.db_session_factory = async_sessionmaker(
        app_db_engine, expire_on_commit=False
    )

    @app.get("/_test/rls")
    async def probe(
        principal: CurrentPrincipal, session: DatabaseSession
    ) -> dict[str, object]:
        # Omit WHERE clauses: isolation must come from PostgreSQL.
        organizations = list(await session.scalars(select(Organization.id)))
        memberships = list(await session.scalars(select(Membership.id)))
        return {
            "user_id": str(principal.user_id),
            "organizations": [str(value) for value in organizations],
            "memberships": [str(value) for value in memberships],
            "database_role": await session.scalar(text("SELECT current_user")),
        }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as probe_client:
        yield probe_client


async def test_requests_isolate_tenants_and_reject_foreign_organization_token(
    client: AsyncClient,
    rls_probe_client: AsyncClient,
    app_db_engine: AsyncEngine,
) -> None:
    registrations = []
    tokens = []
    for email in ("first@example.com", "second@example.com"):
        response = await client.post(
            "/auth/register",
            json={
                "email": email,
                "password": PASSWORD,
                "organization_name": email,
            },
        )
        assert response.status_code == 201
        registrations.append(response.json())
        response = await client.post(
            "/auth/login",
            json={
                "email": email,
                "password": PASSWORD,
            },
        )
        assert response.status_code == 200
        tokens.append(response.json()["access_token"])

    # Alternate tenants on the same one-connection pool, then return to A.
    for index in (0, 1, 0):
        headers = {"Authorization": f"Bearer {tokens[index]}"}
        response = await client.get("/auth/me", headers=headers)
        assert response.status_code == 200
        assert response.json()["user_id"] == registrations[index]["user_id"]
        response = await rls_probe_client.get("/_test/rls", headers=headers)
        assert response.status_code == 200
        assert response.json() == {
            "user_id": registrations[index]["user_id"],
            "organizations": [registrations[index]["organization_id"]],
            "memberships": [registrations[index]["membership_id"]],
            "database_role": "relaymaid_app",
        }

    settings = get_settings()
    token = create_access_token(
        user_id=UUID(registrations[0]["user_id"]),
        organization_id=UUID(registrations[1]["organization_id"]),
        role=MembershipRole.OWNER,
        secret=settings.jwt_secret_token,
        lifetime=settings.jwt_lifetime,
    )
    for path, request_client in (
        ("/auth/me", client),
        ("/_test/rls", rls_probe_client),
    ):
        response = await request_client.get(
            path, headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401

    # Successful requests and rejected authentication must release context.
    async with app_db_engine.connect() as connection:
        for setting in ("relaymaid.user_id", "relaymaid.organization_id"):
            assert (
                await connection.scalar(
                    text("SELECT NULLIF(current_setting(:setting, true), '')"),
                    {"setting": setting},
                )
                is None
            )
        assert list(await connection.scalars(select(Organization.id))) == []
        assert list(await connection.scalars(select(Membership.id))) == []


@pytest.mark.parametrize("context", ["user", "tenant"])
@pytest.mark.parametrize("failure", ["missing", "mismatched"])
async def test_registration_rls_failure_rolls_back_entire_request(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    context: str,
    failure: str,
) -> None:
    setter_name = f"set_{context}_context"
    original_setter = getattr(registration_module, setter_name)

    async def broken_context(session: AsyncSession, **kwargs: UUID) -> None:
        if failure == "mismatched":
            await original_setter(session, uuid4())

    payload = {
        "email": "rollback@example.com",
        "password": PASSWORD,
        "organization_name": "Must roll back",
    }
    with monkeypatch.context() as patch:
        patch.setattr(registration_module, setter_name, broken_context)
        # ASGITransport propagates the server exception for SQLSTATE inspection.
        with pytest.raises(DBAPIError, match="row-level security policy") as error:
            await client.post("/auth/register", json=payload)
        assert getattr(error.value.orig, "sqlstate", None) == "42501"

    async with session_factory() as session:
        for model in (User, Organization, Membership):
            assert await session.scalar(select(func.count()).select_from(model)) == 0

    # The same email and pooled connection remain usable after rollback.
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 201
