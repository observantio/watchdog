"""Authentication middleware and dependencies."""
from typing import Optional
from fastapi import Header, HTTPException, status
from config import config, constants


def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias=config.API_KEY_HEADER)
) -> None:
    """Verify API key from request header.
    
    Args:
        x_api_key: API key from request header
        
    Raises:
        HTTPException: If authentication is enabled and key is invalid
    """
    if not config.ENABLE_AUTH:
        return
    
    if not x_api_key or x_api_key != config.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=constants.ERROR_UNAUTHORIZED,
            headers={"WWW-Authenticate": "ApiKey"},
        )
