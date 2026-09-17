from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from relaymaid.config import get_settings
from relaymaid.db.engine import create_db_engine
from relaymaid.db.session import create_session_factory


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession]:
    """
    Fixture that provides an AsyncSession for database tests.

    This fixture creates a new AsyncSession for each test, ensuring that
    database operations are isolated and do not affect other tests. The session
    is rolled back after each test to maintain a clean state.

    Yields:
        AsyncSession: An asynchronous SQLAlchemy session for database operations.
    """
    settings = get_settings()
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)

    try:
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.rollback()
    finally:
        await engine.dispose()
