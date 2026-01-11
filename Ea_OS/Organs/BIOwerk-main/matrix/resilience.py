"""
Enterprise-grade service mesh resilience patterns.

This module implements:
- Circuit Breaker: Prevents cascading failures by failing fast when a service is down
- Retry with Exponential Backoff: Automatically retries transient failures
- Bulkhead: Isolates resource pools to prevent one service from exhausting all connections
- Health-Aware Routing: Routes to healthy services based on real-time health checks

All patterns include comprehensive Prometheus metrics for observability.
"""
import asyncio
import time
from enum import Enum
from typing import Optional, Callable, Any, Dict, List
from datetime import datetime, timedelta
import httpx
from prometheus_client import Counter, Histogram, Gauge
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


# ============================================================================
# PROMETHEUS METRICS
# ============================================================================

# Circuit Breaker Metrics
circuit_breaker_state = Gauge(
    'circuit_breaker_state',
    'Current state of circuit breaker (0=CLOSED, 1=OPEN, 2=HALF_OPEN)',
    ['service']
)

circuit_breaker_transitions = Counter(
    'circuit_breaker_transitions_total',
    'Total number of circuit breaker state transitions',
    ['service', 'from_state', 'to_state']
)

circuit_breaker_failures = Counter(
    'circuit_breaker_failures_total',
    'Total number of failures tracked by circuit breaker',
    ['service']
)

circuit_breaker_successes = Counter(
    'circuit_breaker_successes_total',
    'Total number of successes tracked by circuit breaker',
    ['service']
)

circuit_breaker_rejected = Counter(
    'circuit_breaker_rejected_total',
    'Total number of requests rejected due to open circuit',
    ['service']
)

# Retry Metrics
retry_attempts = Counter(
    'resilience_retry_attempts_total',
    'Total number of retry attempts',
    ['service', 'attempt']
)

retry_successes = Counter(
    'resilience_retry_successes_total',
    'Total number of successful retries',
    ['service', 'attempt']
)

retry_exhausted = Counter(
    'resilience_retry_exhausted_total',
    'Total number of retries that exhausted all attempts',
    ['service']
)

# Bulkhead Metrics
bulkhead_capacity = Gauge(
    'bulkhead_capacity',
    'Maximum capacity of bulkhead',
    ['service']
)

bulkhead_current = Gauge(
    'bulkhead_current_usage',
    'Current number of active requests in bulkhead',
    ['service']
)

bulkhead_rejected = Counter(
    'bulkhead_rejected_total',
    'Total number of requests rejected due to bulkhead full',
    ['service']
)

bulkhead_wait_time = Histogram(
    'bulkhead_wait_seconds',
    'Time spent waiting for bulkhead slot',
    ['service'],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
)

# HTTP Client Metrics
http_request_duration = Histogram(
    'resilience_http_request_duration_seconds',
    'HTTP request duration including retries',
    ['service', 'method', 'status'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0]
)

http_requests_total = Counter(
    'resilience_http_requests_total',
    'Total HTTP requests made',
    ['service', 'method', 'status']
)


# ============================================================================
# CIRCUIT BREAKER
# ============================================================================

