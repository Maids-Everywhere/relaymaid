import pytest
from pydantic import HttpUrl, TypeAdapter, ValidationError

from relaymaid.api.schemas.webhook_endpoint import DestinationURL, SafeDestinationURL

safe_url = TypeAdapter(SafeDestinationURL)


@pytest.mark.parametrize(
    "value,normalized",
    [
        ("https://EXAMPLE.COM", "https://example.com/"),
        ("http://example.com:8080/events?a=b", "http://example.com:8080/events?a=b"),
        ("https://8.8.8.8/events", "https://8.8.8.8/events"),
        ("https://[2606:4700:4700::1111]/", "https://[2606:4700:4700::1111]/"),
        ("https://[::ffff:8.8.8.8]/", "https://[::ffff:808:808]/"),
    ],
)
def test_safe_url_parses_normalizes_and_serializes(value: str, normalized: str) -> None:
    result = safe_url.validate_python(value)
    assert isinstance(result, HttpUrl)
    assert str(result) == normalized
    assert safe_url.dump_python(result, mode="json") == normalized
    assert safe_url.validate_json(safe_url.dump_json(result)) == result


@pytest.mark.parametrize(
    "value,message",
    [
        ("https://user:password@example.com/", "must not contain credentials"),
        ("https://LOCALHOST./", "Local destination hosts are not allowed"),
        ("https://api.localhost/", "Local destination hosts are not allowed"),
        ("http://redis/", "must use a fully qualified domain name"),
        ("http://127.0.0.1/", "Non-public destination IP addresses"),
        ("http://169.254.169.254/", "Non-public destination IP addresses"),
        ("http://[::1]/", "Non-public destination IP addresses"),
        ("http://[::ffff:127.0.0.1]/", "Non-public destination IP addresses"),
        ("http://224.0.0.1/", "Non-public destination IP addresses"),
    ],
)
@pytest.mark.parametrize("representation", ["string", "http_url", "json"])
def test_safe_url_wraps_policy_rejections_as_validation_errors(
    value: str, message: str, representation: str
) -> None:
    with pytest.raises(ValidationError) as error:
        if representation == "json":
            safe_url.validate_json(TypeAdapter(str).dump_json(value))
        else:
            safe_url.validate_python(
                HttpUrl(value) if representation == "http_url" else value
            )
    detail = error.value.errors()[0]
    assert detail["type"] == "value_error"
    assert message in detail["msg"]


@pytest.mark.parametrize(
    "value,error_type",
    [
        ("not-a-url", "url_parsing"),
        ("/relative", "url_parsing"),
        ("ftp://example.com/", "url_scheme"),
        (None, "url_type"),
        (123, "url_type"),
    ],
)
def test_safe_url_preserves_http_url_validation(value: object, error_type: str) -> None:
    with pytest.raises(ValidationError) as error:
        safe_url.validate_python(value)
    assert error.value.errors()[0]["type"] == error_type


def test_safe_url_preserves_maximum_length_constraint() -> None:
    prefix = "https://example.com/"
    value = prefix + "a" * (2048 - len(prefix))
    assert str(safe_url.validate_python(value)) == value
    with pytest.raises(ValidationError) as error:
        safe_url.validate_python(value + "a")
    assert error.value.errors()[0]["type"] == "url_too_long"


def test_plain_destination_url_remains_available_for_existing_stored_urls() -> None:
    value = "http://127.0.0.1/events"
    assert str(TypeAdapter(DestinationURL).validate_python(value)) == value
