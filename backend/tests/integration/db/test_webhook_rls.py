from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from relaymaid.db.models import Organization
from relaymaid.db.models.webhook import WebhookEndpoint
from relaymaid.db.tenant_context import set_tenant_context, set_user_context

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
TABLE = WebhookEndpoint.__table__


@dataclass
class WebhookData:
    organizations: tuple[UUID, UUID]
    endpoints: tuple[UUID, UUID]
    public_ids: tuple[UUID, UUID]


def endpoint_values(organization_id: UUID) -> dict[str, object]:
    return {
        "id": uuid4(),
        "organization_id": organization_id,
        "public_id": uuid4(),
        "name": "Original",
        "secret_ciphertext": "test-ciphertext",
        "destination_url": "https://example.com/webhook",
    }


@pytest.fixture(params=["relaymaid_app", "relaymaid_migrator"])
async def webhooks(
    db_session: AsyncSession, request: pytest.FixtureRequest
) -> WebhookData:
    """Seed as admin; roll back data, roles and ownership after each test."""
    data = WebhookData((uuid4(), uuid4()), (uuid4(), uuid4()), (uuid4(), uuid4()))
    for organization_id, endpoint_id, public_id in zip(
        data.organizations, data.endpoints, data.public_ids, strict=True
    ):
        await db_session.execute(
            insert(Organization).values(id=organization_id, name="RLS test")
        )
        values = endpoint_values(organization_id)
        values.update(id=endpoint_id, public_id=public_id)
        await db_session.execute(insert(TABLE).values(**values))
    await db_session.execute(
        text("CREATE ROLE relaymaid_app NOSUPERUSER NOBYPASSRLS NOLOGIN")
    )
    await db_session.execute(
        text("CREATE ROLE relaymaid_migrator NOSUPERUSER NOBYPASSRLS NOLOGIN")
    )
    await db_session.execute(
        text("GRANT USAGE ON SCHEMA public TO relaymaid_app, relaymaid_migrator")
    )
    await db_session.execute(
        text(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON webhook_endpoints TO relaymaid_app"
        )
    )
    await db_session.execute(
        text("ALTER TABLE webhook_endpoints OWNER TO relaymaid_migrator")
    )
    await db_session.execute(text("SET LOCAL ROLE relaymaid_app"))
    await assert_role(db_session, "relaymaid_app")
    if request.param == "relaymaid_migrator":
        await db_session.execute(text("SET LOCAL ROLE relaymaid_migrator"))
        await assert_role(db_session, "relaymaid_migrator")
    return data


async def assert_role(session: AsyncSession, expected_role: str) -> None:
    role = (
        await session.execute(
            text(
                "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles "
                "WHERE rolname = current_user"
            )
        )
    ).one()
    assert role == (expected_role, False, False)
    assert (
        await session.scalar(
            text(
                "SELECT pg_get_userbyid(relowner) FROM pg_class "
                "WHERE oid = 'public.webhook_endpoints'::regclass"
            )
        )
        == "relaymaid_migrator"
    )


async def set_context(session: AsyncSession, data: WebhookData, context: str) -> None:
    if context == "matching":
        await set_tenant_context(session, data.organizations[0])
    elif context == "other":
        await set_tenant_context(session, data.organizations[1])
    elif context == "unknown":
        await set_tenant_context(session, uuid4())
    elif context == "user_only":
        await set_user_context(session, data.organizations[0])
    elif context in {"empty", "malformed"}:
        await session.execute(
            text("SELECT set_config('relaymaid.organization_id', :value, true)"),
            {"value": "" if context == "empty" else "not-a-uuid"},
        )


async def test_select_and_update_only_current_tenant(
    db_session: AsyncSession, webhooks: WebhookData
) -> None:
    for organization_id, endpoint_id in zip(
        webhooks.organizations, webhooks.endpoints, strict=True
    ):
        await set_tenant_context(db_session, organization_id)
        assert list(await db_session.scalars(select(TABLE.c.id))) == [endpoint_id]
        assert await db_session.scalar(select(TABLE.c.name)) == "Original"
        assert list(
            await db_session.scalars(
                update(TABLE)
                .values(name="Changed", enabled=False)
                .returning(TABLE.c.id)
            )
        ) == [endpoint_id]
        row = (await db_session.execute(select(TABLE.c.name, TABLE.c.enabled))).one()
        assert row == ("Changed", False)


