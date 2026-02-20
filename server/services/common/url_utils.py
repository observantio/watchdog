"""
Utilities for checking if URLs are valid and properly formatted, including functions to validate URL formats, ensure that URLs have a scheme (defaulting to https:// if missing), and create configured HTTP clients for making requests to external services. This module provides common URL-related utilities that can be used across different parts of the application when working with URLs for external services, such as authentication providers or API endpoints.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from urllib.parse import urlparse


def is_safe_http_url(value: str | None) -> bool:
    if not value or not isinstance(value, str):
        return False
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.netloc:
        return False
    return True
