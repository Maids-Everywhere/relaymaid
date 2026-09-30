from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.community.postgres import PostgresContainer

from relaymaid.db.models import Membership, Organization, User
from relaymaid.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    with PostgresContainer("postgres:17-alpine") as postgres:
        sync_url = postgres.get_connection_url()

        yield sync_url.replace(
            "postgresql+psycopg2",
            "postgresql+psycopg",
        )


@pytest.fixture(scope="session")
def migrated_postgres_url(
    postgres_url: str,
) -> Iterator[str]:
    alembic_config = Config(BACKEND_ROOT / "alembic.ini")
    alembic_config.attributes["migration_database_url"] = postgres_url
    alembic_config.set_main_option(
        "sqlalchemy.url",
        postgres_url,
    )

    command.upgrade(alembic_config, "head")

    yield postgres_url


@pytest.fixture
async def db_engine(
    migrated_postgres_url: str,
) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_postgres_url)

    yield engine

    await engine.dispose()


@pytest.fixture
def session_factory(
    db_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        db_engine,
        expire_on_commit=False,
    )


@pytest.fixture
async def raw_db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Provide a session for tests that manage transaction boundaries themselves."""
    async with session_factory() as session:
        yield session


@pytest.fixture
async def db_session(
    raw_db_session: AsyncSession,
) -> AsyncIterator[AsyncSession]:
    """Provide an active transaction and roll back test data during teardown.

    Use raw_db_session when testing explicit commit or rollback boundaries.
    """
    await raw_db_session.begin()
    try:
        yield raw_db_session
    finally:
        await raw_db_session.rollback()


@pytest.fixture
async def client(
    app_db_engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.state.db_engine = app_db_engine
    app.state.db_session_factory = async_sessionmaker(
        app_db_engine, expire_on_commit=False
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    async with session_factory.begin() as session:
        await session.execute(delete(Membership))
        await session.execute(delete(User))
        await session.execute(delete(Organization))


@pytest.fixture
async def app_db_engine(
    db_engine: AsyncEngine,
) -> AsyncIterator[AsyncEngine]:
    """Use an actual unprivileged login for requests; keep admin access for cleanup."""
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "CREATE ROLE relaymaid_app LOGIN PASSWORD 'test_app_password' "
                "NOSUPERUSER NOBYPASSRLS"
            )
        )
        await connection.execute(
            text("CREATE ROLE relaymaid_migrator NOLOGIN NOSUPERUSER NOBYPASSRLS")
        )
        await connection.execute(
            text("GRANT USAGE ON SCHEMA public TO relaymaid_app, relaymaid_migrator")
        )
        await connection.execute(
            text(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
                "TO relaymaid_app"
            )
        )
        for table in ("organizations", "memberships"):
            await connection.execute(
                text(f"ALTER TABLE {table} OWNER TO relaymaid_migrator")
            )
    engine = create_async_engine(
        db_engine.url.set(username="relaymaid_app", password="test_app_password"),
        pool_size=1,
        max_overflow=0,
    )
    try:
        async with engine.connect() as connection:
            role = (
                await connection.execute(
                    text(
                        "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles "
                        "WHERE rolname = current_user"
                    )
                )
            ).one()
            assert role == ("relaymaid_app", False, False)
            owners = list(
                await connection.scalars(
                    text(
                        "SELECT pg_get_userbyid(relowner) FROM pg_class "
                        "WHERE oid IN ('public.organizations'::regclass, "
                        "'public.memberships'::regclass)"
                    )
                )
            )
            assert owners == ["relaymaid_migrator", "relaymaid_migrator"]
        yield engine
    finally:
        await engine.dispose()
        async with db_engine.begin() as connection:
            await connection.execute(
                text("REASSIGN OWNED BY relaymaid_migrator TO CURRENT_USER")
            )
            await connection.execute(text("DROP OWNED BY relaymaid_app"))
            await connection.execute(text("DROP OWNED BY relaymaid_migrator"))
            await connection.execute(
                text("DROP ROLE relaymaid_app, relaymaid_migrator")
            )
