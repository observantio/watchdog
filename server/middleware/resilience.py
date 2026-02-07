"""Resilience decorators for service calls."""
import asyncio
import logging
from functools import wraps
from typing import Callable, TypeVar, ParamSpec
import httpx

from config import config

logger = logging.getLogger(__name__)

P = ParamSpec('P')
T = TypeVar('T')

def with_retry(
    max_retries: int = config.MAX_RETRIES,
    backoff: float = config.RETRY_BACKOFF
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator to retry failed async operations with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        backoff: Initial backoff time in seconds
        
    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except (httpx.HTTPError, asyncio.TimeoutError) as e:
                    last_exception = e
                    if attempt < max_retries:
                        wait_time = backoff * (2 ** attempt)
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries + 1} failed for "
                            f"{func.__name__}: {e}. Retrying in {wait_time}s..."
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(
                            f"All {max_retries + 1} attempts failed for "
                            f"{func.__name__}: {e}"
                        )
            
            raise last_exception
        
        return wrapper
    return decorator


def with_timeout(timeout: float = config.DEFAULT_TIMEOUT) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator to add timeout to async operations.
    
    Args:
        timeout: Timeout in seconds
        
    Returns:
        Decorated function with timeout
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
            except asyncio.TimeoutError:
                logger.error(f"Timeout after {timeout}s for {func.__name__}")
                raise
        
        return wrapper
    return decorator
