from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    UrlConstraints,
    field_validator,
    model_validator,
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
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    public_id: UUID
    name: WebhookEndpointName
    destination_url: DestinationURL
    enabled: bool
    retry_limit: int
    created_at: datetime


class WebhookEndpointCreateResponse(WebhookEndpointResponse):
    secret: str = Field(repr=False)


class WebhookEndpointListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[WebhookEndpointResponse]
    limit: int
    offset: int
    has_more: bool


class WebhookEndpointUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: WebhookEndpointName | None = None
    destination_url: DestinationURL | None = None
    retry_limit: int | None = Field(default=None, ge=0, le=10)
    enabled: bool | None = None

    @field_validator(
        "name",
        "destination_url",
        "retry_limit",
        "enabled",
    )
    @classmethod
    def reject_explicit_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("Field cannot be null")
        return value

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self
