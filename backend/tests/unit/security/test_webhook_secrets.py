import base64
import re
from unittest.mock import Mock

import pytest
from cryptography.fernet import Fernet, InvalidToken

import relaymaid.security.webhook_secrets as secrets_module
from relaymaid.security.webhook_secrets import (
    WebhookSecretDecryptionError,
    WebhookSecretManager,
)


@pytest.fixture
def encryption_key() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture
def manager(encryption_key: str) -> WebhookSecretManager:
    return WebhookSecretManager(encryption_key)


def test_generate_secret_requests_32_random_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = Mock(return_value="generated-secret")
    monkeypatch.setattr(secrets_module, "token_urlsafe", generator)
    assert WebhookSecretManager.generate_secret() == "generated-secret"
    generator.assert_called_once_with(32)


def test_generated_secrets_are_url_safe_and_distinct() -> None:
    secrets = [WebhookSecretManager.generate_secret() for _ in range(10)]
    assert len(set(secrets)) == len(secrets)
    for secret in secrets:
        assert re.fullmatch(r"[A-Za-z0-9_-]{43}", secret)
        assert len(base64.urlsafe_b64decode(secret + "=")) == 32


@pytest.mark.parametrize(
    "secret", ["webhook-secret", "", "秘密🔐", " \tsecret\n", "a" * 4096]
)
def test_encrypt_decrypt_round_trip(manager: WebhookSecretManager, secret: str) -> None:
    ciphertext = manager.encrypt(secret)
    assert isinstance(ciphertext, str)
    assert ciphertext != secret
    assert manager.decrypt(ciphertext) == secret


def test_generated_secret_can_be_encrypted_and_decrypted(
    manager: WebhookSecretManager,
) -> None:
    secret = manager.generate_secret()
    assert manager.decrypt(manager.encrypt(secret)) == secret


def test_encryption_is_randomized(manager: WebhookSecretManager) -> None:
    first = manager.encrypt("same-secret")
    second = manager.encrypt("same-secret")
    assert first != second
    assert manager.decrypt(first) == manager.decrypt(second) == "same-secret"


def test_separate_managers_with_same_key_can_decrypt(encryption_key: str) -> None:
    writer = WebhookSecretManager(encryption_key)
    reader = WebhookSecretManager(encryption_key)
    assert reader.decrypt(writer.encrypt("shared-secret")) == "shared-secret"


@pytest.mark.parametrize(
    "key", ["", "not-a-fernet-key", base64.urlsafe_b64encode(b"short").decode()]
)
def test_rejects_invalid_encryption_keys(key: str) -> None:
    with pytest.raises(ValueError):
        WebhookSecretManager(key)


@pytest.mark.parametrize("ciphertext", ["", "not-a-token", "plain-secret", "秘密"])
def test_rejects_invalid_ciphertext(
    manager: WebhookSecretManager, ciphertext: str
) -> None:
    with pytest.raises(WebhookSecretDecryptionError) as error:
        manager.decrypt(ciphertext)
    assert str(error.value) == "Failed to decrypt the webhook secret."
    assert isinstance(error.value.__cause__, InvalidToken)


def test_wrong_key_cannot_decrypt(manager: WebhookSecretManager) -> None:
    other = WebhookSecretManager(Fernet.generate_key().decode())
    ciphertext = manager.encrypt("private-secret")
    with pytest.raises(WebhookSecretDecryptionError) as error:
        other.decrypt(ciphertext)
    assert isinstance(error.value.__cause__, InvalidToken)
    assert "private-secret" not in str(error.value)
    assert ciphertext not in str(error.value)


@pytest.mark.parametrize("corruption", ["modified", "truncated"])
def test_rejects_corrupted_ciphertext(
    manager: WebhookSecretManager, corruption: str
) -> None:
    original = manager.encrypt("private-secret")
    decoded = bytearray(base64.urlsafe_b64decode(original))
    if corruption == "modified":
        decoded[-1] ^= 1
    else:
        del decoded[-16:]
    corrupted = base64.urlsafe_b64encode(decoded).decode()
    with pytest.raises(WebhookSecretDecryptionError) as error:
        manager.decrypt(corrupted)
    assert isinstance(error.value.__cause__, InvalidToken)
    assert manager.decrypt(original) == "private-secret"


def test_wraps_non_utf8_plaintext_error(
    manager: WebhookSecretManager, encryption_key: str
) -> None:
    ciphertext = Fernet(encryption_key).encrypt(b"\xff\xfe").decode()
    with pytest.raises(WebhookSecretDecryptionError) as error:
        manager.decrypt(ciphertext)
    assert isinstance(error.value.__cause__, UnicodeDecodeError)
    assert str(error.value) == "Failed to decrypt the webhook secret."