@pytest.mark.parametrize("lookup", ["id", "public_id"])
@pytest.mark.parametrize("operation", ["select", "update"])
async def test_foreign_endpoint_identifiers_do_not_bypass_rls(
    db_session: AsyncSession, webhooks: WebhookData, lookup: str, operation: str
) -> None:
    await set_tenant_context(db_session, webhooks.organizations[0])
    target = webhooks.endpoints[1] if lookup == "id" else webhooks.public_ids[1]
    statement = (
        select(TABLE.c.id)
        if operation == "select"
        else update(TABLE).values(name="Blocked").returning(TABLE.c.id)
    )
    assert (
        list(await db_session.scalars(statement.where(TABLE.c[lookup] == target))) == []
    )
    await set_tenant_context(db_session, webhooks.organizations[1])
    assert await db_session.scalar(select(TABLE.c.name)) == "Original"


@pytest.mark.parametrize("context", ["missing", "empty", "unknown", "user_only"])
async def test_without_tenant_context_cannot_read_or_update(
    db_session: AsyncSession, webhooks: WebhookData, context: str
) -> None:
    await set_context(db_session, webhooks, context)
    assert list(await db_session.scalars(select(TABLE.c.id))) == []
    assert (
        list(
            await db_session.scalars(
                update(TABLE).values(name="Blocked").returning(TABLE.c.id)
            )
        )
        == []
    )
    for organization_id in webhooks.organizations:
        await set_tenant_context(db_session, organization_id)
        assert await db_session.scalar(select(TABLE.c.name)) == "Original"


@pytest.mark.parametrize(
    "context", ["matching", "other", "missing", "empty", "unknown", "user_only"]
)
async def test_insert_requires_matching_organization(
    db_session: AsyncSession, webhooks: WebhookData, context: str
) -> None:
    await set_context(db_session, webhooks, context)
    values = endpoint_values(webhooks.organizations[0])
    statement = insert(TABLE).values(**values).returning(TABLE.c.id)
    if context == "matching":
        assert await db_session.scalar(statement) == values["id"]
        assert (
            await db_session.scalar(
                select(TABLE.c.id).where(TABLE.c.id == values["id"])
            )
            == values["id"]
        )
    else:
        with pytest.raises(DBAPIError, match="row-level security policy") as error:
            async with db_session.begin_nested():
                await db_session.execute(statement)
        assert getattr(error.value.orig, "sqlstate", None) == "42501"
        await set_tenant_context(db_session, webhooks.organizations[0])
        assert list(await db_session.scalars(select(TABLE.c.id))) == [
            webhooks.endpoints[0]
        ]


async def test_update_cannot_move_endpoint_to_another_organization(
    db_session: AsyncSession, webhooks: WebhookData
) -> None:
    await set_tenant_context(db_session, webhooks.organizations[0])
    with pytest.raises(DBAPIError, match="row-level security policy") as error:
        async with db_session.begin_nested():
            await db_session.execute(
                update(TABLE).values(
                    organization_id=webhooks.organizations[1], name="Blocked"
                )
            )
    assert getattr(error.value.orig, "sqlstate", None) == "42501"
    for organization_id, endpoint_id in zip(
        webhooks.organizations, webhooks.endpoints, strict=True
    ):
        await set_tenant_context(db_session, organization_id)
        assert (await db_session.execute(select(TABLE.c.id, TABLE.c.name))).one() == (
            endpoint_id,
            "Original",
        )


@pytest.mark.parametrize(
    "context", ["matching", "other", "missing", "empty", "unknown", "malformed"]
)
async def test_delete_is_denied_for_every_tenant_context(
    db_session: AsyncSession, webhooks: WebhookData, context: str
) -> None:
    await set_context(db_session, webhooks, context)
    assert list(await db_session.scalars(delete(TABLE).returning(TABLE.c.id))) == []
    for organization_id, endpoint_id in zip(
        webhooks.organizations, webhooks.endpoints, strict=True
    ):
        await set_tenant_context(db_session, organization_id)
        assert list(await db_session.scalars(select(TABLE.c.id))) == [endpoint_id]


@pytest.mark.parametrize("operation", ["select", "insert", "update"])
async def test_malformed_tenant_context_fails_closed(
    db_session: AsyncSession, webhooks: WebhookData, operation: str
) -> None:
    await set_context(db_session, webhooks, "malformed")
    statements = {
        "select": select(TABLE),
        "insert": insert(TABLE).values(**endpoint_values(webhooks.organizations[0])),
        "update": update(TABLE).values(name="Blocked"),
    }
    with pytest.raises(DBAPIError, match="invalid input syntax for type uuid") as error:
        async with db_session.begin_nested():
            await db_session.execute(statements[operation])
    assert getattr(error.value.orig, "sqlstate", None) == "22P02"
    for organization_id, endpoint_id in zip(
        webhooks.organizations, webhooks.endpoints, strict=True
    ):
        await set_tenant_context(db_session, organization_id)
        assert (await db_session.execute(select(TABLE.c.id, TABLE.c.name))).one() == (
            endpoint_id,
            "Original",
        )
