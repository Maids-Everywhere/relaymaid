import pytest
from httpx import ASGITransport, AsyncClient

from relaymaid.main import create_app


@pytest.mark.anyio
async def test_health_ready_returns_service_status() -> None:
    app = create_app()
    transport = ASGITransport(app=app)

    async with app.router.lifespan_context(app), AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}