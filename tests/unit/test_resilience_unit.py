"""
Unit tests for resilience patterns (circuit breaker, caching).
"""
import pytest
import asyncio
import time
from unittest.mock import Mock, patch
from app.resilience import CircuitBreaker, _get_from_cache, _set_cache


class TestCircuitBreaker:
    """Unit tests for CircuitBreaker class."""

    def test_circuit_breaker_initial_state(self):
        """Test circuit breaker starts in CLOSED state."""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=1.0, name="test")
        assert breaker.state.value == "closed"

    def test_circuit_breaker_successful_calls(self):
        """Test circuit breaker with successful calls."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=1.0, name="test")
        
        @breaker
        async def successful_func():
            return "success"
        
        # Should work normally
        result = asyncio.run(successful_func())
        assert result == "success"
        assert breaker.state.value == "closed"

    def test_circuit_breaker_failure_threshold(self):
        """Test circuit breaker opens after failure threshold."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=1.0, name="test")
        
        @breaker
        async def failing_func():
            raise ValueError("test error")
        
        # First failure
        with pytest.raises(ValueError):
            asyncio.run(failing_func())
        assert breaker.state.value == "closed"
        
        # Second failure - should open
        with pytest.raises(ValueError):
            asyncio.run(failing_func())
        assert breaker.state.value == "open"

    def test_circuit_breaker_open_state_blocks_calls(self):
        """Test circuit breaker blocks calls when open."""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=1.0, name="test")
        
        @breaker
        async def failing_func():
            raise ValueError("test error")
        
        # First failure opens the breaker
        with pytest.raises(ValueError):
            asyncio.run(failing_func())
        
        # Subsequent calls should be blocked
        with pytest.raises(Exception, match="Circuit breaker test is OPEN - service unavailable"):
            asyncio.run(failing_func())

    def test_circuit_breaker_recovery_timeout(self):
        """Test circuit breaker recovery after timeout."""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1, name="test")
        
        @breaker
        async def failing_func():
            raise ValueError("test error")
        
        # Open the breaker
        with pytest.raises(ValueError):
            asyncio.run(failing_func())
        
        # Wait for recovery timeout
        time.sleep(0.2)
        
        # Make another call - this should transition to half_open
        with pytest.raises(ValueError):
            asyncio.run(failing_func())
        
        # Should be in OPEN state after the call (fails again)
        assert breaker.state.value == "open"

    def test_circuit_breaker_half_open_success(self):
        """Test circuit breaker closes after successful call in half-open state."""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1, name="test")
        
        call_count = {"count": 0}
        
        @breaker
        async def conditional_func():
            call_count["count"] += 1
            if call_count["count"] == 1:
                raise ValueError("test error")
            return "success"
        
        # First call fails, opens breaker
        with pytest.raises(ValueError):
            asyncio.run(conditional_func())
        
        # Wait for recovery
        time.sleep(0.2)
        
        # Second call should succeed and close breaker
        result = asyncio.run(conditional_func())
        assert result == "success"
        assert breaker.state.value == "closed"

    def test_circuit_breaker_half_open_failure(self):
        """Test circuit breaker reopens after failure in half-open state."""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1, name="test")
        
        @breaker
        async def failing_func():
            raise ValueError("test error")
        
        # Open the breaker
        with pytest.raises(ValueError):
            asyncio.run(failing_func())
        
        # Wait for recovery
        time.sleep(0.2)
        
        # Call should fail and reopen breaker
        with pytest.raises(ValueError):
            asyncio.run(failing_func())
        
        assert breaker.state.value == "open"

    def test_circuit_breaker_different_functions(self):
        """Test circuit breaker with different functions."""
        breaker1 = CircuitBreaker(failure_threshold=1, recovery_timeout=1.0, name="test1")
        breaker2 = CircuitBreaker(failure_threshold=1, recovery_timeout=1.0, name="test2")
        
        @breaker1
        async def func1():
            raise ValueError("error1")
        
        @breaker2
        async def func2():
            return "success"
        
        # func1 should open its breaker
        with pytest.raises(ValueError):
            asyncio.run(func1())
        assert breaker1.state.value == "open"
        
        # func2 should work normally
        result = asyncio.run(func2())
        assert result == "success"
        assert breaker2.state.value == "closed"


