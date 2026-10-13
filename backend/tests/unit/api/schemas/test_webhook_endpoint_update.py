import pytest
from pydantic import ValidationError

from relaymaid.api.schemas import WebhookEndpointUpdateRequest


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "  Updated  "},
        {"destination_url": "https://example.com/new"},
        {"retry_limit": 0},
        {"retry_limit": 10},
        {"enabled": False},
        {"enabled": True},
        {"name": "a" * 255, "retry_limit": 3, "enabled": False},
    ],
)
def test_update_accepts_partial_payload_and_preserves_omitted_fields(payload) -> None:
    request = WebhookEndpointUpdateRequest.model_validate(payload)
    expected = dict(payload)
    if "name" in expected:
        expected["name"] = expected["name"].strip()
    assert request.model_fields_set == set(payload)
    assert request.model_dump(mode="json", exclude_unset=True) == expected
    for field in {"name", "destination_url", "retry_limit", "enabled"} - set(payload):
        assert getattr(request, field) is None


def test_update_rejects_empty_payload() -> None:
    with pytest.raises(ValidationError, match="At least one field must be provided"):
        WebhookEndpointUpdateRequest.model_validate({})


@pytest.mark.parametrize("field", ["name", "destination_url", "retry_limit", "enabled"])
def test_update_rejects_explicit_null_even_with_other_valid_fields(field: str) -> None:
    with pytest.raises(ValidationError) as error:
        WebhookEndpointUpdateRequest.model_validate({"name": "Valid", field: None})
    assert error.value.errors()[0]["loc"] == (field,)
    assert "Field cannot be null" in error.value.errors()[0]["msg"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", ""),
        ("name", " \t"),
        ("name", "a" * 256),
        ("destination_url", "not-a-url"),
        ("destination_url", "ftp://example.com"),
        ("destination_url", "https://example.com/" + "a" * 2048),
        ("retry_limit", -1),
        ("retry_limit", 11),
        ("retry_limit", 1.5),
        ("enabled", "invalid"),
        ("secret", "chosen"),
        ("secret_ciphertext", "chosen"),
        ("organization_id", "chosen"),
        ("id", "chosen"),
        ("public_id", "chosen"),
    ],
)
def test_update_rejects_invalid_or_read_only_fields(field: str, value: object) -> None:
    with pytest.raises(ValidationError) as error:
        WebhookEndpointUpdateRequest.model_validate({field: value})
    assert error.value.errors()[0]["loc"] == (field,)
