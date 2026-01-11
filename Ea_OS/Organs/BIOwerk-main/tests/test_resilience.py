"""
Comprehensive tests for service mesh resilience patterns.

Tests cover:
- Circuit Breaker state transitions
- Retry with exponential backoff
- Bulkhead pattern
- ResilientHttpClient integration
- Health-aware routing
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, Mock, patch
import httpx

from matrix.resilience import (
    CircuitBreaker,
    CircuitBreakerState,
    CircuitBreakerError,
    retry_with_backoff,
    RetryExhaustedError,
    Bulkhead,
    BulkheadFullError,
    ResilientHttpClient,
    HealthAwareRouter
)


# ============================================================================
# CIRCUIT BREAKER TESTS
# ============================================================================

class TestCircuitBreaker:
    """Test circuit breaker pattern."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_starts_closed(self):
        """Circuit breaker should start in CLOSED state."""
        cb = CircuitBreaker(service_name="test_service")
        assert cb.state == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_on_failures(self):
        """Circuit breaker should open after threshold failures."""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=3,
            window_size=5
        )

        async def failing_func():
            raise Exception("Service error")

        # Should remain closed for first 2 failures
        for _ in range(2):
            with pytest.raises(Exception):
                await cb.call(failing_func)
            assert cb.state == CircuitBreakerState.CLOSED

        # Should open on 3rd failure
        with pytest.raises(Exception):
            await cb.call(failing_func)
        assert cb.state == CircuitBreakerState.OPEN

    @pytest.mark.asyncio
    async def test_circuit_breaker_rejects_when_open(self):
        """Circuit breaker should reject calls when OPEN."""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=1
        )

        async def failing_func():
            raise Exception("Service error")

        # Open the circuit
        with pytest.raises(Exception):
            await cb.call(failing_func)

        assert cb.state == CircuitBreakerState.OPEN

        # Should reject subsequent calls
        with pytest.raises(CircuitBreakerError) as exc_info:
            await cb.call(failing_func)

        assert "Circuit breaker is OPEN" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_circuit_breaker_transitions_to_half_open(self):
        """Circuit breaker should transition to HALF_OPEN after timeout."""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=1,
            timeout=1  # 1 second timeout
        )

        async def failing_func():
            raise Exception("Service error")

        async def success_func():
            return "success"

        # Open the circuit
        with pytest.raises(Exception):
            await cb.call(failing_func)

        assert cb.state == CircuitBreakerState.OPEN

        # Wait for timeout
        await asyncio.sleep(1.1)

        # Should transition to HALF_OPEN and allow test call
        result = await cb.call(success_func)
        assert result == "success"
        assert cb.state == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_breaker_closes_on_success_in_half_open(self):
        """Circuit breaker should close after success threshold in HALF_OPEN."""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=1,
            success_threshold=2,
            timeout=1
        )

        async def failing_func():
            raise Exception("Service error")

        async def success_func():
            return "success"

        # Open the circuit
        with pytest.raises(Exception):
            await cb.call(failing_func)

        await asyncio.sleep(1.1)

        # First success in HALF_OPEN
        await cb.call(success_func)
        assert cb.state == CircuitBreakerState.HALF_OPEN

        # Second success should close circuit
        await cb.call(success_func)
        assert cb.state == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_breaker_reopens_on_failure_in_half_open(self):
        """Circuit breaker should reopen on any failure in HALF_OPEN."""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=1,
            timeout=1
        )

        async def failing_func():
            raise Exception("Service error")

        # Open the circuit
        with pytest.raises(Exception):
            await cb.call(failing_func)

        await asyncio.sleep(1.1)

        # Failure in HALF_OPEN should reopen circuit
        with pytest.raises(Exception):
            await cb.call(failing_func)

        assert cb.state == CircuitBreakerState.OPEN

    @pytest.mark.asyncio
    async def test_circuit_breaker_failure_rate_threshold(self):
        """Circuit breaker should open based on failure rate."""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=10,  # High threshold
            failure_rate_threshold=0.5,  # 50% failure rate
            window_size=10
        )

        async def failing_func():
            raise Exception("Service error")

        async def success_func():
            return "success"

        # 5 successes, 5 failures = 50% failure rate
        for _ in range(5):
            await cb.call(success_func)

        for _ in range(4):
            with pytest.raises(Exception):
                await cb.call(failing_func)

        assert cb.state == CircuitBreakerState.CLOSED

        # One more failure should trigger open (50% threshold)
        with pytest.raises(Exception):
            await cb.call(failing_func)

        assert cb.state == CircuitBreakerState.OPEN


