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

#
# circuit breaker
# - protects downstream calls when repeated failures occur
# - states: closed (normal), open (short-circuit), half_open (trial)
# - opens after failure_threshold errors; after recovery_timeout it permits a single trial
# - a successful trial closes the breaker; a failed trial reopens it
#
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
            #
            # locking strategy
            # - snapshot current state under a short critical section
            # - release the lock before awaiting the wrapped coroutine
            # - update counters/state only after the await completes
            # this avoids holding locks across awaits and prevents deadlocks
            #
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
            except Exception:
                self._on_failure()
                raise
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

#
# cache
# - in-memory ttl cache keyed by repo_url + activity_type (+kwargs)
# - used as a best-effort accelerator to avoid redundant api calls
#
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
                logger.debug(f"cache hit for {activity_type} - {repo_url}")
                return entry["data"]
            else:
                del _cache[key]
    logger.debug(f"cache miss for {activity_type} - {repo_url}")
    return None

def _set_cache(repo_url: str, activity_type: str, data: Any, ttl: int = 600, **kwargs) -> None:
    key = _generate_cache_key(repo_url, activity_type, **kwargs)
    with _cache_lock:
        _cache[key] = {
            "data": data,
            "expires_at": time.time() + ttl
        }
        logger.debug(f"cached {activity_type} for {repo_url} (ttl: {ttl}s)")

# shared breaker instance
circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30, name="github_api")
