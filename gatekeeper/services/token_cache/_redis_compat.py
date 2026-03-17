"""Optional Redis dependency loader for token cache implementations."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType

_redis_module: ModuleType | None

try:
    _redis_module = import_module("redis")
except ImportError:
    _redis_module = None

redis: ModuleType | None = _redis_module

__all__ = ["redis"]
