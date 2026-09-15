from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from relaymaid.config import Settings


def create_db_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
    )
