"""enable rls for memberships

Revision ID: 8fb97b5600aa
Revises: 0b9b0fd0fadf
Create Date: 2026-09-29 19:29:54.841192

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8fb97b5600aa"
down_revision: str | Sequence[str] | None = "0b9b0fd0fadf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION public.relaymaid_current_user_id()
        RETURNS uuid
        LANGUAGE sql
        STABLE
        as $function$
            SELECT NULLIF(
                current_setting('relaymaid.user_id', true),
                ''
            )::uuid
        $function$
        """
    )

    op.execute(
        """
        ALTER TABLE memberships
        ENABLE ROW LEVEL SECURITY
        """
    )

    op.execute(
        """
        ALTER TABLE memberships
        FORCE ROW LEVEL SECURITY
        """
    )

    op.execute(
        """
        CREATE POLICY membership_select_own
        ON memberships
        FOR SELECT
        USING (
            user_id = public.relaymaid_current_user_id()
            AND (
                public.relaymaid_current_organization_id() IS NULL
                OR organization_id = public.relaymaid_current_organization_id()
            )
        )
        """
    )

    op.execute(
        """
        CREATE POLICY membership_insert_self
        ON memberships
        FOR INSERT
        WITH CHECK (
            user_id = public.relaymaid_current_user_id()
            AND organization_id = public.relaymaid_current_organization_id()
        )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        DROP POLICY membership_insert_self
        ON memberships
        """
    )

    op.execute(
        """
        DROP POLICY membership_select_own
        ON memberships
        """
    )

    op.execute(
        """
        ALTER TABLE memberships
        NO FORCE ROW LEVEL SECURITY
        """
    )

    op.execute(
        """
        ALTER TABLE memberships
        DISABLE ROW LEVEL SECURITY
        """
    )

    op.execute(
        """
        DROP FUNCTION public.relaymaid_current_user_id()
        """
    )
