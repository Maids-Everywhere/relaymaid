from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from relaymaid.db.tenant_context import set_tenant_context, set_user_context

ContextSetter = Callable[[AsyncSession, UUID], Awaitable[None]]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("set_context", "setting_name"),
    [
        (set_user_context, "relaymaid.user_id"),
        (set_tenant_context, "relaymaid.organization_id"),
    ],
)
async def test_set_context_sets_transaction_local_config(
    set_context: ContextSetter,
    setting_name: str,
) -> None:
    session = MagicMock(spec=AsyncSession)
    session.in_transaction.return_value = True
    session.execute = AsyncMock()
    context_id = uuid4()

    await set_context(session, context_id)

    session.execute.assert_awaited_once()
    statement, parameters = session.execute.await_args.args
    assert "set_config" in str(statement)
    assert parameters == {
        "setting_name": setting_name,
        "setting_value": str(context_id),
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("set_context", "error_message"),
    [
        (set_user_context, "User context requires an active transaction"),
        (set_tenant_context, "Tenant context requires an active transaction"),
    ],
)
async def test_set_context_requires_active_transaction(
    set_context: ContextSetter,
    error_message: str,
) -> None:
    session = MagicMock(spec=AsyncSession)
    session.in_transaction.return_value = False
    session.execute = AsyncMock()

    with pytest.raises(RuntimeError, match=error_message):
        await set_context(session, uuid4())

    session.execute.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("set_context", [set_user_context, set_tenant_context])
async def test_set_context_propagates_database_failure(
    set_context: ContextSetter,
) -> None:
    session = MagicMock(spec=AsyncSession)
    session.in_transaction.return_value = True
    session.execute = AsyncMock(side_effect=RuntimeError("database failure"))

    with pytest.raises(RuntimeError, match="database failure"):
        await set_context(session, uuid4())

    session.execute.assert_awaited_once()


async def read_setting(session: AsyncSession, setting_name: str) -> str | None:
    return await session.scalar(
        text("SELECT NULLIF(current_setting(:setting_name, true), '')"),
        {"setting_name": setting_name},
    )


@pytest.mark.integration
@pytest.mark.anyio
@pytest.mark.parametrize(
    ("set_context", "setting_name"),
    [
        (set_user_context, "relaymaid.user_id"),
        (set_tenant_context, "relaymaid.organization_id"),
    ],
)
@pytest.mark.parametrize("transaction_end", ["commit", "rollback"])
async def test_set_context_expires_when_transaction_ends(
    db_session: AsyncSession,
    set_context: ContextSetter,
    setting_name: str,
    transaction_end: str,
) -> None:
    context_id = uuid4()
    transaction = await db_session.begin()

    await set_context(db_session, context_id)
    assert await read_setting(db_session, setting_name) == str(context_id)

    if transaction_end == "commit":
        await transaction.commit()
    else:
        await transaction.rollback()

    assert await read_setting(db_session, setting_name) is None
