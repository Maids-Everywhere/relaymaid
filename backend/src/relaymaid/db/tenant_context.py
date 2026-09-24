from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_SET_CONTEXT_SQL = text(
    """
    SELECT set_config(
        :setting_name,
        :setting_value,
        true
    )
    """
)


async def set_user_context(session: AsyncSession, user_id: UUID):
    if not session.in_transaction():
        raise RuntimeError("User context requires an active transaction")

    await session.execute(
        _SET_CONTEXT_SQL,
        {
            "setting_name": "relaymaid.user_id",
            "setting_value": str(user_id),
        },
    )


async def set_tenant_context(
    session: AsyncSession,
    organization_id: UUID,
) -> None:
    """Set the active organization for the current transaction."""
    if not session.in_transaction():
        raise RuntimeError("Tenant context requires an active transaction")

    await session.execute(
        _SET_CONTEXT_SQL,
        {
            "setting_name": "relaymaid.organization_id",
            "setting_value": str(organization_id),
        },
    )
