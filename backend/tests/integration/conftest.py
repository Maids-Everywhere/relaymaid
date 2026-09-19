from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.community.postgres import PostgresContainer

from relaymaid.db.dependencies import get_db_engine, get_db_session
from relaymaid.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    with PostgresContainer() as postgres:
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
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_engine] = lambda: db_engine
    app.dependency_overrides[get_db_session] = override_db_session
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
