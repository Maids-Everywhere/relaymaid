from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    UrlConstraints,
)

WebhookEndpointName = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=255,
        strip_whitespace=True,
    ),
]

DestinationURL = Annotated[
    HttpUrl,
    UrlConstraints(max_length=2048),
]


class WebhookEndpointCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: WebhookEndpointName
    destination_url: DestinationURL
    retry_limit: int = Field(default=3, ge=0, le=10)


class WebhookEndpointResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    public_id: UUID
    name: WebhookEndpointName
    destination_url: DestinationURL
    enabled: bool
    retry_limit: int
    created_at: datetime


class WebhookEndpointCreateResponse(BaseModel):
    secret: str = Field(repr=False)
