"""Centralized logging configuration for all BIOwerk services."""
import logging
import sys
import os
import json
from typing import Any, Dict, Optional
from datetime import datetime, timezone


# Configure structured logging format
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_LEVEL_STR = os.getenv("LOG_LEVEL", "INFO")
LOG_LEVEL = getattr(logging, LOG_LEVEL_STR.upper(), logging.INFO)
LOG_FORMAT_TYPE = os.getenv("LOG_FORMAT", "json")  # json or text


class JSONFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging compatible with Loki/ELK.
    Includes OpenTelemetry trace context for log-trace correlation.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "process": record.process,
            "thread": record.thread,
        }

        # Add service name if available
        if hasattr(record, "service_name"):
            log_data["service_name"] = record.service_name

        # Add trace context for correlation with OpenTelemetry
        try:
            from opentelemetry import trace

            span = trace.get_current_span()
            if span.is_recording():
                span_context = span.get_span_context()
                log_data["trace_id"] = format(span_context.trace_id, "032x")
                log_data["span_id"] = format(span_context.span_id, "016x")
                log_data["trace_flags"] = span_context.trace_flags
        except (ImportError, Exception):
            # OpenTelemetry not available or no active span
            pass

        # Add custom fields from record
        if hasattr(record, "custom_fields"):
            log_data.update(record.custom_fields)

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info) if record.exc_info else None,
            }

        # Add extra fields (msg_id, agent, endpoint, etc.)
        for key, value in record.__dict__.items():
            if key not in [
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "message", "pathname", "process", "processName", "relativeCreated",
                "thread", "threadName", "exc_info", "exc_text", "stack_info",
                "custom_fields", "service_name"
            ]:
                log_data[key] = value

        return json.dumps(log_data)


class StructuredLogger(logging.LoggerAdapter):
    """
    Logger adapter that adds structured fields to all log records.
    """

    def __init__(self, logger: logging.Logger, service_name: str):
        super().__init__(logger, {"service_name": service_name})
        self.service_name = service_name

    def process(self, msg: str, kwargs: Any) -> tuple[str, Any]:
        """Add service name to all log records."""
        if "extra" not in kwargs:
            kwargs["extra"] = {}
        kwargs["extra"]["service_name"] = self.service_name
        return msg, kwargs


def setup_logging(service_name: str) -> logging.Logger:
    """
    Set up structured logging for a service with JSON formatting.

    Args:
        service_name: Name of the service (e.g., 'mesh', 'osteon')

    Returns:
        Configured logger instance with structured logging
    """
    logger = logging.getLogger(service_name)
    logger.setLevel(LOG_LEVEL)

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Console handler with formatting
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(LOG_LEVEL)

    # Use JSON formatter for structured logging or text format
    if LOG_FORMAT_TYPE == "json":
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(LOG_FORMAT)

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Return wrapped logger with service name
    return StructuredLogger(logger, service_name)


def log_request(logger: logging.Logger, msg_id: str, agent: str, endpoint: str, **kwargs: Any) -> None:
    """Log incoming request details."""
    extra_info = " ".join(f"{k}={v}" for k, v in kwargs.items())
    logger.info(f"Request received: msg_id={msg_id} agent={agent} endpoint={endpoint} {extra_info}".strip())


def log_response(logger: logging.Logger, msg_id: str, agent: str, ok: bool, duration_ms: float, **kwargs: Any) -> None:
    """Log response details."""
    status = "success" if ok else "failure"
    extra_info = " ".join(f"{k}={v}" for k, v in kwargs.items())
    logger.info(f"Response sent: msg_id={msg_id} agent={agent} status={status} duration_ms={duration_ms:.2f} {extra_info}".strip())


def log_error(logger: logging.Logger, msg_id: str, error: Exception, **kwargs: Any) -> None:
    """Log error details."""
    extra_info = " ".join(f"{k}={v}" for k, v in kwargs.items())
    logger.error(f"Error occurred: msg_id={msg_id} error={type(error).__name__} message={str(error)} {extra_info}".strip())
