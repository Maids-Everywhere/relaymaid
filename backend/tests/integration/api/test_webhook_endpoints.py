from datetime import datetime
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import relaymaid.api.routes.webhook_endpoints as route_module
from relaymaid.db.models import Membership
from relaymaid.db.models.webhook import WebhookEndpoint
from relaymaid.domain import MembershipRole
from relaymaid.security.webhook_secrets import WebhookSecretManager
from relaymaid.services.exceptions import WebhookEndpointNotFoundError

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
PAYLOAD = {"name": "  Orders  ", "destination_url": "https://example.com/events"}


async def register_owner(client: AsyncClient, email: str) -> dict[str, str]:
    credentials = {"email": email, "password": "TestPassword12345"}
    response = await client.post(
        "/auth/register", json={**credentials, "organization_name": "Test"}
    )
    assert response.status_code == 201
    registration = response.json()
    response = await client.post("/auth/login", json=credentials)
    assert response.status_code == 200
    return {**registration, "token": response.json()["access_token"]}


@pytest.fixture
async def owner(client: AsyncClient) -> dict[str, str]:
    return await register_owner(client, "webhook-owner@example.com")


def authorization(owner: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {owner['token']}"}


async def assert_no_endpoints(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session:
        assert (
            await session.scalar(select(func.count()).select_from(WebhookEndpoint)) == 0
        )


@pytest.mark.parametrize("retry_limit", [None, 0, 10])
async def test_create_endpoint_returns_secret_and_persists_encrypted_record(
    client: AsyncClient,
    owner: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
    webhook_secret_manager: WebhookSecretManager,
    retry_limit: int | None,
) -> None:
    payload = dict(PAYLOAD)
    if retry_limit is not None:
        payload["retry_limit"] = retry_limit
    response = await client.post(
        "/webhook-endpoints", json=payload, headers=authorization(owner)
    )
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {
        "id",
        "public_id",
        "name",
        "destination_url",
        "enabled",
        "retry_limit",
        "created_at",
        "secret",
    }
    assert body["name"] == "Orders"
    assert body["destination_url"] == PAYLOAD["destination_url"]
    assert body["enabled"] is True
    assert body["retry_limit"] == (3 if retry_limit is None else retry_limit)
    assert datetime.fromisoformat(body["created_at"]).tzinfo is not None
    assert len(body["secret"]) == 43
    async with session_factory() as session:
        endpoint = await session.get(WebhookEndpoint, UUID(body["id"]))
        assert endpoint is not None
        assert endpoint.public_id == UUID(body["public_id"])
        assert endpoint.organization_id == UUID(owner["organization_id"])
        assert endpoint.name == body["name"]
        assert endpoint.retry_limit == body["retry_limit"]
        assert endpoint.secret_ciphertext != body["secret"]
        assert (
            webhook_secret_manager.decrypt(endpoint.secret_ciphertext) == body["secret"]
        )


@pytest.mark.parametrize("token", [None, "invalid-token"])
async def test_create_requires_authentication(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    token: str | None,
) -> None:
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    response = await client.post("/webhook-endpoints", json=PAYLOAD, headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    await assert_no_endpoints(session_factory)


async def test_viewer_cannot_create_even_with_old_owner_token(
    client: AsyncClient,
    owner: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory.begin() as session:
        await session.execute(
            update(Membership)
            .where(Membership.id == UUID(owner["membership_id"]))
            .values(role=MembershipRole.VIEWER)
        )
    response = await client.post(
        "/webhook-endpoints", json=PAYLOAD, headers=authorization(owner)
    )
    assert response.status_code == 403
    assert response.json() == {
        "detail": "You do not have permission to perform this action"
    }
    await assert_no_endpoints(session_factory)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", ""),
        ("name", " \t"),
        ("name", "a" * 256),
        ("destination_url", "not-a-url"),
        ("destination_url", "ftp://example.com"),
        ("retry_limit", -1),
        ("retry_limit", 11),
        ("retry_limit", 1.5),
        ("organization_id", "00000000-0000-0000-0000-000000000001"),
        ("secret", "client-chosen-secret"),
        ("enabled", False),
    ],
)
async def test_invalid_payload_is_rejected_without_writes(
    client: AsyncClient,
    owner: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
    field: str,
    value: object,
) -> None:
    response = await client.post(
        "/webhook-endpoints",
        json={**PAYLOAD, field: value},
        headers=authorization(owner),
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", field]
    await assert_no_endpoints(session_factory)


@pytest.mark.parametrize("field", ["name", "destination_url"])
async def test_missing_required_field_is_rejected(
    client: AsyncClient,
    owner: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
    field: str,
) -> None:
    response = await client.post(
        "/webhook-endpoints",
        headers=authorization(owner),
        json={key: value for key, value in PAYLOAD.items() if key != field},
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "missing"
    await assert_no_endpoints(session_factory)


async def test_requests_assign_endpoints_to_authenticated_tenant(
    client: AsyncClient,
    owner: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    other = await register_owner(client, "other-webhook-owner@example.com")
    responses = []
    for principal in (owner, other, owner):
        response = await client.post(
            "/webhook-endpoints", json=PAYLOAD, headers=authorization(principal)
        )
        assert response.status_code == 201
        body = response.json()
        responses.append(body)
        async with session_factory() as session:
            endpoint = await session.get(WebhookEndpoint, UUID(body["id"]))
            assert endpoint.organization_id == UUID(principal["organization_id"])
    for field in ("id", "public_id", "secret"):
        assert len({body[field] for body in responses}) == 3


async def test_rls_rejects_foreign_tenant_write_and_rolls_back_request(
    client: AsyncClient,
    owner: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = await register_owner(client, "foreign-webhook-owner@example.com")
    original = route_module.create_webhook_endpoint

    async def wrong_tenant(**kwargs):
        kwargs["organization_id"] = UUID(other["organization_id"])
        return await original(**kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(route_module, "create_webhook_endpoint", wrong_tenant)
        with pytest.raises(DBAPIError, match="row-level security policy") as error:
            await client.post(
                "/webhook-endpoints", json=PAYLOAD, headers=authorization(owner)
            )
        assert getattr(error.value.orig, "sqlstate", None) == "42501"
    await assert_no_endpoints(session_factory)
    response = await client.post(
        "/webhook-endpoints", json=PAYLOAD, headers=authorization(owner)
    )
    assert response.status_code == 201


async def test_list_empty_endpoints_uses_default_pagination(
    client: AsyncClient, owner: dict[str, str]
) -> None:
    response = await client.get("/webhook-endpoints", headers=authorization(owner))
    assert response.status_code == 200
    assert response.json() == {"items": [], "limit": 10, "offset": 0, "has_more": False}


async def test_list_paginates_in_stable_order_and_excludes_other_tenants_and_secrets(
    client: AsyncClient,
    owner: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    other = await register_owner(client, "list-other-owner@example.com")
    endpoints = []
    for principal in (owner, other, owner, owner):
        response = await client.post(
            "/webhook-endpoints", json=PAYLOAD, headers=authorization(principal)
        )
        assert response.status_code == 201
        if principal == owner:
            endpoints.append(response.json())
    # Equal timestamps exercise the UUID tie-breaker in the database query.
    async with session_factory.begin() as session:
        await session.execute(
            update(WebhookEndpoint)
            .where(WebhookEndpoint.organization_id == UUID(owner["organization_id"]))
            .values(created_at=datetime.fromisoformat(endpoints[0]["created_at"]))
        )
    expected = sorted(endpoints, key=lambda item: UUID(item["id"]), reverse=True)
    for offset, has_more in ((0, True), (2, False), (3, False)):
        response = await client.get(
            "/webhook-endpoints",
            params={"limit": 2, "offset": offset},
            headers=authorization(owner),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["limit"] == 2
        assert body["offset"] == offset
        assert body["has_more"] is has_more
        assert [item["id"] for item in body["items"]] == [
            item["id"] for item in expected[offset : offset + 2]
        ]
        for item in body["items"]:
            assert set(item) == {
                "id",
                "public_id",
                "name",
                "destination_url",
                "enabled",
                "retry_limit",
                "created_at",
            }
            assert item["name"] == "Orders"
            assert item["destination_url"] == PAYLOAD["destination_url"]


@pytest.mark.parametrize("token", [None, "invalid-token"])
async def test_list_requires_authentication(
    client: AsyncClient, token: str | None
) -> None:
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    response = await client.get("/webhook-endpoints", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_viewer_can_list_own_tenant_endpoints_with_existing_token(
    client: AsyncClient,
    owner: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    other = await register_owner(client, "viewer-other-owner@example.com")
    created = []
    for principal in (owner, other):
        response = await client.post(
            "/webhook-endpoints", json=PAYLOAD, headers=authorization(principal)
        )
        assert response.status_code == 201
        created.append(response.json())
    async with session_factory.begin() as session:
        await session.execute(
            update(Membership)
            .where(Membership.id == UUID(owner["membership_id"]))
            .values(role=MembershipRole.VIEWER)
        )
    response = await client.get("/webhook-endpoints", headers=authorization(owner))
    assert response.status_code == 200
    expected = {key: value for key, value in created[0].items() if key != "secret"}
    assert response.json() == {
        "items": [expected],
        "limit": 10,
        "offset": 0,
        "has_more": False,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("limit", "0"),
        ("limit", "101"),
        ("limit", "1.5"),
        ("limit", "invalid"),
        ("offset", "-1"),
        ("offset", "1.5"),
        ("offset", "invalid"),
    ],
)
async def test_list_rejects_invalid_pagination(
    client: AsyncClient,
    owner: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
) -> None:
    from unittest.mock import AsyncMock

    service = AsyncMock()
    monkeypatch.setattr(route_module, "list_webhook_endpoints", service)
    response = await client.get(
        "/webhook-endpoints", params={field: value}, headers=authorization(owner)
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", field]
    service.assert_not_awaited()


@pytest.mark.parametrize("limit", [1, 100])
async def test_list_accepts_pagination_boundaries(
    client: AsyncClient, owner: dict[str, str], limit: int
) -> None:
    response = await client.get(
        "/webhook-endpoints",
        params={"limit": limit, "offset": 0},
        headers=authorization(owner),
    )
    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "limit": limit,
        "offset": 0,
        "has_more": False,
    }


@pytest.mark.parametrize("role", [MembershipRole.OWNER, MembershipRole.VIEWER])
async def test_get_endpoint_by_internal_id_returns_public_fields(
    client: AsyncClient,
    owner: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
    role: MembershipRole,
) -> None:
    response = await client.post(
        "/webhook-endpoints", json=PAYLOAD, headers=authorization(owner)
    )
    assert response.status_code == 201
    created = response.json()
    async with session_factory.begin() as session:
        await session.execute(
            update(Membership)
            .where(Membership.id == UUID(owner["membership_id"]))
            .values(role=role)
        )
        await session.execute(
            update(WebhookEndpoint)
            .where(WebhookEndpoint.id == UUID(created["id"]))
            .values(enabled=False, retry_limit=0)
        )
    response = await client.get(
        f"/webhook-endpoints/{created['id']}", headers=authorization(owner)
    )
    assert response.status_code == 200
    expected = {key: value for key, value in created.items() if key != "secret"}
    expected.update(enabled=False, retry_limit=0)
    assert response.json() == expected


@pytest.mark.parametrize("token", [None, "invalid-token"])
async def test_get_endpoint_requires_authentication(
    client: AsyncClient, token: str | None
) -> None:
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    response = await client.get(f"/webhook-endpoints/{uuid4()}", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("endpoint_id", ["not-a-uuid", "123", "null"])
async def test_get_endpoint_rejects_invalid_endpoint_id_before_lookup(
    client: AsyncClient,
    owner: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    endpoint_id: str,
) -> None:
    from unittest.mock import AsyncMock

    service = AsyncMock()
    monkeypatch.setattr(route_module, "get_webhook_endpoint_by_id", service)
    response = await client.get(
        f"/webhook-endpoints/{endpoint_id}", headers=authorization(owner)
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["path", "endpoint_id"]
    service.assert_not_awaited()


@pytest.mark.parametrize("lookup", ["missing", "public_id", "foreign_tenant"])
async def test_get_endpoint_returns_404_for_unavailable_endpoint_id(
    client: AsyncClient,
    owner: dict[str, str],
    lookup: str,
) -> None:
    endpoint_id = str(uuid4())
    if lookup != "missing":
        principal = owner
        if lookup == "foreign_tenant":
            principal = await register_owner(client, "lookup-other-owner@example.com")
        response = await client.post(
            "/webhook-endpoints", json=PAYLOAD, headers=authorization(principal)
        )
        assert response.status_code == 201
        field = "public_id" if lookup == "public_id" else "id"
        endpoint_id = response.json()[field]
    response = await client.get(
        f"/webhook-endpoints/{endpoint_id}", headers=authorization(owner)
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Webhook endpoint not found."}
    # A failed lookup must leave the next authenticated request usable.
    response = await client.get("/webhook-endpoints", headers=authorization(owner))
    assert response.status_code == 200


async def test_get_endpoint_propagates_unexpected_service_errors(
    client: AsyncClient,
    owner: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import AsyncMock

    endpoint_id = uuid4()
    failure = RuntimeError("database unavailable")
    service = AsyncMock(side_effect=failure)
    monkeypatch.setattr(route_module, "get_webhook_endpoint_by_id", service)
    with pytest.raises(RuntimeError, match="database unavailable") as error:
        await client.get(
            f"/webhook-endpoints/{endpoint_id}", headers=authorization(owner)
        )
    assert error.value is failure
    service.assert_awaited_once()
    assert service.await_args.kwargs["endpoint_id"] == endpoint_id
    assert service.await_args.kwargs["organization_id"] == UUID(
        owner["organization_id"]
    )


@pytest.mark.parametrize("message", [None, "Internal tenant and database details"])
async def test_get_endpoint_returns_fixed_404_detail(
    client: AsyncClient,
    owner: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    message: str | None,
) -> None:
    from unittest.mock import AsyncMock

    failure = (
        WebhookEndpointNotFoundError()
        if message is None
        else WebhookEndpointNotFoundError(message)
    )
    service = AsyncMock(side_effect=failure)
    monkeypatch.setattr(route_module, "get_webhook_endpoint_by_id", service)
    endpoint_id = uuid4()
    response = await client.get(
        f"/webhook-endpoints/{endpoint_id}", headers=authorization(owner)
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Webhook endpoint not found."}
    service.assert_awaited_once()
    assert service.await_args.kwargs["endpoint_id"] == endpoint_id
    assert service.await_args.kwargs["organization_id"] == UUID(
        owner["organization_id"]
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "  Updated  "},
        {"destination_url": "https://example.com/new"},
        {"retry_limit": 0},
        {"enabled": False},
        {
            "name": "Updated",
            "destination_url": "https://example.com/new",
            "retry_limit": 10,
            "enabled": False,
        },
    ],
)
async def test_patch_persists_only_supplied_fields_and_preserves_secret(
    client: AsyncClient,
    owner: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
    changes,
) -> None:
    response = await client.post(
        "/webhook-endpoints", json=PAYLOAD, headers=authorization(owner)
    )
    assert response.status_code == 201
    created = response.json()
    endpoint_id = UUID(created["id"])
    async with session_factory() as session:
        original = await session.get(WebhookEndpoint, endpoint_id)
        ciphertext = original.secret_ciphertext
    expected = {key: value for key, value in created.items() if key != "secret"}
    expected.update(changes)
    expected["name"] = expected["name"].strip()
    response = await client.patch(
        f"/webhook-endpoints/{endpoint_id}", json=changes, headers=authorization(owner)
    )
    assert response.status_code == 200
    assert response.json() == expected
    response = await client.get(
        f"/webhook-endpoints/{endpoint_id}", headers=authorization(owner)
    )
    assert response.status_code == 200
    assert response.json() == expected
    async with session_factory() as session:
        persisted = await session.get(WebhookEndpoint, endpoint_id)
        assert persisted.secret_ciphertext == ciphertext
        assert persisted.organization_id == UUID(owner["organization_id"])


@pytest.mark.parametrize("token", [None, "invalid-token"])
async def test_patch_requires_authentication(
    client: AsyncClient, token: str | None
) -> None:
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    response = await client.patch(
        f"/webhook-endpoints/{uuid4()}", json={"name": "Updated"}, headers=headers
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_viewer_cannot_patch_existing_endpoint(
    client: AsyncClient,
    owner: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    response = await client.post(
        "/webhook-endpoints", json=PAYLOAD, headers=authorization(owner)
    )
    assert response.status_code == 201
    created = response.json()
    async with session_factory.begin() as session:
        await session.execute(
            update(Membership)
            .where(Membership.id == UUID(owner["membership_id"]))
            .values(role=MembershipRole.VIEWER)
        )
    response = await client.patch(
        f"/webhook-endpoints/{created['id']}",
        json={"name": "Updated"},
        headers=authorization(owner),
    )
    assert response.status_code == 403
    async with session_factory() as session:
        endpoint = await session.get(WebhookEndpoint, UUID(created["id"]))
        assert endpoint.name == created["name"]


@pytest.mark.parametrize("lookup", ["missing", "public_id", "foreign_tenant"])
async def test_patch_returns_404_without_changing_unavailable_endpoint(
    client: AsyncClient,
    owner: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
    lookup: str,
) -> None:
    endpoint_id = str(uuid4())
    created = None
    if lookup != "missing":
        principal = (
            owner
            if lookup == "public_id"
            else await register_owner(client, "patch-other-owner@example.com")
        )
        response = await client.post(
            "/webhook-endpoints", json=PAYLOAD, headers=authorization(principal)
        )
        assert response.status_code == 201
        created = response.json()
        endpoint_id = created["public_id" if lookup == "public_id" else "id"]
    response = await client.patch(
        f"/webhook-endpoints/{endpoint_id}",
        json={"name": "Updated"},
        headers=authorization(owner),
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Webhook endpoint not found."}
    if created:
        async with session_factory() as session:
            endpoint = await session.get(WebhookEndpoint, UUID(created["id"]))
            assert endpoint.name == created["name"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": None},
        {"destination_url": None},
        {"retry_limit": None},
        {"enabled": None},
        {"name": " "},
        {"destination_url": "invalid"},
        {"retry_limit": -1},
        {"retry_limit": 11},
        {"secret": "chosen"},
    ],
)
async def test_patch_rejects_invalid_payload_before_update(
    client: AsyncClient,
    owner: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    payload,
) -> None:
    from unittest.mock import AsyncMock

    service = AsyncMock()
    monkeypatch.setattr(route_module, "update_webhook_endpoint_by_id", service)
    response = await client.patch(
        f"/webhook-endpoints/{uuid4()}", json=payload, headers=authorization(owner)
    )
    assert response.status_code == 422
    service.assert_not_awaited()


async def test_patch_rejects_invalid_endpoint_id_before_update(
    client: AsyncClient,
    owner: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import AsyncMock

    service = AsyncMock()
    monkeypatch.setattr(route_module, "update_webhook_endpoint_by_id", service)
    response = await client.patch(
        "/webhook-endpoints/not-a-uuid",
        json={"name": "Updated"},
        headers=authorization(owner),
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["path", "endpoint_id"]
    service.assert_not_awaited()
