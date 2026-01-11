"""
Enterprise-grade health check module for BIOwerk services.

Provides comprehensive health and readiness checks with:
- Database connectivity (PostgreSQL, MongoDB)
- Cache availability (Redis)
- External service dependencies
- System resource monitoring
- Startup grace period handling
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import httpx
from fastapi import FastAPI, Response, status
from pydantic import BaseModel, Field

from matrix.config import settings


class HealthStatus(str, Enum):
    """Health check status values."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class ComponentHealth(BaseModel):
    """Health status for a single component."""
    name: str
    status: HealthStatus
    message: Optional[str] = None
    latency_ms: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)


class HealthCheckResponse(BaseModel):
    """Complete health check response."""
    status: HealthStatus
    service: str
    version: str = "1.0.0"
    timestamp: float = Field(default_factory=time.time)
    uptime_seconds: float
    checks: List[ComponentHealth]
    metadata: Dict[str, Any] = Field(default_factory=dict)


@dataclass
class HealthChecker:
    """
    Enterprise health checker with comprehensive dependency validation.

    Features:
    - Async health checks with timeout handling
    - Startup grace period for readiness checks
    - Detailed component-level health reporting
    - Database, cache, and service dependency checks
    - Configurable check inclusion
    """

    service_name: str
    startup_time: float = dataclass_field(default_factory=time.time)
    version: str = "1.0.0"

    def __post_init__(self):
        """Initialize health checker."""
        self.check_timeout = settings.health_check_timeout
        self.grace_period = settings.health_startup_grace_period

    async def check_postgres(self) -> ComponentHealth:
        """Check PostgreSQL database connectivity."""
        start = time.time()
        try:
            from matrix.database import get_db_session

            # Try to get a database session and execute a simple query
            async with get_db_session() as session:
                await session.execute("SELECT 1")

            latency = (time.time() - start) * 1000
            return ComponentHealth(
                name="postgres",
                status=HealthStatus.HEALTHY,
                message="Database connection successful",
                latency_ms=round(latency, 2),
                metadata={
                    "host": settings.postgres_host,
                    "port": settings.postgres_port,
                    "database": settings.postgres_db
                }
            )
        except Exception as e:
            latency = (time.time() - start) * 1000
            return ComponentHealth(
                name="postgres",
                status=HealthStatus.UNHEALTHY,
                message=f"Database connection failed: {str(e)}",
                latency_ms=round(latency, 2),
                metadata={"error": type(e).__name__}
            )

    async def check_redis(self) -> ComponentHealth:
        """Check Redis cache connectivity."""
        start = time.time()
        try:
            import redis.asyncio as aioredis

            # Create Redis client and test connection
            redis_client = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True
            )

            # Test with PING command
            await redis_client.ping()
            await redis_client.close()

            latency = (time.time() - start) * 1000
            return ComponentHealth(
                name="redis",
                status=HealthStatus.HEALTHY,
                message="Redis connection successful",
                latency_ms=round(latency, 2),
                metadata={
                    "host": settings.redis_host,
                    "port": settings.redis_port,
                    "db": settings.redis_db
                }
            )
        except Exception as e:
            latency = (time.time() - start) * 1000
            return ComponentHealth(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                message=f"Redis connection failed: {str(e)}",
                latency_ms=round(latency, 2),
                metadata={"error": type(e).__name__}
            )

    async def check_mongodb(self) -> ComponentHealth:
        """Check MongoDB connectivity."""
        start = time.time()
        try:
            from motor.motor_asyncio import AsyncIOMotorClient

            # Create MongoDB client and test connection
            client = AsyncIOMotorClient(settings.mongo_url)

            # Test with server info command
            await client.admin.command('ping')
            client.close()

            latency = (time.time() - start) * 1000
            return ComponentHealth(
                name="mongodb",
                status=HealthStatus.HEALTHY,
                message="MongoDB connection successful",
                latency_ms=round(latency, 2),
                metadata={
                    "host": settings.mongo_host,
                    "port": settings.mongo_port,
                    "database": settings.mongo_db
                }
            )
        except Exception as e:
            latency = (time.time() - start) * 1000
            return ComponentHealth(
                name="mongodb",
                status=HealthStatus.UNHEALTHY,
                message=f"MongoDB connection failed: {str(e)}",
                latency_ms=round(latency, 2),
                metadata={"error": type(e).__name__}
            )

    async def check_external_service(
        self,
        name: str,
        url: str,
        method: str = "GET",
        timeout: float = 5.0
    ) -> ComponentHealth:
        """
        Check external service health endpoint.

        Args:
            name: Service name
            url: Health check URL
            method: HTTP method (GET/POST)
            timeout: Request timeout in seconds
        """
        start = time.time()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if method.upper() == "GET":
                    response = await client.get(url)
                else:
                    response = await client.post(url)

                response.raise_for_status()
                latency = (time.time() - start) * 1000

                return ComponentHealth(
                    name=name,
                    status=HealthStatus.HEALTHY,
                    message=f"Service {name} is healthy",
                    latency_ms=round(latency, 2),
                    metadata={
                        "url": url,
                        "status_code": response.status_code
                    }
                )
        except Exception as e:
            latency = (time.time() - start) * 1000
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Service {name} check failed: {str(e)}",
                latency_ms=round(latency, 2),
                metadata={
                    "url": url,
                    "error": type(e).__name__
                }
            )

    async def run_check_with_timeout(
        self,
        check_func: Callable,
        timeout: float = None
    ) -> ComponentHealth:
        """Run a health check with timeout protection."""
        timeout = timeout or self.check_timeout

        try:
            return await asyncio.wait_for(check_func(), timeout=timeout)
        except asyncio.TimeoutError:
            return ComponentHealth(
                name=getattr(check_func, '__name__', 'unknown').replace('check_', ''),
                status=HealthStatus.UNHEALTHY,
                message=f"Health check timeout after {timeout}s",
                metadata={"timeout": timeout}
            )
        except Exception as e:
            return ComponentHealth(
                name=getattr(check_func, '__name__', 'unknown').replace('check_', ''),
                status=HealthStatus.UNHEALTHY,
                message=f"Health check error: {str(e)}",
                metadata={"error": type(e).__name__}
            )

    async def health(self) -> HealthCheckResponse:
        """
        Perform health check (liveness probe).

        This endpoint indicates if the service is alive and running.
        It performs basic checks and returns quickly.
        """
        checks: List[ComponentHealth] = []

        # Always include service status
        checks.append(ComponentHealth(
            name="service",
            status=HealthStatus.HEALTHY,
            message=f"{self.service_name} is running",
            metadata={
                "uptime_seconds": round(time.time() - self.startup_time, 2)
            }
        ))

        # Run checks based on configuration
        check_tasks = []

        if settings.health_check_redis:
            check_tasks.append(self.run_check_with_timeout(self.check_redis))

        if settings.health_check_db:
            check_tasks.append(self.run_check_with_timeout(self.check_postgres))

        # Run all checks concurrently
        if check_tasks:
            check_results = await asyncio.gather(*check_tasks, return_exceptions=True)
            for result in check_results:
                if isinstance(result, ComponentHealth):
                    checks.append(result)
                elif isinstance(result, Exception):
                    checks.append(ComponentHealth(
                        name="unknown",
                        status=HealthStatus.UNHEALTHY,
                        message=f"Check failed: {str(result)}"
                    ))

        # Determine overall status
        if all(check.status == HealthStatus.HEALTHY for check in checks):
            overall_status = HealthStatus.HEALTHY
        elif any(check.status == HealthStatus.UNHEALTHY for check in checks):
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.UNKNOWN

        return HealthCheckResponse(
            status=overall_status,
            service=self.service_name,
            version=self.version,
            uptime_seconds=round(time.time() - self.startup_time, 2),
            checks=checks,
            metadata={
                "environment": settings.environment,
                "timestamp_iso": datetime.fromtimestamp(time.time()).isoformat()
            }
        )

    async def ready(self) -> HealthCheckResponse:
        """
        Perform readiness check (readiness probe).

        This endpoint indicates if the service is ready to accept traffic.
        It performs comprehensive checks including all dependencies.
        Respects startup grace period.
        """
        checks: List[ComponentHealth] = []
        uptime = time.time() - self.startup_time

        # Check if we're still in startup grace period
        if uptime < self.grace_period:
            return HealthCheckResponse(
                status=HealthStatus.DEGRADED,
                service=self.service_name,
                version=self.version,
                uptime_seconds=round(uptime, 2),
                checks=[ComponentHealth(
                    name="startup",
                    status=HealthStatus.DEGRADED,
                    message=f"Service in startup grace period ({round(uptime, 1)}s / {self.grace_period}s)",
                    metadata={
                        "grace_period_seconds": self.grace_period,
                        "elapsed_seconds": round(uptime, 2)
                    }
                )],
                metadata={
                    "environment": settings.environment,
                    "grace_period_active": True
                }
            )

        # Service is running
        checks.append(ComponentHealth(
            name="service",
            status=HealthStatus.HEALTHY,
            message=f"{self.service_name} is ready",
            metadata={"uptime_seconds": round(uptime, 2)}
        ))

        # Run comprehensive checks
        check_tasks = []

        if settings.health_check_redis:
            check_tasks.append(self.run_check_with_timeout(self.check_redis))

        if settings.health_check_db:
            check_tasks.append(self.run_check_with_timeout(self.check_postgres))
            check_tasks.append(self.run_check_with_timeout(self.check_mongodb))

        # Run all checks concurrently
        if check_tasks:
            check_results = await asyncio.gather(*check_tasks, return_exceptions=True)
            for result in check_results:
                if isinstance(result, ComponentHealth):
                    checks.append(result)
                elif isinstance(result, Exception):
                    checks.append(ComponentHealth(
                        name="unknown",
                        status=HealthStatus.UNHEALTHY,
                        message=f"Check failed: {str(result)}"
                    ))

        # Determine overall readiness status
        # Service is ready only if ALL checks pass
        if all(check.status == HealthStatus.HEALTHY for check in checks):
            overall_status = HealthStatus.HEALTHY
        else:
            overall_status = HealthStatus.UNHEALTHY

        return HealthCheckResponse(
            status=overall_status,
            service=self.service_name,
            version=self.version,
            uptime_seconds=round(uptime, 2),
            checks=checks,
            metadata={
                "environment": settings.environment,
                "grace_period_active": False,
                "timestamp_iso": datetime.fromtimestamp(time.time()).isoformat()
            }
        )


