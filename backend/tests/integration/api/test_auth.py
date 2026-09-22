from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import relaymaid.services.registration as registration_module
from relaymaid.db.models import Membership, Organization, User
from relaymaid.domain import MembershipRole

NEW_USER_EMAIL = "test@example.com"
NEW_USER_PASSWORD = "qwerty12345Test"
NEW_USER_ORGANIZATION_NAME = "ACME"

JSON_NEW_USER = {
    "email": NEW_USER_EMAIL,
    "password": NEW_USER_PASSWORD,
    "organization_name": NEW_USER_ORGANIZATION_NAME,
}


@pytest.mark.integration
@pytest.mark.anyio
async def test_register_user_via_api(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    response = await client.post("/auth/register", json=JSON_NEW_USER)

    assert response.status_code == 201

    body = response.json()

    assert body["email"] == NEW_USER_EMAIL
    assert body["role"] == "owner"
    assert body["user_id"]
    assert body["organization_id"]
    assert body["membership_id"]

    async with session_factory() as session:
        user = await session.get(User, UUID(body["user_id"]))
        organization = await session.get(Organization, UUID(body["organization_id"]))
        membership = await session.get(Membership, UUID(body["membership_id"]))

    assert user is not None
    assert organization is not None
    assert membership is not None


@pytest.mark.integration
@pytest.mark.anyio
async def test_register_returns_409_when_email_already_exists(
    client: AsyncClient,
) -> None:
    first_response = await client.post("/auth/register", json=JSON_NEW_USER)
    second_response = await client.post("/auth/register", json=JSON_NEW_USER)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json() == {"detail": "A user with this email already exists"}


@pytest.mark.integration
@pytest.mark.anyio
async def test_register_rolls_back_all_records_when_membership_fails(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
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
        await client.post("/auth/register", json=JSON_NEW_USER)

    async with session_factory() as session:
        user_count = await session.scalar(select(func.count()).select_from(User))
        organization_count = await session.scalar(
            select(func.count()).select_from(Organization)
        )
        membership_count = await session.scalar(
            select(func.count()).select_from(Membership)
        )

    assert user_count == 0
    assert organization_count == 0
    assert membership_count == 0


@pytest.mark.integration
@pytest.mark.anyio
async def test_login_user_via_api(client: AsyncClient) -> None:
    register_response = await client.post("/auth/register", json=JSON_NEW_USER)
    assert register_response.status_code == 201
    organization_id = register_response.json()["organization_id"]

    login_json = {"email": NEW_USER_EMAIL, "password": NEW_USER_PASSWORD}
    login_response = await client.post("/auth/login", json=login_json)

    assert login_response.status_code == 200

    body = login_response.json()
    assert body["email"] == NEW_USER_EMAIL
    assert body["user_id"]
    assert body["organization_id"] == organization_id
    assert body["role"] == "owner"
    assert body["access_token"]


@pytest.mark.integration
@pytest.mark.anyio
async def test_login_rejects_organization_until_selection_is_supported(
    client: AsyncClient,
) -> None:
    register_response = await client.post("/auth/register", json=JSON_NEW_USER)
    assert register_response.status_code == 201

    login_response = await client.post(
        "/auth/login",
        json={
            "email": NEW_USER_EMAIL,
            "password": NEW_USER_PASSWORD,
            "organization_id": str(uuid4()),
        },
    )

    assert login_response.status_code == 422


@pytest.mark.integration
@pytest.mark.anyio
async def test_get_me_returns_current_user(client: AsyncClient) -> None:
    register_response = await client.post("/auth/register", json=JSON_NEW_USER)
    assert register_response.status_code == 201

    login_response = await client.post(
        "/auth/login",
        json={"email": NEW_USER_EMAIL, "password": NEW_USER_PASSWORD},
    )
    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]
    user_id = login_response.json()["user_id"]
    organization_id = login_response.json()["organization_id"]

    me_response = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )

    assert me_response.status_code == 200
    body = me_response.json()
    assert body["user_id"] == user_id
    assert body["organization_id"] == organization_id
    assert body["email"] == NEW_USER_EMAIL
    assert body["role"] == "owner"


@pytest.mark.integration
@pytest.mark.anyio
async def test_get_me_uses_current_membership_role(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    register_response = await client.post("/auth/register", json=JSON_NEW_USER)
    membership_id = UUID(register_response.json()["membership_id"])
    login_response = await client.post(
        "/auth/login",
        json={"email": NEW_USER_EMAIL, "password": NEW_USER_PASSWORD},
    )
    access_token = login_response.json()["access_token"]

    async with session_factory.begin() as session:
        membership = await session.get(Membership, membership_id)
        assert membership is not None
        membership.role = MembershipRole.VIEWER

    response = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "viewer"


@pytest.mark.integration
@pytest.mark.anyio
async def test_get_me_returns_401_without_token(client: AsyncClient) -> None:
    me_response = await client.get("/auth/me")

    assert me_response.status_code == 401


@pytest.mark.integration
@pytest.mark.anyio
async def test_get_me_returns_401_with_invalid_token(client: AsyncClient) -> None:
    me_response = await client.get(
        "/auth/me", headers={"Authorization": "Bearer invalid-token"}
    )

    assert me_response.status_code == 401


@pytest.mark.integration
@pytest.mark.anyio
async def test_get_me_returns_401_with_expired_token(client: AsyncClient) -> None:
    from datetime import UTC, datetime, timedelta

    import jwt

    from relaymaid.config import get_settings

    secret = get_settings().jwt_secret_token
    expired_payload = {
        "sub": "550e8400-e29b-41d4-a716-446655440000",
        "iat": int((datetime.now(UTC) - timedelta(minutes=30)).timestamp()),
        "exp": int((datetime.now(UTC) - timedelta(minutes=1)).timestamp()),
    }
    expired_token = jwt.encode(expired_payload, secret, algorithm="HS256")

    me_response = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {expired_token}"}
    )

    assert me_response.status_code == 401
