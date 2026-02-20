"""
Ensure cookies are marked Secure when appropriate based on the request scheme and proxy headers, with support for trusting specific proxy CIDRs when determining if the original request was made over HTTPS.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from ipaddress import ip_address, ip_network

def is_secure_cookie_request(request, *, trust_proxy_headers: bool, trusted_proxy_cidrs: list[str] | None = None) -> bool:
    """Return True when cookie should be marked Secure for the given request."""
    if request.url.scheme == "https":
        return True

    if not trust_proxy_headers:
        return False

    trusted_cidrs = trusted_proxy_cidrs or []
    direct_peer = (request.client.host if request.client else "").strip()

    if trusted_cidrs:
        try:
            peer_ip = ip_address(direct_peer)
            for cidr in trusted_cidrs:
                try:
                    if peer_ip in ip_network(cidr, strict=False):
                        return request.headers.get("x-forwarded-proto", "").lower() == "https"
                except ValueError:
                    continue
        except ValueError:
            return False
        return False

    return request.headers.get("x-forwarded-proto", "").lower() == "https"
