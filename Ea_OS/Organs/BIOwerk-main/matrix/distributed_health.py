"""Distributed health checking for service mesh with Redis-backed state.

This module provides distributed health checking that aggregates health status
across all service instances, ensuring consistent routing decisions across
all mesh gateway replicas.

Key Features:
- Distributed health state in Redis
- Aggregated health decisions across all instances
- Configurable health/unhealthy thresholds
- Automatic health probe execution
- Health state expiration (TTL)
- Prometheus metrics integration

Usage:
    # Create distributed health checker
    health_checker = DistributedHealthChecker(
        redis=redis_client,
        service_name="agent_service",
        health_url="http://agent:8000/health",
        interval=10,
        unhealthy_threshold=3,
        healthy_threshold=2
    )

    # Start health checking
    await health_checker.start()

    # Check if service is healthy (aggregated across all instances)
    is_healthy = await health_checker.is_healthy()

    # Get health details
    status = await health_checker.get_status()
    # {'healthy': True, 'consecutive_successes': 5, 'last_check': 1234567890}
"""

import asyncio
import time
from typing import Optional, Dict, Any
from redis.asyncio import Redis
import httpx
from prometheus_client import Counter, Gauge, Histogram
import structlog

logger = structlog.get_logger(__name__)


# Prometheus metrics
health_check_total = Counter(
    'distributed_health_check_total',
    'Total number of distributed health checks performed',
    ['service', 'status']
)

health_check_duration = Histogram(
    'distributed_health_check_duration_seconds',
    'Duration of distributed health checks',
    ['service'],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
)

health_status = Gauge(
    'distributed_health_status',
    'Current distributed health status (1=healthy, 0=unhealthy)',
    ['service']
)


