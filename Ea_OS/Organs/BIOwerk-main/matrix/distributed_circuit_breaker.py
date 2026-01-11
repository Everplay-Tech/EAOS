"""Distributed circuit breaker using Redis for shared state across instances.

This module extends the standard circuit breaker pattern to work across multiple
service instances, ensuring all replicas make consistent decisions about service
health and circuit state.

Key Features:
- Shared state in Redis (all instances see same circuit state)
- Atomic state transitions using Lua scripts
- Sliding window for failure rate calculation
- Automatic state recovery and cleanup
- Prometheus metrics integration
- Compatible with existing CircuitBreaker interface

Usage:
    # Create distributed circuit breaker
    breaker = DistributedCircuitBreaker(
        redis=redis_client,
        service_name="agent_service",
        failure_threshold=5,
        timeout=60
    )

    # Use with async function
    try:
        result = await breaker.call(agent_service.process, request)
    except CircuitBreakerError:
        # Circuit is open, fail fast
        return fallback_response()

    # Check circuit state
    if breaker.state == CircuitBreakerState.OPEN:
        # Service is down across all instances
        use_fallback()
"""

import asyncio
import time
import json
from enum import Enum
from typing import Optional, Callable, Any, List
from datetime import datetime
from redis.asyncio import Redis
from prometheus_client import Counter, Gauge
import structlog

logger = structlog.get_logger(__name__)