def setup_health_endpoints(app: FastAPI, service_name: str, version: str = "1.0.0") -> HealthChecker:
    """
    Setup health and readiness endpoints on a FastAPI application.

    Endpoints:
    - GET /health: Liveness probe (is the service alive?)
    - GET /ready: Readiness probe (is the service ready for traffic?)

    Args:
        app: FastAPI application instance
        service_name: Name of the service
        version: Service version

    Returns:
        HealthChecker instance for advanced usage
    """
    if not settings.health_enabled:
        return None

    checker = HealthChecker(service_name=service_name, version=version)

    @app.get(
        "/health",
        tags=["Health"],
        summary="Health check (liveness probe)",
        description="Returns the health status of the service. Used by orchestrators to detect if service is alive.",
        response_model=HealthCheckResponse,
        status_code=status.HTTP_200_OK
    )
    async def health_endpoint(response: Response):
        """Health check endpoint (liveness probe)."""
        result = await checker.health()

        # Set appropriate status code based on health
        if result.status == HealthStatus.HEALTHY:
            response.status_code = status.HTTP_200_OK
        elif result.status == HealthStatus.DEGRADED:
            response.status_code = status.HTTP_200_OK  # Still alive, just degraded
        else:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        return result

    @app.get(
        "/ready",
        tags=["Health"],
        summary="Readiness check (readiness probe)",
        description="Returns the readiness status of the service. Used by orchestrators to determine if service can accept traffic.",
        response_model=HealthCheckResponse,
        status_code=status.HTTP_200_OK
    )
    async def readiness_endpoint(response: Response):
        """Readiness check endpoint (readiness probe)."""
        result = await checker.ready()

        # Set appropriate status code based on readiness
        if result.status == HealthStatus.HEALTHY:
            response.status_code = status.HTTP_200_OK
        else:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        return result

    return checker
