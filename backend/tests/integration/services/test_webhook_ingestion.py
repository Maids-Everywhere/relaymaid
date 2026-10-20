from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from relaymaid.db.models import Event, Organization, OutboxMessage, WebhookEndpoint
from relaymaid.db.tenant_context import set_tenant_context
from relaymaid.domain import EventStatus
from relaymaid.services.webhook_ingestion import (
    VerifiedWebhookEndpoint,
    persist_webhook_event,
)

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
PAYLOAD = b'{ "event": "created", "raw": "\xff" }\n'


@pytest.fixture
async def endpoint(db_session: AsyncSession) -> VerifiedWebhookEndpoint:
    organization = Organization(name="Ingestion test")
    db_session.add(organization)
    await db_session.flush()
    endpoint = WebhookEndpoint(
        organization_id=organization.id,
        name="Ingestion endpoint",
        destination_url="https://example.com/events",
        secret_ciphertext="encrypted",
    )
    db_session.add(endpoint)
    await db_session.flush()
    verified = VerifiedWebhookEndpoint(id=endpoint.id, organization_id=organization.id)
    await db_session.execute(
        text("CREATE ROLE ingestion_service_test NOSUPERUSER NOBYPASSRLS NOLOGIN")
    )
    await db_session.execute(
        text("GRANT USAGE ON SCHEMA public TO ingestion_service_test")
    )
    await db_session.execute(
        text(
            "GRANT SELECT, INSERT ON events, outbox_messages TO ingestion_service_test"
        )
    )
    await db_session.execute(text("SET LOCAL ROLE ingestion_service_test"))
    assert (
        await db_session.execute(
            text(
                "SELECT rolsuper, rolbypassrls FROM pg_roles "
                "WHERE rolname = current_user"
            )
        )
    ).one() == (False, False)
    return verified


async def persist(session: AsyncSession, endpoint: VerifiedWebhookEndpoint):
    return await persist_webhook_event(
        session=session,
        endpoint=endpoint,
        external_event_id="external-123",
        event_type="order.created",
        payload_raw=PAYLOAD,
        content_type="application/json",
    )


async def test_persist_creates_linked_event_and_outbox_under_endpoint_tenant(
    db_session: AsyncSession, endpoint: VerifiedWebhookEndpoint
) -> None:
    await set_tenant_context(db_session, uuid4())
    result = await persist(db_session, endpoint)
    event_id, message_id = result.event.id, result.outbox_message.id
    db_session.expunge_all()
    event = await db_session.get(Event, event_id)
    message = await db_session.get(OutboxMessage, message_id)
    assert event is not None
    assert message is not None
    assert event.organization_id == message.organization_id == endpoint.organization_id
    assert event.endpoint_id == endpoint.id
    assert message.event_id == event.id
    assert event.external_event_id == "external-123"
    assert event.event_type == "order.created"
    assert event.payload_raw == PAYLOAD
    assert event.content_type == "application/json"
    assert event.status is EventStatus.PENDING
    assert event.received_at.tzinfo is not None
    assert message.created_at.tzinfo is not None
    assert message.published_at is None


async def test_duplicate_external_event_does_not_create_another_outbox_message(
    db_session: AsyncSession, endpoint: VerifiedWebhookEndpoint
) -> None:
    original = await persist(db_session, endpoint)
    event_id, message_id = original.event.id, original.outbox_message.id
    with pytest.raises(IntegrityError) as error:
        async with db_session.begin_nested():
            await persist(db_session, endpoint)
    assert error.value.orig.sqlstate == "23505"
    assert (
        error.value.orig.diag.constraint_name
        == "uq_events_organization_endpoint_external_event"
    )
    assert list(await db_session.scalars(select(Event.id))) == [event_id]
    assert list(await db_session.scalars(select(OutboxMessage.id))) == [message_id]


async def test_outbox_insert_failure_rolls_back_event_with_callers_transaction(
    db_session: AsyncSession, endpoint: VerifiedWebhookEndpoint
) -> None:
    # Force a real outbox failure after the service has flushed the event.
    await db_session.execute(text("RESET ROLE"))
    await db_session.execute(
        text("REVOKE INSERT ON outbox_messages FROM ingestion_service_test")
    )
    await db_session.execute(text("SET LOCAL ROLE ingestion_service_test"))
    with pytest.raises(
        DBAPIError, match="permission denied for table outbox_messages"
    ) as error:
        async with db_session.begin_nested():
            await persist(db_session, endpoint)
    assert error.value.orig.sqlstate == "42501"
    await set_tenant_context(db_session, endpoint.organization_id)
    assert list(await db_session.scalars(select(Event.id))) == []
    assert list(await db_session.scalars(select(OutboxMessage.id))) == []
