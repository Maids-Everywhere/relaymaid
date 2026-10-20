import hashlib
import hmac

import pytest

from relaymaid.security.webhook_signatures import (
    InvalidWebhookSignatureError,
    InvalidWebhookTimestampError,
    WebhookTimestampOutsideToleranceError,
    verify_webhook_signature,
)

NOW = 1_800_000_000
SECRET = "webhook-secret-秘密"
BODY = b'{ "message": "hello" }\n'


def sign(timestamp: str, body: bytes = BODY, secret: str = SECRET) -> str:
    digest = hmac.new(
        secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    return f"v1={digest}"


@pytest.mark.parametrize("offset", [-300, -1, 0, 1, 300])
def test_accepts_valid_signature_within_inclusive_tolerance(offset: int) -> None:
    timestamp = str(NOW + offset)
    assert (
        verify_webhook_signature(
            secret=SECRET,
            timestamp=timestamp,
            raw_body=BODY,
            signature=sign(timestamp),
            now_timestamp=NOW,
        )
        is None
    )


@pytest.mark.parametrize("body", [b"", b"\x00\xff\xfe", BODY])
def test_verifies_exact_raw_bytes_using_current_time(body: bytes, monkeypatch) -> None:
    monkeypatch.setattr("relaymaid.security.webhook_signatures.time.time", lambda: NOW)
    timestamp = str(NOW)
    verify_webhook_signature(
        secret=SECRET,
        timestamp=timestamp,
        raw_body=body,
        signature=sign(timestamp, body),
    )


@pytest.mark.parametrize(
    "timestamp", ["", "invalid", "1.5", "-1", "+1", " 123", "123 ", "1" * 21]
)
def test_rejects_malformed_timestamp(timestamp: str) -> None:
    with pytest.raises(InvalidWebhookTimestampError):
        verify_webhook_signature(
            secret=SECRET,
            timestamp=timestamp,
            raw_body=BODY,
            signature="invalid",
            now_timestamp=NOW,
        )


@pytest.mark.parametrize("offset", [-301, 301])
def test_rejects_old_and_future_timestamps(offset: int) -> None:
    timestamp = str(NOW + offset)
    with pytest.raises(WebhookTimestampOutsideToleranceError):
        verify_webhook_signature(
            secret=SECRET,
            timestamp=timestamp,
            raw_body=BODY,
            signature=sign(timestamp),
            now_timestamp=NOW,
        )


def test_respects_custom_tolerance() -> None:
    timestamp = str(NOW - 2)
    with pytest.raises(WebhookTimestampOutsideToleranceError):
        verify_webhook_signature(
            secret=SECRET,
            timestamp=timestamp,
            raw_body=BODY,
            signature=sign(timestamp),
            now_timestamp=NOW,
            tolerance_seconds=1,
        )


@pytest.mark.parametrize("signature", ["", "v1=", "v2=abc", "abc", "v1=" + "0" * 64])
def test_rejects_missing_malformed_or_mismatched_signatures(signature: str) -> None:
    with pytest.raises(InvalidWebhookSignatureError):
        verify_webhook_signature(
            secret=SECRET,
            timestamp=str(NOW),
            raw_body=BODY,
            signature=signature,
            now_timestamp=NOW,
        )


@pytest.mark.parametrize("tamper", ["body", "secret", "timestamp"])
def test_signature_binds_body_secret_and_timestamp(tamper: str) -> None:
    timestamp = str(NOW)
    with pytest.raises(InvalidWebhookSignatureError):
        verify_webhook_signature(
            secret="wrong" if tamper == "secret" else SECRET,
            timestamp=str(NOW + 1) if tamper == "timestamp" else timestamp,
            raw_body=b'{"message":"hello"}' if tamper == "body" else BODY,
            signature=sign(timestamp),
            now_timestamp=NOW,
        )
