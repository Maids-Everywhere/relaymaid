from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from relaymaid.config import get_settings
from relaymaid.db.engine import create_db_engine
from relaymaid.db.session import create_session_factory


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)

    app.state.db_engine = engine
    app.state.db_session_factory = session_factory

    try:
        yield
    finally:
        await engine.dispose()
