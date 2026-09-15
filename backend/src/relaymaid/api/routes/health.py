from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from relaymaid.db.dependencies import get_db_engine

router = APIRouter(tags=["health"], prefix="/health")
DatabaseEngine = Annotated[AsyncEngine, Depends(get_db_engine)]


class LiveResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["relaymaid"]


class ReadinessResponse(BaseModel):
    status: Literal["ready"]


@router.get("/live", response_model=LiveResponse)
async def health() -> LiveResponse:
    """Report process health without checking external dependencies."""
    return LiveResponse(status="ok", service="relaymaid")


@router.get("/ready", response_model=ReadinessResponse)
async def health_ready(engine: DatabaseEngine) -> ReadinessResponse:
    """Report process readiness without checking external dependencies."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed",
        ) from error

    return ReadinessResponse(status="ready")
