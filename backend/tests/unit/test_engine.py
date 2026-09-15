import pytest

from relaymaid.config import Settings
from relaymaid.db.engine import create_db_engine


@pytest.mark.anyio
async def test_create_db_engine_uses_configured_url() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:password@database:5432/test_db"
    )

    engine = create_db_engine(settings)

    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.url.host == "database"
        assert engine.url.port == 5432
        assert engine.url.database == "test_db"
    finally:
        await engine.dispose()