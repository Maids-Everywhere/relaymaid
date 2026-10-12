from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from relaymaid.db.models.webhook import WebhookEndpoint
from relaymaid.domain import CreateWebhookEndpointResult
from relaymaid.security.webhook_secrets import WebhookSecretManager


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
    :raises ValueError: If any of the input parameters are invalid.
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
