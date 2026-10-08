from typing import Annotated

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
