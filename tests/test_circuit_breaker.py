import asyncio
import time
import pytest

from app.resilience import CircuitBreaker


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_failures():
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=0.2, name="test")

    call_count = {"n": 0}

    @breaker
    async def flaky():
        call_count["n"] += 1
        raise RuntimeError("boom")

    # 3 failures trip the breaker
    for _ in range(3):
        with pytest.raises(RuntimeError):
            await flaky()

    # now breaker should be open; calls are rejected immediately
    with pytest.raises(Exception) as exc:
        await flaky()
    assert "OPEN" in str(exc.value)


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_and_close_on_success():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1, name="test2")

    state = {"fail": True, "calls": 0}

    @breaker
    async def sometimes():
        state["calls"] += 1
        if state["fail"]:
            raise RuntimeError("boom")
        return "ok"

    # first failure opens (threshold=1)
    with pytest.raises(RuntimeError):
        await sometimes()

    # immediate call is blocked (still open)
    with pytest.raises(Exception):
        await sometimes()

    # wait for half-open window
    await asyncio.sleep(0.11)

    # next call is trial in HALF_OPEN; make it succeed
    state["fail"] = False
    out = await sometimes()
    assert out == "ok"

    # subsequent calls pass in CLOSED
    out2 = await sometimes()
    assert out2 == "ok"  # stays closed after success 