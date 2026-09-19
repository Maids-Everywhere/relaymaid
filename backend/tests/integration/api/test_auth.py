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
