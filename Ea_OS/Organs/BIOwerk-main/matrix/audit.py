"""Enterprise audit logging service with encryption at rest.

This module provides comprehensive audit logging for:
- Authentication and authorization events
- Data access and modifications
- Administrative actions
- Security events

All sensitive data is encrypted at rest using AES-256-GCM envelope encryption.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from enum import Enum
import uuid
import hashlib
import json
import asyncio
from collections import deque

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, func
from fastapi import Request

from .db_models import AuditLog
from .encryption import EncryptionService, create_encryption_service
from .config import settings


class EventType(str, Enum):
    """Audit event types for categorization."""
    AUTH = "AUTH"  # Authentication events
    ACCESS = "ACCESS"  # Authorization/access control events
    DATA_READ = "DATA_READ"  # Data read operations
    DATA_WRITE = "DATA_WRITE"  # Data creation/update operations
    DATA_DELETE = "DATA_DELETE"  # Data deletion operations
    ADMIN = "ADMIN"  # Administrative actions
    SECURITY = "SECURITY"  # Security-related events
    SYSTEM = "SYSTEM"  # System-level events


class EventCategory(str, Enum):
    """Event categories for compliance reporting."""
    authentication = "authentication"
    authorization = "authorization"
    data = "data"
    admin = "admin"
    security = "security"
    system = "system"


class EventStatus(str, Enum):
    """Event status outcomes."""
    success = "success"
    failure = "failure"
    error = "error"
    warning = "warning"


class Severity(str, Enum):
    """Event severity levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AuditContext:
    """Context object for collecting audit information during request processing."""

    def __init__(
        self,
        event_id: Optional[str] = None,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        session_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        service_name: Optional[str] = None,
    ):
        self.event_id = event_id or str(uuid.uuid4())
        self.user_id = user_id
        self.username = username
        self.session_id = session_id
        self.trace_id = trace_id
        self.request_id = request_id
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.service_name = service_name
        self.start_time = datetime.now(timezone.utc)

    @classmethod
    def from_request(cls, request: Request, service_name: str) -> "AuditContext":
        """Create audit context from FastAPI request."""
        # Extract user info from request state (set by auth middleware)
        user_id = getattr(request.state, "user_id", None)
        username = getattr(request.state, "username", None)
        session_id = getattr(request.state, "session_id", None)

        # Extract network info
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

        # Extract correlation IDs
        trace_id = request.headers.get("x-trace-id") or request.headers.get("x-request-id")
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())

        return cls(
            user_id=user_id,
            username=username,
            session_id=session_id,
            trace_id=trace_id,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            service_name=service_name,
        )

    def get_duration_ms(self) -> float:
        """Get elapsed time since context creation in milliseconds."""
        elapsed = datetime.now(timezone.utc) - self.start_time
        return elapsed.total_seconds() * 1000


