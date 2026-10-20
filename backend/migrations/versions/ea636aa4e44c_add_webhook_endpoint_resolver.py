"""add webhook endpoint resolver

Revision ID: ea636aa4e44c
Revises: 059e21cdb12c
Create Date: 2026-10-20 18:31:43.215842

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ea636aa4e44c"
down_revision: str | Sequence[str] | None = "059e21cdb12c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE POLICY webhook_endpoints_resolver_owner_select
        ON webhook_endpoints
        FOR SELECT
        USING (
            enabled AND current_user = pg_catalog.pg_get_userbyid(
                (
                    SELECT relowner
                    FROM pg_catalog.pg_class
                    WHERE oid = 'public.webhook_endpoints'::regclass
                )
            )
        )
        """
    )

    op.execute(
        """
        CREATE FUNCTION public.relaymaid_resolve_webhook_endpoint(
            p_public_id uuid
        )
        RETURNS TABLE (
            id uuid,
            organization_id uuid,
            secret_ciphertext text
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        SELECT
            endpoint.id,
            endpoint.organization_id,
            endpoint.secret_ciphertext
        FROM public.webhook_endpoints AS endpoint
        WHERE endpoint.public_id = p_public_id
          AND endpoint.enabled IS TRUE
        $function$
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        DROP FUNCTION IF EXISTS public.relaymaid_resolve_webhook_endpoint(uuid)
        """
    )
    op.execute(
        """
        DROP POLICY IF EXISTS webhook_endpoints_resolver_owner_select ON webhook_endpoints
        """
    )
