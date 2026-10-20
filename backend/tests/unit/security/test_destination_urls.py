import re
import socket
from unittest.mock import Mock

import pytest
from pydantic import HttpUrl

from relaymaid.security.destination_urls import validate_destination_url


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com/webhooks",
        "http://hooks.example.com:8080/events?type=order#details",
        "https://EXAMPLE.COM./events",
        "https://bücher.example/events",
        "https://8.8.8.8/events",
        "http://1.1.1.1:8080/events",
        "https://[2606:4700:4700::1111]/events",
        "https://[::ffff:8.8.8.8]/events",
    ],
)
def test_accepts_public_destinations_and_returns_original_url(value: str) -> None:
    url = HttpUrl(value)
    assert validate_destination_url(url) is url


@pytest.mark.parametrize(
    "value",
    [
        "https://user@example.com/events",
        "https://user:password@example.com/events",
        "https://:password@example.com/events",
        "https://us%65r:p%40ss@example.com/events",
    ],
)
def test_rejects_url_credentials_without_exposing_them(value: str) -> None:
    with pytest.raises(ValueError) as error:
        validate_destination_url(HttpUrl(value))
    assert str(error.value) == "Destination URL must not contain credentials"


@pytest.mark.parametrize(
    "host",
    ["localhost", "LOCALHOST", "localhost.", "api.localhost", "API.LOCALHOST."],
)
def test_rejects_localhost_and_subdomains(host: str) -> None:
    with pytest.raises(ValueError, match=r"^Local destination hosts are not allowed$"):
        validate_destination_url(HttpUrl(f"https://{host}/events"))


@pytest.mark.parametrize("host", ["redis", "postgres", "metadata", "REDIS."])
def test_rejects_single_label_service_names(host: str) -> None:
    with pytest.raises(ValueError) as error:
        validate_destination_url(HttpUrl(f"http://{host}/events"))
    assert str(error.value) == "Destination URL must use a fully qualified domain name"


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "127.255.255.254",  # Loopback
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",  # Private
        "169.254.169.254",  # Link-local metadata endpoint
        "100.64.0.1",  # Shared address space
        "0.0.0.0",
        "192.0.2.1",
        "198.51.100.1",
        "203.0.113.1",
        "224.0.0.1",
        "239.255.255.250",  # Multicast
        "240.0.0.1",
        "255.255.255.255",  # Reserved/broadcast
        "[::]",
        "[::1]",
        "[fc00::1]",
        "[fd00::1]",
        "[fe80::1]",
        "[2001:db8::1]",
        "[ff02::1]",
        "[ff0e::1]",
        "[::ffff:127.0.0.1]",
        "[::ffff:10.0.0.1]",
        "[::ffff:169.254.169.254]",
        "[::ffff:224.0.0.1]",
    ],
)
def test_rejects_non_public_and_multicast_ip_addresses(host: str) -> None:
    with pytest.raises(ValueError) as error:
        validate_destination_url(HttpUrl(f"http://{host}/events"))
    assert str(error.value) == "Non-public destination IP addresses are not allowed"


@pytest.mark.parametrize("host", ["2130706433", "0x7f000001", "127.1"])
def test_rejects_nonstandard_ipv4_loopback_notation(host: str) -> None:
    # HttpUrl canonicalizes these forms before the policy inspects the host.
    with pytest.raises(ValueError, match="Non-public destination IP addresses"):
        validate_destination_url(HttpUrl(f"http://{host}/events"))


@pytest.mark.parametrize(
    "host",
    ["localhost.example.com", "notlocalhost.example.com", "unresolvable.invalid"],
)
def test_domain_validation_does_not_resolve_dns(
    host: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolve = Mock(side_effect=AssertionError("DNS lookup must not occur"))
    for function in ("getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        monkeypatch.setattr(socket, function, resolve)
    url = HttpUrl(f"https://{host}/events")
    assert validate_destination_url(url) is url
    resolve.assert_not_called()


def test_rejects_missing_host() -> None:
    # HttpUrl normally enforces a host; exercise the validator's defensive guard.
    url = Mock(spec=HttpUrl, username=None, password=None, host=None)
    with pytest.raises(
        ValueError, match=re.escape("Destination URL must contain a host")
    ):
        validate_destination_url(url)
