from typing import Annotated

from fastapi import APIRouter, Query, status

from relaymaid.api.dependencies.auth import OwnerPrincipal
from relaymaid.api.dependencies.database import DatabaseSession
from relaymaid.api.dependencies.webhook_secrets import WebhookSecretManagerDependency
from relaymaid.api.schemas import (
    WebhookEndpointCreateRequest,
    WebhookEndpointCreateResponse,
    WebhookEndpointListResponse,
    WebhookEndpointResponse,
)
from relaymaid.services.webhook_endpoints import (
    create_webhook_endpoint,
    list_webhook_endpoints,
)

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


@router.get(
    "",
    response_model=WebhookEndpointListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_endpoints(
    session: DatabaseSession,
    principal: OwnerPrincipal,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> WebhookEndpointListResponse:
    result = await list_webhook_endpoints(
        session=session,
        organization_id=principal.organization_id,
        limit=limit,
        offset=offset,
    )

    return WebhookEndpointListResponse(
        items=[
            WebhookEndpointResponse.model_validate(endpoint)
            for endpoint in result.items
        ],
        limit=limit,
        offset=offset,
        has_more=result.has_more,
    )
    