class TestCaching:
    """Unit tests for caching functionality."""

    def test_set_and_get_cache(self):
        """Test basic cache set and get functionality."""
        key = "test_key"
        value = {"data": "test"}
        ttl = 60
        
        _set_cache(key, "test_type", value, ttl=ttl)
        result = _get_from_cache(key, "test_type")
        
        assert result == value

    def test_cache_miss(self):
        """Test cache miss returns None."""
        result = _get_from_cache("nonexistent_key", "test_type")
        assert result is None

    def test_cache_with_parameters(self):
        """Test cache with additional parameters."""
        key = "test_key"
        value = {"data": "test"}
        params = {"limit": 50, "offset": 0}
        
        _set_cache(key, "test_type", value, ttl=60, **params)
        result = _get_from_cache(key, "test_type", **params)
        
        assert result == value

    def test_cache_parameter_mismatch(self):
        """Test cache miss when parameters don't match."""
        key = "test_key"
        value = {"data": "test"}
        
        _set_cache(key, "test_type", value, ttl=60, limit=50)
        result = _get_from_cache(key, "test_type", limit=100)  # Different limit
        
        assert result is None

    def test_cache_ttl_expiration(self):
        """Test cache TTL expiration."""
        key = "test_key"
        value = {"data": "test"}
        ttl = 0.1  # Very short TTL
        
        _set_cache(key, "test_type", value, ttl=ttl)
        
        # Should be available immediately
        result = _get_from_cache(key, "test_type")
        assert result == value
        
        # Wait for expiration
        time.sleep(0.2)
        
        # Should be None after expiration
        result = _get_from_cache(key, "test_type")
        assert result is None

    def test_cache_different_types(self):
        """Test cache with different types."""
        key = "test_key"
        value1 = {"data": "test1"}
        value2 = {"data": "test2"}
        
        _set_cache(key, "type1", value1, ttl=60)
        _set_cache(key, "type2", value2, ttl=60)
        
        result1 = _get_from_cache(key, "type1")
        result2 = _get_from_cache(key, "type2")
        
        assert result1 == value1
        assert result2 == value2

    def test_cache_overwrite(self):
        """Test cache overwrite functionality."""
        key = "test_key"
        value1 = {"data": "test1"}
        value2 = {"data": "test2"}
        
        _set_cache(key, "test_type", value1, ttl=60)
        _set_cache(key, "test_type", value2, ttl=60)
        
        result = _get_from_cache(key, "test_type")
        assert result == value2

    def test_cache_cleanup(self):
        """Test cache cleanup of expired entries."""
        key1 = "test_key1"
        key2 = "test_key2"
        value = {"data": "test"}
        
        # Set with different TTLs
        _set_cache(key1, "test_type", value, ttl=0.1)  # Short TTL
        _set_cache(key2, "test_type", value, ttl=60)   # Long TTL
        
        # Wait for first to expire
        time.sleep(0.2)
        
        # First should be None, second should still be available
        result1 = _get_from_cache(key1, "test_type")
        result2 = _get_from_cache(key2, "test_type")
        
        assert result1 is None
        assert result2 == value

    def test_cache_with_complex_data(self):
        """Test cache with complex data structures."""
        key = "test_key"
        value = {
            "list": [1, 2, 3],
            "dict": {"nested": "value"},
            "string": "test",
            "number": 42,
            "boolean": True,
            "none": None
        }
        
        _set_cache(key, "test_type", value, ttl=60)
        result = _get_from_cache(key, "test_type")
        
        assert result == value
        assert result["list"] == [1, 2, 3]
        assert result["dict"]["nested"] == "value"
        assert result["string"] == "test"
        assert result["number"] == 42
        assert result["boolean"] is True
        assert result["none"] is None
