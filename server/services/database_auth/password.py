"""
Database authentication service utilities for handling password hashing and verification operations, providing functions to securely hash user passwords using bcrypt and verify plaintext passwords against stored hashed passwords during authentication. This module abstracts away the details of password hashing and verification, allowing for consistent and secure handling of user passwords within the database authentication service while also supporting optional synchronization of password operations with external authentication providers when configured.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from passlib.context import CryptContext

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