class DistributedHealthChecker:
    """Distributed health checker with Redis-backed aggregated state.

    Performs periodic health checks and stores aggregated health status in Redis,
    allowing all mesh gateway instances to make consistent routing decisions.

    Attributes:
        redis: Redis client instance
        service_name: Name of the service being monitored
        health_url: URL to perform health checks against
        interval: Seconds between health checks (default: 10)
        timeout: Health check timeout in seconds (default: 5)
        unhealthy_threshold: Consecutive failures before marking unhealthy (default: 3)
        healthy_threshold: Consecutive successes before marking healthy (default: 2)
        ttl: TTL for health state in Redis in seconds (default: 60)
    """

    KEY_PREFIX = "health:"

    def __init__(
        self,
        redis: Redis,
        service_name: str,
        health_url: str,
        interval: int = 10,
        timeout: float = 5.0,
        unhealthy_threshold: int = 3,
        healthy_threshold: int = 2,
        ttl: int = 60,
    ):
        """Initialize distributed health checker.

        Args:
            redis: Redis client instance
            service_name: Service name
            health_url: Health check endpoint URL
            interval: Check interval in seconds
            timeout: Check timeout in seconds
            unhealthy_threshold: Failures before unhealthy
            healthy_threshold: Successes before healthy
            ttl: State TTL in Redis
        """
        self.redis = redis
        self.service_name = service_name
        self.health_url = health_url
        self.interval = interval
        self.timeout = timeout
        self.unhealthy_threshold = unhealthy_threshold
        self.healthy_threshold = healthy_threshold
        self.ttl = ttl

        # Redis keys
        self.key_status = f"{self.KEY_PREFIX}{service_name}:status"
        self.key_consecutive_failures = f"{self.KEY_PREFIX}{service_name}:consecutive_failures"
        self.key_consecutive_successes = f"{self.KEY_PREFIX}{service_name}:consecutive_successes"
        self.key_last_check = f"{self.KEY_PREFIX}{service_name}:last_check"
        self.key_last_error = f"{self.KEY_PREFIX}{service_name}:last_error"

        # HTTP client for health checks
        self.client = httpx.AsyncClient(timeout=timeout)

        # Background task
        self._task: Optional[asyncio.Task] = None
        self._running = False

        logger.info(
            "distributed_health_checker_initialized",
            service=service_name,
            url=health_url,
            interval=interval,
            unhealthy_threshold=unhealthy_threshold,
            healthy_threshold=healthy_threshold,
        )

    async def _perform_health_check(self) -> bool:
        """Perform single health check.

        Returns:
            True if healthy, False otherwise
        """
        start_time = time.time()

        try:
            response = await self.client.get(self.health_url)
            duration = time.time() - start_time

            health_check_duration.labels(service=self.service_name).observe(duration)

            if response.status_code == 200:
                health_check_total.labels(
                    service=self.service_name,
                    status="success"
                ).inc()
                return True
            else:
                health_check_total.labels(
                    service=self.service_name,
                    status="failure"
                ).inc()
                await self.redis.set(
                    self.key_last_error,
                    f"HTTP {response.status_code}",
                    ex=self.ttl
                )
                return False

        except Exception as e:
            duration = time.time() - start_time
            health_check_duration.labels(service=self.service_name).observe(duration)
            health_check_total.labels(
                service=self.service_name,
                status="error"
            ).inc()

            await self.redis.set(
                self.key_last_error,
                str(e),
                ex=self.ttl
            )

            logger.debug(
                "distributed_health_check_error",
                service=self.service_name,
                error=str(e),
            )
            return False

    async def _update_health_state(self, check_passed: bool) -> None:
        """Update health state in Redis based on check result.

        Args:
            check_passed: Whether the health check passed
        """
        # Update last check timestamp
        await self.redis.set(self.key_last_check, int(time.time()), ex=self.ttl)

        if check_passed:
            # Reset failure count, increment success count
            await self.redis.set(self.key_consecutive_failures, 0, ex=self.ttl)
            consecutive_successes = await self.redis.incr(self.key_consecutive_successes)
            await self.redis.expire(self.key_consecutive_successes, self.ttl)

            # Check if we should mark as healthy
            current_status = await self.redis.get(self.key_status)
            if current_status != b"1":  # Not already healthy
                if consecutive_successes >= self.healthy_threshold:
                    await self.redis.set(self.key_status, 1, ex=self.ttl)
                    health_status.labels(service=self.service_name).set(1)
                    logger.info(
                        "distributed_health_status_healthy",
                        service=self.service_name,
                        consecutive_successes=consecutive_successes,
                    )
            else:
                # Already healthy, just update TTL
                await self.redis.expire(self.key_status, self.ttl)

        else:
            # Reset success count, increment failure count
            await self.redis.set(self.key_consecutive_successes, 0, ex=self.ttl)
            consecutive_failures = await self.redis.incr(self.key_consecutive_failures)
            await self.redis.expire(self.key_consecutive_failures, self.ttl)

            # Check if we should mark as unhealthy
            current_status = await self.redis.get(self.key_status)
            if current_status == b"1":  # Currently healthy
                if consecutive_failures >= self.unhealthy_threshold:
                    await self.redis.set(self.key_status, 0, ex=self.ttl)
                    health_status.labels(service=self.service_name).set(0)
                    logger.warning(
                        "distributed_health_status_unhealthy",
                        service=self.service_name,
                        consecutive_failures=consecutive_failures,
                    )
            else:
                # Already unhealthy, just update TTL
                await self.redis.expire(self.key_status, self.ttl)

    async def _health_check_loop(self) -> None:
        """Background loop for periodic health checks."""
        logger.info(
            "distributed_health_check_loop_started",
            service=self.service_name,
        )

        # Initialize as healthy
        await self.redis.set(self.key_status, 1, ex=self.ttl)
        health_status.labels(service=self.service_name).set(1)

        while self._running:
            try:
                check_passed = await self._perform_health_check()
                await self._update_health_state(check_passed)

            except Exception as e:
                logger.error(
                    "distributed_health_check_loop_error",
                    service=self.service_name,
                    error=str(e),
                )

            # Wait for next interval
            await asyncio.sleep(self.interval)

        logger.info(
            "distributed_health_check_loop_stopped",
            service=self.service_name,
        )

    async def start(self) -> None:
        """Start background health checking."""
        if self._running:
            logger.warning(
                "distributed_health_checker_already_running",
                service=self.service_name,
            )
            return

        self._running = True
        self._task = asyncio.create_task(self._health_check_loop())

        logger.info(
            "distributed_health_checker_started",
            service=self.service_name,
        )

    async def stop(self) -> None:
        """Stop background health checking."""
        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        await self.client.aclose()

        logger.info(
            "distributed_health_checker_stopped",
            service=self.service_name,
        )

    async def is_healthy(self) -> bool:
        """Check if service is healthy (aggregated across all instances).

        Returns:
            True if healthy, False otherwise (defaults to False if no data)
        """
        status = await self.redis.get(self.key_status)
        if status is None:
            # No health data, assume unhealthy
            return False

        return int(status) == 1

    async def get_status(self) -> Dict[str, Any]:
        """Get detailed health status.

        Returns:
            Dictionary with health status details
        """
        status = await self.redis.get(self.key_status)
        consecutive_failures = await self.redis.get(self.key_consecutive_failures)
        consecutive_successes = await self.redis.get(self.key_consecutive_successes)
        last_check = await self.redis.get(self.key_last_check)
        last_error = await self.redis.get(self.key_last_error)

        return {
            "service": self.service_name,
            "healthy": int(status) == 1 if status else False,
            "consecutive_failures": int(consecutive_failures) if consecutive_failures else 0,
            "consecutive_successes": int(consecutive_successes) if consecutive_successes else 0,
            "last_check": int(last_check) if last_check else None,
            "last_error": last_error.decode() if last_error else None,
        }

    async def force_healthy(self) -> None:
        """Force service to healthy state (admin operation)."""
        await self.redis.set(self.key_status, 1, ex=self.ttl)
        await self.redis.set(self.key_consecutive_failures, 0, ex=self.ttl)
        await self.redis.set(self.key_consecutive_successes, self.healthy_threshold, ex=self.ttl)
        health_status.labels(service=self.service_name).set(1)

        logger.warning(
            "distributed_health_force_healthy",
            service=self.service_name,
        )

    async def force_unhealthy(self) -> None:
        """Force service to unhealthy state (admin operation)."""
        await self.redis.set(self.key_status, 0, ex=self.ttl)
        await self.redis.set(self.key_consecutive_successes, 0, ex=self.ttl)
        await self.redis.set(self.key_consecutive_failures, self.unhealthy_threshold, ex=self.ttl)
        health_status.labels(service=self.service_name).set(0)

        logger.warning(
            "distributed_health_force_unhealthy",
            service=self.service_name,
        )


