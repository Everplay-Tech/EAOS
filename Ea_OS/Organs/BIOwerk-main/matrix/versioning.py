"""
API Versioning Middleware and Utilities

This module provides comprehensive API versioning support for BIOwerk microservices,
ensuring backward compatibility and graceful version transitions.

Features:
- URL path-based versioning (/v1/endpoint, /v2/endpoint)
- Automatic version extraction from request paths
- Default to latest version when no version specified
- Deprecation warnings for old versions
- Version validation and negotiation
- Support for multiple concurrent versions

Usage:
    from matrix.versioning import (
        extract_version,
        validate_version,
        version_middleware,
        deprecation_warning
    )

    # In FastAPI app
    app.middleware("http")(version_middleware)
"""

from typing import Optional, List, Tuple, Callable
from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
import re
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# Version Configuration
# ============================================================================

# Supported API versions in order from oldest to newest
SUPPORTED_VERSIONS = ["v1"]

# Latest/current version (default when no version specified)
LATEST_VERSION = "v1"

# Deprecated versions that still work but show warnings
DEPRECATED_VERSIONS: List[str] = []

# Version deprecation messages
DEPRECATION_MESSAGES = {
    # Example: "v0": "API v0 is deprecated and will be removed in 2025-Q2. Please migrate to v1."
}

# ============================================================================
# Version Extraction and Validation
# ============================================================================

def extract_version(path: str) -> Tuple[Optional[str], str]:
    """
    Extract API version from URL path.

    Args:
        path: Request path (e.g., "/v1/osteon/draft" or "/osteon/draft")

    Returns:
        Tuple of (version, path_without_version)
        - If version found: ("v1", "/osteon/draft")
        - If no version: (None, "/osteon/draft")

    Examples:
        >>> extract_version("/v1/osteon/draft")
        ('v1', '/osteon/draft')
        >>> extract_version("/osteon/draft")
        (None, '/osteon/draft')
        >>> extract_version("/v2/nucleus/plan")
        ('v2', '/nucleus/plan')
    """
    # Match version pattern at start of path: /v{number}/
    match = re.match(r'^/(v\d+)/(.*)$', path)

    if match:
        version = match.group(1)
        remaining_path = '/' + match.group(2)
        return version, remaining_path

    return None, path


def validate_version(version: Optional[str], default_to_latest: bool = True) -> str:
    """
    Validate and normalize API version.

    Args:
        version: Version string (e.g., "v1") or None
        default_to_latest: If True, return latest version when version is None

    Returns:
        Normalized version string

    Raises:
        HTTPException: If version is invalid and default_to_latest is False

    Examples:
        >>> validate_version("v1")
        'v1'
        >>> validate_version(None)
        'v1'
        >>> validate_version("v99")
        HTTPException(400)
    """
    # If no version specified, use latest
    if version is None:
        if default_to_latest:
            return LATEST_VERSION
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Missing API Version",
                "message": "API version must be specified in the URL path",
                "supported_versions": SUPPORTED_VERSIONS,
                "latest_version": LATEST_VERSION
            }
        )

    # Validate version is supported
    if version not in SUPPORTED_VERSIONS:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Unsupported API Version",
                "message": f"API version '{version}' is not supported",
                "requested_version": version,
                "supported_versions": SUPPORTED_VERSIONS,
                "latest_version": LATEST_VERSION
            }
        )

    return version


def is_deprecated(version: str) -> bool:
    """
    Check if a version is deprecated.

    Args:
        version: Version string (e.g., "v1")

    Returns:
        True if version is deprecated, False otherwise
    """
    return version in DEPRECATED_VERSIONS


def get_deprecation_message(version: str) -> Optional[str]:
    """
    Get deprecation message for a version.

    Args:
        version: Version string (e.g., "v1")

    Returns:
        Deprecation message if version is deprecated, None otherwise
    """
    return DEPRECATION_MESSAGES.get(version)


# ============================================================================
# Middleware
# ============================================================================

