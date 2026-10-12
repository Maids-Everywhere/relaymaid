from fastapi import APIRouter, status

from relaymaid.api.dependencies.auth import OwnerPrincipal
from relaymaid.api.dependencies.database import DatabaseSession
from relaymaid.api.dependencies.webhook_secrets import WebhookSecretManagerDependency
from relaymaid.api.schemas import (
    WebhookEndpointCreateRequest,
    WebhookEndpointCreateResponse,
)
from relaymaid.services.webhook_endpoints import create_webhook_endpoint

router = APIRouter(
    prefix="/webhook-endpoints",
    tags=["webhook-endpoints"],
)


@router.post(
    "",
    response_model=WebhookEndpointCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_endpoint(
    data: WebhookEndpointCreateRequest,
    session: DatabaseSession,
    principal: OwnerPrincipal,
    secret_manager: WebhookSecretManagerDependency,
) -> WebhookEndpointCreateResponse:
    result = await create_webhook_endpoint(
        session=session,
        organization_id=principal.organization_id,
        name=data.name,
        destination_url=str(data.destination_url),
        retry_limit=data.retry_limit,
        secret_manager=secret_manager,
    )

    return WebhookEndpointCreateResponse.model_validate(
        {
            "id": result.endpoint.id,
            "public_id": result.endpoint.public_id,
            "name": result.endpoint.name,
            "destination_url": result.endpoint.destination_url,
            "enabled": result.endpoint.enabled,
            "retry_limit": result.endpoint.retry_limit,
            "created_at": result.endpoint.created_at,
            "secret": result.secret,
        }
    )