class DistributedHealthManager:
    """Manager for distributed health checkers.

    Provides centralized management of multiple health checkers and
    health-aware routing logic.

    Usage:
        manager = DistributedHealthManager(redis)

        # Register services
        await manager.register_service("agent", "http://agent:8000/health")
        await manager.register_service("circadian", "http://circadian:8000/health")

        # Start all health checking
        await manager.start_all()

        # Get healthy services
        healthy = await manager.get_healthy_services()
    """

    def __init__(self, redis: Redis):
        """Initialize health manager.

        Args:
            redis: Redis client instance
        """
        self.redis = redis
        self._checkers: Dict[str, DistributedHealthChecker] = {}

    async def register_service(
        self,
        service_name: str,
        health_url: str,
        interval: int = 10,
        timeout: float = 5.0,
        unhealthy_threshold: int = 3,
        healthy_threshold: int = 2,
    ) -> DistributedHealthChecker:
        """Register a service for health checking.

        Args:
            service_name: Service name
            health_url: Health check endpoint
            interval: Check interval
            timeout: Check timeout
            unhealthy_threshold: Failures before unhealthy
            healthy_threshold: Successes before healthy

        Returns:
            DistributedHealthChecker instance
        """
        if service_name in self._checkers:
            logger.warning(
                "distributed_health_service_already_registered",
                service=service_name,
            )
            return self._checkers[service_name]

        checker = DistributedHealthChecker(
            redis=self.redis,
            service_name=service_name,
            health_url=health_url,
            interval=interval,
            timeout=timeout,
            unhealthy_threshold=unhealthy_threshold,
            healthy_threshold=healthy_threshold,
        )

        self._checkers[service_name] = checker
        return checker

    async def start_all(self) -> None:
        """Start all registered health checkers."""
        for checker in self._checkers.values():
            await checker.start()

    async def stop_all(self) -> None:
        """Stop all registered health checkers."""
        for checker in self._checkers.values():
            await checker.stop()

    async def is_healthy(self, service_name: str) -> bool:
        """Check if a service is healthy.

        Args:
            service_name: Service name

        Returns:
            True if healthy, False otherwise
        """
        if service_name not in self._checkers:
            logger.warning(
                "distributed_health_service_not_registered",
                service=service_name,
            )
            return False

        return await self._checkers[service_name].is_healthy()

    async def get_healthy_services(self) -> list[str]:
        """Get list of all healthy services.

        Returns:
            List of healthy service names
        """
        healthy = []
        for service_name, checker in self._checkers.items():
            if await checker.is_healthy():
                healthy.append(service_name)
        return healthy

    async def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all registered services.

        Returns:
            Dictionary mapping service names to their status
        """
        status = {}
        for service_name, checker in self._checkers.items():
            status[service_name] = await checker.get_status()
        return status
