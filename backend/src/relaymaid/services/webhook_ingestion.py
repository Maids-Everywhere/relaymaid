from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from relaymaid.db.models import Event, OutboxMessage
from relaymaid.db.tenant_context import set_tenant_context
from relaymaid.security.webhook_secrets import WebhookSecretManager
from relaymaid.security.webhook_signatures import verify_webhook_signature
from relaymaid.services.exceptions import WebhookEndpointUnavailableError


@dataclass(frozen=True, slots=True)
class ResolvedWebhookEndpoint:
    id: UUID
    organization_id: UUID
    secret_ciphertext: str


@dataclass(frozen=True, slots=True)
class VerifiedWebhookEndpoint:
    id: UUID
    organization_id: UUID


@dataclass(frozen=True, slots=True)
class PersistedWebhookEvent:
    event: Event
    outbox_message: OutboxMessage | None
    created: bool


async def resolve_webhook_endpoint(
    session: AsyncSession,
    public_id: UUID,
) -> ResolvedWebhookEndpoint | None:
    row = (
        await session.execute(
            text(
                """
                SELECT id, organization_id, secret_ciphertext
                FROM public.relaymaid_resolve_webhook_endpoint(:public_id)
                """
            ),
            {"public_id": public_id},
        )
    ).one_or_none()

    if row is None:
        return None

    return ResolvedWebhookEndpoint(
        id=row.id,
        organization_id=row.organization_id,
        secret_ciphertext=row.secret_ciphertext,
    )


async def authenticate_incoming_webhook(
    *,
    session: AsyncSession,
    secret_manager: WebhookSecretManager,
    public_id: UUID,
    timestamp: str,
    signature: str,
    raw_body: bytes,
) -> VerifiedWebhookEndpoint:
    endpoint = await resolve_webhook_endpoint(
        session=session,
        public_id=public_id,
    )

    if endpoint is None:
        raise WebhookEndpointUnavailableError

    secret = secret_manager.decrypt(endpoint.secret_ciphertext)

    verify_webhook_signature(
        secret=secret,
        timestamp=timestamp,
        signature=signature,
        raw_body=raw_body,
    )

    return VerifiedWebhookEndpoint(
        id=endpoint.id,
        organization_id=endpoint.organization_id,
    )


async def persist_webhook_event(
    *,
    session: AsyncSession,
    endpoint: VerifiedWebhookEndpoint,
    external_event_id: str,
    event_type: str,
    payload_raw: bytes,
    content_type: str,
) -> PersistedWebhookEvent:
    await set_tenant_context(
        session,
        endpoint.organization_id,
    )

    event = await session.scalar(
        insert(Event)
        .values(
            organization_id=endpoint.organization_id,
            endpoint_id=endpoint.id,
            external_event_id=external_event_id,
            event_type=event_type,
            payload_raw=payload_raw,
            content_type=content_type,
        )
        .on_conflict_do_nothing(
            constraint="uq_events_organization_endpoint_external_event",
        )
        .returning(Event)
    )

    if event is None:
        existing_event = await session.scalar(
            select(Event).where(
                Event.organization_id == endpoint.organization_id,
                Event.endpoint_id == endpoint.id,
                Event.external_event_id == external_event_id,
            )
        )

        if existing_event is None:
            raise RuntimeError("Conflicting webhook event could not be loaded")

        return PersistedWebhookEvent(
            event=existing_event,
            outbox_message=None,
            created=False,
        )

    outbox_message = OutboxMessage(
        organization_id=endpoint.organization_id,
        event_id=event.id,
    )
    session.add(outbox_message)
    await session.flush()

    return PersistedWebhookEvent(
        event=event, outbox_message=outbox_message, created=True
    )
