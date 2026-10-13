from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relaymaid.db.models.webhook import WebhookEndpoint
from relaymaid.security.webhook_secrets import WebhookSecretManager
from relaymaid.services.exceptions import WebhookEndpointNotFoundError


@dataclass(frozen=True, slots=True)
class CreateWebhookEndpointResult:
    endpoint: WebhookEndpoint
    secret: str


@dataclass(frozen=True, slots=True)
class ListWebhookEndpointsResult:
    items: tuple[WebhookEndpoint, ...]
    has_more: bool


async def create_webhook_endpoint(
    session: AsyncSession,
    *,
    organization_id: UUID,
    name: str,
    destination_url: str,
    retry_limit: int,
    secret_manager: WebhookSecretManager,
) -> CreateWebhookEndpointResult:
    """
    Creates a new webhook endpoint for the specified organization.

    :param session: The database session to use for the operation.
    :param organization_id: The ID of the organization for which the webhook endpoint is
      being created.
    :param name: The name of the webhook endpoint.
    :param destination_url: The URL to which the webhook will send requests.
    :param retry_limit: The maximum number of retry attempts for failed webhook
      deliveries.
    :param secret_manager: An instance of WebhookSecretManager for generating and
      encrypting the webhook secret.
    :return: An instance of CreateWebhookEndpointResult containing the created
      WebhookEndpoint and the generated secret.
    """
    secret = secret_manager.generate_secret()
    encrypted_secret = secret_manager.encrypt(secret)

    endpoint = WebhookEndpoint(
        organization_id=organization_id,
        name=name,
        destination_url=destination_url,
        retry_limit=retry_limit,
        secret_ciphertext=encrypted_secret,
    )

    session.add(endpoint)
    await session.flush()

    return CreateWebhookEndpointResult(endpoint=endpoint, secret=secret)


async def list_webhook_endpoints(
    session: AsyncSession,
    *,
    organization_id: UUID,
    limit: int = 10,
    offset: int = 0,
) -> ListWebhookEndpointsResult:
    """
    Lists webhook endpoints for the specified organization.

    :param session: The database session to use for the operation.
    :param organization_id: The ID of the organization for which to list webhook
      endpoints.
    :param limit: The maximum number of webhook endpoints to return.
    :param offset: The number of webhook endpoints to skip before starting to collect
      the result set.
    :return: Paginated webhook endpoint listing result.
    """
    result = await session.execute(
        select(WebhookEndpoint)
        .where(WebhookEndpoint.organization_id == organization_id)
        .order_by(WebhookEndpoint.created_at.desc(), WebhookEndpoint.id.desc())
        .limit(limit + 1)
        .offset(offset)
    )

    endpoints = list(result.scalars())

    return ListWebhookEndpointsResult(
        items=tuple(endpoints[:limit]),
        has_more=len(endpoints) > limit,
    )


async def get_webhook_endpoint_by_public_id(
    session: AsyncSession,
    *,
    organization_id: UUID,
    endpoint_id: UUID,
) -> WebhookEndpoint | None:
    """
    Retrieves a webhook endpoint by its ID for the specified organization.

    :param session: The database session to use for the operation.
    :param organization_id: The ID of the organization to which the webhook endpoint
      belongs.
    :param endpoint_id: The ID of the webhook endpoint to retrieve.
    :return: The WebhookEndpoint instance if found, otherwise None.
    """
    query = await session.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.organization_id == organization_id,
            WebhookEndpoint.id == endpoint_id,
        )
    )

    result = query.scalar_one_or_none()

    if result is None:
        raise WebhookEndpointNotFoundError("Webhook endpoint not found.")

    return result
