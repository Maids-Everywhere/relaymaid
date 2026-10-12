from typing import Annotated

from fastapi import Depends, Request

from relaymaid.security.webhook_secrets import WebhookSecretManager


def get_webhook_secret_manager(
    request: Request,
) -> WebhookSecretManager:
    manager = getattr(
        request.app.state,
        "webhook_secret_manager",
        None,
    )

    if not isinstance(manager, WebhookSecretManager):
        raise RuntimeError("Webhook secret manager is not initialized")

    return manager


WebhookSecretManagerDependency = Annotated[
    WebhookSecretManager,
    Depends(get_webhook_secret_manager),
]
