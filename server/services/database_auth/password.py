"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from passlib.context import CryptContext  # type: ignore[import-untyped]

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(service, password: str) -> str:
    sem = getattr(service, "_password_op_semaphore", None)
    if sem:
        with sem:
            return _pwd_ctx.hash(password)
    return _pwd_ctx.hash(password)


def verify_password(service, plain_password: str, hashed_password: str) -> bool:
    sem = getattr(service, "_password_op_semaphore", None)
    if sem:
        with sem:
            return _pwd_ctx.verify(plain_password, hashed_password)
    return _pwd_ctx.verify(plain_password, hashed_password)
