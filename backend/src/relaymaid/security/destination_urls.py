from ipaddress import IPv6Address, ip_address

from pydantic import HttpUrl


def validate_destination_url(url: HttpUrl) -> HttpUrl:
    """Validate the configuration-time SSRF policy.

    This function does not resolve DNS. Destination IP addresses must be
    resolved and validated again immediately before outbound delivery.
    """
    if url.username is not None or url.password is not None:
        raise ValueError("Destination URL must not contain credentials")

    if url.host is None:
        raise ValueError("Destination URL must contain a host")

    host = url.host.lower().rstrip(".")
    host_without_brackets = host.removeprefix("[").removesuffix("]")

    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("Local destination hosts are not allowed")

    try:
        address = ip_address(host_without_brackets)
    except ValueError:
        # Reject Docker/service names such as `redis`, `postgres`, `metadata`.
        if "." not in host:
            raise ValueError(
                "Destination URL must use a fully qualified domain name"
            ) from None

        return url

    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped

    if not address.is_global or address.is_multicast:
        raise ValueError("Non-public destination IP addresses are not allowed")

    return url
