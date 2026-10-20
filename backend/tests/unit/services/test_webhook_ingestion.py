import hashlib
import hmac
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession

from relaymaid.security.webhook_secrets import (
    WebhookSecretDecryptionError,
    WebhookSecretManager,
)
from relaymaid.security.webhook_signatures import (
    InvalidWebhookSignatureError,
    InvalidWebhookTimestampError,
    WebhookTimestampOutsideToleranceError,
)
from relaymaid.services.exceptions import WebhookEndpointUnavailableError
from relaymaid.services.webhook_ingestion import (
    VerifiedWebhookEndpoint,
    authenticate_incoming_webhook,
    persist_webhook_event,
    resolve_webhook_endpoint,
)

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("found", [True, False])
async def test_resolver_maps_database_result_or_returns_none(found: bool) -> None:
    session = MagicMock(spec=AsyncSession)
    row = SimpleNamespace(
        id=uuid4(), organization_id=uuid4(), secret_ciphertext="ciphertext"
    )
    result = MagicMock()
    result.one_or_none.return_value = row if found else None
    session.execute.return_value = result
    public_id = uuid4()
    endpoint = await resolve_webhook_endpoint(session, public_id)
    session.execute.assert_awaited_once()
    assert session.execute.await_args.args[1] == {"public_id": public_id}
    if found:
        assert endpoint.id == row.id
        assert endpoint.organization_id == row.organization_id
        assert endpoint.secret_ciphertext == row.secret_ciphertext
    else:
        assert endpoint is None


@pytest.mark.parametrize(
    "outcome",
    ["valid", "unknown", "ciphertext", "signature", "timestamp", "expired", "database"],
)
async def test_authentication_checks_availability_decryption_and_signature(
    outcome: str, monkeypatch
) -> None:
    monkeypatch.setattr(
        "relaymaid.security.webhook_signatures.time.time", lambda: 1800000000
    )
    session = MagicMock(spec=AsyncSession)
    manager = WebhookSecretManager(Fernet.generate_key().decode())
    secret = "ingestion-secret"
    timestamp = (
        "invalid"
        if outcome == "timestamp"
        else "1799999699"
        if outcome == "expired"
        else "1800000000"
    )
    body = b'{ "event": "created" }'
    digest = hmac.new(
        secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    row = SimpleNamespace(
        id=uuid4(),
        organization_id=uuid4(),
        secret_ciphertext="invalid"
        if outcome == "ciphertext"
        else manager.encrypt(secret),
    )
    result = MagicMock()
    result.one_or_none.return_value = None if outcome == "unknown" else row
    session.execute.return_value = result
    failure = RuntimeError("database unavailable")
    if outcome == "database":
        session.execute.side_effect = failure
    errors = {
        "unknown": WebhookEndpointUnavailableError,
        "ciphertext": WebhookSecretDecryptionError,
        "signature": InvalidWebhookSignatureError,
        "timestamp": InvalidWebhookTimestampError,
        "expired": WebhookTimestampOutsideToleranceError,
        "database": RuntimeError,
    }
    kwargs = dict(
        session=session,
        secret_manager=manager,
        public_id=uuid4(),
        timestamp=timestamp,
        raw_body=body,
        signature="v1=wrong" if outcome == "signature" else f"v1={digest}",
    )
    if outcome == "valid":
        verified = await authenticate_incoming_webhook(**kwargs)
        assert verified.id == row.id
        assert verified.organization_id == row.organization_id
        assert not hasattr(verified, "secret_ciphertext")
        assert not hasattr(verified, "secret")
    else:
        with pytest.raises(errors[outcome]) as error:
            await authenticate_incoming_webhook(**kwargs)
        if outcome == "database":
            assert error.value is failure
    session.flush.assert_not_awaited()
    session.commit.assert_not_awaited()


async def test_persist_raises_when_conflicting_event_cannot_be_loaded() -> None:
    session = MagicMock(spec=AsyncSession)
    session.scalar.side_effect = [None, None]
    endpoint = VerifiedWebhookEndpoint(id=uuid4(), organization_id=uuid4())
    with pytest.raises(
        RuntimeError, match="Conflicting webhook event could not be loaded"
    ):
        await persist_webhook_event(
            session=session,
            endpoint=endpoint,
            external_event_id="external-123",
            event_type="order.created",
            payload_raw=b"{}",
            content_type="application/json",
        )
    assert session.scalar.await_count == 2
    session.add.assert_not_called()
    session.flush.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()
