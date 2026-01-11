"""
Enterprise-grade observability helpers for FastAPI services.

Provides comprehensive instrumentation with:
- OpenTelemetry distributed tracing
- Prometheus metrics
- Automatic instrumentation of FastAPI, HTTP clients, databases
- Trace context propagation
- Configurable exporters (OTLP, Jaeger, Console)
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from matrix.config import settings

# OpenTelemetry imports
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
        SpanExporter,
    )
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter as OTLPGrpcSpanExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter as OTLPHttpSpanExporter
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter
    from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    logging.warning("OpenTelemetry packages not installed. Tracing disabled.")


logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _instrumentator() -> Instrumentator:
    """Return a cached Prometheus instrumentator instance.

    Using a shared instance prevents duplicate metric registration when the
    helper is called multiple times (e.g., in tests or hot reloads).
    """
    return Instrumentator()


def _create_otlp_exporter() -> Optional[SpanExporter]:
    """Create OTLP exporter based on protocol configuration."""
    try:
        if settings.otel_exporter_protocol == "grpc":
            return OTLPGrpcSpanExporter(
                endpoint=settings.otel_exporter_endpoint,
                timeout=settings.otel_export_timeout,
            )
        elif settings.otel_exporter_protocol in ["http", "http/protobuf"]:
            # For HTTP, append /v1/traces if not present
            endpoint = settings.otel_exporter_endpoint
            if not endpoint.endswith("/v1/traces"):
                endpoint = f"{endpoint.rstrip('/')}/v1/traces"

            return OTLPHttpSpanExporter(
                endpoint=endpoint,
                timeout=settings.otel_export_timeout,
            )
        else:
            logger.error(f"Unknown OTLP protocol: {settings.otel_exporter_protocol}")
            return None
    except Exception as e:
        logger.error(f"Failed to create OTLP exporter: {e}")
        return None


def _create_jaeger_exporter() -> Optional[SpanExporter]:
    """Create Jaeger exporter."""
    try:
        # Parse Jaeger endpoint (e.g., "http://jaeger:14268")
        # Jaeger Thrift exporter uses the collector endpoint
        endpoint = settings.otel_exporter_endpoint.replace(":4317", ":14268")
        endpoint = endpoint.replace(":4318", ":14268")

        return JaegerExporter(
            agent_host_name=endpoint.split("://")[1].split(":")[0],
            agent_port=14268,
        )
    except Exception as e:
        logger.error(f"Failed to create Jaeger exporter: {e}")
        return None


def _create_span_exporter() -> Optional[SpanExporter]:
    """Create appropriate span exporter based on configuration."""
    exporter_type = settings.otel_exporter_type.lower()

    if exporter_type == "otlp":
        return _create_otlp_exporter()
    elif exporter_type == "jaeger":
        return _create_jaeger_exporter()
    elif exporter_type == "console":
        return ConsoleSpanExporter()
    elif exporter_type == "none":
        logger.info("OpenTelemetry exporter disabled (type=none)")
        return None
    else:
        logger.warning(f"Unknown exporter type '{exporter_type}', falling back to console")
        return ConsoleSpanExporter()


def setup_tracing(service_name: str, service_version: str = "1.0.0") -> Optional[TracerProvider]:
    """
    Setup OpenTelemetry distributed tracing.

    Args:
        service_name: Name of the service for trace identification
        service_version: Version of the service

    Returns:
        TracerProvider instance if successful, None otherwise
    """
    if not settings.otel_enabled:
        logger.info("OpenTelemetry tracing disabled by configuration")
        return None

    if not OTEL_AVAILABLE:
        logger.warning("OpenTelemetry packages not available, tracing disabled")
        return None

    try:
        # Create resource with service information
        resource = Resource.create({
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
            "deployment.environment": settings.environment,
        })

        # Create tracer provider with sampling
        sampler = TraceIdRatioBased(settings.otel_sampling_ratio)
        tracer_provider = TracerProvider(
            resource=resource,
            sampler=sampler,
        )

        # Create and configure span exporter
        exporter = _create_span_exporter()
        if exporter:
            # Use BatchSpanProcessor for production-grade async export
            span_processor = BatchSpanProcessor(
                exporter,
                max_queue_size=settings.otel_max_queue_size,
                max_export_batch_size=settings.otel_max_export_batch_size,
                export_timeout_millis=settings.otel_export_timeout * 1000,
            )
            tracer_provider.add_span_processor(span_processor)

            logger.info(
                f"OpenTelemetry tracing enabled for '{service_name}' "
                f"(exporter={settings.otel_exporter_type}, "
                f"sampling={settings.otel_sampling_ratio}, "
                f"endpoint={settings.otel_exporter_endpoint})"
            )
        else:
            logger.warning("No span exporter configured, traces will not be exported")

        # Set global tracer provider
        trace.set_tracer_provider(tracer_provider)

        # Instrument libraries based on configuration
        if settings.otel_instrument_http:
            try:
                HTTPXClientInstrumentor().instrument()
                logger.info("HTTPX client instrumentation enabled")
            except Exception as e:
                logger.warning(f"Failed to instrument HTTPX: {e}")

        if settings.otel_instrument_db:
            try:
                AsyncPGInstrumentor().instrument()
                logger.info("AsyncPG instrumentation enabled")
            except Exception as e:
                logger.warning(f"Failed to instrument AsyncPG: {e}")

            try:
                SQLAlchemyInstrumentor().instrument()
                logger.info("SQLAlchemy instrumentation enabled")
            except Exception as e:
                logger.warning(f"Failed to instrument SQLAlchemy: {e}")

        if settings.otel_instrument_redis:
            try:
                RedisInstrumentor().instrument()
                logger.info("Redis instrumentation enabled")
            except Exception as e:
                logger.warning(f"Failed to instrument Redis: {e}")

        return tracer_provider

    except Exception as e:
        logger.error(f"Failed to setup OpenTelemetry tracing: {e}", exc_info=True)
        return None


def setup_instrumentation(app: FastAPI, service_name: str = None, service_version: str = "1.0.0") -> None:
    """
    Attach comprehensive observability instrumentation to a FastAPI app.

    This includes:
    - Prometheus metrics at /metrics
    - OpenTelemetry distributed tracing (if enabled)
    - Automatic FastAPI request tracing

    Args:
        app: FastAPI application instance
        service_name: Service name for tracing (defaults to app.title)
        service_version: Service version for tracing
    """
    # Setup Prometheus metrics
    instrumentator = _instrumentator()
    instrumentator.instrument(app)
    instrumentator.expose(app, include_in_schema=False, endpoint="/metrics")
    logger.info("Prometheus metrics enabled at /metrics")

    # Setup OpenTelemetry tracing
    if settings.otel_enabled and OTEL_AVAILABLE:
        service_name = service_name or app.title or "biowerk-service"

        # Initialize tracing backend
        tracer_provider = setup_tracing(service_name, service_version)

        if tracer_provider:
            # Instrument FastAPI application
            try:
                FastAPIInstrumentor.instrument_app(
                    app,
                    tracer_provider=tracer_provider,
                    excluded_urls="/health,/ready,/metrics"  # Don't trace health/metrics endpoints
                )
                logger.info(f"FastAPI instrumentation enabled for '{service_name}'")
            except Exception as e:
                logger.error(f"Failed to instrument FastAPI app: {e}", exc_info=True)
    else:
        if settings.otel_enabled:
            logger.warning("OpenTelemetry enabled but packages not available")


def get_tracer(name: str) -> trace.Tracer:
    """
    Get a tracer instance for manual instrumentation.

    Args:
        name: Tracer name (typically module or component name)

    Returns:
        Tracer instance

    Example:
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("my_operation"):
            # Your code here
            pass
    """
    if OTEL_AVAILABLE:
        return trace.get_tracer(name)
    else:
        # Return a no-op tracer if OpenTelemetry is not available
        class NoOpTracer:
            def start_as_current_span(self, *args, **kwargs):
                from contextlib import contextmanager
                @contextmanager
                def noop():
                    yield
                return noop()

        return NoOpTracer()
