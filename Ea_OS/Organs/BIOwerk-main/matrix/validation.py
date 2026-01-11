"""Validation middleware for global input sanitization and attack prevention.

This module provides middleware and utilities for:
- XSS prevention
- Path traversal prevention
- SQL/NoSQL injection detection
- Command injection detection
- Request size limits
"""

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable, Any, Dict
import json
import re
from matrix.errors import ValidationError
from matrix.logging_config import setup_logging

logger = setup_logging("validation")

# Maximum request body size (10MB)
MAX_REQUEST_SIZE = 10 * 1024 * 1024

# Patterns for detecting various injection attacks
XSS_PATTERNS = [
    re.compile(r"<script[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL),
    re.compile(r"javascript:", re.IGNORECASE),
    re.compile(r"on\w+\s*=", re.IGNORECASE),  # onload=, onerror=, etc.
    re.compile(r"<iframe", re.IGNORECASE),
    re.compile(r"<embed", re.IGNORECASE),
    re.compile(r"<object", re.IGNORECASE),
]

PATH_TRAVERSAL_PATTERNS = [
    re.compile(r"\.\./"),
    re.compile(r"\.\.\\"),
    re.compile(r"%2e%2e/", re.IGNORECASE),
    re.compile(r"%2e%2e\\", re.IGNORECASE),
]

SQL_INJECTION_PATTERNS = [
    re.compile(r"\bunion\s+select\b", re.IGNORECASE),
    re.compile(r"\binsert\s+into\b", re.IGNORECASE),
    re.compile(r"\bdelete\s+from\b", re.IGNORECASE),
    re.compile(r"\bdrop\s+table\b", re.IGNORECASE),
    re.compile(r"\bdrop\s+database\b", re.IGNORECASE),
    re.compile(r";\s*drop\s+", re.IGNORECASE),
    re.compile(r"'\s*or\s+'1'\s*=\s*'1", re.IGNORECASE),
    re.compile(r"'\s*or\s+1\s*=\s*1", re.IGNORECASE),
]

NOSQL_INJECTION_PATTERNS = [
    re.compile(r"\$where", re.IGNORECASE),
    re.compile(r"\$ne\b", re.IGNORECASE),
    re.compile(r"\$gt\b", re.IGNORECASE),
    re.compile(r"\$lt\b", re.IGNORECASE),
    re.compile(r"\$gte\b", re.IGNORECASE),
    re.compile(r"\$lte\b", re.IGNORECASE),
    re.compile(r"\$regex", re.IGNORECASE),
]

COMMAND_INJECTION_PATTERNS = [
    re.compile(r"[;&|]\s*(rm|cat|ls|wget|curl|bash|sh|nc|netcat)\s+", re.IGNORECASE),
    re.compile(r"`.*`"),
    re.compile(r"\$\(.*\)"),
    re.compile(r"\$\{.*\}"),
]


def check_xss(value: str) -> bool:
    """Check if string contains XSS attack patterns.

    Args:
        value: String to check

    Returns:
        True if XSS pattern detected, False otherwise
    """
    for pattern in XSS_PATTERNS:
        if pattern.search(value):
            return True
    return False


def check_path_traversal(value: str) -> bool:
    """Check if string contains path traversal patterns.

    Args:
        value: String to check

    Returns:
        True if path traversal pattern detected, False otherwise
    """
    for pattern in PATH_TRAVERSAL_PATTERNS:
        if pattern.search(value):
            return True
    return False


def check_sql_injection(value: str) -> bool:
    """Check if string contains SQL injection patterns.

    Args:
        value: String to check

    Returns:
        True if SQL injection pattern detected, False otherwise
    """
    for pattern in SQL_INJECTION_PATTERNS:
        if pattern.search(value):
            return True
    return False


def check_nosql_injection(value: str) -> bool:
    """Check if string contains NoSQL injection patterns.

    Args:
        value: String to check

    Returns:
        True if NoSQL injection pattern detected, False otherwise
    """
    for pattern in NOSQL_INJECTION_PATTERNS:
        if pattern.search(value):
            return True
    return False


def check_command_injection(value: str) -> bool:
    """Check if string contains command injection patterns.

    Args:
        value: String to check

    Returns:
        True if command injection pattern detected, False otherwise
    """
    for pattern in COMMAND_INJECTION_PATTERNS:
        if pattern.search(value):
            return True
    return False


def sanitize_string(value: str, field_name: str = "field") -> None:
    """Perform comprehensive sanitization checks on a string.

    Args:
        value: String to sanitize
        field_name: Name of the field for error messages

    Raises:
        ValidationError: If any malicious patterns are detected
    """
    if not isinstance(value, str):
        return

    if check_xss(value):
        logger.warning(f"XSS attempt detected in field '{field_name}'")
        raise ValidationError(
            f"Potential XSS attack detected in '{field_name}'",
            {"field": field_name, "attack_type": "xss"}
        )

    if check_path_traversal(value):
        logger.warning(f"Path traversal attempt detected in field '{field_name}'")
        raise ValidationError(
            f"Potential path traversal attack detected in '{field_name}'",
            {"field": field_name, "attack_type": "path_traversal"}
        )

    if check_sql_injection(value):
        logger.warning(f"SQL injection attempt detected in field '{field_name}'")
        raise ValidationError(
            f"Potential SQL injection attack detected in '{field_name}'",
            {"field": field_name, "attack_type": "sql_injection"}
        )

    if check_nosql_injection(value):
        logger.warning(f"NoSQL injection attempt detected in field '{field_name}'")
        raise ValidationError(
            f"Potential NoSQL injection attack detected in '{field_name}'",
            {"field": field_name, "attack_type": "nosql_injection"}
        )

    if check_command_injection(value):
        logger.warning(f"Command injection attempt detected in field '{field_name}'")
        raise ValidationError(
            f"Potential command injection attack detected in '{field_name}'",
            {"field": field_name, "attack_type": "command_injection"}
        )


def sanitize_dict(data: Dict[str, Any], prefix: str = "") -> None:
    """Recursively sanitize all strings in a dictionary.

    Args:
        data: Dictionary to sanitize
        prefix: Prefix for nested field names

    Raises:
        ValidationError: If any malicious patterns are detected
    """
    for key, value in data.items():
        field_name = f"{prefix}.{key}" if prefix else key

        if isinstance(value, str):
            sanitize_string(value, field_name)
        elif isinstance(value, dict):
            sanitize_dict(value, field_name)
        elif isinstance(value, list):
            sanitize_list(value, field_name)


def sanitize_list(data: list, field_name: str = "list") -> None:
    """Recursively sanitize all strings in a list.

    Args:
        data: List to sanitize
        field_name: Name of the field for error messages

    Raises:
        ValidationError: If any malicious patterns are detected
    """
    for i, item in enumerate(data):
        item_name = f"{field_name}[{i}]"

        if isinstance(item, str):
            sanitize_string(item, item_name)
        elif isinstance(item, dict):
            sanitize_dict(item, item_name)
        elif isinstance(item, list):
            sanitize_list(item, item_name)


class ValidationMiddleware(BaseHTTPMiddleware):
    """Middleware for global request validation and sanitization."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process and validate incoming requests.

        Args:
            request: The incoming request
            call_next: The next middleware or endpoint handler

        Returns:
            Response from the endpoint or error response
        """
        # Skip validation for health and metrics endpoints
        if request.url.path in ["/health", "/ready", "/metrics", "/docs", "/openapi.json", "/redoc"]:
            return await call_next(request)

        try:
            # Check request size
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > MAX_REQUEST_SIZE:
                logger.warning(
                    f"Request size {content_length} exceeds maximum {MAX_REQUEST_SIZE}",
                    extra={"path": request.url.path}
                )
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": "PayloadTooLarge",
                        "message": f"Request body exceeds maximum size of {MAX_REQUEST_SIZE} bytes"
                    }
                )

            # Validate query parameters
            for key, value in request.query_params.items():
                sanitize_string(value, f"query.{key}")

            # Validate path parameters (check for path traversal)
            path = request.url.path
            if check_path_traversal(path):
                logger.warning(f"Path traversal attempt in URL: {path}")
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "ValidationError",
                        "message": "Invalid path"
                    }
                )

            # For requests with JSON body, validate the content
            if request.method in ["POST", "PUT", "PATCH"]:
                content_type = request.headers.get("content-type", "")
                if "application/json" in content_type:
                    # Read and parse body
                    body = await request.body()
                    if body:
                        try:
                            data = json.loads(body)
                            # Sanitize the entire request body
                            if isinstance(data, dict):
                                sanitize_dict(data)
                            elif isinstance(data, list):
                                sanitize_list(data, "body")
                        except json.JSONDecodeError:
                            logger.warning("Invalid JSON in request body")
                            return JSONResponse(
                                status_code=400,
                                content={
                                    "error": "ValidationError",
                                    "message": "Invalid JSON format"
                                }
                            )
                        except ValidationError as e:
                            return JSONResponse(
                                status_code=400,
                                content={
                                    "error": "ValidationError",
                                    "message": str(e),
                                    "details": e.details
                                }
                            )

                        # Reconstruct request with validated body
                        # Store the original body for FastAPI to parse
                        async def receive():
                            return {"type": "http.request", "body": body}

                        request._receive = receive

            # Continue to the next middleware/endpoint
            response = await call_next(request)
            return response

        except ValidationError as e:
            logger.warning(f"Validation error: {e.message}", extra={"details": e.details})
            return JSONResponse(
                status_code=400,
                content={
                    "error": "ValidationError",
                    "message": str(e),
                    "details": e.details
                }
            )
        except Exception as e:
            logger.error(f"Unexpected error in validation middleware: {str(e)}")
            return JSONResponse(
                status_code=500,
                content={
                    "error": "InternalServerError",
                    "message": "An internal error occurred"
                }
            )


def setup_validation_middleware(app):
    """Add validation middleware to a FastAPI application.

    Args:
        app: FastAPI application instance
    """
    app.add_middleware(ValidationMiddleware)
    logger.info("Validation middleware configured")