class CircuitBreakerState(Enum):
    """Circuit breaker states following the standard pattern."""
    CLOSED = 0      # Normal operation, requests pass through
    OPEN = 1        # Failing fast, requests are rejected immediately
    HALF_OPEN = 2   # Testing if service recovered, limited requests allowed


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open and request is rejected."""
    pass


class CircuitBreaker:
    """
    Enterprise-grade circuit breaker implementation.

    States:
    - CLOSED: Normal operation. Tracks failures. Opens on threshold breach.
    - OPEN: Fails fast. Rejects all requests. Transitions to HALF_OPEN after timeout.
    - HALF_OPEN: Testing recovery. Allows limited requests. Closes on success or opens on failure.

    Args:
        service_name: Name of the service for metrics and logging
        failure_threshold: Number of consecutive failures before opening (default: 5)
        success_threshold: Number of consecutive successes in HALF_OPEN to close (default: 2)
        timeout: Seconds to wait before transitioning from OPEN to HALF_OPEN (default: 60)
        failure_rate_threshold: Percentage of failures in window to trigger open (default: 50%)
        window_size: Number of recent calls to consider for failure rate (default: 10)
    """

    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: int = 60,
        failure_rate_threshold: float = 0.5,
        window_size: int = 10
    ):
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout = timeout
        self.failure_rate_threshold = failure_rate_threshold
        self.window_size = window_size

        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._opened_at: Optional[datetime] = None

        # Sliding window for failure rate calculation
        self._recent_calls: List[bool] = []  # True=success, False=failure

        # Initialize metrics
        circuit_breaker_state.labels(service=service_name).set(self._state.value)

        logger.info(
            f"CircuitBreaker initialized for {service_name}: "
            f"failure_threshold={failure_threshold}, "
            f"success_threshold={success_threshold}, "
            f"timeout={timeout}s, "
            f"failure_rate_threshold={failure_rate_threshold*100}%"
        )

    @property
    def state(self) -> CircuitBreakerState:
        """Get current circuit breaker state."""
        return self._state

    def _transition_to(self, new_state: CircuitBreakerState):
        """Transition to a new state with metrics and logging."""
        if new_state == self._state:
            return

        old_state = self._state
        self._state = new_state

        # Update metrics
        circuit_breaker_state.labels(service=self.service_name).set(new_state.value)
        circuit_breaker_transitions.labels(
            service=self.service_name,
            from_state=old_state.name,
            to_state=new_state.name
        ).inc()

        # Reset counters on state change
        if new_state == CircuitBreakerState.OPEN:
            self._opened_at = datetime.now()
            logger.warning(
                f"CircuitBreaker {self.service_name} OPENED: "
                f"failure_count={self._failure_count}, "
                f"failure_rate={self._calculate_failure_rate():.1%}"
            )
        elif new_state == CircuitBreakerState.HALF_OPEN:
            self._success_count = 0
            self._failure_count = 0
            logger.info(f"CircuitBreaker {self.service_name} transitioned to HALF_OPEN (testing recovery)")
        elif new_state == CircuitBreakerState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
            self._opened_at = None
            logger.info(f"CircuitBreaker {self.service_name} CLOSED (service recovered)")

    def _calculate_failure_rate(self) -> float:
        """Calculate failure rate from recent calls."""
        if not self._recent_calls:
            return 0.0
        failures = sum(1 for success in self._recent_calls if not success)
        return failures / len(self._recent_calls)

    def _record_call(self, success: bool):
        """Record a call result in the sliding window."""
        self._recent_calls.append(success)
        if len(self._recent_calls) > self.window_size:
            self._recent_calls.pop(0)

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute a function with circuit breaker protection.

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result of func if successful

        Raises:
            CircuitBreakerError: If circuit is open and request is rejected
            Exception: Original exception from func if it fails
        """
        # Check if we should transition from OPEN to HALF_OPEN
        if self._state == CircuitBreakerState.OPEN:
            if self._opened_at and datetime.now() - self._opened_at >= timedelta(seconds=self.timeout):
                self._transition_to(CircuitBreakerState.HALF_OPEN)
            else:
                circuit_breaker_rejected.labels(service=self.service_name).inc()
                raise CircuitBreakerError(
                    f"Circuit breaker is OPEN for {self.service_name}. "
                    f"Failing fast to prevent cascading failures."
                )

        try:
            # Execute the function
            result = await func(*args, **kwargs)

            # Record success
            self._record_call(success=True)
            circuit_breaker_successes.labels(service=self.service_name).inc()

            if self._state == CircuitBreakerState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._transition_to(CircuitBreakerState.CLOSED)
            elif self._state == CircuitBreakerState.CLOSED:
                # Reset failure count on success
                self._failure_count = 0

            return result

        except Exception as e:
            # Record failure
            self._record_call(success=False)
            self._failure_count += 1
            self._last_failure_time = datetime.now()
            circuit_breaker_failures.labels(service=self.service_name).inc()

            logger.warning(
                f"CircuitBreaker {self.service_name} recorded failure: {type(e).__name__}: {str(e)}"
            )

            if self._state == CircuitBreakerState.HALF_OPEN:
                # Any failure in HALF_OPEN goes back to OPEN
                self._transition_to(CircuitBreakerState.OPEN)
            elif self._state == CircuitBreakerState.CLOSED:
                # Check if we should open based on consecutive failures or failure rate
                failure_rate = self._calculate_failure_rate()
                if (self._failure_count >= self.failure_threshold or
                    failure_rate >= self.failure_rate_threshold):
                    self._transition_to(CircuitBreakerState.OPEN)

            raise


# ============================================================================
# RETRY WITH EXPONENTIAL BACKOFF
# ============================================================================

class RetryExhaustedError(Exception):
    """Raised when all retry attempts are exhausted."""
    pass


