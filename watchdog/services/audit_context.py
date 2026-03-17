"""
Service for managing audit context information, providing functions to set, reset, and retrieve audit-related data such as the IP address and user agent of incoming requests. This module uses Python's `contextvars` to maintain request-specific audit information that can be accessed throughout the request handling process. The service allows for setting the audit context at the beginning of a request, resetting it after the request is processed, and retrieving the current audit context when needed for logging or other purposes.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from contextvars import ContextVar, Token
from typing import Optional

audit_ip: ContextVar[Optional[str]] = ContextVar("audit_ip", default=None)
audit_user_agent: ContextVar[Optional[str]] = ContextVar("audit_user_agent", default=None)

def set_request_audit_context(ip_address: Optional[str], user_agent: Optional[str]) -> tuple[Token[Optional[str]], Token[Optional[str]]]:
    token_ip = audit_ip.set(ip_address)
    token_ua = audit_user_agent.set(user_agent)
    return token_ip, token_ua


def reset_request_audit_context(tokens: tuple[Token[Optional[str]], Token[Optional[str]]]) -> None:
    token_ip, token_ua = tokens
    audit_ip.reset(token_ip)
    audit_user_agent.reset(token_ua)


def get_request_audit_context() -> tuple[Optional[str], Optional[str]]:
    return audit_ip.get(), audit_user_agent.get()
