from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from relaymaid.security.webhook_secrets import WebhookSecretManager
from relaymaid.services.webhook_endpoints import create_webhook_endpoint

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
