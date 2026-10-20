from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from relaymaid.db.models import Event, Organization, OutboxMessage, WebhookEndpoint
from relaymaid.db.tenant_context import set_tenant_context, set_user_context

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
TABLE = OutboxMessage.__table__


@dataclass(frozen=True)
class OutboxData:
    organizations: tuple[UUID, UUID]
    events: tuple[UUID, UUID]
    messages: tuple[UUID, UUID]


@pytest.fixture(params=["outbox_rls_app", "outbox_rls_owner"])
async def outbox(
    db_session: AsyncSession, request: pytest.FixtureRequest
) -> OutboxData:
    organizations, events, messages = [], [], []
    for _ in range(2):
        organization = Organization(name="Outbox RLS test")
        db_session.add(organization)
        await db_session.flush()
        endpoint = WebhookEndpoint(
            organization_id=organization.id,
            name="Outbox RLS",
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
            payload_raw=b"{}",
            content_type="application/json",
        )
        db_session.add(event)
        await db_session.flush()
        message = OutboxMessage(organization_id=organization.id, event_id=event.id)
        db_session.add(message)
        await db_session.flush()
        organizations.append(organization.id)
        events.append(event.id)
        messages.append(message.id)
    for role in ("outbox_rls_app", "outbox_rls_owner"):
        await db_session.execute(
            text(f"CREATE ROLE {role} NOSUPERUSER NOBYPASSRLS NOLOGIN")
        )
    await db_session.execute(
        text("GRANT USAGE ON SCHEMA public TO outbox_rls_app, outbox_rls_owner")
    )
    # Grant all operations so rejected writes exercise RLS, not missing privileges.
    await db_session.execute(
        text(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON outbox_messages TO outbox_rls_app"
        )
    )
    await db_session.execute(
        text("ALTER TABLE outbox_messages OWNER TO outbox_rls_owner")
    )
    await db_session.execute(text(f"SET LOCAL ROLE {request.param}"))
    assert (
        await db_session.execute(
            text(
                "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles "
                "WHERE rolname = current_user"
            )
        )
    ).one() == (request.param, False, False)
    assert (
        await db_session.execute(
            text(
                "SELECT pg_get_userbyid(relowner), relrowsecurity, relforcerowsecurity "
                "FROM pg_class WHERE oid = 'public.outbox_messages'::regclass"
            )
        )
    ).one() == ("outbox_rls_owner", True, True)
    return OutboxData(tuple(organizations), tuple(events), tuple(messages))


async def set_context(session: AsyncSession, context: str) -> None:
    if context == "unknown":
        await set_tenant_context(session, uuid4())
    elif context == "user_only":
        await set_user_context(session, uuid4())
    elif context in {"empty", "malformed"}:
        await session.execute(
            text("SELECT set_config('relaymaid.organization_id', :value, true)"),
            {"value": "" if context == "empty" else "not-a-uuid"},
        )


async def assert_original_messages(session: AsyncSession, data: OutboxData) -> None:
    for organization, message in zip(data.organizations, data.messages, strict=True):
        await set_tenant_context(session, organization)
        assert (
            await session.execute(select(TABLE.c.id, TABLE.c.published_at))
        ).one() == (message, None)


async def test_select_only_returns_current_tenant_messages(
    db_session: AsyncSession, outbox: OutboxData
) -> None:
    for index in range(2):
        await set_tenant_context(db_session, outbox.organizations[index])
        assert list(await db_session.scalars(select(TABLE.c.id))) == [
            outbox.messages[index]
        ]
        assert (
            await db_session.scalar(
                select(TABLE.c.id).where(TABLE.c.id == outbox.messages[1 - index])
            )
            is None
        )


async def test_insert_accepts_current_tenant_message(
    db_session: AsyncSession, outbox: OutboxData
) -> None:
    await set_tenant_context(db_session, outbox.organizations[0])
    message_id = uuid4()
    assert (
        await db_session.scalar(
            insert(TABLE)
            .values(
                id=message_id,
                organization_id=outbox.organizations[0],
                event_id=outbox.events[0],
            )
            .returning(TABLE.c.id)
        )
        == message_id
    )
    assert set(await db_session.scalars(select(TABLE.c.id))) == {
        message_id,
        outbox.messages[0],
    }
    await set_tenant_context(db_session, outbox.organizations[1])
    assert list(await db_session.scalars(select(TABLE.c.id))) == [outbox.messages[1]]


@pytest.mark.parametrize(
    "context", ["other", "missing", "empty", "unknown", "user_only"]
)
async def test_insert_rejects_without_matching_tenant(
    db_session: AsyncSession, outbox: OutboxData, context: str
) -> None:
    if context == "other":
        await set_tenant_context(db_session, outbox.organizations[1])
    else:
        await set_context(db_session, context)
    with pytest.raises(DBAPIError, match="row-level security policy") as error:
        async with db_session.begin_nested():
            await db_session.execute(
                insert(TABLE).values(
                    id=uuid4(),
                    organization_id=outbox.organizations[0],
                    event_id=outbox.events[0],
                )
            )
    assert error.value.orig.sqlstate == "42501"
    await assert_original_messages(db_session, outbox)


@pytest.mark.parametrize("context", ["missing", "empty", "unknown", "user_only"])
async def test_select_hides_messages_without_tenant_context(
    db_session: AsyncSession, outbox: OutboxData, context: str
) -> None:
    await set_context(db_session, context)
    assert list(await db_session.scalars(select(TABLE.c.id))) == []


@pytest.mark.parametrize("operation", ["select", "insert"])
async def test_malformed_context_fails_closed(
    db_session: AsyncSession, outbox: OutboxData, operation: str
) -> None:
    await set_context(db_session, "malformed")
    statement = (
        select(TABLE.c.id)
        if operation == "select"
        else insert(TABLE).values(
            id=uuid4(),
            organization_id=outbox.organizations[0],
            event_id=outbox.events[0],
        )
    )
    with pytest.raises(DBAPIError, match="invalid input syntax for type uuid") as error:
        async with db_session.begin_nested():
            await db_session.execute(statement)
    assert error.value.orig.sqlstate == "22P02"
    await assert_original_messages(db_session, outbox)


@pytest.mark.parametrize("operation", ["update", "delete"])
@pytest.mark.parametrize("context", ["matching", "missing"])
async def test_mutations_are_denied_even_for_own_messages(
    db_session: AsyncSession, outbox: OutboxData, operation: str, context: str
) -> None:
    if context == "matching":
        await set_tenant_context(db_session, outbox.organizations[0])
    statement = (
        update(TABLE).values(published_at=text("now()"))
        if operation == "update"
        else delete(TABLE)
    )
    assert list(await db_session.scalars(statement.returning(TABLE.c.id))) == []
    await assert_original_messages(db_session, outbox)