# ============================================================================
# RETRY TESTS
# ============================================================================

class TestRetryWithBackoff:
    """Test retry with exponential backoff."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_immediately(self):
        """Retry should return immediately on first success."""
        call_count = 0

        async def success_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await retry_with_backoff(
            success_func,
            max_attempts=3,
            service_name="test"
        )

        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_succeeds_after_failures(self):
        """Retry should succeed after transient failures."""
        call_count = 0

        async def eventually_succeeds():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Transient error")
            return "success"

        start = time.time()
        result = await retry_with_backoff(
            eventually_succeeds,
            max_attempts=3,
            initial_delay=0.01,
            service_name="test"
        )
        duration = time.time() - start

        assert result == "success"
        assert call_count == 3
        # Should have some delay (2 retries with ~0.01s each)
        assert duration > 0.01

    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        """Retry should raise RetryExhaustedError after max attempts."""
        call_count = 0

        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise Exception("Persistent error")

        with pytest.raises(RetryExhaustedError) as exc_info:
            await retry_with_backoff(
                always_fails,
                max_attempts=3,
                initial_delay=0.01,
                service_name="test"
            )

        assert call_count == 3
        assert "3 retry attempts failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_retry_exponential_backoff(self):
        """Retry delays should follow exponential backoff."""
        call_times = []

        async def failing_func():
            call_times.append(time.time())
            raise Exception("Error")

        try:
            await retry_with_backoff(
                failing_func,
                max_attempts=3,
                initial_delay=0.1,
                exponential_base=2.0,
                jitter=False,  # Disable jitter for predictable delays
                service_name="test"
            )
        except RetryExhaustedError:
            pass

        # Check delays between calls
        if len(call_times) >= 2:
            delay1 = call_times[1] - call_times[0]
            # First retry delay should be ~0.1s
            assert 0.08 < delay1 < 0.15

        if len(call_times) >= 3:
            delay2 = call_times[2] - call_times[1]
            # Second retry delay should be ~0.2s (exponential base 2)
            assert 0.15 < delay2 < 0.25

    @pytest.mark.asyncio
    async def test_retry_max_delay(self):
        """Retry should not exceed max_delay."""
        call_times = []

        async def failing_func():
            call_times.append(time.time())
            raise Exception("Error")

        try:
            await retry_with_backoff(
                failing_func,
                max_attempts=5,
                initial_delay=1.0,
                max_delay=0.5,  # Lower than initial delay
                exponential_base=2.0,
                jitter=False,
                service_name="test"
            )
        except RetryExhaustedError:
            pass

        # All delays should be capped at max_delay
        for i in range(1, len(call_times)):
            delay = call_times[i] - call_times[i-1]
            assert delay <= 0.6  # Allow some tolerance


# ============================================================================
# BULKHEAD TESTS
# ============================================================================

class TestBulkhead:
    """Test bulkhead pattern."""

    @pytest.mark.asyncio
    async def test_bulkhead_allows_within_capacity(self):
        """Bulkhead should allow requests within capacity."""
        bulkhead = Bulkhead(
            service_name="test_service",
            max_concurrent=2
        )

        results = []

        async def slow_task(task_id):
            async with bulkhead.acquire():
                await asyncio.sleep(0.1)
                results.append(task_id)

        # Run 2 concurrent tasks (within capacity)
        await asyncio.gather(
            slow_task(1),
            slow_task(2)
        )

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_bulkhead_queues_excess_requests(self):
        """Bulkhead should queue requests exceeding capacity."""
        bulkhead = Bulkhead(
            service_name="test_service",
            max_concurrent=2,
            timeout=2.0
        )

        start_times = []
        end_times = []

        async def slow_task(task_id):
            start_times.append(time.time())
            async with bulkhead.acquire():
                await asyncio.sleep(0.2)
                end_times.append(time.time())

        # Run 4 tasks with max_concurrent=2
        await asyncio.gather(
            slow_task(1),
            slow_task(2),
            slow_task(3),
            slow_task(4)
        )

        # All should complete
        assert len(end_times) == 4

        # Tasks should be processed in batches
        # First 2 should start immediately
        # Last 2 should wait for first batch

    @pytest.mark.asyncio
    async def test_bulkhead_rejects_on_timeout(self):
        """Bulkhead should reject if can't acquire slot within timeout."""
        bulkhead = Bulkhead(
            service_name="test_service",
            max_concurrent=1,
            timeout=0.1
        )

        async def long_task():
            async with bulkhead.acquire():
                await asyncio.sleep(1.0)

        async def quick_task():
            async with bulkhead.acquire():
                return "success"

        # Start long task
        long_task_future = asyncio.create_task(long_task())

        # Wait a bit to ensure long task has acquired slot
        await asyncio.sleep(0.05)

        # Quick task should timeout waiting for slot
        with pytest.raises(BulkheadFullError) as exc_info:
            await quick_task()

        assert "Timeout waiting for bulkhead" in str(exc_info.value)

        # Cleanup
        long_task_future.cancel()
        try:
            await long_task_future
        except asyncio.CancelledError:
            pass


