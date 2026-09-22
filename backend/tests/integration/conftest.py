from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
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
    alembic_config.attributes["database_url"] = postgres_url
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
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:

    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(
    db_engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.state.db_engine = db_engine
    app.state.db_session_factory = session_factory
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    async with session_factory.begin() as session:
        await session.execute(delete(Membership))
        await session.execute(delete(User))
        await session.execute(delete(Organization))
