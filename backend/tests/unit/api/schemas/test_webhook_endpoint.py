import pytest
from pydantic import ValidationError

from relaymaid.api.schemas import WebhookEndpointCreateRequest

VALID_PAYLOAD = {
    "name": "Webhook",
    "destination_url": "https://example.com/events",
}


def test_accepts_valid_payload_and_defaults_retry_limit() -> None:
    request = WebhookEndpointCreateRequest.model_validate(VALID_PAYLOAD)
    assert request.name == "Webhook"
    assert str(request.destination_url) == "https://example.com/events"
    assert request.retry_limit == 3
    assert request.model_dump(mode="json") == {**VALID_PAYLOAD, "retry_limit": 3}


@pytest.mark.parametrize("name", ["a", "a" * 255, "通知", "Order created"])
def test_accepts_valid_names(name: str) -> None:
    request = WebhookEndpointCreateRequest.model_validate(
        {**VALID_PAYLOAD, "name": name}
    )
    assert request.name == name


@pytest.mark.parametrize(
    "name", ["  Webhook  ", "\tWebhook\n", "  " + "a" * 255 + "  "]
)
def test_strips_name_whitespace_before_checking_length(name: str) -> None:
    request = WebhookEndpointCreateRequest.model_validate(
        {**VALID_PAYLOAD, "name": name}
    )
    assert request.name == name.strip()


@pytest.mark.parametrize(
    ("name", "error_type"),
    [
        ("", "string_too_short"),
        (" \t\n", "string_too_short"),
        ("a" * 256, "string_too_long"),
        (None, "string_type"),
        (123, "string_type"),
    ],
)
def test_rejects_invalid_names(name: object, error_type: str) -> None:
    with pytest.raises(ValidationError) as error:
        WebhookEndpointCreateRequest.model_validate({**VALID_PAYLOAD, "name": name})
    assert error.value.errors()[0]["loc"] == ("name",)
    assert error.value.errors()[0]["type"] == error_type


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/events",
        "https://example.com/events",
        "https://example.com:8443/events?source=test",
        "https://example.com/" + "a" * (2048 - len("https://example.com/")),
    ],
)
def test_accepts_http_urls_including_maximum_length(url: str) -> None:
    request = WebhookEndpointCreateRequest.model_validate(
        {**VALID_PAYLOAD, "destination_url": url}
    )
    assert str(request.destination_url) == url


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not-a-url",
        "/relative/path",
        "https://",
        "ftp://example.com/events",
        "file:///tmp/events",
        "javascript:alert(1)",
        None,
        123,
        "https://example.com/" + "a" * (2049 - len("https://example.com/")),
    ],
)
def test_rejects_invalid_destination_urls(url: object) -> None:
    with pytest.raises(ValidationError) as error:
        WebhookEndpointCreateRequest.model_validate(
            {**VALID_PAYLOAD, "destination_url": url}
        )
    assert error.value.errors()[0]["loc"] == ("destination_url",)


@pytest.mark.parametrize("retry_limit", [0, 1, 3, 10])
def test_accepts_retry_limits_including_boundaries(retry_limit: int) -> None:
    request = WebhookEndpointCreateRequest.model_validate(
        {**VALID_PAYLOAD, "retry_limit": retry_limit}
    )
    assert request.retry_limit == retry_limit


@pytest.mark.parametrize(
    ("retry_limit", "error_type"),
    [
        (-1, "greater_than_equal"),
        (11, "less_than_equal"),
        (1.5, "int_from_float"),
        ("invalid", "int_parsing"),
        (None, "int_type"),
    ],
)
def test_rejects_invalid_retry_limits(retry_limit: object, error_type: str) -> None:
    with pytest.raises(ValidationError) as error:
        WebhookEndpointCreateRequest.model_validate(
            {**VALID_PAYLOAD, "retry_limit": retry_limit}
        )
    assert error.value.errors()[0]["loc"] == ("retry_limit",)
    assert error.value.errors()[0]["type"] == error_type


@pytest.mark.parametrize("field", ["name", "destination_url"])
def test_rejects_missing_required_fields(field: str) -> None:
    payload = {key: value for key, value in VALID_PAYLOAD.items() if key != field}
    with pytest.raises(ValidationError) as error:
        WebhookEndpointCreateRequest.model_validate(payload)
    assert error.value.errors()[0]["loc"] == (field,)
    assert error.value.errors()[0]["type"] == "missing"


@pytest.mark.parametrize("field", ["organization_id", "secret_ciphertext", "enabled"])
def test_rejects_extra_fields(field: str) -> None:
    with pytest.raises(ValidationError) as error:
        WebhookEndpointCreateRequest.model_validate(
            {**VALID_PAYLOAD, field: "unexpected"}
        )
    assert error.value.errors()[0]["loc"] == (field,)
    assert error.value.errors()[0]["type"] == "extra_forbidden"
