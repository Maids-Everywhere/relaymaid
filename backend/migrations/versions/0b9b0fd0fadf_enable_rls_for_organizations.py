"""enable rls for organizations

Revision ID: 0b9b0fd0fadf
Revises: 190c6e2489b7
Create Date: 2026-09-28 11:30:52.005609

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0b9b0fd0fadf"
down_revision: str | Sequence[str] | None = "190c6e2489b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE FUNCTION public.relaymaid_current_organization_id()
        RETURNS uuid
        LANGUAGE sql
        STABLE
        AS $function$
            SELECT NULLIF(
                current_setting('relaymaid.organization_id', true),
                ''
            )::uuid
        $function$
        """
    )

    op.execute(
        """
        ALTER TABLE organizations
        ENABLE ROW LEVEL SECURITY
        """
    )

    op.execute(
        """
        ALTER TABLE organizations
        FORCE ROW LEVEL SECURITY
        """
    )

    op.execute(
        """
        CREATE POLICY organizations_select_own
        ON organizations
        FOR SELECT
        USING (
            id = public.relaymaid_current_organization_id()
        )
        """
    )

    op.execute(
        """
        CREATE POLICY organizations_insert_own
        ON organizations
        FOR INSERT
        WITH CHECK (
            id = public.relaymaid_current_organization_id()
        );
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        DROP POLICY organizations_select_own
        ON organizations
        """
    )

    op.execute(
        """
        DROP POLICY organizations_insert_own
        ON organizations
        """
    )

    op.execute(
        """
        ALTER TABLE organizations
        NO FORCE ROW LEVEL SECURITY
        """
    )

    op.execute(
        """
        ALTER TABLE organizations
        DISABLE ROW LEVEL SECURITY
        """
    )

    op.execute(
        """
        DROP FUNCTION public.relaymaid_current_organization_id()
        """
    )
