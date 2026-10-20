from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from relaymaid.db.models import Event, Organization, OutboxMessage, WebhookEndpoint

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
async def events(db_session: AsyncSession) -> tuple[Event, Event]:
    events = []
    for _ in range(2):
        organization = Organization(name="Outbox test")
        db_session.add(organization)
        await db_session.flush()
        endpoint = WebhookEndpoint(
            organization_id=organization.id,
            name="Outbox endpoint",
            destination_url="https://example.com/events",
            secret_ciphertext="encrypted",
        )
        db_session.add(endpoint)
        await db_session.flush()
        event = Event(
            organization_id=organization.id,
            endpoint_id=endpoint.id,
            external_event_id="external-123",
            event_type="order.created",
            payload_raw=b'{"id": 123}',
            content_type="application/json",
        )
        db_session.add(event)
        events.append(event)
    await db_session.flush()
    return events[0], events[1]


async def test_outbox_persists_reference_and_unpublished_defaults(
    db_session: AsyncSession, events: tuple[Event, Event]
) -> None:
    message = OutboxMessage(
        organization_id=events[0].organization_id, event_id=events[0].id
    )
    db_session.add(message)
    await db_session.flush()
    message_id = message.id
    db_session.expunge(message)
    stored = await db_session.get(OutboxMessage, message_id)
    assert stored is not None
    assert isinstance(stored.id, UUID)
    assert stored.organization_id == events[0].organization_id
    assert stored.event_id == events[0].id
    assert stored.created_at.tzinfo is not None
    assert stored.published_at is None


async def test_published_message_leaves_unpublished_queue(
    db_session: AsyncSession, events: tuple[Event, Event]
) -> None:
    messages = [
        OutboxMessage(organization_id=event.organization_id, event_id=event.id)
        for event in events
    ]
    db_session.add_all(messages)
    await db_session.flush()
    published_at = datetime(2026, 10, 21, 12, 30, tzinfo=UTC)
    messages[0].published_at = published_at
    await db_session.flush()
    await db_session.refresh(messages[0])
    assert messages[0].published_at == published_at
    assert list(
        await db_session.scalars(
            select(OutboxMessage.id)
            .where(OutboxMessage.published_at.is_(None))
            .order_by(OutboxMessage.created_at, OutboxMessage.id)
        )
    ) == [messages[1].id]
    assert await db_session.get(OutboxMessage, messages[0].id) is not None


@pytest.mark.parametrize("target", ["foreign_tenant", "missing_event"])
async def test_outbox_rejects_event_outside_organization(
    db_session: AsyncSession, events: tuple[Event, Event], target: str
) -> None:
    event_id = events[1].id if target == "foreign_tenant" else uuid4()
    with pytest.raises(IntegrityError) as error:
        async with db_session.begin_nested():
            db_session.add(
                OutboxMessage(
                    organization_id=events[0].organization_id, event_id=event_id
                )
            )
            await db_session.flush()
    assert error.value.orig.sqlstate == "23503"
    assert (
        error.value.orig.diag.constraint_name
        == "fk_outbox_messages_organization_event_events"
    )
    assert list(await db_session.scalars(select(OutboxMessage.id))) == []


@pytest.mark.parametrize("field", ["organization_id", "event_id"])
async def test_outbox_requires_tenant_and_event(
    db_session: AsyncSession, events: tuple[Event, Event], field: str
) -> None:
    values = {"organization_id": events[0].organization_id, "event_id": events[0].id}
    values[field] = None
    with pytest.raises(IntegrityError) as error:
        async with db_session.begin_nested():
            db_session.add(OutboxMessage(**values))
            await db_session.flush()
    assert error.value.orig.sqlstate == "23502"
    assert error.value.orig.diag.column_name == field


@pytest.mark.parametrize("published", [False, True])
async def test_referenced_event_cannot_be_deleted(
    db_session: AsyncSession, events: tuple[Event, Event], published: bool
) -> None:
    message = OutboxMessage(
        organization_id=events[0].organization_id,
        event_id=events[0].id,
        published_at=datetime.now(UTC) if published else None,
    )
    db_session.add(message)
    await db_session.flush()
    with pytest.raises(IntegrityError) as error:
        async with db_session.begin_nested():
            await db_session.execute(delete(Event).where(Event.id == events[0].id))
    assert error.value.orig.sqlstate == "23503"
    assert (
        error.value.orig.diag.constraint_name
        == "fk_outbox_messages_organization_event_events"
    )
    assert await db_session.get(Event, events[0].id) is not None
    assert await db_session.get(OutboxMessage, message.id) is not None


async def test_event_and_outbox_insertions_roll_back_together(
    db_session: AsyncSession, events: tuple[Event, Event]
) -> None:
    savepoint = await db_session.begin_nested()
    event = Event(
        organization_id=events[0].organization_id,
        endpoint_id=events[0].endpoint_id,
        external_event_id="rolled-back",
        event_type="order.created",
        payload_raw=b"{}",
        content_type="application/json",
    )
    db_session.add(event)
    await db_session.flush()
    message = OutboxMessage(organization_id=event.organization_id, event_id=event.id)
    db_session.add(message)
    await db_session.flush()
    event_id, message_id = event.id, message.id
    await savepoint.rollback()
    assert await db_session.get(Event, event_id) is None
    assert await db_session.get(OutboxMessage, message_id) is None
    assert set(await db_session.scalars(select(Event.id))) == {
        event.id for event in events
    }


async def test_migration_creates_partial_unpublished_index(
    db_session: AsyncSession,
) -> None:
    connection = await db_session.connection()
    indexes = await connection.run_sync(
        lambda sync_connection: inspect(sync_connection).get_indexes("outbox_messages")
    )
    index = next(
        index
        for index in indexes
        if index["name"] == "ix_outbox_messages_unpublished_created_at_id"
    )
    assert index["column_names"] == ["created_at", "id"]
    assert index["unique"] is False
    predicate = index["dialect_options"]["postgresql_where"]
    assert predicate.strip("()") == "published_at IS NULL"