# Import state enum and error from resilience module
class CircuitBreakerState(Enum):
    """Circuit breaker states following the standard pattern."""
    CLOSED = 0      # Normal operation, requests pass through
    OPEN = 1        # Failing fast, requests are rejected immediately
    HALF_OPEN = 2   # Testing if service recovered, limited requests allowed


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open and request is rejected."""
    pass


# Prometheus metrics (shared with local circuit breaker)
circuit_breaker_state_metric = Gauge(
    'distributed_circuit_breaker_state',
    'Current state of distributed circuit breaker (0=CLOSED, 1=OPEN, 2=HALF_OPEN)',
    ['service']
)

circuit_breaker_transitions_metric = Counter(
    'distributed_circuit_breaker_transitions_total',
    'Total number of distributed circuit breaker state transitions',
    ['service', 'from_state', 'to_state']
)

circuit_breaker_failures_metric = Counter(
    'distributed_circuit_breaker_failures_total',
    'Total number of failures tracked by distributed circuit breaker',
    ['service']
)

circuit_breaker_successes_metric = Counter(
    'distributed_circuit_breaker_successes_total',
    'Total number of successes tracked by distributed circuit breaker',
    ['service']
)

circuit_breaker_rejected_metric = Counter(
    'distributed_circuit_breaker_rejected_total',
    'Total number of requests rejected due to open distributed circuit',
    ['service']
)


class DistributedCircuitBreaker:
    """Distributed circuit breaker with Redis-backed shared state.

    All instances of this circuit breaker (across multiple service replicas)
    share the same state in Redis, ensuring consistent circuit decisions.

    Attributes:
        redis: Redis client instance
        service_name: Name of the service for metrics and logging
        failure_threshold: Consecutive failures before opening (default: 5)
        success_threshold: Consecutive successes in HALF_OPEN to close (default: 2)
        timeout: Seconds before transitioning OPEN -> HALF_OPEN (default: 60)
        failure_rate_threshold: Failure rate to trigger open (default: 0.5)
        window_size: Number of recent calls for failure rate (default: 10)
    """

    KEY_PREFIX = "circuit_breaker:"

    def __init__(
        self,
        redis: Redis,
        service_name: str,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: int = 60,
        failure_rate_threshold: float = 0.5,
        window_size: int = 10,
    ):
        """Initialize distributed circuit breaker.

        Args:
            redis: Redis client instance
            service_name: Service name for circuit breaker
            failure_threshold: Failures before opening
            success_threshold: Successes to close from HALF_OPEN
            timeout: Timeout before OPEN -> HALF_OPEN
            failure_rate_threshold: Failure rate threshold (0.0-1.0)
            window_size: Size of sliding window for failure rate
        """
        self.redis = redis
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout = timeout
        self.failure_rate_threshold = failure_rate_threshold
        self.window_size = window_size

        # Redis keys
        self.key_state = f"{self.KEY_PREFIX}{service_name}:state"
        self.key_failure_count = f"{self.KEY_PREFIX}{service_name}:failure_count"
        self.key_success_count = f"{self.KEY_PREFIX}{service_name}:success_count"
        self.key_opened_at = f"{self.KEY_PREFIX}{service_name}:opened_at"
        self.key_recent_calls = f"{self.KEY_PREFIX}{service_name}:recent_calls"

        logger.info(
            "distributed_circuit_breaker_initialized",
            service=service_name,
            failure_threshold=failure_threshold,
            success_threshold=success_threshold,
            timeout=timeout,
            failure_rate_threshold=failure_rate_threshold,
        )

    async def _get_state(self) -> CircuitBreakerState:
        """Get current circuit state from Redis."""
        state_value = await self.redis.get(self.key_state)
        if state_value is None:
            # Initialize to CLOSED
            await self.redis.set(self.key_state, CircuitBreakerState.CLOSED.value)
            return CircuitBreakerState.CLOSED

        return CircuitBreakerState(int(state_value))

    async def _set_state(self, new_state: CircuitBreakerState) -> None:
        """Set circuit state in Redis."""
        await self.redis.set(self.key_state, new_state.value)
        circuit_breaker_state_metric.labels(service=self.service_name).set(new_state.value)

    async def _transition_to(self, new_state: CircuitBreakerState) -> None:
        """Transition to a new state with metrics and logging."""
        old_state = await self._get_state()
        if new_state == old_state:
            return

        await self._set_state(new_state)

        # Update metrics
        circuit_breaker_transitions_metric.labels(
            service=self.service_name,
            from_state=old_state.name,
            to_state=new_state.name,
        ).inc()

        # Handle state-specific logic
        if new_state == CircuitBreakerState.OPEN:
            await self.redis.set(self.key_opened_at, int(time.time()))
            failure_rate = await self._calculate_failure_rate()
            logger.warning(
                "distributed_circuit_breaker_opened",
                service=self.service_name,
                failure_rate=failure_rate,
            )
        elif new_state == CircuitBreakerState.HALF_OPEN:
            await self.redis.set(self.key_success_count, 0)
            await self.redis.set(self.key_failure_count, 0)
            logger.info(
                "distributed_circuit_breaker_half_open",
                service=self.service_name,
            )
        elif new_state == CircuitBreakerState.CLOSED:
            await self.redis.delete(
                self.key_failure_count,
                self.key_success_count,
                self.key_opened_at,
            )
            logger.info(
                "distributed_circuit_breaker_closed",
                service=self.service_name,
            )

    async def _get_count(self, key: str) -> int:
        """Get counter value from Redis."""
        value = await self.redis.get(key)
        return int(value) if value else 0

    async def _increment_count(self, key: str) -> int:
        """Increment counter in Redis."""
        return await self.redis.incr(key)

    async def _calculate_failure_rate(self) -> float:
        """Calculate failure rate from recent calls in Redis."""
        # Get recent calls from Redis list
        recent_calls_raw = await self.redis.lrange(self.key_recent_calls, 0, -1)

        if not recent_calls_raw:
            return 0.0

        # Decode calls (1=success, 0=failure)
        recent_calls = [int(call) for call in recent_calls_raw]
        failures = sum(1 for call in recent_calls if call == 0)

        return failures / len(recent_calls)

    async def _record_call(self, success: bool) -> None:
        """Record call result in Redis sliding window."""
        # Push to list (1=success, 0=failure)
        await self.redis.lpush(self.key_recent_calls, 1 if success else 0)

        # Trim to window size
        await self.redis.ltrim(self.key_recent_calls, 0, self.window_size - 1)

    async def _should_allow_request(self) -> bool:
        """Check if request should be allowed based on circuit state.

        Uses Lua script for atomic state check and transition.
        """
        state = await self._get_state()

        if state == CircuitBreakerState.CLOSED:
            return True

        elif state == CircuitBreakerState.OPEN:
            # Check if timeout expired (OPEN -> HALF_OPEN)
            opened_at = await self.redis.get(self.key_opened_at)
            if opened_at:
                elapsed = time.time() - int(opened_at)
                if elapsed >= self.timeout:
                    # Transition to HALF_OPEN
                    await self._transition_to(CircuitBreakerState.HALF_OPEN)
                    return True

            # Circuit still open
            circuit_breaker_rejected_metric.labels(service=self.service_name).inc()
            return False

        elif state == CircuitBreakerState.HALF_OPEN:
            # Allow limited requests in HALF_OPEN
            return True

        return False

    async def _on_success(self) -> None:
        """Handle successful call."""
        circuit_breaker_successes_metric.labels(service=self.service_name).inc()
        await self._record_call(success=True)

        state = await self._get_state()

        if state == CircuitBreakerState.CLOSED:
            # Reset failure count on success
            await self.redis.set(self.key_failure_count, 0)

        elif state == CircuitBreakerState.HALF_OPEN:
            # Increment success count
            success_count = await self._increment_count(self.key_success_count)

            # Check if we should close the circuit
            if success_count >= self.success_threshold:
                await self._transition_to(CircuitBreakerState.CLOSED)

    async def _on_failure(self) -> None:
        """Handle failed call."""
        circuit_breaker_failures_metric.labels(service=self.service_name).inc()
        await self._record_call(success=False)

        state = await self._get_state()

        if state == CircuitBreakerState.CLOSED:
            # Increment failure count
            failure_count = await self._increment_count(self.key_failure_count)

            # Check if we should open the circuit
            if failure_count >= self.failure_threshold:
                await self._transition_to(CircuitBreakerState.OPEN)
            else:
                # Also check failure rate
                failure_rate = await self._calculate_failure_rate()
                if failure_rate >= self.failure_rate_threshold:
                    await self._transition_to(CircuitBreakerState.OPEN)

        elif state == CircuitBreakerState.HALF_OPEN:
            # Any failure in HALF_OPEN reopens the circuit
            await self._transition_to(CircuitBreakerState.OPEN)

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection.

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result from func

        Raises:
            CircuitBreakerError: If circuit is open
            Exception: Any exception from func execution
        """
        # Check if request should be allowed
        if not await self._should_allow_request():
            raise CircuitBreakerError(
                f"Circuit breaker is OPEN for service '{self.service_name}'"
            )

        # Execute function
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise

    @property
    async def state(self) -> CircuitBreakerState:
        """Get current circuit breaker state.

        Note: This is an async property accessor.
        Use: state = await breaker.state
        """
        return await self._get_state()

    async def get_state(self) -> CircuitBreakerState:
        """Get current circuit breaker state (async method)."""
        return await self._get_state()

    async def reset(self) -> None:
        """Reset circuit breaker to CLOSED state (admin operation)."""
        await self._transition_to(CircuitBreakerState.CLOSED)
        logger.warning(
            "distributed_circuit_breaker_reset",
            service=self.service_name,
        )

    async def force_open(self) -> None:
        """Force circuit breaker to OPEN state (admin operation)."""
        await self._transition_to(CircuitBreakerState.OPEN)
        logger.warning(
            "distributed_circuit_breaker_force_opened",
            service=self.service_name,
        )

    async def get_metrics(self) -> dict:
        """Get current circuit breaker metrics.

        Returns:
            Dictionary with current metrics
        """
        state = await self._get_state()
        failure_count = await self._get_count(self.key_failure_count)
        success_count = await self._get_count(self.key_success_count)
        failure_rate = await self._calculate_failure_rate()

        metrics = {
            "service": self.service_name,
            "state": state.name,
            "failure_count": failure_count,
            "success_count": success_count,
            "failure_rate": failure_rate,
        }

        if state == CircuitBreakerState.OPEN:
            opened_at = await self.redis.get(self.key_opened_at)
            if opened_at:
                metrics["opened_at"] = int(opened_at)
                metrics["time_in_open"] = int(time.time()) - int(opened_at)

        return metrics


