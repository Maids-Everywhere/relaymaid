from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from relaymaid.security.webhook_secrets import WebhookSecretManager
from relaymaid.services.exceptions import WebhookEndpointNotFoundError
from relaymaid.services.webhook_endpoints import (
    create_webhook_endpoint,
    get_webhook_endpoint_by_id,
    list_webhook_endpoints,
)

pytestmark = pytest.mark.anyio


async def test_creation_encrypts_secret_and_leaves_commit_to_caller() -> None:
    session = MagicMock(spec=AsyncSession)
    manager = MagicMock(spec=WebhookSecretManager)
    manager.generate_secret.return_value = "plain-secret"
    manager.encrypt.return_value = "encrypted-secret"
    organization_id = uuid4()
    result = await create_webhook_endpoint(
        session,
        organization_id=organization_id,
        name="Endpoint",
        destination_url="https://example.com/events",
        retry_limit=3,
        secret_manager=manager,
    )
    assert result.secret == "plain-secret"
    assert result.endpoint.secret_ciphertext == "encrypted-secret"
    assert result.endpoint.organization_id == organization_id
    assert result.endpoint.name == "Endpoint"
    assert result.endpoint.destination_url == "https://example.com/events"
    assert result.endpoint.retry_limit == 3
    manager.generate_secret.assert_called_once_with()
    manager.encrypt.assert_called_once_with("plain-secret")
    session.add.assert_called_once_with(result.endpoint)
    session.flush.assert_awaited_once_with()
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()


@pytest.mark.parametrize("stage", ["generate_secret", "encrypt", "flush"])
async def test_creation_propagates_failures_without_committing(stage: str) -> None:
    session = MagicMock(spec=AsyncSession)
    session.flush = AsyncMock()
    manager = MagicMock(spec=WebhookSecretManager)
    manager.generate_secret.return_value = "plain-secret"
    manager.encrypt.return_value = "encrypted-secret"
    failure = RuntimeError("operation failed")
    target = session if stage == "flush" else manager
    getattr(target, stage).side_effect = failure
    with pytest.raises(RuntimeError, match="operation failed") as error:
        await create_webhook_endpoint(
            session,
            organization_id=uuid4(),
            name="Endpoint",
            destination_url="https://example.com/events",
            retry_limit=3,
            secret_manager=manager,
        )
    assert error.value is failure
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()
    if stage != "flush":
        session.add.assert_not_called()
        session.flush.assert_not_awaited()
    if stage == "generate_secret":
        manager.encrypt.assert_not_called()


@pytest.mark.parametrize(
    "count, has_more", [(0, False), (1, False), (2, False), (3, True)]
)
async def test_listing_returns_page_and_detects_more_results(
    count: int, has_more: bool
) -> None:
    session = MagicMock(spec=AsyncSession)
    endpoints = [MagicMock() for _ in range(count)]
    query_result = MagicMock()
    query_result.scalars.return_value = iter(endpoints)
    session.execute.return_value = query_result
    result = await list_webhook_endpoints(
        session, organization_id=uuid4(), limit=2, offset=1
    )
    assert result.items == tuple(endpoints[:2])
    assert result.has_more is has_more
    session.execute.assert_awaited_once()
    session.commit.assert_not_awaited()
    session.flush.assert_not_awaited()


async def test_listing_propagates_database_failure_without_committing() -> None:
    session = MagicMock(spec=AsyncSession)
    failure = RuntimeError("database unavailable")
    session.execute.side_effect = failure
    with pytest.raises(RuntimeError, match="database unavailable") as error:
        await list_webhook_endpoints(session, organization_id=uuid4())
    assert error.value is failure
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()


@pytest.mark.parametrize("found", [False, True])
async def test_lookup_returns_endpoint_or_raises_not_found_without_writes(
    found: bool,
) -> None:
    session = MagicMock(spec=AsyncSession)
    query_result = MagicMock()
    endpoint = MagicMock() if found else None
    query_result.scalar_one_or_none.return_value = endpoint
    session.execute.return_value = query_result
    organization_id = uuid4()
    endpoint_id = uuid4()
    if found:
        result = await get_webhook_endpoint_by_id(
            session, organization_id=organization_id, endpoint_id=endpoint_id
        )
        assert result is endpoint
    else:
        with pytest.raises(WebhookEndpointNotFoundError) as error:
            await get_webhook_endpoint_by_id(
                session, organization_id=organization_id, endpoint_id=endpoint_id
            )
        assert error.value.args == ()
    session.execute.assert_awaited_once()
    query_result.scalar_one_or_none.assert_called_once_with()
    session.add.assert_not_called()
    session.flush.assert_not_awaited()
    session.commit.assert_not_awaited()


async def test_lookup_propagates_database_failure_without_committing() -> None:
    session = MagicMock(spec=AsyncSession)
    failure = RuntimeError("database unavailable")
    session.execute.side_effect = failure
    with pytest.raises(RuntimeError, match="database unavailable") as error:
        await get_webhook_endpoint_by_id(
            session, organization_id=uuid4(), endpoint_id=uuid4()
        )
    assert error.value is failure
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "Updated"},
        {"destination_url": "https://example.com/new"},
        {"retry_limit": 0},
        {"enabled": False},
        {
            "name": "Updated",
            "destination_url": "https://example.com/new",
            "retry_limit": 10,
            "enabled": True,
        },
    ],
)
async def test_update_changes_only_supplied_fields_without_committing(changes) -> None:
    from relaymaid.db.models.webhook import WebhookEndpoint
    from relaymaid.services.webhook_endpoints import update_webhook_endpoint_by_id

    session = MagicMock(spec=AsyncSession)
    endpoint = WebhookEndpoint(
        id=uuid4(),
        public_id=uuid4(),
        organization_id=uuid4(),
        name="Original",
        destination_url="https://example.com/original",
        retry_limit=3,
        enabled=False,
        secret_ciphertext="encrypted-secret",
    )
    query_result = MagicMock()
    query_result.scalar_one_or_none.return_value = endpoint
    session.execute.return_value = query_result
    original = {
        field: getattr(endpoint, field)
        for field in (
            "name",
            "destination_url",
            "retry_limit",
            "enabled",
            "id",
            "public_id",
            "organization_id",
            "secret_ciphertext",
        )
    }
    result = await update_webhook_endpoint_by_id(
        session,
        organization_id=endpoint.organization_id,
        endpoint_id=endpoint.id,
        **changes,
    )
    assert result is endpoint
    for field, value in original.items():
        assert getattr(endpoint, field) == changes.get(field, value)
    session.flush.assert_awaited_once_with()
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()


@pytest.mark.parametrize("stage", ["missing", "execute", "flush"])
async def test_update_propagates_failures_without_committing(stage: str) -> None:
    from relaymaid.services.webhook_endpoints import update_webhook_endpoint_by_id

    session = MagicMock(spec=AsyncSession)
    query_result = MagicMock()
    query_result.scalar_one_or_none.return_value = (
        None if stage == "missing" else MagicMock()
    )
    session.execute.return_value = query_result
    failure = RuntimeError("database unavailable")
    if stage != "missing":
        getattr(session, stage).side_effect = failure
    expected = WebhookEndpointNotFoundError if stage == "missing" else RuntimeError
    with pytest.raises(expected) as error:
        await update_webhook_endpoint_by_id(
            session, organization_id=uuid4(), endpoint_id=uuid4(), name="Updated"
        )
    if stage != "missing":
        assert error.value is failure
    if stage != "flush":
        session.flush.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()
