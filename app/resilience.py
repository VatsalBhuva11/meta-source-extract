import asyncio
import time
from typing import Any, Callable, Dict, Optional, TypeVar
import threading
import hashlib
import json
import functools

from application_sdk.observability.logger_adaptor import get_logger

logger = get_logger(__name__)

T = TypeVar('T')

# Simple in-memory cache
_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = threading.Lock()

def _generate_cache_key(repo_url: str, activity_type: str, **kwargs) -> str:
    """Generate a cache key based on repo URL, activity type, and parameters."""
    key_data = {
        "repo_url": repo_url,
        "activity_type": activity_type,
        **kwargs
    }
    key_string = json.dumps(key_data, sort_keys=True)
    return hashlib.md5(key_string.encode()).hexdigest()

def _get_from_cache(repo_url: str, activity_type: str, **kwargs) -> Optional[Any]:
    """Get cached data if available and not expired."""
    key = _generate_cache_key(repo_url, activity_type, **kwargs)
    
    with _cache_lock:
        if key in _cache:
            entry = _cache[key]
            if time.time() < entry["expires_at"]:
                logger.debug(f"Cache hit for {activity_type} - {repo_url}")
                return entry["data"]
            else:
                # Expired, remove it
                del _cache[key]
    
    logger.debug(f"Cache miss for {activity_type} - {repo_url}")
    return None

def _set_cache(repo_url: str, activity_type: str, data: Any, ttl: int = 600, **kwargs) -> None:
    """Cache data with TTL."""
    key = _generate_cache_key(repo_url, activity_type, **kwargs)
    
    with _cache_lock:
        _cache[key] = {
            "data": data,
            "expires_at": time.time() + ttl
        }
        logger.debug(f"Cached {activity_type} for {repo_url} (TTL: {ttl}s)")

def with_resilience(activity_type: str, cache_ttl: int = 600):
    """
    Minimal resilience decorator that only adds caching.
    This reduces the risk of timeouts while still providing caching benefits.
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # Extract repo_url from args (assuming it's the first argument after self)
            repo_url = args[1] if len(args) > 1 else None
            
            # Check cache first - this is fast and doesn't add delay
            if repo_url:
                cached_result = _get_from_cache(repo_url, activity_type, **kwargs)
                if cached_result is not None:
                    return cached_result
            
            # Execute the function
            try:
                result = await func(*args, **kwargs)
                
                # Cache successful results
                if repo_url:
                    _set_cache(repo_url, activity_type, result, cache_ttl, **kwargs)
                
                return result
            except Exception as e:
                logger.error(f"Activity {activity_type} failed", extra={"repo_url": repo_url, "error": str(e)})
                raise
        
        return wrapper
    return decorator