async def retry_with_backoff(
    func: Callable,
    *args,
    max_attempts: int = 3,
    initial_delay: float = 0.1,
    max_delay: float = 10.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    service_name: str = "unknown",
    **kwargs
) -> Any:
    """
    Execute a function with exponential backoff retry logic.

    Retry strategy:
    - Attempt 1: Immediate
    - Attempt 2: Wait initial_delay (e.g., 100ms)
    - Attempt 3: Wait initial_delay * base (e.g., 200ms)
    - Attempt 4: Wait initial_delay * base^2 (e.g., 400ms)
    - And so on until max_delay is reached

    Args:
        func: Async function to execute
        *args: Positional arguments for func
        max_attempts: Maximum number of attempts (default: 3)
        initial_delay: Initial delay in seconds (default: 0.1)
        max_delay: Maximum delay between retries (default: 10.0)
        exponential_base: Base for exponential backoff (default: 2.0)
        jitter: Add random jitter to prevent thundering herd (default: True)
        service_name: Service name for metrics
        **kwargs: Keyword arguments for func

    Returns:
        Result of func if successful

    Raises:
        RetryExhaustedError: If all attempts are exhausted
        Exception: Last exception if all retries fail
    """
    import random

    last_exception = None

    for attempt in range(1, max_attempts + 1):
        try:
            retry_attempts.labels(service=service_name, attempt=str(attempt)).inc()

            result = await func(*args, **kwargs)

            if attempt > 1:
                # Success after retry
                retry_successes.labels(service=service_name, attempt=str(attempt)).inc()
                logger.info(
                    f"Retry succeeded for {service_name} on attempt {attempt}/{max_attempts}"
                )

            return result

        except Exception as e:
            last_exception = e

            if attempt >= max_attempts:
                # All retries exhausted
                retry_exhausted.labels(service=service_name).inc()
                logger.error(
                    f"All {max_attempts} retry attempts exhausted for {service_name}. "
                    f"Last error: {type(e).__name__}: {str(e)}"
                )
                raise RetryExhaustedError(
                    f"All {max_attempts} retry attempts failed for {service_name}"
                ) from e

            # Calculate delay with exponential backoff
            delay = min(initial_delay * (exponential_base ** (attempt - 1)), max_delay)

            # Add jitter to prevent thundering herd
            if jitter:
                delay = delay * (0.5 + random.random())  # Random between 50%-150% of delay

            logger.warning(
                f"Attempt {attempt}/{max_attempts} failed for {service_name}: "
                f"{type(e).__name__}: {str(e)}. "
                f"Retrying in {delay:.3f}s..."
            )

            await asyncio.sleep(delay)

    # Should never reach here, but just in case
    raise last_exception


# ============================================================================
# BULKHEAD PATTERN
# ============================================================================

class BulkheadFullError(Exception):
    """Raised when bulkhead is at capacity and cannot accept more requests."""
    pass


class Bulkhead:
    """
    Bulkhead pattern for resource isolation.

    Limits the number of concurrent requests to a service, preventing
    one slow/failing service from exhausting all connection pools.

    Args:
        service_name: Name of the service for metrics and logging
        max_concurrent: Maximum number of concurrent requests (default: 10)
        queue_size: Maximum number of requests to queue when at capacity (default: 5)
        timeout: Maximum time to wait for a slot in seconds (default: 5.0)
    """

    def __init__(
        self,
        service_name: str,
        max_concurrent: int = 10,
        queue_size: int = 5,
        timeout: float = 5.0
    ):
        self.service_name = service_name
        self.max_concurrent = max_concurrent
        self.queue_size = queue_size
        self.timeout = timeout

        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._current_requests = 0

        # Initialize metrics
        bulkhead_capacity.labels(service=service_name).set(max_concurrent)
        bulkhead_current.labels(service=service_name).set(0)

        logger.info(
            f"Bulkhead initialized for {service_name}: "
            f"max_concurrent={max_concurrent}, "
            f"queue_size={queue_size}, "
            f"timeout={timeout}s"
        )

    @asynccontextmanager
    async def acquire(self):
        """
        Acquire a slot in the bulkhead.

        Usage:
            async with bulkhead.acquire():
                # Make request to service
                result = await make_request()
        """
        start_time = time.time()

        try:
            # Try to acquire semaphore with timeout
            acquired = await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=self.timeout
            )

            if not acquired:
                bulkhead_rejected.labels(service=self.service_name).inc()
                raise BulkheadFullError(
                    f"Bulkhead for {self.service_name} is full. "
                    f"Max concurrent requests: {self.max_concurrent}"
                )

            wait_time = time.time() - start_time
            bulkhead_wait_time.labels(service=self.service_name).observe(wait_time)

            self._current_requests += 1
            bulkhead_current.labels(service=self.service_name).set(self._current_requests)

            if wait_time > 0.1:  # Log if we waited more than 100ms
                logger.debug(
                    f"Acquired bulkhead slot for {self.service_name} "
                    f"after {wait_time:.3f}s wait. "
                    f"Current: {self._current_requests}/{self.max_concurrent}"
                )

            yield

        except asyncio.TimeoutError:
            bulkhead_rejected.labels(service=self.service_name).inc()
            logger.warning(
                f"Bulkhead timeout for {self.service_name} after {self.timeout}s. "
                f"Current requests: {self._current_requests}/{self.max_concurrent}"
            )
            raise BulkheadFullError(
                f"Timeout waiting for bulkhead slot for {self.service_name}. "
                f"Waited {self.timeout}s."
            )

        finally:
            if acquired:
                self._current_requests -= 1
                bulkhead_current.labels(service=self.service_name).set(self._current_requests)
                self._semaphore.release()