async def version_middleware(request: Request, call_next: Callable) -> Response:
    """
    FastAPI middleware for API versioning.

    This middleware:
    1. Extracts version from URL path
    2. Validates version or defaults to latest
    3. Adds version info to request state
    4. Adds deprecation warnings to response headers
    5. Passes request to next handler

    The middleware adds the following to request.state:
    - api_version: The validated API version
    - api_version_explicit: Whether version was explicitly specified

    Args:
        request: FastAPI request
        call_next: Next middleware/handler in chain

    Returns:
        Response with version headers added
    """
    # Extract version from path
    version, path_without_version = extract_version(request.url.path)

    # Track whether version was explicitly specified
    explicit_version = version is not None

    # Validate version (defaults to latest if not specified)
    try:
        validated_version = validate_version(version, default_to_latest=True)
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail
        )

    # Store version info in request state for handlers to use
    request.state.api_version = validated_version
    request.state.api_version_explicit = explicit_version
    request.state.path_without_version = path_without_version

    # Log version usage
    if not explicit_version:
        logger.info(f"Request to {request.url.path} defaulted to version {validated_version}")
    else:
        logger.debug(f"Request using explicit version {validated_version}")

    # Process request
    response = await call_next(request)

    # Add version headers to response
    response.headers["X-API-Version"] = validated_version
    response.headers["X-API-Latest-Version"] = LATEST_VERSION

    # Add deprecation warning if applicable
    if is_deprecated(validated_version):
        deprecation_msg = get_deprecation_message(validated_version)
        if deprecation_msg:
            response.headers["Warning"] = f'299 - "Deprecated API Version: {deprecation_msg}"'
            logger.warning(f"Deprecated version {validated_version} used: {deprecation_msg}")

    # Warn if version was not explicit
    if not explicit_version:
        response.headers["Warning"] = (
            f'199 - "API version not specified, defaulting to {validated_version}. '
            f'Please use /{validated_version}/... in your request path for explicit versioning."'
        )

    return response


# ============================================================================
# Utility Functions
# ============================================================================

def get_version_from_request(request: Request) -> str:
    """
    Get the API version from request state.

    This should be called after version_middleware has processed the request.

    Args:
        request: FastAPI request

    Returns:
        API version string

    Raises:
        RuntimeError: If version_middleware hasn't been applied
    """
    if not hasattr(request.state, 'api_version'):
        raise RuntimeError(
            "API version not found in request state. "
            "Ensure version_middleware is applied to the application."
        )

    return request.state.api_version


def deprecation_warning(version: str, endpoint: str) -> dict:
    """
    Generate a deprecation warning response.

    Args:
        version: Deprecated version
        endpoint: Endpoint path

    Returns:
        Warning dictionary to include in response
    """
    message = get_deprecation_message(version) or f"API version {version} is deprecated"

    return {
        "warning": {
            "code": "deprecated_version",
            "message": message,
            "deprecated_version": version,
            "current_version": LATEST_VERSION,
            "endpoint": endpoint
        }
    }


# ============================================================================
# Version-aware Route Helpers
# ============================================================================

def version_route(path: str, version: Optional[str] = None) -> str:
    """
    Generate a versioned route path.

    Args:
        path: Endpoint path (e.g., "/osteon/draft")
        version: Version to use (defaults to LATEST_VERSION)

    Returns:
        Versioned path (e.g., "/v1/osteon/draft")

    Examples:
        >>> version_route("/osteon/draft")
        '/v1/osteon/draft'
        >>> version_route("/osteon/draft", "v2")
        '/v2/osteon/draft'
    """
    version = version or LATEST_VERSION

    # Remove leading slash if present
    path = path.lstrip('/')

    return f"/{version}/{path}"


def get_all_version_routes(path: str) -> List[str]:
    """
    Generate route paths for all supported versions.

    Args:
        path: Endpoint path (e.g., "/osteon/draft")

    Returns:
        List of versioned paths for all supported versions

    Examples:
        >>> get_all_version_routes("/osteon/draft")
        ['/v1/osteon/draft']
    """
    return [version_route(path, v) for v in SUPPORTED_VERSIONS]
