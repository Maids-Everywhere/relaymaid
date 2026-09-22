import pytest
from httpx import AsyncClient

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
async def test_register_user_via_api(client: AsyncClient) -> None:
    response = await client.post("/auth/register", json=JSON_NEW_USER)

    assert response.status_code == 201

    body = response.json()

    assert body["email"] == NEW_USER_EMAIL
    assert body["role"] == "owner"
    assert body["user_id"]
    assert body["organization_id"]
    assert body["membership_id"]


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
async def test_login_user_via_api(client: AsyncClient) -> None:
    register_response = await client.post("/auth/register", json=JSON_NEW_USER)
    assert register_response.status_code == 201

    login_json = {"email": NEW_USER_EMAIL, "password": NEW_USER_PASSWORD}
    login_response = await client.post("/auth/login", json=login_json)

    assert login_response.status_code == 200

    body = login_response.json()
    assert body["email"] == NEW_USER_EMAIL
    assert body["user_id"]
    assert body["access_token"]


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

    me_response = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )

    assert me_response.status_code == 200
    body = me_response.json()
    assert body["id"] == user_id
    assert body["email"] == NEW_USER_EMAIL


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
