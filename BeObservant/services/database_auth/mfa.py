"""
Database authentication service utilities for handling multi-factor authentication (MFA) operations, including TOTP enrollment, verification, and recovery code management. This module provides functions to enroll users in TOTP-based MFA, verify TOTP codes during login, generate and manage recovery codes for MFA, and disable or reset MFA settings for users as needed. The utilities in this module ensure that MFA operations are performed securely, with support for encryption of TOTP secrets and proper handling of recovery codes to enhance the security of user accounts in the database authentication service.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import secrets
from typing import Dict, List, Optional, TYPE_CHECKING

import bcrypt
import pyotp
from cryptography.fernet import Fernet, InvalidToken

from services.auth.auth_ops import create_mfa_setup_token as create_mfa_setup_token_op
from database import get_db_session
from db_models import User
from custom_types.json import JSONDict

if TYPE_CHECKING:
    from services.database_auth_service import DatabaseAuthService

def _get_fernet(service: DatabaseAuthService) -> Optional[Fernet]:
    from config import config as cfg

    if not cfg.DATA_ENCRYPTION_KEY:
        if cfg.REQUIRE_TOTP_ENCRYPTION_KEY:
            raise ValueError("DATA_ENCRYPTION_KEY must be configured for MFA/TOTP operations")
        return None
    try:
        return Fernet(cfg.DATA_ENCRYPTION_KEY)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid DATA_ENCRYPTION_KEY format") from exc


def _encrypt_mfa_secret(service: DatabaseAuthService, secret: str) -> str:
    f = _get_fernet(service)
    if not f:
        raise ValueError("DATA_ENCRYPTION_KEY is not configured")
    return f.encrypt(secret.encode()).decode()


def _decrypt_mfa_secret(service: DatabaseAuthService, token: str) -> str:
    f = _get_fernet(service)
    if not f:
        raise ValueError("DATA_ENCRYPTION_KEY is not configured")
    try:
        return f.decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Cannot decrypt TOTP secret") from exc


def _generate_recovery_codes(service: DatabaseAuthService, count: int = 10) -> List[str]:
    return [secrets.token_urlsafe(10) for _ in range(count)]


def _hash_recovery_codes(service: DatabaseAuthService, codes: List[str]) -> List[str]:
    return [
        bcrypt.hashpw(code.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        for code in codes
    ]


def _consume_recovery_code(service: DatabaseAuthService, db_user: User, code: str) -> bool:
    hashes: List[str] = list(getattr(db_user, "mfa_recovery_hashes", None) or [])
    for i, h in enumerate(hashes):
        try:
            if bcrypt.checkpw(code.encode("utf-8"), h.encode("utf-8")):
                hashes.pop(i)
                db_user.mfa_recovery_hashes = hashes
                return True
        except (TypeError, ValueError):
            continue
    return False


def _verify_totp_code_in_db_user(service: DatabaseAuthService, db_user: User, code: str) -> bool:
    if not db_user or not db_user.totp_secret:
        return False
    if _consume_recovery_code(service, db_user, code):
        return True
    try:
        secret = _decrypt_mfa_secret(service, db_user.totp_secret)
    except ValueError:
        return False
    return bool(pyotp.TOTP(secret).verify(code, valid_window=1))


def enroll_totp(service: DatabaseAuthService, user_id: str) -> Dict[str, str]:
    if not _get_fernet(service):
        raise ValueError("DATA_ENCRYPTION_KEY must be configured to use TOTP")
    with get_db_session() as db:
        user = db.query(User).filter_by(id=user_id).first()
        if not user:
            raise ValueError("User not found")
        secret = pyotp.random_base32()
        user.totp_secret = _encrypt_mfa_secret(service, secret)
        db.flush()
        uri = pyotp.TOTP(secret).provisioning_uri(
            name=user.email or user.username,
            issuer_name="Be Observant",
        )
        return {"otpauth_url": uri, "secret": secret}


def verify_enable_totp(service: DatabaseAuthService, user_id: str, code: str) -> List[str]:
    with get_db_session() as db:
        user = db.query(User).filter_by(id=user_id).first()
        if not user or not user.totp_secret:
            raise ValueError("TOTP not enrolled for user")
        if not pyotp.TOTP(_decrypt_mfa_secret(service, user.totp_secret)).verify(code, valid_window=1):
            raise ValueError("Invalid TOTP code")
        user.mfa_enabled = True
        user.must_setup_mfa = False
        codes = _generate_recovery_codes(service)
        user.mfa_recovery_hashes = _hash_recovery_codes(service, codes)
        service._log_audit(db, user.tenant_id, user.id, "mfa.enabled", "users", user.id, {})
        return codes


def verify_totp_code(service: DatabaseAuthService, user: User, code: str) -> bool:
    if not user or not user.totp_secret:
        return False
    with get_db_session() as db:
        db_user = db.query(User).filter_by(id=user.id).first()
        return _verify_totp_code_in_db_user(service, db_user, code) if db_user else False


def disable_totp(
    service: DatabaseAuthService,
    user_id: str,
    current_password: Optional[str] = None,
    code: Optional[str] = None,
) -> bool:
    with get_db_session() as db:
        user = db.query(User).filter_by(id=user_id).first()
        if not user or not user.mfa_enabled:
            return False
        del current_password
        verified = bool(code and _verify_totp_code_in_db_user(service, user, code))
        if not verified:
            return False
        user.mfa_enabled = False
        user.totp_secret = None
        user.mfa_recovery_hashes = None
        service._log_audit(db, user.tenant_id, user.id, "mfa.disabled", "users", user.id, {})
        return True


def reset_totp(service: DatabaseAuthService, user_id: str, admin_id: str) -> bool:
    with get_db_session() as db:
        user = db.query(User).filter_by(id=user_id).first()
        if not user or not user.mfa_enabled:
            return False
        user.mfa_enabled = False
        user.totp_secret = None
        user.mfa_recovery_hashes = None
        service._log_audit(db, user.tenant_id, admin_id, "mfa.reset", "users", user.id, {"admin_id": admin_id})
        return True

def mfa_setup_challenge(service: DatabaseAuthService, user: User) -> JSONDict:
    setup_token = create_mfa_setup_token_op(user)
    if not setup_token:
        raise ValueError("Unable to create MFA setup token")
    return {
        service._MFA_SETUP_RESPONSE: True,
        "setup_token": setup_token.access_token,
    }


def needs_mfa_setup(user: User) -> bool:
    return getattr(user, "must_setup_mfa", False) and not getattr(user, "mfa_enabled", False)
