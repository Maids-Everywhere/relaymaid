import pytest
from httpx import ASGITransport, AsyncClient

from relaymaid.main import create_app


@pytest.mark.anyio
async def test_health_live_returns_service_status() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "relaymaid"}
