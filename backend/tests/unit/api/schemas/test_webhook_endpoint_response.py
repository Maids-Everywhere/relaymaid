from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from relaymaid.api.schemas import (
    WebhookEndpointCreateResponse,
    WebhookEndpointResponse,
)

PAYLOAD = {
    "id": "12345678-1234-5678-1234-567812345678",
    "public_id": "87654321-4321-8765-4321-876543218765",
    "name": "Webhook",
    "destination_url": "https://example.com/events",
    "enabled": True,
    "retry_limit": 3,
    "created_at": "2026-10-12T12:30:00Z",
}


def test_response_parses_json_values_and_serializes() -> None:
    response = WebhookEndpointResponse.model_validate(PAYLOAD)
    assert response.id == UUID(str(PAYLOAD["id"]))
    assert response.public_id == UUID(str(PAYLOAD["public_id"]))
    assert response.name == "Webhook"
    assert str(response.destination_url) == PAYLOAD["destination_url"]
    assert response.enabled is True
    assert response.retry_limit == 3
    assert response.created_at == datetime(2026, 10, 12, 12, 30, tzinfo=UTC)
    assert response.model_dump(mode="json") == PAYLOAD
    assert (
        WebhookEndpointResponse.model_validate_json(response.model_dump_json())
        == response
    )


def test_response_accepts_native_uuid_and_datetime_values() -> None:
    created_at = datetime(2026, 10, 12, tzinfo=UTC)
    response = WebhookEndpointResponse.model_validate(
        {
            **PAYLOAD,
            "id": UUID(str(PAYLOAD["id"])),
            "public_id": UUID(str(PAYLOAD["public_id"])),
            "created_at": created_at,
        }
    )
    assert response.created_at == created_at
    assert isinstance(response.id, UUID)
    assert isinstance(response.public_id, UUID)


@pytest.mark.parametrize("name", ["a", "a" * 255, "  Webhook\t", "通知"])
def test_response_accepts_and_trims_names(name: str) -> None:
    response = WebhookEndpointResponse.model_validate({**PAYLOAD, "name": name})
    assert response.name == name.strip()


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("retry_limit", [0, 3, 10])
def test_response_preserves_enabled_and_retry_limit(
    enabled: bool, retry_limit: int
) -> None:
    response = WebhookEndpointResponse.model_validate(
        {
            **PAYLOAD,
            "enabled": enabled,
            "retry_limit": retry_limit,
        }
    )
    assert response.enabled is enabled
    assert response.retry_limit == retry_limit


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/events",
        "https://example.com/" + "a" * (2048 - len("https://example.com/")),
    ],
)
def test_response_accepts_http_urls_and_maximum_length(url: str) -> None:
    response = WebhookEndpointResponse.model_validate(
        {**PAYLOAD, "destination_url": url}
    )
    assert str(response.destination_url) == url


@pytest.mark.parametrize("field", list(PAYLOAD))
def test_response_rejects_missing_required_fields(field: str) -> None:
    with pytest.raises(ValidationError) as error:
        WebhookEndpointResponse.model_validate(
            {k: v for k, v in PAYLOAD.items() if k != field}
        )
    assert error.value.errors()[0]["loc"] == (field,)
    assert error.value.errors()[0]["type"] == "missing"


@pytest.mark.parametrize("field", list(PAYLOAD))
def test_response_rejects_null_fields(field: str) -> None:
    with pytest.raises(ValidationError) as error:
        WebhookEndpointResponse.model_validate({**PAYLOAD, field: None})
    assert error.value.errors()[0]["loc"] == (field,)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", "not-a-uuid"),
        ("public_id", "not-a-uuid"),
        ("name", ""),
        ("name", " \t\n"),
        ("name", "a" * 256),
        ("destination_url", "not-a-url"),
        ("destination_url", "/relative"),
        ("destination_url", "ftp://example.com/events"),
        (
            "destination_url",
            "https://example.com/" + "a" * (2049 - len("https://example.com/")),
        ),
        ("enabled", "maybe"),
        ("enabled", 2),
        ("retry_limit", "invalid"),
        ("retry_limit", 1.5),
        ("created_at", "not-a-date"),
        ("created_at", "2026-02-30T00:00:00Z"),
    ],
)
def test_response_rejects_invalid_fields(field: str, value: object) -> None:
    with pytest.raises(ValidationError) as error:
        WebhookEndpointResponse.model_validate({**PAYLOAD, field: value})
    assert error.value.errors()[0]["loc"] == (field,)


@pytest.mark.parametrize("field", ["secret", "secret_ciphertext", "organization_id"])
def test_response_rejects_unexpected_fields(field: str) -> None:
    with pytest.raises(ValidationError) as error:
        WebhookEndpointResponse.model_validate({**PAYLOAD, field: "unexpected"})
    assert error.value.errors()[0]["loc"] == (field,)
    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_create_response_preserves_secret_for_json_but_hides_it_in_repr() -> None:
    secret = "test-webhook-secret"
    response = WebhookEndpointCreateResponse(secret=secret)
    assert response.secret == secret
    assert secret not in repr(response)
    assert secret not in str(response)
    assert response.model_dump() == {"secret": secret}
    assert (
        WebhookEndpointCreateResponse.model_validate_json(
            response.model_dump_json()
        ).secret
        == secret
    )


def test_create_response_requires_secret() -> None:
    with pytest.raises(ValidationError) as error:
        WebhookEndpointCreateResponse.model_validate({})
    assert error.value.errors()[0]["loc"] == ("secret",)
    assert error.value.errors()[0]["type"] == "missing"


@pytest.mark.parametrize("secret", [None, 123, True, [], {}])
def test_create_response_rejects_non_string_secret(secret: object) -> None:
    with pytest.raises(ValidationError) as error:
        WebhookEndpointCreateResponse.model_validate({"secret": secret})
    assert error.value.errors()[0]["loc"] == ("secret",)
    assert error.value.errors()[0]["type"] == "string_type"
