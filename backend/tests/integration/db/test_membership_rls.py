from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from relaymaid.db.tenant_context import set_tenant_context, set_user_context

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@dataclass
class MembershipData:
    users: tuple[UUID, UUID]
    organizations: tuple[UUID, UUID, UUID]


@pytest.fixture(params=["relaymaid_app", "relaymaid_migrator"])
async def memberships(
    db_session: AsyncSession, request: pytest.FixtureRequest
) -> MembershipData:
    """Roll back seeded data, roles, grants and ownership with the test transaction."""
    data = MembershipData((uuid4(), uuid4()), (uuid4(), uuid4(), uuid4()))
    for user_id in data.users:
        await db_session.execute(
            text(
                "INSERT INTO users (id, email, hashed_password) VALUES (:id, "
                ":email, 'unused')"
            ),
            {"id": user_id, "email": f"{user_id}@example.com"},
        )
    for organization_id in data.organizations:
        await db_session.execute(
            text("INSERT INTO organizations (id, name) VALUES (:id, 'RLS test')"),
            {"id": organization_id},
        )
    for user_id in data.users:
        for organization_id in data.organizations[:2]:
            await db_session.execute(
                text(
                    "INSERT INTO memberships (id, user_id, organization_id, "
                    "role) VALUES (:id, :user, :org, 'viewer')"
                ),
                {"id": uuid4(), "user": user_id, "org": organization_id},
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
        text("GRANT SELECT, INSERT, UPDATE, DELETE ON memberships TO relaymaid_app")
    )
    await db_session.execute(
        text("ALTER TABLE memberships OWNER TO relaymaid_migrator")
    )
    await db_session.execute(text("SET LOCAL ROLE relaymaid_app"))
    await assert_unprivileged_role(db_session, "relaymaid_app")
    if request.param == "relaymaid_migrator":
        await db_session.execute(text("SET LOCAL ROLE relaymaid_migrator"))
        await assert_unprivileged_role(db_session, "relaymaid_migrator")
    return data


async def assert_unprivileged_role(session: AsyncSession, expected_role: str) -> None:
    role = (
        await session.execute(
            text(
                "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles "
                "WHERE rolname = current_user"
            )
        )
    ).one()
    assert role.current_user == expected_role
    assert role.rolsuper is False
    assert role.rolbypassrls is False
    assert (
        await session.scalar(
            text(
                "SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid = "
                "'public.memberships'::regclass"
            )
        )
        == "relaymaid_migrator"
    )


async def set_contexts(
    session: AsyncSession,
    data: MembershipData,
    user_context: str,
    org_context: str,
    matching_org: UUID,
) -> None:
    if user_context == "own":
        await set_user_context(session, data.users[0])
    elif user_context == "other":
        await set_user_context(session, data.users[1])
    elif user_context == "unknown":
        await set_user_context(session, uuid4())
    elif user_context == "empty":
        await session.execute(text("SELECT set_config('relaymaid.user_id', '', true)"))
    if org_context == "matching":
        await set_tenant_context(session, matching_org)
    elif org_context == "other":
        await set_tenant_context(session, data.organizations[1])
    elif org_context == "unknown":
        await set_tenant_context(session, uuid4())
    elif org_context == "empty":
        await session.execute(
            text("SELECT set_config('relaymaid.organization_id', '', true)")
        )


@pytest.mark.parametrize(
    "user_context", ["own", "other", "missing", "empty", "unknown"]
)
@pytest.mark.parametrize(
    "org_context", ["matching", "other", "missing", "empty", "unknown"]
)
async def test_select_memberships_scopes_user_and_optional_organization(
    db_session: AsyncSession,
    memberships: MembershipData,
    user_context: str,
    org_context: str,
) -> None:
    await set_contexts(
        db_session, memberships, user_context, org_context, memberships.organizations[0]
    )
    rows = set(
        (
            await db_session.execute(
                text("SELECT user_id, organization_id FROM memberships")
            )
        ).all()
    )
    expected = set()
    if user_context in {"own", "other"} and org_context != "unknown":
        user_id = memberships.users[user_context == "other"]
        orgs = memberships.organizations[:2]
        if org_context == "matching":
            orgs = orgs[:1]
        elif org_context == "other":
            orgs = orgs[1:]
        expected = {(user_id, org) for org in orgs}
    assert rows == expected


@pytest.mark.parametrize(
    "user_context", ["own", "other", "missing", "empty", "unknown"]
)
@pytest.mark.parametrize(
    "org_context", ["matching", "other", "missing", "empty", "unknown"]
)
async def test_insert_membership_requires_self_and_optional_matching_organization(
    db_session: AsyncSession,
    memberships: MembershipData,
    user_context: str,
    org_context: str,
) -> None:
    target_org = memberships.organizations[2]
    await set_contexts(db_session, memberships, user_context, org_context, target_org)
    statement = text(
        "INSERT INTO memberships (id, user_id, organization_id, role) VALUES "
        "(:id, :user, :org, 'viewer') RETURNING id"
    )
    parameters = {"id": uuid4(), "user": memberships.users[0], "org": target_org}
    if user_context == "own" and org_context in {"matching", "missing", "empty"}:
        assert await db_session.scalar(statement, parameters) == parameters["id"]
    else:
        with pytest.raises(DBAPIError, match="row-level security policy") as error:
            async with db_session.begin_nested():
                await db_session.execute(statement, parameters)
        assert getattr(error.value.orig, "sqlstate", None) == "42501"
        await set_user_context(db_session, memberships.users[0])
        await set_tenant_context(db_session, target_org)
        assert await db_session.scalar(text("SELECT id FROM memberships")) is None


@pytest.mark.parametrize("operation", ["update", "delete"])
@pytest.mark.parametrize(
    "user_context", ["own", "other", "missing", "empty", "unknown"]
)
async def test_memberships_cannot_be_updated_or_deleted(
    db_session: AsyncSession,
    memberships: MembershipData,
    operation: str,
    user_context: str,
) -> None:
    await set_contexts(
        db_session, memberships, user_context, "missing", memberships.organizations[0]
    )
    statement = (
        "UPDATE memberships SET role = 'owner' RETURNING id"
        if operation == "update"
        else "DELETE FROM memberships RETURNING id"
    )
    assert list(await db_session.scalars(text(statement))) == []
    for user_id in memberships.users:
        await set_user_context(db_session, user_id)
        assert list(await db_session.scalars(text("SELECT role FROM memberships"))) == [
            "viewer",
            "viewer",
        ]
