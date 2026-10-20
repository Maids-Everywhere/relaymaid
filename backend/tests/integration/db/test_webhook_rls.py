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


@pytest.fixture
async def webhooks(db_session: AsyncSession) -> WebhookData:
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
    await db_session.execute(
        text(
            "ALTER FUNCTION public.relaymaid_resolve_webhook_endpoint(uuid) "
            "OWNER TO relaymaid_migrator"
        )
    )
    await db_session.execute(
        text(
            "GRANT EXECUTE ON FUNCTION "
            "public.relaymaid_resolve_webhook_endpoint(uuid) TO relaymaid_app"
        )
    )
    await db_session.execute(text("SET LOCAL ROLE relaymaid_app"))
    await assert_role(db_session, "relaymaid_app")
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

    resolver_owner = (
        await session.execute(
            text(
                "SELECT owner.rolname, owner.rolsuper, owner.rolbypassrls, "
                "resolver.prosecdef FROM pg_proc AS resolver "
                "JOIN pg_roles AS owner ON owner.oid = resolver.proowner "
                "WHERE resolver.oid = "
                "'public.relaymaid_resolve_webhook_endpoint(uuid)'::regprocedure"
            )
        )
    ).one()
    assert resolver_owner == ("relaymaid_migrator", False, False, True)
    assert (
        await session.scalar(
            text(
                "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
                "WHERE oid = 'public.webhook_endpoints'::regclass"
            )
        )
        is True
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
@pytest.mark.parametrize("operation", ["select", "update", "delete"])
async def test_foreign_endpoint_identifiers_do_not_bypass_rls(
    db_session: AsyncSession, webhooks: WebhookData, lookup: str, operation: str
) -> None:
    await set_tenant_context(db_session, webhooks.organizations[0])
    target = webhooks.endpoints[1] if lookup == "id" else webhooks.public_ids[1]
    statements = {
        "select": select(TABLE.c.id),
        "update": update(TABLE).values(name="Blocked").returning(TABLE.c.id),
        "delete": delete(TABLE).returning(TABLE.c.id),
    }
    statement = statements[operation]
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


@pytest.mark.parametrize("context", ["missing", "empty", "unknown", "user_only"])
async def test_delete_without_tenant_context_preserves_all_endpoints(
    db_session: AsyncSession, webhooks: WebhookData, context: str
) -> None:
    await set_context(db_session, webhooks, context)
    assert list(await db_session.scalars(delete(TABLE).returning(TABLE.c.id))) == []
    for organization_id, endpoint_id in zip(
        webhooks.organizations, webhooks.endpoints, strict=True
    ):
        await set_tenant_context(db_session, organization_id)
        assert list(await db_session.scalars(select(TABLE.c.id))) == [endpoint_id]


@pytest.mark.parametrize("operation", ["select", "insert", "update", "delete"])
async def test_malformed_tenant_context_fails_closed(
    db_session: AsyncSession, webhooks: WebhookData, operation: str
) -> None:
    await set_context(db_session, webhooks, "malformed")
    statements = {
        "select": select(TABLE),
        "insert": insert(TABLE).values(**endpoint_values(webhooks.organizations[0])),
        "update": update(TABLE).values(name="Blocked"),
        "delete": delete(TABLE),
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


async def test_delete_only_removes_current_tenant_endpoints(
    db_session: AsyncSession, webhooks: WebhookData
) -> None:
    # No application filter: PostgreSQL must restrict the DELETE itself.
    await set_tenant_context(db_session, webhooks.organizations[0])
    assert list(await db_session.scalars(delete(TABLE).returning(TABLE.c.id))) == [
        webhooks.endpoints[0]
    ]
    assert list(await db_session.scalars(select(TABLE.c.id))) == []

    await set_tenant_context(db_session, webhooks.organizations[1])
    assert list(await db_session.scalars(select(TABLE.c.id))) == [webhooks.endpoints[1]]
    assert list(await db_session.scalars(delete(TABLE).returning(TABLE.c.id))) == [
        webhooks.endpoints[1]
    ]
    assert list(await db_session.scalars(select(TABLE.c.id))) == []

    await set_tenant_context(db_session, webhooks.organizations[0])
    assert list(await db_session.scalars(select(TABLE.c.id))) == []


@pytest.mark.parametrize("lookup", ["id", "public_id"])
async def test_delete_current_tenant_endpoint_by_identifier_can_be_rolled_back(
    db_session: AsyncSession, webhooks: WebhookData, lookup: str
) -> None:
    await set_tenant_context(db_session, webhooks.organizations[0])
    target = webhooks.endpoints[0] if lookup == "id" else webhooks.public_ids[0]
    savepoint = await db_session.begin_nested()
    assert list(
        await db_session.scalars(
            delete(TABLE).where(TABLE.c[lookup] == target).returning(TABLE.c.id)
        )
    ) == [webhooks.endpoints[0]]
    assert list(await db_session.scalars(select(TABLE.c.id))) == []
    await savepoint.rollback()
    for organization_id, endpoint_id in zip(
        webhooks.organizations, webhooks.endpoints, strict=True
    ):
        await set_tenant_context(db_session, organization_id)
        assert list(await db_session.scalars(select(TABLE.c.id))) == [endpoint_id]


async def test_resolver_returns_active_endpoint_without_tenant_context(
    db_session: AsyncSession,
    webhooks: WebhookData,
) -> None:
    row = (
        await db_session.execute(
            text(
                """
                SELECT id, organization_id, secret_ciphertext
                FROM public.relaymaid_resolve_webhook_endpoint(:public_id)
                """
            ),
            {"public_id": webhooks.public_ids[0]},
        )
    ).one()

    assert row == (
        webhooks.endpoints[0],
        webhooks.organizations[0],
        "test-ciphertext",
    )


@pytest.mark.parametrize("lookup", ["unknown", "internal_id", "disabled"])
async def test_resolver_hides_unavailable_endpoints(
    db_session: AsyncSession, webhooks: WebhookData, lookup: str
) -> None:
    public_id = uuid4()
    if lookup == "internal_id":
        public_id = webhooks.endpoints[0]
    elif lookup == "disabled":
        await set_tenant_context(db_session, webhooks.organizations[0])
        await db_session.execute(update(TABLE).values(enabled=False))
        public_id = webhooks.public_ids[0]
    assert (
        list(
            await db_session.execute(
                text(
                    "SELECT * FROM "
                    "public.relaymaid_resolve_webhook_endpoint(:public_id)"
                ),
                {"public_id": public_id},
            )
        )
        == []
    )


async def test_resolver_can_find_other_tenant_without_exposing_direct_reads(
    db_session: AsyncSession, webhooks: WebhookData
) -> None:
    from relaymaid.services.webhook_ingestion import resolve_webhook_endpoint

    await set_tenant_context(db_session, webhooks.organizations[0])
    resolved = await resolve_webhook_endpoint(db_session, webhooks.public_ids[1])
    assert resolved is not None
    assert resolved.id == webhooks.endpoints[1]
    assert resolved.organization_id == webhooks.organizations[1]
    assert resolved.secret_ciphertext == "test-ciphertext"
    assert list(await db_session.scalars(select(TABLE.c.id))) == [webhooks.endpoints[0]]


async def test_table_owner_can_read_enabled_endpoints_but_cannot_write_other_tenant(
    db_session: AsyncSession, webhooks: WebhookData
) -> None:
    await set_tenant_context(db_session, webhooks.organizations[1])
    await db_session.execute(update(TABLE).values(enabled=False))
    await db_session.execute(
        text("SELECT set_config('relaymaid.organization_id', '', true)")
    )
    await db_session.execute(text("SET LOCAL ROLE relaymaid_migrator"))
    await assert_role(db_session, "relaymaid_migrator")
    assert list(await db_session.scalars(select(TABLE.c.id))) == [webhooks.endpoints[0]]
    assert (
        list(
            await db_session.scalars(
                update(TABLE).values(name="Blocked").returning(TABLE.c.id)
            )
        )
        == []
    )
    assert list(await db_session.scalars(delete(TABLE).returning(TABLE.c.id))) == []
    await set_tenant_context(db_session, webhooks.organizations[1])
    assert set(await db_session.scalars(select(TABLE.c.id))) == set(webhooks.endpoints)
    assert (
        list(
            await db_session.scalars(
                update(TABLE)
                .where(TABLE.c.id == webhooks.endpoints[0])
                .values(name="Blocked")
                .returning(TABLE.c.id)
            )
        )
        == []
    )
    assert (
        list(
            await db_session.scalars(
                delete(TABLE)
                .where(TABLE.c.id == webhooks.endpoints[0])
                .returning(TABLE.c.id)
            )
        )
        == []
    )


async def test_resolver_requires_owner_select_policy(
    db_session: AsyncSession, webhooks: WebhookData
) -> None:
    savepoint = await db_session.begin_nested()
    try:
        await db_session.execute(text("SET LOCAL ROLE relaymaid_migrator"))
        await db_session.execute(
            text(
                "DROP POLICY webhook_endpoints_resolver_owner_select "
                "ON webhook_endpoints"
            )
        )
        await db_session.execute(text("SET LOCAL ROLE relaymaid_app"))
        rows = await db_session.execute(
            text("SELECT * FROM public.relaymaid_resolve_webhook_endpoint(:public_id)"),
            {"public_id": webhooks.public_ids[0]},
        )
        assert list(rows) == []
    finally:
        await savepoint.rollback()
