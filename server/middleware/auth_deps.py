from fastapi import Depends
from models.auth_models import TokenData, Permission
from routers.auth_router import get_current_user, require_permission


async def get_auth_user(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    return current_user


def require_read_alerts():
    return require_permission(Permission.READ_ALERTS)


def require_write_alerts():
    return require_permission(Permission.WRITE_ALERTS)


def require_delete_alerts():
    return require_permission(Permission.DELETE_ALERTS)


def require_read_channels():
    return require_permission(Permission.READ_CHANNELS)


def require_write_channels():
    return require_permission(Permission.WRITE_CHANNELS)


def require_delete_channels():
    return require_permission(Permission.DELETE_CHANNELS)


def require_read_logs():
    return require_permission(Permission.READ_LOGS)


def require_read_traces():
    return require_permission(Permission.READ_TRACES)


def require_read_agents():
    return require_permission(Permission.READ_AGENTS)


def require_read_dashboards():
    return require_permission(Permission.READ_DASHBOARDS)


def require_write_dashboards():
    return require_permission(Permission.WRITE_DASHBOARDS)


def require_delete_dashboards():
    return require_permission(Permission.DELETE_DASHBOARDS)
