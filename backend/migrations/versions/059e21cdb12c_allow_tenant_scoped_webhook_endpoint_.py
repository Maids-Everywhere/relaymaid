"""allow tenant scoped webhook endpoint deletes

Revision ID: 059e21cdb12c
Revises: 22ea746a840d
Create Date: 2026-10-20 16:44:14.853800

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "059e21cdb12c"
down_revision: str | Sequence[str] | None = "22ea746a840d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        CREATE POLICY webhook_endpoints_delete_own
        ON webhook_endpoints
        FOR DELETE
        USING (
            organization_id = public.relaymaid_current_organization_id()
        )
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("""
        DROP POLICY webhook_endpoints_delete_own
        ON webhook_endpoints
    """)