# ============================================================================
# RESILIENT HTTP CLIENT
# ============================================================================

class ResilientHttpClient:
    """
    HTTP client with built-in circuit breaker, retry, and bulkhead patterns.

    This is a drop-in replacement for httpx.AsyncClient that adds enterprise-grade
    resilience patterns to all HTTP requests.

    Args:
        service_name: Name of the service for metrics and logging
        base_url: Optional base URL for the service
        timeout: Default timeout in seconds (default: 30.0)
        circuit_breaker_kwargs: Optional kwargs for CircuitBreaker
        retry_kwargs: Optional kwargs for retry_with_backoff
        bulkhead_kwargs: Optional kwargs for Bulkhead
        enable_circuit_breaker: Enable circuit breaker (default: True)
        enable_retry: Enable retry logic (default: True)
        enable_bulkhead: Enable bulkhead pattern (default: True)
    """

    def __init__(
        self,
        service_name: str,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        circuit_breaker_kwargs: Optional[Dict] = None,
        retry_kwargs: Optional[Dict] = None,
        bulkhead_kwargs: Optional[Dict] = None,
        enable_circuit_breaker: bool = True,
        enable_retry: bool = True,
        enable_bulkhead: bool = True,
        **httpx_kwargs
    ):
        self.service_name = service_name
        self.base_url = base_url

        # Initialize httpx client
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            **httpx_kwargs
        )

        # Initialize resilience patterns
        self.circuit_breaker = None
        self.bulkhead = None
        self.retry_config = {}

        if enable_circuit_breaker:
            cb_kwargs = circuit_breaker_kwargs or {}
            self.circuit_breaker = CircuitBreaker(service_name, **cb_kwargs)

        if enable_bulkhead:
            bh_kwargs = bulkhead_kwargs or {}
            self.bulkhead = Bulkhead(service_name, **bh_kwargs)

        if enable_retry:
            self.retry_config = {
                'max_attempts': 3,
                'initial_delay': 0.1,
                'max_delay': 5.0,
                'exponential_base': 2.0,
                'jitter': True,
                'service_name': service_name,
                **(retry_kwargs or {})
            }

        logger.info(
            f"ResilientHttpClient initialized for {service_name}: "
            f"circuit_breaker={enable_circuit_breaker}, "
            f"retry={enable_retry}, "
            f"bulkhead={enable_bulkhead}"
        )

    async def _make_request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> httpx.Response:
        """Internal method to make HTTP request with all resilience patterns."""

        async def _http_call():
            """Actual HTTP call wrapped in resilience patterns."""
            start_time = time.time()

            try:
                response = await getattr(self._client, method.lower())(url, **kwargs)

                duration = time.time() - start_time
                http_request_duration.labels(
                    service=self.service_name,
                    method=method,
                    status=response.status_code
                ).observe(duration)

                http_requests_total.labels(
                    service=self.service_name,
                    method=method,
                    status=response.status_code
                ).inc()

                # Raise for 5xx errors (server errors should trigger retries)
                if response.status_code >= 500:
                    response.raise_for_status()

                return response

            except Exception as e:
                duration = time.time() - start_time
                http_request_duration.labels(
                    service=self.service_name,
                    method=method,
                    status='error'
                ).observe(duration)

                http_requests_total.labels(
                    service=self.service_name,
                    method=method,
                    status='error'
                ).inc()

                raise

        # Apply bulkhead pattern
        if self.bulkhead:
            async with self.bulkhead.acquire():
                # Apply circuit breaker and retry
                if self.circuit_breaker:
                    if self.retry_config:
                        # Circuit breaker + Retry
                        return await self.circuit_breaker.call(
                            retry_with_backoff,
                            _http_call,
                            **self.retry_config
                        )
                    else:
                        # Circuit breaker only
                        return await self.circuit_breaker.call(_http_call)
                elif self.retry_config:
                    # Retry only
                    return await retry_with_backoff(_http_call, **self.retry_config)
                else:
                    # No additional patterns
                    return await _http_call()
        else:
            # No bulkhead
            if self.circuit_breaker:
                if self.retry_config:
                    return await self.circuit_breaker.call(
                        retry_with_backoff,
                        _http_call,
                        **self.retry_config
                    )
                else:
                    return await self.circuit_breaker.call(_http_call)
            elif self.retry_config:
                return await retry_with_backoff(_http_call, **self.retry_config)
            else:
                return await _http_call()

    async def get(self, url: str, **kwargs) -> httpx.Response:
        """Make a GET request with resilience patterns."""
        return await self._make_request('GET', url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        """Make a POST request with resilience patterns."""
        return await self._make_request('POST', url, **kwargs)

    async def put(self, url: str, **kwargs) -> httpx.Response:
        """Make a PUT request with resilience patterns."""
        return await self._make_request('PUT', url, **kwargs)

    async def delete(self, url: str, **kwargs) -> httpx.Response:
        """Make a DELETE request with resilience patterns."""
        return await self._make_request('DELETE', url, **kwargs)

    async def patch(self, url: str, **kwargs) -> httpx.Response:
        """Make a PATCH request with resilience patterns."""
        return await self._make_request('PATCH', url, **kwargs)

    async def aclose(self):
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.aclose()


# ============================================================================
# HEALTH-AWARE ROUTING
# ============================================================================

class ServiceHealth:
    """Track health status of a service."""

    def __init__(self, service_name: str, url: str):
        self.service_name = service_name
        self.url = url
        self.is_healthy = True
        self.last_check: Optional[datetime] = None
        self.consecutive_failures = 0
        self.health_score = 1.0  # 0.0 = completely unhealthy, 1.0 = perfectly healthy


class HealthAwareRouter:
    """
    Routes requests to healthy services based on real-time health checks.

    Integrates with Harry health monitor to avoid sending requests to
    unhealthy services.

    Args:
        health_check_interval: Seconds between health checks (default: 10)
        unhealthy_threshold: Consecutive failures before marking unhealthy (default: 3)
        healthy_threshold: Consecutive successes before marking healthy (default: 2)
    """

    def __init__(
        self,
        health_check_interval: int = 10,
        unhealthy_threshold: int = 3,
        healthy_threshold: int = 2
    ):
        self.health_check_interval = health_check_interval
        self.unhealthy_threshold = unhealthy_threshold
        self.healthy_threshold = healthy_threshold

        self._services: Dict[str, ServiceHealth] = {}
        self._health_check_task: Optional[asyncio.Task] = None

        logger.info(
            f"HealthAwareRouter initialized: "
            f"check_interval={health_check_interval}s, "
            f"unhealthy_threshold={unhealthy_threshold}, "
            f"healthy_threshold={healthy_threshold}"
        )

    def register_service(self, service_name: str, health_url: str):
        """Register a service for health monitoring."""
        self._services[service_name] = ServiceHealth(service_name, health_url)
        logger.info(f"Registered service {service_name} with health URL: {health_url}")

    def is_healthy(self, service_name: str) -> bool:
        """Check if a service is healthy."""
        service = self._services.get(service_name)
        if not service:
            # Unknown service, assume healthy
            return True
        return service.is_healthy

    def get_health_score(self, service_name: str) -> float:
        """Get health score for a service (0.0-1.0)."""
        service = self._services.get(service_name)
        if not service:
            return 1.0
        return service.health_score

    async def update_health(self, service_name: str, is_healthy: bool):
        """Update health status for a service."""
        service = self._services.get(service_name)
        if not service:
            return

        service.last_check = datetime.now()

        if is_healthy:
            service.consecutive_failures = 0
            if not service.is_healthy:
                # Service recovering
                if service.health_score >= 0.5:  # Need 50% health score to recover
                    service.is_healthy = True
                    logger.info(f"Service {service_name} marked as HEALTHY")

            # Gradually improve health score
            service.health_score = min(1.0, service.health_score + 0.2)
        else:
            service.consecutive_failures += 1

            # Gradually degrade health score
            service.health_score = max(0.0, service.health_score - 0.25)

            if service.consecutive_failures >= self.unhealthy_threshold and service.is_healthy:
                service.is_healthy = False
                logger.warning(
                    f"Service {service_name} marked as UNHEALTHY "
                    f"after {service.consecutive_failures} consecutive failures"
                )