class DistributedCircuitBreakerManager:
    """Manager for creating distributed circuit breakers with shared Redis connection.

    Provides a convenient interface for creating circuit breakers without
    passing Redis connection each time.

    Usage:
        manager = DistributedCircuitBreakerManager(redis)

        breaker = manager.get_breaker("agent_service")
        result = await breaker.call(agent_service.process, request)
    """

    def __init__(self, redis: Redis):
        """Initialize circuit breaker manager.

        Args:
            redis: Redis client instance
        """
        self.redis = redis
        self._breakers: dict[str, DistributedCircuitBreaker] = {}

    def get_breaker(
        self,
        service_name: str,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: int = 60,
        failure_rate_threshold: float = 0.5,
        window_size: int = 10,
    ) -> DistributedCircuitBreaker:
        """Get or create a circuit breaker for a service.

        Args:
            service_name: Service name
            failure_threshold: Failures before opening
            success_threshold: Successes to close
            timeout: Timeout before OPEN -> HALF_OPEN
            failure_rate_threshold: Failure rate threshold
            window_size: Sliding window size

        Returns:
            DistributedCircuitBreaker instance
        """
        if service_name not in self._breakers:
            self._breakers[service_name] = DistributedCircuitBreaker(
                redis=self.redis,
                service_name=service_name,
                failure_threshold=failure_threshold,
                success_threshold=success_threshold,
                timeout=timeout,
                failure_rate_threshold=failure_rate_threshold,
                window_size=window_size,
            )

        return self._breakers[service_name]

    async def get_all_metrics(self) -> List[dict]:
        """Get metrics for all circuit breakers.

        Returns:
            List of metric dictionaries
        """
        metrics = []
        for breaker in self._breakers.values():
            metrics.append(await breaker.get_metrics())
        return metrics

    async def reset_all(self) -> None:
        """Reset all circuit breakers to CLOSED state."""
        for breaker in self._breakers.values():
            await breaker.reset()
