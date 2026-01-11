"""FastAPI middleware for automatic audit logging of all requests.

This middleware automatically captures and logs:
- All HTTP requests and responses
- Authentication and authorization events
- Errors and exceptions
- Performance metrics

All logs are written with encryption at rest for sensitive fields.
"""

from typing import Callable, Optional, Dict, Any
import time
import json
from datetime import datetime, timezone

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from sqlalchemy.ext.asyncio import AsyncSession

from .audit import (
    AuditLogger,
    AuditContext,
    EventType,
    EventCategory,
    EventStatus,
    Severity,
    get_audit_logger
)
from .database import get_db
from .config import settings


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Middleware for automatic audit logging of all API requests.

    Features:
    - Automatic capture of request/response data
    - User and session context tracking
    - Performance metrics (duration)
    - Error tracking
    - Encryption of sensitive fields
    - Configurable exclusions (health checks, metrics, etc.)
    """

    def __init__(
        self,
        app: ASGIApp,
        service_name: str,
        exclude_paths: Optional[list] = None,
        audit_logger: Optional[AuditLogger] = None,
    ):
        """
        Initialize audit middleware.

        Args:
            app: ASGI application
            service_name: Name of the service (osteon, myocyte, mesh, etc.)
            exclude_paths: List of paths to exclude from audit logging
            audit_logger: Custom audit logger instance
        """
        super().__init__(app)
        self.service_name = service_name
        self.audit_logger = audit_logger or get_audit_logger()

        # Default exclusions + custom exclusions
        default_exclusions = ["/health", "/metrics", "/docs", "/redoc", "/openapi.json"]
        self.exclude_paths = set(default_exclusions + (exclude_paths or []))

    def should_audit(self, request: Request) -> bool:
        """Determine if the request should be audited."""
        # Skip if audit logging is disabled
        if not settings.audit_enabled:
            return False

        # Skip excluded paths
        path = request.url.path
        if any(path.startswith(excluded) for excluded in self.exclude_paths):
            return False

        return True

    async def dispatch(
        self,
        request: Request,
        call_next: Callable
    ) -> Response:
        """Process the request and audit log it."""
        # Check if we should audit this request
        if not self.should_audit(request):
            return await call_next(request)

        # Create audit context from request
        context = AuditContext.from_request(request, self.service_name)

        # Capture request data
        request_data = await self._capture_request_data(request)

        # Process the request
        response = None
        error_message = None
        error_code = None
        http_status_code = 500

        try:
            response = await call_next(request)
            http_status_code = response.status_code

            # Capture response data if configured
            if settings.audit_log_responses:
                response_data = await self._capture_response_data(response)
            else:
                response_data = None

        except Exception as e:
            # Capture exception details
            error_message = str(e)
            error_code = type(e).__name__
            http_status_code = 500
            response_data = None
            raise  # Re-raise the exception

        finally:
            # Determine event status
            if error_message:
                event_status = EventStatus.error
                severity = Severity.ERROR
            elif http_status_code >= 500:
                event_status = EventStatus.error
                severity = Severity.ERROR
            elif http_status_code >= 400:
                event_status = EventStatus.failure
                severity = Severity.WARNING
            else:
                event_status = EventStatus.success
                severity = Severity.INFO

            # Categorize the event
            event_type, event_category = self._categorize_request(request, http_status_code)

            # Get database session for logging
            async for session in get_db():
                try:
                    # Log the audit event
                    await self.audit_logger.log(
                        event_type=event_type,
                        event_category=event_category,
                        event_action=self._get_action_name(request),
                        event_status=event_status,
                        severity=severity,
                        context=context,
                        endpoint=request.url.path,
                        http_method=request.method,
                        http_status_code=http_status_code,
                        request_data=request_data if settings.audit_log_requests else None,
                        response_data=response_data,
                        error_message=error_message,
                        error_code=error_code,
                        authentication_method=self._get_auth_method(request),
                        session=session,
                    )
                except Exception as log_error:
                    # Don't fail the request if audit logging fails
                    # In production, you might want to send this to a monitoring system
                    print(f"Audit logging failed: {log_error}")
                finally:
                    break  # Exit the session generator

        return response

    async def _capture_request_data(self, request: Request) -> Optional[Dict[str, Any]]:
        """Capture request data for audit logging."""
        if not settings.audit_log_requests:
            return None

        try:
            data = {
                "method": request.method,
                "url": str(request.url),
                "path": request.url.path,
                "query_params": dict(request.query_params),
                "path_params": dict(request.path_params) if hasattr(request, 'path_params') else {},
            }

            # Capture headers (exclude sensitive ones)
            headers = dict(request.headers)
            sensitive_headers = ["authorization", "cookie", "x-api-key"]
            data["headers"] = {
                k: v for k, v in headers.items()
                if k.lower() not in sensitive_headers
            }

            # Capture body for POST/PUT/PATCH requests
            if request.method in ["POST", "PUT", "PATCH"]:
                try:
                    # Read body (this might have already been read)
                    body = await request.body()
                    if body:
                        # Try to parse as JSON
                        try:
                            data["body"] = json.loads(body.decode('utf-8'))
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            # Store as base64 if not JSON
                            import base64
                            data["body_base64"] = base64.b64encode(body).decode('utf-8')
                except Exception:
                    # Body might have already been consumed
                    pass

            return data

        except Exception as e:
            return {"error": f"Failed to capture request data: {str(e)}"}

    async def _capture_response_data(self, response: Response) -> Optional[Dict[str, Any]]:
        """Capture response data for audit logging."""
        try:
            data = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
            }

            # Note: Capturing response body is complex in FastAPI middleware
            # as it requires re-streaming the response. For now, we just capture
            # status and headers. If you need body capture, consider using a
            # custom response class or dependency injection.

            return data

        except Exception as e:
            return {"error": f"Failed to capture response data: {str(e)}"}

    def _categorize_request(
        self,
        request: Request,
        status_code: int
    ) -> tuple[EventType, EventCategory]:
        """Categorize the request into event type and category."""
        path = request.url.path.lower()
        method = request.method.upper()

        # Authentication endpoints
        if any(auth_path in path for auth_path in ["/login", "/logout", "/token", "/auth", "/refresh"]):
            return EventType.AUTH, EventCategory.authentication

        # Administrative endpoints
        if any(admin_path in path for admin_path in ["/admin", "/users", "/config", "/settings"]):
            return EventType.ADMIN, EventCategory.admin

        # Data operations based on HTTP method
        if method == "GET":
            return EventType.DATA_READ, EventCategory.data
        elif method in ["POST", "PUT", "PATCH"]:
            return EventType.DATA_WRITE, EventCategory.data
        elif method == "DELETE":
            return EventType.DATA_DELETE, EventCategory.data

        # Default
        return EventType.ACCESS, EventCategory.data

    def _get_action_name(self, request: Request) -> str:
        """Generate a descriptive action name from the request."""
        method = request.method.upper()
        path = request.url.path

        # Try to extract resource name from path
        path_parts = [p for p in path.split('/') if p]
        if path_parts:
            resource = path_parts[-1] if not path_parts[-1].replace('-', '').isalnum() else path_parts[0]
        else:
            resource = "root"

        # Map HTTP methods to action verbs
        action_map = {
            "GET": "read",
            "POST": "create",
            "PUT": "update",
            "PATCH": "update",
            "DELETE": "delete",
            "HEAD": "check",
            "OPTIONS": "options",
        }

        action = action_map.get(method, method.lower())
        return f"{action}_{resource}"

    def _get_auth_method(self, request: Request) -> Optional[str]:
        """Determine the authentication method used."""
        # Check for JWT in Authorization header
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            return "jwt"

        # Check for API key
        if request.headers.get("x-api-key") or request.headers.get("api-key"):
            return "api_key"

        # Check for session cookie
        if "session" in request.cookies:
            return "session"

        # Check for mTLS client certificate
        if hasattr(request.state, "client_cert"):
            return "mtls"

        return "anonymous"


def create_audit_middleware(
    service_name: str,
    exclude_paths: Optional[list] = None
) -> type[AuditMiddleware]:
    """
    Factory function to create audit middleware for a service.

    Args:
        service_name: Name of the service
        exclude_paths: Additional paths to exclude from audit logging

    Returns:
        AuditMiddleware class configured for the service

    Example:
        app.add_middleware(
            create_audit_middleware("osteon", exclude_paths=["/internal"])
        )
    """
    class ConfiguredAuditMiddleware(AuditMiddleware):
        def __init__(self, app: ASGIApp):
            super().__init__(app, service_name, exclude_paths)

    return ConfiguredAuditMiddleware
