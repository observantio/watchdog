"""
Compatibility layer for tests and modules importing ``services.config``.

This module reloads and re-exports the root ``config`` module so
``importlib.reload(services.config)`` also refreshes environment-driven
configuration values.
"""

from __future__ import annotations

import importlib

_root_config = importlib.reload(importlib.import_module("config"))

for _name, _value in vars(_root_config).items():
    if not _name.startswith("_"):
        globals()[_name] = _value

__all__ = [name for name in globals() if name.isupper()]
