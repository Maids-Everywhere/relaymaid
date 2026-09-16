import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from relaymaid.config import Settings
from relaymaid.db.engine import create_db_engine
from relaymaid.db.session import create_session_factory


@pytest.mark.anyio
async def test_session_factory_create_async_session():
    settings = Settings(
        database_url="postgresql+psycopg://user:password@localhost/test_db"
    )

    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)

    try:
        async with session_factory() as session:
            assert isinstance(session, AsyncSession)
            assert session.bind is engine
    finally:
        await engine.dispose()