# ============================================================================
# RESILIENT HTTP CLIENT TESTS
# ============================================================================

class TestResilientHttpClient:
    """Test ResilientHttpClient integration."""

    @pytest.mark.asyncio
    async def test_resilient_client_success(self):
        """ResilientHttpClient should handle successful requests."""
        async with ResilientHttpClient(
            service_name="test_service",
            base_url="http://test.example.com",
            enable_circuit_breaker=False,
            enable_retry=False,
            enable_bulkhead=False
        ) as client:
            # Mock the underlying httpx client
            with patch.object(client._client, 'get') as mock_get:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"result": "success"}
                mock_get.return_value = mock_response

                response = await client.get("/test")

                assert response.status_code == 200
                assert response.json() == {"result": "success"}

    @pytest.mark.asyncio
    async def test_resilient_client_with_circuit_breaker(self):
        """ResilientHttpClient should integrate circuit breaker."""
        async with ResilientHttpClient(
            service_name="test_service",
            base_url="http://test.example.com",
            circuit_breaker_kwargs={
                'failure_threshold': 2,
                'timeout': 1
            },
            enable_circuit_breaker=True,
            enable_retry=False,
            enable_bulkhead=False
        ) as client:
            # Mock failing requests
            with patch.object(client._client, 'get') as mock_get:
                mock_get.side_effect = httpx.HTTPError("Connection error")

                # First 2 failures should trigger circuit breaker
                for _ in range(2):
                    with pytest.raises(httpx.HTTPError):
                        await client.get("/test")

                # Circuit should be open now
                assert client.circuit_breaker.state == CircuitBreakerState.OPEN

                # Next call should be rejected by circuit breaker
                with pytest.raises(CircuitBreakerError):
                    await client.get("/test")

    @pytest.mark.asyncio
    async def test_resilient_client_with_retry(self):
        """ResilientHttpClient should integrate retry logic."""
        call_count = 0

        async with ResilientHttpClient(
            service_name="test_service",
            base_url="http://test.example.com",
            retry_kwargs={
                'max_attempts': 3,
                'initial_delay': 0.01
            },
            enable_circuit_breaker=False,
            enable_retry=True,
            enable_bulkhead=False
        ) as client:
            with patch.object(client._client, 'get') as mock_get:
                def side_effect(*args, **kwargs):
                    nonlocal call_count
                    call_count += 1
                    if call_count < 3:
                        # Simulate server error (should retry)
                        raise httpx.HTTPError("Server error")
                    # Third attempt succeeds
                    mock_response = Mock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {"result": "success"}
                    return mock_response

                mock_get.side_effect = side_effect

                response = await client.get("/test")

                assert response.status_code == 200
                assert call_count == 3  # Should have retried twice


