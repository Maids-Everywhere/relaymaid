from dataclasses import dataclass

from relaymaid.db.models.webhook import WebhookEndpoint


@dataclass(frozen=True, slots=True)
class CreateWebhookEndpointResult:
    endpoint: WebhookEndpoint
    secret: str
