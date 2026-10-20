class EmailAlreadyExistsError(Exception):
    """Raised when registration uses an existing email address."""


class InvalidCredentialsError(Exception):
    """Raised when supplied credentials cannot authenticate a user."""


class WebhookEndpointNotFoundError(Exception):
    """
    Raised when a webhook endpoint is not found in the database or is not accessible to
    the user.
    """


class WebhookEndpointUnavailableError(Exception):
    """Raised when an ingestion endpoint is unknown or disabled."""
