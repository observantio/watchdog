"""
Ensure cookies are marked Secure when appropriate based on the request scheme
and proxy headers, with support for trusting specific proxy CIDRs when
determining if the original request was made over HTTPS.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network
import re
from typing import Sequence

from fastapi import Request

from config import config

Network = IPv4Network | IPv6Network

def _parse_networks(cidrs: Sequence[str]) -> list[Network]:
    try:
        return [ip_network(c, strict=False) for c in cidrs]
    except ValueError:
        return []


def _forwarded_proto(request: Request) -> str:
    forwarded = request.headers.get("forwarded", "")
    match = re.search(r"(?:^|[;,\s])proto=\"?([A-Za-z]+)", forwarded)
    if match:
        return match.group(1).strip().lower()
    proto = request.headers.get("x-forwarded-proto", "")
    return proto.split(",")[0].strip().lower()

def is_secure_cookie_request(
    request: Request,
    *,
    trust_proxy_headers: bool,
    trusted_proxy_cidrs: Sequence[str] | None = None,
) -> bool:
    if request.url.scheme == "https":
        return True

    if not trust_proxy_headers:
        return False

    if not trusted_proxy_cidrs:
        return False

    client = request.client
    if not client:
        return False

    try:
        peer_ip = ip_address(client.host.strip())
    except ValueError:
        return False

    networks = _parse_networks(trusted_proxy_cidrs)
    if not networks:
        return False

    if not any(peer_ip in net for net in networks):
        return False

    return _forwarded_proto(request) == "https"


def cookie_secure(request: Request) -> bool:
    return is_secure_cookie_request(
        request,
        trust_proxy_headers=bool(config.TRUST_PROXY_HEADERS),
        trusted_proxy_cidrs=getattr(config, "TRUSTED_PROXY_CIDRS", []) or [],
    )
