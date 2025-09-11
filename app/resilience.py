import asyncio
import time
from typing import Any, Callable, Dict, Optional, TypeVar
import threading
import hashlib
import json
import functools
from enum import Enum

from application_sdk.observability.logger_adaptor import get_logger

logger = get_logger(__name__)

T = TypeVar('T')

# Circuit Breaker Implementation
class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    def __init__(self, failure_threshold=3, recovery_timeout=30, name="default"):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.name = name
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
        self._lock = threading.Lock()
    
    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # Snapshot state under lock, then release before awaiting
            with self._lock:
                state = self.state
                if state == CircuitState.OPEN and not self._should_attempt_reset():
                    raise Exception(f"Circuit breaker {self.name} is OPEN - service unavailable")
                if state == CircuitState.OPEN and self._should_attempt_reset():
                    self.state = CircuitState.HALF_OPEN
                    logger.info(f"Circuit breaker {self.name} transitioning to HALF_OPEN")
            
            try:
                result = await func(*args, **kwargs)
                self._on_success()
                return result
            except Exception as e:
                self._on_failure()
                raise e
        return wrapper
    
    def _should_attempt_reset(self) -> bool:
        if self.last_failure_time is None:
            return True
        return time.time() - self.last_failure_time >= self.recovery_timeout
    
    def _on_success(self):
        with self._lock:
            self.failure_count = 0
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.CLOSED
                logger.info(f"Circuit breaker {self.name} reset to CLOSED")
    
    def _on_failure(self):
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                logger.warning(f"Circuit breaker {self.name} opened after {self.failure_count} failures")

# Rate Limiter Implementation
class RateLimiter:
    def __init__(self, rate=2.0, capacity=5, name="default"):
        self.rate = rate
        self.capacity = capacity
        self.name = name
        self.tokens = capacity
        self.last_update = time.time()
        self._lock = threading.Lock()
    
    async def acquire(self, tokens=1) -> bool:
        with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_update = now
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            else:
                logger.warning(f"Rate limiter {self.name} blocked request - insufficient tokens")
                return False
    
    async def wait_for_tokens(self, tokens=1, max_wait=5.0) -> None:
        start_time = time.time()
        while not await self.acquire(tokens):
            wait_time = min((tokens - self.tokens) / self.rate, 1.0)
            if time.time() - start_time > max_wait:
                logger.warning(f"Rate limiter {self.name} exceeded max wait time, proceeding anyway")
                break
            await asyncio.sleep(wait_time)

# Cache Implementation
_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = threading.Lock()

def _generate_cache_key(repo_url: str, activity_type: str, **kwargs) -> str:
    key_data = {
        "repo_url": repo_url,
        "activity_type": activity_type,
        **kwargs
    }
    key_string = json.dumps(key_data, sort_keys=True)
    return hashlib.md5(key_string.encode()).hexdigest()

def _get_from_cache(repo_url: str, activity_type: str, **kwargs) -> Optional[Any]:
    key = _generate_cache_key(repo_url, activity_type, **kwargs)
    
    with _cache_lock:
        if key in _cache:
            entry = _cache[key]
            if time.time() < entry["expires_at"]:
                logger.debug(f"Cache hit for {activity_type} - {repo_url}")
                return entry["data"]
            else:
                del _cache[key]
    
    logger.debug(f"Cache miss for {activity_type} - {repo_url}")
    return None

def _set_cache(repo_url: str, activity_type: str, data: Any, ttl: int = 600, **kwargs) -> None:
    key = _generate_cache_key(repo_url, activity_type, **kwargs)
    
    with _cache_lock:
        _cache[key] = {
            "data": data,
            "expires_at": time.time() + ttl
        }
        logger.debug(f"Cached {activity_type} for {repo_url} (TTL: {ttl}s)")

# Global instances
circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30, name="github_api")
rate_limiter = RateLimiter(rate=2.0, capacity=5, name="github_api")

def with_resilience(activity_type: str, cache_ttl: int = 600):
    """
    Complete resilience decorator with caching, rate limiting, and circuit breaker.
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # Extract repo_url from args
            repo_url = args[1] if len(args) > 1 else None
            
            # 1. Check cache first (fastest)
            if repo_url:
                cached_result = _get_from_cache(repo_url, activity_type, **kwargs)
                if cached_result is not None:
                    return cached_result
            
            # 2. Apply rate limiting
            try:
                await asyncio.wait_for(
                    rate_limiter.wait_for_tokens(max_wait=5.0),
                    timeout=6.0
                )
            except asyncio.TimeoutError:
                logger.warning(f"Rate limiter timeout for {activity_type}, proceeding anyway")
            
            # 3. Apply circuit breaker
            @circuit_breaker
            async def _wrapped_func():
                return await func(*args, **kwargs)
            
            try:
                result = await _wrapped_func()
                
                # 4. Cache successful results
                if repo_url:
                    _set_cache(repo_url, activity_type, result, cache_ttl, **kwargs)
                
                return result
            except Exception as e:
                logger.error(f"Activity {activity_type} failed", extra={"repo_url": repo_url, "error": str(e)})
                raise
        
        return wrapper
    return decorator