# ============================================================================
# HEALTH-AWARE ROUTER TESTS
# ============================================================================

class TestHealthAwareRouter:
    """Test health-aware routing."""

    def test_router_initializes_with_defaults(self):
        """HealthAwareRouter should initialize with default settings."""
        router = HealthAwareRouter()
        assert router.health_check_interval == 10
        assert router.unhealthy_threshold == 3
        assert router.healthy_threshold == 2

    def test_router_registers_services(self):
        """HealthAwareRouter should register services."""
        router = HealthAwareRouter()
        router.register_service("test_service", "http://test:8000/health")

        assert router.is_healthy("test_service") is True

    @pytest.mark.asyncio
    async def test_router_marks_service_unhealthy(self):
        """HealthAwareRouter should mark service unhealthy after threshold."""
        router = HealthAwareRouter(unhealthy_threshold=3)
        router.register_service("test_service", "http://test:8000/health")

        # Report failures
        for _ in range(2):
            await router.update_health("test_service", is_healthy=False)
            assert router.is_healthy("test_service") is True  # Still healthy

        # Third failure should mark unhealthy
        await router.update_health("test_service", is_healthy=False)
        assert router.is_healthy("test_service") is False

    @pytest.mark.asyncio
    async def test_router_marks_service_healthy_after_recovery(self):
        """HealthAwareRouter should mark service healthy after recovery."""
        router = HealthAwareRouter(
            unhealthy_threshold=2,
            healthy_threshold=2
        )
        router.register_service("test_service", "http://test:8000/health")

        # Mark unhealthy
        await router.update_health("test_service", is_healthy=False)
        await router.update_health("test_service", is_healthy=False)
        assert router.is_healthy("test_service") is False

        # Report successes to recover
        await router.update_health("test_service", is_healthy=True)
        # Health score needs to be > 0.5 to recover
        await router.update_health("test_service", is_healthy=True)
        await router.update_health("test_service", is_healthy=True)

        assert router.is_healthy("test_service") is True

    @pytest.mark.asyncio
    async def test_router_health_score(self):
        """HealthAwareRouter should track health scores."""
        router = HealthAwareRouter()
        router.register_service("test_service", "http://test:8000/health")

        # Initial health score should be 1.0
        assert router.get_health_score("test_service") == 1.0

        # Failures should decrease score
        await router.update_health("test_service", is_healthy=False)
        assert router.get_health_score("test_service") < 1.0

        # Successes should increase score
        for _ in range(5):
            await router.update_health("test_service", is_healthy=True)

        assert router.get_health_score("test_service") == 1.0


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """Integration tests combining multiple patterns."""

    @pytest.mark.asyncio
    async def test_all_patterns_together(self):
        """Test circuit breaker + retry + bulkhead working together."""
        async with ResilientHttpClient(
            service_name="test_service",
            base_url="http://test.example.com",
            circuit_breaker_kwargs={'failure_threshold': 5},
            retry_kwargs={'max_attempts': 2, 'initial_delay': 0.01},
            bulkhead_kwargs={'max_concurrent': 3},
            enable_circuit_breaker=True,
            enable_retry=True,
            enable_bulkhead=True
        ) as client:
            assert client.circuit_breaker is not None
            assert client.bulkhead is not None
            assert client.retry_config is not None

            # All patterns should be active
            assert client.circuit_breaker.state == CircuitBreakerState.CLOSED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
