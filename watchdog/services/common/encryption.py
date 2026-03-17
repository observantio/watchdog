"""
Encryption utilities for symmetrically encrypting and decrypting sensitive configuration data using Fernet encryption. This module provides functions to encrypt and decrypt dictionary configurations, ensuring that sensitive information such as API keys and channel credentials are stored securely in the database and can be recovered only with the correct encryption key.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import json
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from config import config as app_config
from custom_types.json import JSONDict

@lru_cache(maxsize=8)
def _get_fernet_for_key(key: str) -> Fernet:
    try:
        return Fernet(key)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("Invalid DATA_ENCRYPTION_KEY format") from exc


def _get_fernet() -> Fernet:
    key = app_config.DATA_ENCRYPTION_KEY
    if not key:
        raise RuntimeError("DATA_ENCRYPTION_KEY is not configured")
    return _get_fernet_for_key(str(key))


_get_fernet.cache_clear = _get_fernet_for_key.cache_clear  # type: ignore[attr-defined]


def encrypt_config(cfg: JSONDict) -> JSONDict:
    try:
        f = _get_fernet()
        try:
            payload = json.dumps(cfg).encode()
        except (TypeError, ValueError) as exc:
            raise ValueError("Channel config must be JSON-serializable") from exc
        return {"__encrypted__": f.encrypt(payload).decode(), "__v": 1}
    except RuntimeError:
        raise
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Failed to encrypt channel config") from exc


def decrypt_config(cfg: JSONDict) -> JSONDict:
    if "__encrypted__" not in cfg:
        return cfg
    try:
        f = _get_fernet()
        encrypted_value = cfg["__encrypted__"]
        if not isinstance(encrypted_value, str):
            raise ValueError("Encrypted channel config payload must be a string")
        decrypted = json.loads(f.decrypt(encrypted_value.encode()).decode())
        if not isinstance(decrypted, dict):
            raise ValueError("Encrypted channel config must decrypt to an object")
        return decrypted
    except RuntimeError:
        raise
    except ValueError:
        raise
    except InvalidToken as exc:
        raise ValueError("Cannot decrypt channel config – wrong key or corrupted data") from exc
    except Exception as exc:
        raise ValueError("Failed to decrypt channel config") from exc
