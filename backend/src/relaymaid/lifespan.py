from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from relaymaid.config import get_settings
from relaymaid.db.engine import create_db_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    print("Starting up...")
    settings = get_settings()
    engine = create_db_engine(settings)

    app.state.db_engine = engine

    try:
        yield
    finally:
        await engine.dispose()
