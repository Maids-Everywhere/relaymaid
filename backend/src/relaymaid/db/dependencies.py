from typing import cast

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine


def get_db_engine(request: Request) -> AsyncEngine:
    return cast(AsyncEngine, request.app.state.db_engine)
