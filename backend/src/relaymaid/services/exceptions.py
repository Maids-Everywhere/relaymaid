class EmailAlreadyExistsError(Exception):
    """Raised when registration uses an existing email address."""


class InvalidCredentialsError(Exception):
    """Raised when supplied credentials cannot authenticate a user."""
