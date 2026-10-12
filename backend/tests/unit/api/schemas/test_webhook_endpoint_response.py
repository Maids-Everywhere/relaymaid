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


@pytest.fixture(params=[WebhookEndpointResponse, WebhookEndpointCreateResponse])
def response_model(request: pytest.FixtureRequest) -> type[WebhookEndpointResponse]:
    return request.param


@pytest.fixture
def response_payload(
    response_model: type[WebhookEndpointResponse],
) -> dict[str, object]:
    payload = dict(PAYLOAD)
    if response_model is WebhookEndpointCreateResponse:
        payload["secret"] = "test-webhook-secret"
    return payload


def test_response_parses_json_values_and_serializes(
    response_model: type[WebhookEndpointResponse],
    response_payload: dict[str, object],
) -> None:
    response = response_model.model_validate(response_payload)
    assert response.id == UUID(str(response_payload["id"]))
    assert response.public_id == UUID(str(response_payload["public_id"]))
    assert response.name == "Webhook"
    assert str(response.destination_url) == response_payload["destination_url"]
    assert response.enabled is True
    assert response.retry_limit == 3
    assert response.created_at == datetime(2026, 10, 12, 12, 30, tzinfo=UTC)
    assert response.model_dump(mode="json") == response_payload
    assert response_model.model_validate_json(response.model_dump_json()) == response


def test_response_accepts_native_uuid_and_datetime_values(
    response_model: type[WebhookEndpointResponse],
    response_payload: dict[str, object],
) -> None:
    created_at = datetime(2026, 10, 12, tzinfo=UTC)
    response = response_model.model_validate(
        {
            **response_payload,
            "id": UUID(str(response_payload["id"])),
            "public_id": UUID(str(response_payload["public_id"])),
            "created_at": created_at,
        }
    )
    assert response.created_at == created_at
    assert isinstance(response.id, UUID)
    assert isinstance(response.public_id, UUID)


@pytest.mark.parametrize("name", ["a", "a" * 255, "  Webhook\t", "通知"])
def test_response_accepts_and_trims_names(
    response_model: type[WebhookEndpointResponse],
    response_payload: dict[str, object],
    name: str,
) -> None:
    response = response_model.model_validate({**response_payload, "name": name})
    assert response.name == name.strip()


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("retry_limit", [0, 3, 10])
def test_response_preserves_enabled_and_retry_limit(
    response_model: type[WebhookEndpointResponse],
    response_payload: dict[str, object],
    enabled: bool,
    retry_limit: int,
) -> None:
    response = response_model.model_validate(
        {
            **response_payload,
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
def test_response_accepts_http_urls_and_maximum_length(
    response_model: type[WebhookEndpointResponse],
    response_payload: dict[str, object],
    url: str,
) -> None:
    response = response_model.model_validate(
        {**response_payload, "destination_url": url}
    )
    assert str(response.destination_url) == url


@pytest.mark.parametrize("field", list(PAYLOAD))
def test_response_rejects_missing_required_fields(
    response_model: type[WebhookEndpointResponse],
    response_payload: dict[str, object],
    field: str,
) -> None:
    with pytest.raises(ValidationError) as error:
        response_model.model_validate(
            {k: v for k, v in response_payload.items() if k != field}
        )
    assert error.value.errors()[0]["loc"] == (field,)
    assert error.value.errors()[0]["type"] == "missing"


@pytest.mark.parametrize("field", list(PAYLOAD))
def test_response_rejects_null_fields(
    response_model: type[WebhookEndpointResponse],
    response_payload: dict[str, object],
    field: str,
) -> None:
    with pytest.raises(ValidationError) as error:
        response_model.model_validate({**response_payload, field: None})
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
def test_response_rejects_invalid_fields(
    response_model: type[WebhookEndpointResponse],
    response_payload: dict[str, object],
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValidationError) as error:
        response_model.model_validate({**response_payload, field: value})
    assert error.value.errors()[0]["loc"] == (field,)


@pytest.mark.parametrize("field", ["secret", "secret_ciphertext", "organization_id"])
def test_response_rejects_unexpected_fields(field: str) -> None:
    with pytest.raises(ValidationError) as error:
        WebhookEndpointResponse.model_validate({**PAYLOAD, field: "unexpected"})
    assert error.value.errors()[0]["loc"] == (field,)
    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_create_response_preserves_secret_for_json_but_hides_it_in_repr() -> None:
    secret = "test-webhook-secret"
    response = WebhookEndpointCreateResponse.model_validate(
        {**PAYLOAD, "secret": secret}
    )
    assert response.secret == secret
    assert secret not in repr(response)
    assert secret not in str(response)
    assert response.model_dump(mode="json") == {**PAYLOAD, "secret": secret}
    assert (
        WebhookEndpointCreateResponse.model_validate_json(
            response.model_dump_json()
        ).secret
        == secret
    )


def test_create_response_requires_secret() -> None:
    with pytest.raises(ValidationError) as error:
        WebhookEndpointCreateResponse.model_validate(PAYLOAD)
    assert error.value.errors()[0]["loc"] == ("secret",)
    assert error.value.errors()[0]["type"] == "missing"


@pytest.mark.parametrize("secret", [None, 123, True, [], {}])
def test_create_response_rejects_non_string_secret(secret: object) -> None:
    with pytest.raises(ValidationError) as error:
        WebhookEndpointCreateResponse.model_validate({**PAYLOAD, "secret": secret})
    assert error.value.errors()[0]["loc"] == ("secret",)
    assert error.value.errors()[0]["type"] == "string_type"


@pytest.mark.parametrize(
    "field", ["secret_ciphertext", "organization_id", "unexpected"]
)
def test_create_response_inherits_extra_field_rejection(field: str) -> None:
    with pytest.raises(ValidationError) as error:
        WebhookEndpointCreateResponse.model_validate(
            {
                **PAYLOAD,
                "secret": "test-secret",
                field: "unexpected",
            }
        )
    assert error.value.errors()[0]["loc"] == (field,)
    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_create_response_rejects_secret_only_payload() -> None:
    with pytest.raises(ValidationError) as error:
        WebhookEndpointCreateResponse.model_validate({"secret": "test-secret"})
    assert {item["loc"] for item in error.value.errors()} == {
        (field,) for field in PAYLOAD
    }
    assert all(item["type"] == "missing" for item in error.value.errors())
