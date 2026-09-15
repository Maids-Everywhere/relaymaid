from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["relaymaid"]


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report process health without checking external dependencies."""
    return HealthResponse(status="ok", service="relaymaid")
