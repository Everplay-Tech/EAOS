"""FastAPI middleware for comprehensive security headers.

This middleware adds essential security headers to all HTTP responses:
- Content-Security-Policy (CSP)
- HTTP Strict-Transport-Security (HSTS)
- X-Frame-Options
- X-Content-Type-Options
- X-XSS-Protection
- Referrer-Policy
- Permissions-Policy

All headers are configurable via environment variables and can be
customized for different environments (development, staging, production).
"""

from typing import Callable, Optional, Dict, Any, List
import os
import json
from datetime import datetime, timezone

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from starlette.datastructures import Headers

from .config import settings
from .logging_config import setup_logging


logger = setup_logging("security_headers")


class SecurityHeadersConfig:
    """Configuration for security headers."""

    def __init__(self):
        """Initialize security headers configuration from environment."""
        # Environment detection
        self.environment = settings.environment.lower()
        self.is_production = self.environment == "production"
        self.is_development = self.environment == "development"

        # Content-Security-Policy
        self.csp_enabled = os.getenv("CSP_ENABLED", "true").lower() == "true"
        self.csp_report_only = os.getenv("CSP_REPORT_ONLY", "false" if self.is_production else "true").lower() == "true"
        self.csp_directives = self._build_csp_directives()

        # HSTS (HTTP Strict-Transport-Security)
        self.hsts_enabled = os.getenv("HSTS_ENABLED", str(self.is_production)).lower() == "true"
        self.hsts_max_age = int(os.getenv("HSTS_MAX_AGE", "31536000"))  # 1 year
        self.hsts_include_subdomains = os.getenv("HSTS_INCLUDE_SUBDOMAINS", "true").lower() == "true"
        self.hsts_preload = os.getenv("HSTS_PRELOAD", "false").lower() == "true"

        # X-Frame-Options
        self.x_frame_options = os.getenv("X_FRAME_OPTIONS", "DENY")  # DENY, SAMEORIGIN, ALLOW-FROM

        # X-Content-Type-Options
        self.x_content_type_options = os.getenv("X_CONTENT_TYPE_OPTIONS", "nosniff")

        # X-XSS-Protection (legacy, but still useful for older browsers)
        self.x_xss_protection = os.getenv("X_XSS_PROTECTION", "1; mode=block")

        # Referrer-Policy
        self.referrer_policy = os.getenv("REFERRER_POLICY", "strict-origin-when-cross-origin")

        # Permissions-Policy (formerly Feature-Policy)
        self.permissions_policy = os.getenv(
            "PERMISSIONS_POLICY",
            "geolocation=(), microphone=(), camera=(), payment=(), usb=(), magnetometer=(), gyroscope=(), speaker=()"
        )

        # CSP Violation Reporting
        self.csp_report_uri = os.getenv("CSP_REPORT_URI", "/api/csp-report")
        self.csp_report_to = os.getenv("CSP_REPORT_TO", "csp-endpoint")

        # Additional security headers
        self.cross_origin_embedder_policy = os.getenv("CROSS_ORIGIN_EMBEDDER_POLICY", "")  # require-corp (opt-in)
        self.cross_origin_opener_policy = os.getenv("CROSS_ORIGIN_OPENER_POLICY", "same-origin")
        self.cross_origin_resource_policy = os.getenv("CROSS_ORIGIN_RESOURCE_POLICY", "same-origin")

    def _build_csp_directives(self) -> Dict[str, str]:
        """Build CSP directives based on environment and configuration."""
        # Base CSP directives
        directives = {
            "default-src": os.getenv("CSP_DEFAULT_SRC", "'self'"),
            "script-src": os.getenv("CSP_SCRIPT_SRC", "'self'"),
            "style-src": os.getenv("CSP_STYLE_SRC", "'self' 'unsafe-inline'"),  # unsafe-inline needed for some frameworks
            "img-src": os.getenv("CSP_IMG_SRC", "'self' data: https:"),
            "font-src": os.getenv("CSP_FONT_SRC", "'self' data:"),
            "connect-src": os.getenv("CSP_CONNECT_SRC", "'self'"),
            "media-src": os.getenv("CSP_MEDIA_SRC", "'self'"),
            "object-src": os.getenv("CSP_OBJECT_SRC", "'none'"),
            "frame-src": os.getenv("CSP_FRAME_SRC", "'none'"),
            "frame-ancestors": os.getenv("CSP_FRAME_ANCESTORS", "'none'"),
            "base-uri": os.getenv("CSP_BASE_URI", "'self'"),
            "form-action": os.getenv("CSP_FORM_ACTION", "'self'"),
            "upgrade-insecure-requests": os.getenv("CSP_UPGRADE_INSECURE_REQUESTS", "" if self.is_development else "upgrade-insecure-requests"),
        }

        # Add report-uri in development or if explicitly enabled
        if not self.is_production or os.getenv("CSP_REPORT_ENABLED", "true").lower() == "true":
            directives["report-uri"] = self.csp_report_uri
            directives["report-to"] = self.csp_report_to

        # Filter out empty directives
        return {k: v for k, v in directives.items() if v}

    def get_csp_header_value(self) -> str:
        """Generate CSP header value from directives."""
        parts = []
        for directive, value in self.csp_directives.items():
            # Handle directives with no value (like upgrade-insecure-requests)
            if directive == value:
                parts.append(directive)
            else:
                parts.append(f"{directive} {value}")
        return "; ".join(parts)

    def get_hsts_header_value(self) -> str:
        """Generate HSTS header value."""
        value = f"max-age={self.hsts_max_age}"
        if self.hsts_include_subdomains:
            value += "; includeSubDomains"
        if self.hsts_preload:
            value += "; preload"
        return value


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware for adding comprehensive security headers to all HTTP responses.

    Features:
    - Content-Security-Policy (CSP) with configurable directives
    - HTTP Strict-Transport-Security (HSTS) for HTTPS enforcement
    - X-Frame-Options to prevent clickjacking
    - X-Content-Type-Options to prevent MIME sniffing
    - X-XSS-Protection for legacy browser XSS protection
    - Referrer-Policy to control referrer information
    - Permissions-Policy to control browser features
    - Environment-specific configurations
    - CSP violation reporting
    """

    def __init__(
        self,
        app: ASGIApp,
        config: Optional[SecurityHeadersConfig] = None,
        exclude_paths: Optional[List[str]] = None,
    ):
        """
        Initialize security headers middleware.

        Args:
            app: ASGI application
            config: Security headers configuration (None = use default from env)
            exclude_paths: List of paths to exclude from security headers
        """
        super().__init__(app)
        self.config = config or SecurityHeadersConfig()

        # Default exclusions for paths that might need relaxed security
        default_exclusions = []
        self.exclude_paths = set(default_exclusions + (exclude_paths or []))

        # Log configuration on startup
        self._log_config()

    def _log_config(self):
        """Log security headers configuration on startup."""
        logger.info(
            f"Security Headers Middleware initialized for environment: {self.config.environment}"
        )
        logger.info(f"CSP Enabled: {self.config.csp_enabled} (Report Only: {self.config.csp_report_only})")
        logger.info(f"HSTS Enabled: {self.config.hsts_enabled}")
        logger.info(f"X-Frame-Options: {self.config.x_frame_options}")

        if self.config.is_development:
            logger.warning(
                "Running in DEVELOPMENT mode - some security features may be relaxed. "
                "Ensure proper security headers are enforced in PRODUCTION."
            )

    def should_apply_headers(self, request: Request) -> bool:
        """Determine if security headers should be applied to this request."""
        path = request.url.path

        # Skip excluded paths
        if any(path.startswith(excluded) for excluded in self.exclude_paths):
            return False

        return True

    async def dispatch(
        self,
        request: Request,
        call_next: Callable
    ) -> Response:
        """Process the request and add security headers to response."""
        # Process the request
        response = await call_next(request)

        # Check if we should apply headers
        if not self.should_apply_headers(request):
            return response

        # Add security headers
        self._add_security_headers(response)

        return response

    def _add_security_headers(self, response: Response):
        """Add all security headers to the response."""
        # Content-Security-Policy
        if self.config.csp_enabled:
            csp_value = self.config.get_csp_header_value()
            if self.config.csp_report_only:
                response.headers["Content-Security-Policy-Report-Only"] = csp_value
            else:
                response.headers["Content-Security-Policy"] = csp_value

        # HTTP Strict-Transport-Security (HSTS)
        # Only add HSTS if TLS is enabled or in production
        if self.config.hsts_enabled and (settings.tls_enabled or self.config.is_production):
            response.headers["Strict-Transport-Security"] = self.config.get_hsts_header_value()
        elif self.config.hsts_enabled and not settings.tls_enabled:
            logger.warning(
                "HSTS is enabled but TLS is not. HSTS header will not be added. "
                "Enable TLS in production for HSTS to work."
            )

        # X-Frame-Options
        response.headers["X-Frame-Options"] = self.config.x_frame_options

        # X-Content-Type-Options
        response.headers["X-Content-Type-Options"] = self.config.x_content_type_options

        # X-XSS-Protection (legacy, but still useful)
        response.headers["X-XSS-Protection"] = self.config.x_xss_protection

        # Referrer-Policy
        response.headers["Referrer-Policy"] = self.config.referrer_policy

        # Permissions-Policy
        if self.config.permissions_policy:
            response.headers["Permissions-Policy"] = self.config.permissions_policy

        # Cross-Origin-Embedder-Policy (opt-in)
        if self.config.cross_origin_embedder_policy:
            response.headers["Cross-Origin-Embedder-Policy"] = self.config.cross_origin_embedder_policy

        # Cross-Origin-Opener-Policy
        if self.config.cross_origin_opener_policy:
            response.headers["Cross-Origin-Opener-Policy"] = self.config.cross_origin_opener_policy

        # Cross-Origin-Resource-Policy
        if self.config.cross_origin_resource_policy:
            response.headers["Cross-Origin-Resource-Policy"] = self.config.cross_origin_resource_policy

        # Report-To header for CSP reporting (NEL, Crash Reporting, etc.)
        if not self.config.is_production or os.getenv("CSP_REPORT_ENABLED", "true").lower() == "true":
            report_to = {
                "group": self.config.csp_report_to,
                "max_age": 10886400,  # 126 days
                "endpoints": [{"url": self.config.csp_report_uri}],
            }
            response.headers["Report-To"] = json.dumps(report_to)


def create_security_headers_middleware(
    config: Optional[SecurityHeadersConfig] = None,
    exclude_paths: Optional[List[str]] = None
) -> type[SecurityHeadersMiddleware]:
    """
    Factory function to create security headers middleware.

    Args:
        config: Security headers configuration
        exclude_paths: Paths to exclude from security headers

    Returns:
        SecurityHeadersMiddleware class configured with provided settings

    Example:
        app.add_middleware(
            create_security_headers_middleware(
                exclude_paths=["/internal", "/admin"]
            )
        )
    """
    class ConfiguredSecurityHeadersMiddleware(SecurityHeadersMiddleware):
        def __init__(self, app: ASGIApp):
            super().__init__(app, config, exclude_paths)

    return ConfiguredSecurityHeadersMiddleware
