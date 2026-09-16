from unittest.mock import AsyncMock, Mock, patch

import pytest

from relaymaid.main import create_app


@pytest.mark.anyio
async def test_lifespan_creates_and_disposes_engine() -> None:
    engine = Mock()
    engine.dispose = AsyncMock()
    session_factory = Mock()

    with (
        patch(
            "relaymaid.lifespan.create_db_engine",
            return_value=engine,
        ),
        patch(
            "relaymaid.lifespan.create_session_factory", return_value=session_factory
        ),
    ):
        app = create_app()

        async with app.router.lifespan_context(app):
            assert app.state.db_engine is engine
            assert app.state.db_session_factory is session_factory
            engine.dispose.assert_not_awaited()

        engine.dispose.assert_awaited_once()
