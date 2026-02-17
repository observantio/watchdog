"""DEPRECATED: server-side gateway router

This module previously provided `/api/gateway/validate` but the
standalone `gateway-auth-service` (container `gateway-auth`) now
implements OTLP token validation and is used by the nginx OTLP
gateway (see `configs/otlp-gateway.conf`).

The router is no longer registered in the main server. The file is left
in place as a deprecated reference and **may be removed** in a follow-up
commit.
"""

# Deprecated: no runtime behaviour in the main server.