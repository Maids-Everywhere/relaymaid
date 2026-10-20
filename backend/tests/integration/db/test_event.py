from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from relaymaid.db.models import Event, Organization, WebhookEndpoint
from relaymaid.domain import EventStatus

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
async def endpoints(db_session: AsyncSession) -> list[WebhookEndpoint]:
    result = []
    for _ in range(2):
        organization = Organization(name="Events test")
        db_session.add(organization)
        await db_session.flush()
        for _ in range(2):
            endpoint = WebhookEndpoint(
                organization_id=organization.id,
                name="Events",
                destination_url="https://example.com/events",
                secret_ciphertext="encrypted",
            )
            db_session.add(endpoint)
            result.append(endpoint)
    await db_session.flush()
    return result


def event_for(endpoint: WebhookEndpoint, **overrides) -> Event:
    return Event(
        **{
            "organization_id": endpoint.organization_id,
            "endpoint_id": endpoint.id,
            "external_event_id": "external-123",
            "event_type": "order.created",
            "payload_raw": b'{ "binary": "\xff" }\n',
            "content_type": "application/json",
            **overrides,
        }
    )


async def test_event_persists_raw_bytes_and_database_defaults(
    db_session, endpoints
) -> None:
    event = event_for(endpoints[0])
    db_session.add(event)
    await db_session.flush()
    await db_session.refresh(event)
    assert event.id is not None
    assert event.status is EventStatus.PENDING
    assert event.received_at.tzinfo is not None
    assert event.completed_at is None
    assert event.payload_raw == b'{ "binary": "\xff" }\n'
    assert event.event_type == "order.created"
    assert event.content_type == "application/json"


async def test_external_event_id_is_unique_per_endpoint(db_session, endpoints) -> None:
    # Reuse the identifier for another endpoint in the same and another tenant.
    db_session.add_all([event_for(endpoint) for endpoint in endpoints])
    await db_session.flush()
    with pytest.raises(IntegrityError) as error:
        async with db_session.begin_nested():
            db_session.add(event_for(endpoints[0]))
            await db_session.flush()
    assert error.value.orig.sqlstate == "23505"
    assert (
        error.value.orig.diag.constraint_name
        == "uq_events_organization_endpoint_external_event"
    )
    assert len(list(await db_session.scalars(select(Event.id)))) == 4


@pytest.mark.parametrize("target", ["foreign_tenant", "unknown_endpoint"])
async def test_event_requires_endpoint_in_same_organization(
    db_session, endpoints, target
) -> None:
    endpoint_id = endpoints[2].id if target == "foreign_tenant" else uuid4()
    with pytest.raises(IntegrityError) as error:
        async with db_session.begin_nested():
            db_session.add(event_for(endpoints[0], endpoint_id=endpoint_id))
            await db_session.flush()
    assert error.value.orig.sqlstate == "23503"
    assert (
        error.value.orig.diag.constraint_name
        == "fk_events_organization_endpoint_webhook_endpoints"
    )


async def test_endpoint_with_events_cannot_be_deleted(db_session, endpoints) -> None:
    db_session.add(event_for(endpoints[0]))
    await db_session.flush()
    with pytest.raises(IntegrityError) as error:
        async with db_session.begin_nested():
            await db_session.execute(
                delete(WebhookEndpoint).where(WebhookEndpoint.id == endpoints[0].id)
            )
    assert error.value.orig.sqlstate == "23503"
    assert await db_session.get(WebhookEndpoint, endpoints[0].id) is not None


@pytest.mark.parametrize("status", list(EventStatus))
async def test_event_status_round_trips(db_session, endpoints, status) -> None:
    event = event_for(endpoints[0], status=status)
    db_session.add(event)
    await db_session.flush()
    await db_session.refresh(event)
    assert event.status is status


async def test_database_rejects_invalid_status(db_session, endpoints) -> None:
    with pytest.raises(IntegrityError) as error:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO events (id, organization_id, endpoint_id, "
                    "external_event_id, "
                    "event_type, payload_raw, content_type, status) "
                    "VALUES (:id, :org, :endpoint, 'bad', 'test', "
                    "''::bytea, 'text/plain', 'invalid')"
                ),
                {
                    "id": uuid4(),
                    "org": endpoints[0].organization_id,
                    "endpoint": endpoints[0].id,
                },
            )
    assert error.value.orig.sqlstate == "23514"
