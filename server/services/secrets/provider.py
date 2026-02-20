"""SecretProvider interface + environment-backed provider."""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Protocol


class SecretProvider(Protocol):
    def get(self, key: str) -> Optional[str]: ...

    def get_many(self, keys: List[str]) -> Dict[str, Optional[str]]: ...


class EnvSecretProvider:
    """Simple provider that reads from process environment.

    Treats explicitly-set empty strings as absent (returns None).
    """

    def get(self, key: str) -> Optional[str]:
        val = os.getenv(key)
        return val if val else None

    def get_many(self, keys: List[str]) -> Dict[str, Optional[str]]:
        return {k: self.get(k) for k in keys}