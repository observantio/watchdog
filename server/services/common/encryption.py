"""
Encryption utilities for securely hashing and verifying sensitive data such as passwords and API keys, using bcrypt for password hashing and Fernet symmetric encryption for encrypting API key values in the database. This module provides functions to hash passwords, verify passwords against hashes, encrypt API key values, and decrypt API key values, ensuring that sensitive information is stored securely and can be validated when needed.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""
import json
import logging
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken

from config import config as app_config

logger = logging.getLogger(__name__)


def _get_fernet() -> Optional[Fernet]:
    key = app_config.DATA_ENCRYPTION_KEY
    if not key:
        return None
    try:
        return Fernet(key)
    except ValueError:
        logger.error("Invalid DATA_ENCRYPTION_KEY – channel config will be stored unencrypted")
        return None


def encrypt_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    if not _get_fernet():
        return cfg
    try:
        f = _get_fernet()
        if not f:
            return cfg
        return {"__encrypted__": f.encrypt(json.dumps(cfg, default=str).encode()).decode()}
    except Exception:
        logger.exception("Failed to encrypt channel config")
        return cfg


def decrypt_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    if "__encrypted__" not in cfg:
        return cfg
    f = _get_fernet()
    if not f:
        raise ValueError("Encrypted channel config found but DATA_ENCRYPTION_KEY is not set")
    try:
        return json.loads(f.decrypt(cfg["__encrypted__"].encode()).decode())
    except InvalidToken as exc:
        raise ValueError("Cannot decrypt channel config – wrong key?") from exc
