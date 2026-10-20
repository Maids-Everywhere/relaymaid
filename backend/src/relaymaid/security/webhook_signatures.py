import hashlib
import hmac
import re
import time

_SIGNATURE_PATTERN = re.compile(r"v1=[0-9a-f]{64}\Z")
DEFAULT_TIMESTAMP_TOLERANCE_SECONDS = 300
SIGNATURE_PREFIX = "v1="


class WebhookVerificationError(Exception):
    """Base error for webhook verification failures."""


class InvalidWebhookTimestampError(WebhookVerificationError):
    """Timestamp is missing or malformed."""


class WebhookTimestampOutsideToleranceError(WebhookVerificationError):
    """Timestamp is too old or too far in the future."""


class InvalidWebhookSignatureError(WebhookVerificationError):
    """HMAC signature does not match."""


def verify_webhook_signature(
    *,
    secret: str,
    timestamp: str,
    raw_body: bytes,
    signature: str,
    now_timestamp: int | None = None,
    tolerance_seconds: int = DEFAULT_TIMESTAMP_TOLERANCE_SECONDS,
) -> None:
    if not timestamp.isascii() or not timestamp.isdigit() or len(timestamp) > 20:
        raise InvalidWebhookTimestampError

    timestamp_value = int(timestamp)
    current_timestamp = int(time.time()) if now_timestamp is None else now_timestamp

    if abs(current_timestamp - timestamp_value) > tolerance_seconds:
        raise WebhookTimestampOutsideToleranceError

    if not signature.startswith(SIGNATURE_PREFIX):
        raise InvalidWebhookSignatureError

    if _SIGNATURE_PATTERN.fullmatch(signature) is None:
        raise InvalidWebhookSignatureError

    signed_payload = timestamp.encode("ascii") + b"." + raw_body

    expected_digest = hmac.new(
        secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    provided_digest = signature.removeprefix(SIGNATURE_PREFIX)

    if not hmac.compare_digest(expected_digest, provided_digest):
        raise InvalidWebhookSignatureError
