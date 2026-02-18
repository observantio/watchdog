"""
Centralized Fernet-based encryption helpers for sensitive data at rest.
Behavior matches the legacy implementation in `storage_db_service.py`.
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
