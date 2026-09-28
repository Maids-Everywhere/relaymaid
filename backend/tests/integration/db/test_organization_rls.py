from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from relaymaid.db.tenant_context import set_tenant_context

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


async def assert_unprivileged_app_role(session: AsyncSession) -> None:
    role = (
        await session.execute(
            text(
                """
                SELECT current_user, rolsuper, rolbypassrls
                FROM pg_roles
                WHERE rolname = current_user
                """
            )
        )
    ).one()
    table_owner = await session.scalar(
        text(
            """
            SELECT pg_get_userbyid(relowner)
            FROM pg_class
            WHERE oid = 'public.organizations'::regclass
            """
        )
    )

    assert role.current_user == "relaymaid_app"
    assert role.rolsuper is False
    assert role.rolbypassrls is False
    assert table_owner == "relaymaid_migrator"


@pytest.fixture(params=[False, True], ids=["app_role", "table_owner"])
async def organizations(
    db_session: AsyncSession, request: pytest.FixtureRequest
) -> tuple[UUID, UUID]:
    """Seed as admin, then switch to a role subject to RLS.

    The enclosing transaction rolls back data, grants, ownership, and both roles.
    The owner case also verifies FORCE ROW LEVEL SECURITY.
    """
    first, second = uuid4(), uuid4()
    await db_session.execute(
        text(
            "INSERT INTO organizations (id, name) VALUES (:first, 'A'), (:second, 'B')"
        ),
        {"first": first, "second": second},
    )
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
        text("GRANT SELECT, INSERT, UPDATE, DELETE ON organizations TO relaymaid_app")
    )
    await db_session.execute(
        text("ALTER TABLE organizations OWNER TO relaymaid_migrator")
    )
    await db_session.execute(text("SET LOCAL ROLE relaymaid_app"))
    await assert_unprivileged_app_role(db_session)

    if request.param:
        # Exercise FORCE RLS separately, after validating the app role setup.
        await db_session.execute(text("SET LOCAL ROLE relaymaid_migrator"))
        role = (
            await db_session.execute(
                text(
                    "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles "
                    "WHERE rolname = current_user"
                )
            )
        ).one()
        assert role.current_user == "relaymaid_migrator"
        assert role.rolsuper is False
        assert role.rolbypassrls is False
    return first, second


async def test_select_only_current_organization(
    db_session: AsyncSession, organizations: tuple[UUID, UUID]
) -> None:
    for organization_id in organizations:
        await set_tenant_context(db_session, organization_id)
        assert list(await db_session.scalars(text("SELECT id FROM organizations"))) == [
            organization_id
        ]


@pytest.mark.parametrize("context", ["missing", "empty", "unknown"])
async def test_without_matching_context_cannot_read_or_modify_rows(
    db_session: AsyncSession, organizations: tuple[UUID, UUID], context: str
) -> None:
    if context == "empty":
        await db_session.execute(
            text("SELECT set_config('relaymaid.organization_id', '', true)")
        )
    elif context == "unknown":
        await set_tenant_context(db_session, uuid4())
    assert list(await db_session.scalars(text("SELECT id FROM organizations"))) == []
    assert (
        list(
            await db_session.scalars(
                text("UPDATE organizations SET name = 'Blocked' RETURNING id")
            )
        )
        == []
    )
    assert (
        list(await db_session.scalars(text("DELETE FROM organizations RETURNING id")))
        == []
    )
    for organization_id, expected_name in zip(organizations, ("A", "B"), strict=True):
        await set_tenant_context(db_session, organization_id)
        assert (
            await db_session.scalar(text("SELECT name FROM organizations"))
            == expected_name
        )


async def test_update_and_delete_only_affect_current_organization(
    db_session: AsyncSession, organizations: tuple[UUID, UUID]
) -> None:
    first, second = organizations
    await set_tenant_context(db_session, first)
    assert list(
        await db_session.scalars(
            text("UPDATE organizations SET name = 'Updated' RETURNING id")
        )
    ) == [first]
    assert await db_session.scalar(text("SELECT name FROM organizations")) == "Updated"
    assert list(
        await db_session.scalars(text("DELETE FROM organizations RETURNING id"))
    ) == [first]
    assert await db_session.scalar(text("SELECT id FROM organizations")) is None
    await set_tenant_context(db_session, second)
    assert await db_session.scalar(text("SELECT name FROM organizations")) == "B"


async def test_insert_with_matching_context_succeeds(
    db_session: AsyncSession, organizations: tuple[UUID, UUID]
) -> None:
    organization_id = uuid4()
    await set_tenant_context(db_session, organization_id)
    assert (
        await db_session.scalar(
            text(
                "INSERT INTO organizations (id, name) VALUES (:id, 'New') RETURNING id"
            ),
            {"id": organization_id},
        )
        == organization_id
    )


@pytest.mark.parametrize("context", ["missing", "empty", "other_tenant"])
async def test_insert_without_matching_context_is_rejected(
    db_session: AsyncSession, organizations: tuple[UUID, UUID], context: str
) -> None:
    if context == "other_tenant":
        await set_tenant_context(db_session, organizations[0])
    elif context == "empty":
        await db_session.execute(
            text("SELECT set_config('relaymaid.organization_id', '', true)")
        )
    with pytest.raises(DBAPIError, match="row-level security policy") as error:
        async with db_session.begin_nested():
            await db_session.execute(
                text("INSERT INTO organizations (id, name) VALUES (:id, 'Blocked')"),
                {"id": uuid4()},
            )
    assert getattr(error.value.orig, "sqlstate", None) == "42501"


async def test_cannot_change_organization_id_to_escape_tenant(
    db_session: AsyncSession, organizations: tuple[UUID, UUID]
) -> None:
    await set_tenant_context(db_session, organizations[0])
    with pytest.raises(DBAPIError, match="row-level security policy") as error:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE organizations SET id = :id"), {"id": uuid4()}
            )
    assert getattr(error.value.orig, "sqlstate", None) == "42501"
    assert (
        await db_session.scalar(text("SELECT id FROM organizations"))
        == organizations[0]
    )
