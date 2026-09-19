import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_health_ready_returns_service_status(client: AsyncClient) -> None:
    response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
