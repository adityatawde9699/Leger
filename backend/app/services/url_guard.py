"""
SSRF guard for user-supplied URLs (webhooks).

A user can register an arbitrary webhook URL that the server later POSTs to. Without
validation that is a Server-Side Request Forgery vector: a user could point a webhook
at the cloud metadata endpoint (169.254.169.254), localhost, or an internal/private
host and make the server fetch it. This module resolves the host and rejects any URL
that resolves to a non-public address.
"""

import ipaddress
import socket
from urllib.parse import urlparse

ALLOWED_SCHEMES = {"http", "https"}


class UnsafeURLError(ValueError):
    """Raised when a URL is not a safe, public http(s) endpoint."""


def _ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local  # covers 169.254.0.0/16 (cloud metadata)
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_webhook_url(url: str) -> None:
    """
    Raise UnsafeURLError unless `url` is an http(s) URL whose host resolves
    exclusively to public IP addresses. Performs DNS resolution.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UnsafeURLError("URL must use http or https")
    host = parsed.hostname
    if not host:
        raise UnsafeURLError("URL has no host")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise UnsafeURLError(f"could not resolve host: {host}") from e

    addrs = {info[4][0] for info in infos}
    if not addrs:
        raise UnsafeURLError(f"could not resolve host: {host}")

    for addr in addrs:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError as e:
            raise UnsafeURLError(f"invalid resolved address: {addr}") from e
        if _ip_is_blocked(ip):
            raise UnsafeURLError(f"host resolves to a non-public address ({addr})")


def is_safe_webhook_url(url: str) -> bool:
    try:
        validate_webhook_url(url)
        return True
    except UnsafeURLError:
        return False
