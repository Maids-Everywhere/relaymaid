import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from relaymaid.db.models import Event, Organization, OutboxMessage, WebhookEndpoint
from relaymaid.db.tenant_context import set_tenant_context
from relaymaid.domain import EventStatus
from relaymaid.services.webhook_ingestion import (
    PersistedWebhookEvent,
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
    assert result.created is True
    assert result.outbox_message is not None
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
    assert original.created is True
    assert original.outbox_message is not None
    event_id, message_id = original.event.id, original.outbox_message.id
    db_session.expunge_all()
    duplicate = await persist_webhook_event(
        session=db_session,
        endpoint=endpoint,
        external_event_id="external-123",
        event_type="different.event",
        payload_raw=b"changed payload",
        content_type="text/plain",
    )
    assert duplicate.created is False
    assert duplicate.outbox_message is None
    assert duplicate.event.id == event_id
    assert duplicate.event.payload_raw == PAYLOAD
    assert duplicate.event.event_type == "order.created"
    assert duplicate.event.content_type == "application/json"
    assert list(await db_session.scalars(select(Event.id))) == [event_id]
    assert list(await db_session.scalars(select(OutboxMessage.id))) == [message_id]


async def test_outbox_insert_failure_rolls_back_event_with_callers_transaction(
    db_session: AsyncSession, endpoint: VerifiedWebhookEndpoint
) -> None:
    # Force a real outbox failure after the service has inserted the event.
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


@pytest.mark.parametrize("same_organization", [True, False])
async def test_external_event_id_is_scoped_to_endpoint_and_tenant(
    db_session: AsyncSession,
    endpoint: VerifiedWebhookEndpoint,
    same_organization: bool,
) -> None:
    first = await persist(db_session, endpoint)
    await db_session.execute(text("RESET ROLE"))
    organization_id = endpoint.organization_id
    if not same_organization:
        organization = Organization(name="Other ingestion tenant")
        db_session.add(organization)
        await db_session.flush()
        organization_id = organization.id
    other = WebhookEndpoint(
        organization_id=organization_id,
        name="Other endpoint",
        destination_url="https://example.com/events",
        secret_ciphertext="encrypted",
    )
    db_session.add(other)
    await db_session.flush()
    other_endpoint = VerifiedWebhookEndpoint(
        id=other.id, organization_id=organization_id
    )
    await db_session.execute(text("SET LOCAL ROLE ingestion_service_test"))
    second = await persist(db_session, other_endpoint)
    assert first.created is second.created is True
    assert first.outbox_message is not None
    assert second.outbox_message is not None
    assert second.event.id != first.event.id
    assert second.outbox_message.id != first.outbox_message.id
    assert second.event.endpoint_id == other_endpoint.id
    assert second.event.organization_id == organization_id
    assert second.outbox_message.organization_id == organization_id
    assert second.outbox_message.event_id == second.event.id
    for principal, result in ((endpoint, first), (other_endpoint, second)):
        await set_tenant_context(db_session, principal.organization_id)
        assert (
            await db_session.scalar(select(Event.id).where(Event.id == result.event.id))
            == result.event.id
        )
        assert (
            await db_session.scalar(
                select(OutboxMessage.id).where(
                    OutboxMessage.event_id == result.event.id
                )
            )
            == result.outbox_message.id
        )


async def test_concurrent_duplicates_create_one_event_and_one_outbox(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    organization_id = uuid4()
    try:
        # Commit setup so both independent transactions can see the endpoint.
        async with session_factory.begin() as setup_session:
            organization = Organization(id=organization_id, name="Concurrent ingestion")
            setup_session.add(organization)
            await setup_session.flush()
            webhook_endpoint = WebhookEndpoint(
                organization_id=organization_id,
                name="Concurrent endpoint",
                destination_url="https://example.com/events",
                secret_ciphertext="encrypted",
            )
            setup_session.add(webhook_endpoint)
            await setup_session.flush()
            endpoint = VerifiedWebhookEndpoint(
                id=webhook_endpoint.id, organization_id=organization_id
            )

        barrier = asyncio.Barrier(2)

        async def persist_in_separate_transaction() -> PersistedWebhookEvent:
            async with session_factory.begin() as session:
                await barrier.wait()
                return await persist_webhook_event(
                    session=session,
                    endpoint=endpoint,
                    external_event_id="concurrent-123",
                    event_type="order.created",
                    payload_raw=PAYLOAD,
                    content_type="application/json",
                )

        # Wait for both transactions even if one fails, before starting cleanup.
        async with asyncio.timeout(15):
            results = await asyncio.gather(
                persist_in_separate_transaction(),
                persist_in_separate_transaction(),
                return_exceptions=True,
            )
        for result in results:
            if isinstance(result, BaseException):
                raise result
        first, second = results
        assert {first.created, second.created} == {True, False}
        assert first.event.id == second.event.id
        created_result = first if first.created else second
        duplicate_result = second if first.created else first
        assert created_result.outbox_message is not None
        assert duplicate_result.outbox_message is None

        async with session_factory.begin() as assertion_session:
            events = list(
                await assertion_session.scalars(
                    select(Event).where(Event.organization_id == organization_id)
                )
            )
            messages = list(
                await assertion_session.scalars(
                    select(OutboxMessage).where(
                        OutboxMessage.organization_id == organization_id
                    )
                )
            )
            assert len(events) == 1
            assert len(messages) == 1
            assert events[0].id == first.event.id
            assert messages[0].id == created_result.outbox_message.id
            assert messages[0].event_id == events[0].id
    finally:
        # These rows are committed, so the normal rollback fixture cannot remove them.
        async with session_factory.begin() as cleanup_session:
            for model in (OutboxMessage, Event, WebhookEndpoint):
                await cleanup_session.execute(
                    delete(model).where(model.organization_id == organization_id)
                )
            await cleanup_session.execute(
                delete(Organization).where(Organization.id == organization_id)
            )
