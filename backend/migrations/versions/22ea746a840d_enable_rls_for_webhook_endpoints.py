"""enable rls for webhook endpoints

Revision ID: 22ea746a840d
Revises: 6ab4c49ed5e4
Create Date: 2026-10-05 18:18:50.919190

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "22ea746a840d"
down_revision: str | Sequence[str] | None = "6ab4c49ed5e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        ALTER TABLE webhook_endpoints
        ENABLE ROW LEVEL SECURITY
        """
    )

    op.execute(
        """
        ALTER TABLE webhook_endpoints
        FORCE ROW LEVEL SECURITY
        """
    )

    op.execute(
        """
        CREATE POLICY webhook_endpoints_select_own
        ON webhook_endpoints
        FOR SELECT
        USING (
            organization_id = public.relaymaid_current_organization_id()
        )
        """
    )

    op.execute(
        """
        CREATE POLICY webhook_endpoints_insert_own
        ON webhook_endpoints
        FOR INSERT
        WITH CHECK (
            organization_id = public.relaymaid_current_organization_id()
        )
        """
    )

    op.execute(
        """
        CREATE POLICY webhook_endpoints_update_own
        ON webhook_endpoints
        FOR UPDATE
        USING (
            organization_id =
                public.relaymaid_current_organization_id()
        )
        WITH CHECK (
            organization_id =
                public.relaymaid_current_organization_id()
        )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        DROP POLICY webhook_endpoints_insert_own
        ON webhook_endpoints
        """
    )

    op.execute(
        """
        DROP POLICY webhook_endpoints_select_own
        ON webhook_endpoints
        """
    )

    op.execute(
        """
        DROP POLICY webhook_endpoints_update_own
        ON webhook_endpoints
        """
    )

    op.execute(
        """
        ALTER TABLE webhook_endpoints
        NO FORCE ROW LEVEL SECURITY
        """
    )

    op.execute(
        """
        ALTER TABLE webhook_endpoints
        DISABLE ROW LEVEL SECURITY
        """
    )
