"""Client address helpers shared by session tracking, the public-link spread check and the bot check.

Behind nginx and the load balancer ``REMOTE_ADDR`` is the proxy, so the client address comes from
``core.observability.current_client_ip()`` (bound per request by ``RequestIdMiddleware`` from the
trusted ``X-Forwarded-For`` hops), falling back to ``REMOTE_ADDR`` outside a request.
"""

from __future__ import annotations

import ipaddress


def client_ip(request=None) -> str:
    from core.observability import current_client_ip

    ip = current_client_ip() or ""
    if not ip and request is not None:
        ip = (getattr(request, "META", {}) or {}).get("REMOTE_ADDR") or ""
    return str(ip).strip()


def ip_prefix(ip: str | None) -> str:
    """The /24 (IPv4) or /48 (IPv6) network of an address; never the address itself."""
    raw = (ip or "").strip()
    if raw.startswith("[") and "]" in raw:  # "[2001:db8::1]:443"
        raw = raw[1:raw.index("]")]
    elif raw.count(":") == 1:  # "203.0.113.45:5555"
        raw = raw.split(":", 1)[0]
    try:
        addr = ipaddress.ip_address(raw)
    except ValueError:
        return ""
    if addr.version == 6 and addr.ipv4_mapped is not None:  # ::ffff:203.0.113.45 is an IPv4 client
        addr = addr.ipv4_mapped
    bits = 24 if addr.version == 4 else 48
    return str(ipaddress.ip_network(f"{addr}/{bits}", strict=False))
