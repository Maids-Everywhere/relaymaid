from fastapi import FastAPI

from relaymaid.api.routes.health import router as health_router
from relaymaid.lifespan import lifespan


def create_app() -> FastAPI:
    app = FastAPI(
        title="RelayMaid API",
        description="Reliable webhook delivery for multi-tenant applications.",
        version="0.1.0",
        lifespan=lifespan
    )
    app.include_router(health_router)
    return app


app = create_app()