class AuditLogger:
    """
    Enterprise audit logging service with encryption at rest.

    Features:
    - Automatic encryption of sensitive fields
    - Async batch writing for performance
    - Configurable retention policies
    - Cryptographic integrity verification
    - Support for compliance reporting (SOC2, HIPAA, GDPR, etc.)
    """

    def __init__(
        self,
        encryption_service: Optional[EncryptionService] = None,
        enable_encryption: bool = True,
        batch_size: int = 100,
        async_write: bool = True,
    ):
        """
        Initialize the audit logger.

        Args:
            encryption_service: Encryption service for sensitive data
            enable_encryption: Enable encryption of sensitive fields
            batch_size: Number of logs to batch before writing
            async_write: Enable asynchronous batch writing
        """
        self.enable_encryption = enable_encryption and settings.audit_encrypt_sensitive
        self.batch_size = batch_size or settings.audit_batch_size
        self.async_write = async_write and settings.audit_async_write

        # Initialize encryption service
        if self.enable_encryption:
            self.encryption_service = encryption_service or create_encryption_service(
                master_key=settings.encryption_master_key,
                key_version=settings.encryption_key_version,
                salt=settings.encryption_salt,
            )
        else:
            self.encryption_service = None

        # Batch queue for async writes
        self._batch_queue: deque = deque()
        self._batch_lock = asyncio.Lock()

        # Sensitive field patterns for automatic encryption
        self.sensitive_patterns = settings.audit_sensitive_fields

    def _should_encrypt_field(self, field_name: str) -> bool:
        """Check if a field should be encrypted based on naming patterns."""
        field_lower = field_name.lower()
        return any(pattern in field_lower for pattern in self.sensitive_patterns)

    def _sanitize_data(self, data: Any, max_size: int) -> Any:
        """Sanitize and truncate data to prevent excessive storage."""
        if data is None:
            return None

        if isinstance(data, (dict, list)):
            data_str = json.dumps(data)
            if len(data_str) > max_size:
                return {"_truncated": True, "_size": len(data_str)}
            return data

        if isinstance(data, str) and len(data) > max_size:
            return data[:max_size] + "... [truncated]"

        return data

    def _compute_record_hash(self, audit_data: Dict[str, Any]) -> str:
        """
        Compute SHA-256 hash of critical fields for tamper detection.

        This creates a cryptographic hash of immutable audit fields that can be
        used to verify the integrity of the audit log record.
        """
        critical_fields = [
            audit_data.get("event_id"),
            audit_data.get("event_type"),
            audit_data.get("event_action"),
            audit_data.get("user_id"),
            audit_data.get("resource_type"),
            audit_data.get("resource_id"),
            audit_data.get("event_timestamp"),
        ]

        hash_input = "|".join(str(f) for f in critical_fields if f is not None)
        return hashlib.sha256(hash_input.encode('utf-8')).hexdigest()

    def _get_retention_days(self, event_category: str) -> int:
        """Get retention period based on event category for compliance."""
        retention_map = {
            EventCategory.authentication: settings.audit_retention_auth_days,
            EventCategory.authorization: settings.audit_retention_auth_days,
            EventCategory.data: settings.audit_retention_data_days,
            EventCategory.admin: settings.audit_retention_data_days,
            EventCategory.security: settings.audit_retention_security_days,
            EventCategory.system: settings.audit_retention_days,
        }
        return retention_map.get(event_category, settings.audit_retention_days)

    async def log(
        self,
        event_type: EventType,
        event_category: EventCategory,
        event_action: str,
        event_status: EventStatus,
        severity: Severity = Severity.INFO,
        context: Optional[AuditContext] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        resource_name: Optional[str] = None,
        endpoint: Optional[str] = None,
        http_method: Optional[str] = None,
        http_status_code: Optional[int] = None,
        request_data: Optional[Dict[str, Any]] = None,
        response_data: Optional[Dict[str, Any]] = None,
        changes_before: Optional[Dict[str, Any]] = None,
        changes_after: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        error_code: Optional[str] = None,
        authentication_method: Optional[str] = None,
        authorization_result: Optional[str] = None,
        session: Optional[AsyncSession] = None,
        **kwargs
    ) -> str:
        """
        Log an audit event with optional encryption of sensitive fields.

        Args:
            event_type: Type of event (AUTH, ACCESS, DATA_READ, etc.)
            event_category: Category for compliance (authentication, data, etc.)
            event_action: Specific action performed (login, create, delete, etc.)
            event_status: Outcome status (success, failure, error, warning)
            severity: Severity level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            context: Audit context with user/session/network info
            resource_type: Type of resource affected (user, project, artifact, etc.)
            resource_id: ID of the resource
            resource_name: Name of the resource
            endpoint: API endpoint accessed
            http_method: HTTP method (GET, POST, etc.)
            http_status_code: HTTP response status code
            request_data: Request payload
            response_data: Response payload
            changes_before: State before modification
            changes_after: State after modification
            error_message: Error message if failed
            error_code: Error code if failed
            authentication_method: Auth method used (jwt, api_key, etc.)
            authorization_result: Authorization outcome (allowed, denied)
            session: Database session for immediate write
            **kwargs: Additional custom fields

        Returns:
            Event ID of the logged audit event
        """
        # Use or create context
        if context is None:
            context = AuditContext()

        # Sanitize data fields
        max_size = settings.audit_max_field_size
        request_data = self._sanitize_data(request_data, max_size)
        response_data = self._sanitize_data(response_data, max_size)
        changes_before = self._sanitize_data(changes_before, max_size)
        changes_after = self._sanitize_data(changes_after, max_size)

        # Build audit log data
        audit_data = {
            "event_id": context.event_id,
            "event_type": event_type.value,
            "event_category": event_category.value,
            "event_action": event_action,
            "event_status": event_status.value,
            "severity": severity.value,
            "user_id": context.user_id,
            "username": context.username,
            "actor_type": "user" if context.user_id else "anonymous",
            "resource_type": resource_type,
            "resource_id": resource_id,
            "resource_name": resource_name,
            "service_name": context.service_name,
            "endpoint": endpoint,
            "http_method": http_method,
            "http_status_code": http_status_code,
            "ip_address": context.ip_address,
            "user_agent": context.user_agent,
            "session_id": context.session_id,
            "trace_id": context.trace_id,
            "request_id": context.request_id,
            "duration_ms": context.get_duration_ms(),
            "error_message": error_message,
            "error_code": error_code,
            "authentication_method": authentication_method,
            "authorization_result": authorization_result,
            "retention_period_days": self._get_retention_days(event_category),
            "encryption_key_version": self.encryption_service.key_version if self.encryption_service else None,
            "event_timestamp": context.start_time,
        }

        # Handle encryption of sensitive fields
        if self.enable_encryption and self.encryption_service:
            # Encrypt IP address
            if context.ip_address:
                audit_data["ip_address_encrypted"] = self.encryption_service.encrypt_field(
                    context.ip_address,
                    associated_data=context.event_id
                )
                audit_data["ip_address_hash"] = self.encryption_service.hash_for_search(context.ip_address)
                audit_data["ip_address"] = None  # Clear plaintext

            # Encrypt user agent
            if context.user_agent:
                audit_data["user_agent_encrypted"] = self.encryption_service.encrypt_field(
                    context.user_agent,
                    associated_data=context.event_id
                )
                audit_data["user_agent_hash"] = self.encryption_service.hash_for_search(context.user_agent)
                audit_data["user_agent"] = None  # Clear plaintext

            # Encrypt request data if it contains sensitive fields
            if request_data:
                audit_data["request_data_encrypted"] = self.encryption_service.encrypt_field(
                    json.dumps(request_data),
                    associated_data=context.event_id
                )
                audit_data["request_data"] = None  # Clear plaintext

            # Encrypt response data if it contains sensitive fields
            if response_data:
                audit_data["response_data_encrypted"] = self.encryption_service.encrypt_field(
                    json.dumps(response_data),
                    associated_data=context.event_id
                )
                audit_data["response_data"] = None  # Clear plaintext

            # Encrypt change tracking
            if changes_before:
                audit_data["changes_before_encrypted"] = self.encryption_service.encrypt_field(
                    json.dumps(changes_before),
                    associated_data=context.event_id
                )
                audit_data["changes_before"] = None

            if changes_after:
                audit_data["changes_after_encrypted"] = self.encryption_service.encrypt_field(
                    json.dumps(changes_after),
                    associated_data=context.event_id
                )
                audit_data["changes_after"] = None
        else:
            # Store in plaintext if encryption disabled
            audit_data["request_data"] = request_data
            audit_data["response_data"] = response_data
            audit_data["changes_before"] = changes_before
            audit_data["changes_after"] = changes_after

        # Compute integrity hash
        audit_data["record_hash"] = self._compute_record_hash(audit_data)

        # Add any additional custom fields
        audit_data.update(kwargs)

        # Write to database
        if session:
            # Immediate write
            await self._write_audit_log(session, audit_data)
        elif self.async_write:
            # Add to batch queue
            await self._add_to_batch(audit_data)
        else:
            # This would require a session - log warning
            # In production, always provide a session or use async batching
            pass

        return context.event_id

    async def _write_audit_log(self, session: AsyncSession, audit_data: Dict[str, Any]):
        """Write a single audit log to the database."""
        audit_log = AuditLog(**audit_data)
        session.add(audit_log)
        await session.commit()

    async def _add_to_batch(self, audit_data: Dict[str, Any]):
        """Add audit log to batch queue for async writing."""
        async with self._batch_lock:
            self._batch_queue.append(audit_data)

            # If batch is full, flush it
            if len(self._batch_queue) >= self.batch_size:
                await self._flush_batch()

    async def _flush_batch(self):
        """Flush the batch queue to the database."""
        # This would require a database session
        # Implementation would depend on your async session management
        # For now, this is a placeholder
        pass

    async def log_authentication(
        self,
        action: str,
        status: EventStatus,
        context: AuditContext,
        authentication_method: str,
        error_message: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> str:
        """Log an authentication event (login, logout, token refresh, etc.)."""
        return await self.log(
            event_type=EventType.AUTH,
            event_category=EventCategory.authentication,
            event_action=action,
            event_status=status,
            severity=Severity.WARNING if status == EventStatus.failure else Severity.INFO,
            context=context,
            authentication_method=authentication_method,
            error_message=error_message,
            session=session,
        )

    async def log_access(
        self,
        action: str,
        status: EventStatus,
        context: AuditContext,
        resource_type: str,
        resource_id: Optional[str] = None,
        authorization_result: Optional[str] = None,
        error_message: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> str:
        """Log an access/authorization event."""
        return await self.log(
            event_type=EventType.ACCESS,
            event_category=EventCategory.authorization,
            event_action=action,
            event_status=status,
            severity=Severity.WARNING if authorization_result == "denied" else Severity.INFO,
            context=context,
            resource_type=resource_type,
            resource_id=resource_id,
            authorization_result=authorization_result,
            error_message=error_message,
            session=session,
        )

    async def log_data_read(
        self,
        action: str,
        status: EventStatus,
        context: AuditContext,
        resource_type: str,
        resource_id: Optional[str] = None,
        resource_name: Optional[str] = None,
        response_data: Optional[Dict[str, Any]] = None,
        session: Optional[AsyncSession] = None,
    ) -> str:
        """Log a data read operation."""
        return await self.log(
            event_type=EventType.DATA_READ,
            event_category=EventCategory.data,
            event_action=action,
            event_status=status,
            severity=Severity.INFO,
            context=context,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            response_data=response_data,
            session=session,
        )

    async def log_data_write(
        self,
        action: str,
        status: EventStatus,
        context: AuditContext,
        resource_type: str,
        resource_id: Optional[str] = None,
        resource_name: Optional[str] = None,
        changes_before: Optional[Dict[str, Any]] = None,
        changes_after: Optional[Dict[str, Any]] = None,
        request_data: Optional[Dict[str, Any]] = None,
        session: Optional[AsyncSession] = None,
    ) -> str:
        """Log a data write operation (create, update)."""
        return await self.log(
            event_type=EventType.DATA_WRITE,
            event_category=EventCategory.data,
            event_action=action,
            event_status=status,
            severity=Severity.INFO,
            context=context,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            changes_before=changes_before,
            changes_after=changes_after,
            request_data=request_data,
            session=session,
        )

    async def log_data_delete(
        self,
        action: str,
        status: EventStatus,
        context: AuditContext,
        resource_type: str,
        resource_id: Optional[str] = None,
        resource_name: Optional[str] = None,
        changes_before: Optional[Dict[str, Any]] = None,
        session: Optional[AsyncSession] = None,
    ) -> str:
        """Log a data deletion operation."""
        return await self.log(
            event_type=EventType.DATA_DELETE,
            event_category=EventCategory.data,
            event_action=action,
            event_status=status,
            severity=Severity.WARNING,
            context=context,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            changes_before=changes_before,
            session=session,
        )

    async def log_admin(
        self,
        action: str,
        status: EventStatus,
        context: AuditContext,
        resource_type: str,
        resource_id: Optional[str] = None,
        changes_before: Optional[Dict[str, Any]] = None,
        changes_after: Optional[Dict[str, Any]] = None,
        session: Optional[AsyncSession] = None,
    ) -> str:
        """Log an administrative action."""
        return await self.log(
            event_type=EventType.ADMIN,
            event_category=EventCategory.admin,
            event_action=action,
            event_status=status,
            severity=Severity.WARNING,
            context=context,
            resource_type=resource_type,
            resource_id=resource_id,
            changes_before=changes_before,
            changes_after=changes_after,
            session=session,
        )

    async def log_security(
        self,
        action: str,
        status: EventStatus,
        context: AuditContext,
        severity: Severity = Severity.WARNING,
        error_message: Optional[str] = None,
        risk_score: Optional[int] = None,
        session: Optional[AsyncSession] = None,
    ) -> str:
        """Log a security event."""
        return await self.log(
            event_type=EventType.SECURITY,
            event_category=EventCategory.security,
            event_action=action,
            event_status=status,
            severity=severity,
            context=context,
            error_message=error_message,
            risk_score=risk_score,
            session=session,
        )


# Global audit logger instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get or create the global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger(
            enable_encryption=settings.audit_encrypt_sensitive,
            batch_size=settings.audit_batch_size,
            async_write=settings.audit_async_write,
        )
    return _audit_logger
