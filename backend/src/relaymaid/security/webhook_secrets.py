from secrets import token_urlsafe

from cryptography.fernet import Fernet


class WebhookSecretDecryptionError(Exception):
    """Raised when a webhook secret cannot be decrypted."""

    pass


class WebhookSecretManager:
    def __init__(self, encryption_key: str) -> None:
        self._fernet = Fernet(encryption_key)

    @staticmethod
    def generate_secret() -> str:
        return token_urlsafe(32)

    def encrypt(self, secret: str) -> str:
        return self._fernet.encrypt(secret.encode()).decode()

    def decrypt(self, encrypted_secret: str) -> str:
        try:
            return self._fernet.decrypt(encrypted_secret.encode()).decode()
        except Exception as e:
            raise WebhookSecretDecryptionError(
                "Failed to decrypt the webhook secret."
            ) from e
