from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import insert, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from relaymaid.db.models import Organization
from relaymaid.db.models.webhook import WebhookEndpoint
from relaymaid.db.tenant_context import set_tenant_context
from relaymaid.security.webhook_secrets import WebhookSecretManager
from relaymaid.services.webhook_endpoints import create_webhook_endpoint

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
async def organization_id(db_session: AsyncSession) -> UUID:
    organization_id = uuid4()
    await db_session.execute(
        insert(Organization).values(id=organization_id, name="Test")
    )
    await db_session.execute(
        text("CREATE ROLE webhook_service_test NOSUPERUSER NOBYPASSRLS NOLOGIN")
    )
    await db_session.execute(
        text("GRANT USAGE ON SCHEMA public TO webhook_service_test")
    )
    await db_session.execute(
        text("GRANT SELECT, INSERT ON webhook_endpoints TO webhook_service_test")
    )
    await db_session.execute(text("SET LOCAL ROLE webhook_service_test"))
    role = (
        await db_session.execute(
            text(
                "SELECT rolsuper, rolbypassrls FROM pg_roles "
                "WHERE rolname = current_user"
            )
        )
    ).one()
    assert role == (False, False)
    return organization_id


@pytest.fixture
def secret_manager() -> WebhookSecretManager:
    return WebhookSecretManager(Fernet.generate_key().decode())


@pytest.mark.parametrize("retry_limit", [0, 3, 10])
async def test_create_persists_encrypted_endpoint_with_generated_defaults(
    db_session: AsyncSession,
    organization_id: UUID,
    secret_manager: WebhookSecretManager,
    retry_limit: int,
) -> None:
    await set_tenant_context(db_session, organization_id)
    results = []
    for _ in range(2):
        result = await create_webhook_endpoint(
            db_session,
            organization_id=organization_id,
            name="a" * 255,
            destination_url="https://example.com/events",
            retry_limit=retry_limit,
            secret_manager=secret_manager,
        )
        endpoint = result.endpoint
        assert isinstance(endpoint.id, UUID)
        assert isinstance(endpoint.public_id, UUID)
        assert endpoint.enabled is True
        assert endpoint.created_at is not None
        # Reload to verify stored values, rather than only the constructed object.
        await db_session.refresh(endpoint)
        assert endpoint.organization_id == organization_id
        assert endpoint.name == "a" * 255
        assert endpoint.destination_url == "https://example.com/events"
        assert endpoint.retry_limit == retry_limit
        assert endpoint.secret_ciphertext != result.secret
        assert secret_manager.decrypt(endpoint.secret_ciphertext) == result.secret
        results.append(result)
    assert results[0].endpoint.id != results[1].endpoint.id
    assert results[0].endpoint.public_id != results[1].endpoint.public_id
    assert results[0].secret != results[1].secret


@pytest.mark.parametrize("context", ["missing", "wrong"])
async def test_creation_is_rejected_without_matching_tenant_context(
    db_session: AsyncSession,
    organization_id: UUID,
    secret_manager: WebhookSecretManager,
    context: str,
) -> None:
    if context == "wrong":
        await set_tenant_context(db_session, uuid4())
    with pytest.raises(DBAPIError, match="row-level security policy") as error:
        async with db_session.begin_nested():
            await create_webhook_endpoint(
                db_session,
                organization_id=organization_id,
                name="Blocked",
                destination_url="https://example.com/events",
                retry_limit=3,
                secret_manager=secret_manager,
            )
    assert getattr(error.value.orig, "sqlstate", None) == "42501"
    await set_tenant_context(db_session, organization_id)
    assert list(await db_session.scalars(select(WebhookEndpoint.id))) == []


@pytest.mark.parametrize("retry_limit", [-1, 11])
async def test_creation_rejects_invalid_retry_limit_without_persisting(
    db_session: AsyncSession,
    organization_id: UUID,
    secret_manager: WebhookSecretManager,
    retry_limit: int,
) -> None:
    await set_tenant_context(db_session, organization_id)
    with pytest.raises(IntegrityError) as error:
        async with db_session.begin_nested():
            await create_webhook_endpoint(
                db_session,
                organization_id=organization_id,
                name="Invalid",
                destination_url="https://example.com/events",
                retry_limit=retry_limit,
                secret_manager=secret_manager,
            )
    assert getattr(error.value.orig, "sqlstate", None) == "23514"
    assert (
        error.value.orig.diag.constraint_name
        == "ck_webhook_endpoints_retry_limit_range"
    )
    assert list(await db_session.scalars(select(WebhookEndpoint.id))) == []


async def test_caller_can_roll_back_created_endpoint(
    db_session: AsyncSession,
    organization_id: UUID,
    secret_manager: WebhookSecretManager,
) -> None:
    await set_tenant_context(db_session, organization_id)
    savepoint = await db_session.begin_nested()
    await create_webhook_endpoint(
        db_session,
        organization_id=organization_id,
        name="Rollback",
        destination_url="https://example.com/events",
        retry_limit=3,
        secret_manager=secret_manager,
    )
    await savepoint.rollback()
    assert list(await db_session.scalars(select(WebhookEndpoint.id))) == []
