"""Audit log management, querying, and export capabilities.

This module provides:
- Advanced querying and filtering of audit logs
- Export to various formats (JSON, CSV)
- Retention policy enforcement
- Log archival and deletion
- Compliance reporting
- Decryption of encrypted fields for authorized access
"""

from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta, timezone
from enum import Enum
import csv
import json
import io

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, func, delete, update
from sqlalchemy.sql import Select

from .db_models import AuditLog
from .encryption import EncryptionService, create_encryption_service, DecryptionError
from .audit import EventType, EventCategory, EventStatus, Severity
from .config import settings


class ExportFormat(str, Enum):
    """Supported export formats for audit logs."""
    JSON = "json"
    CSV = "csv"
    JSON_LINES = "jsonl"


class AuditQueryBuilder:
    """Builder for constructing complex audit log queries."""

    def __init__(self):
        self.filters = []
        self._query: Optional[Select] = None

    def filter_by_user(self, user_id: str) -> "AuditQueryBuilder":
        """Filter by user ID."""
        self.filters.append(AuditLog.user_id == user_id)
        return self

    def filter_by_event_type(self, event_type: EventType) -> "AuditQueryBuilder":
        """Filter by event type."""
        self.filters.append(AuditLog.event_type == event_type.value)
        return self

    def filter_by_event_category(self, category: EventCategory) -> "AuditQueryBuilder":
        """Filter by event category."""
        self.filters.append(AuditLog.event_category == category.value)
        return self

    def filter_by_event_action(self, action: str) -> "AuditQueryBuilder":
        """Filter by event action."""
        self.filters.append(AuditLog.event_action == action)
        return self

    def filter_by_status(self, status: EventStatus) -> "AuditQueryBuilder":
        """Filter by event status."""
        self.filters.append(AuditLog.event_status == status.value)
        return self

    def filter_by_severity(self, severity: Severity, min_severity: bool = True) -> "AuditQueryBuilder":
        """Filter by severity level."""
        if min_severity:
            severity_order = {
                "DEBUG": 0,
                "INFO": 1,
                "WARNING": 2,
                "ERROR": 3,
                "CRITICAL": 4
            }
            min_level = severity_order.get(severity.value, 0)
            valid_severities = [s for s, l in severity_order.items() if l >= min_level]
            self.filters.append(AuditLog.severity.in_(valid_severities))
        else:
            self.filters.append(AuditLog.severity == severity.value)
        return self

    def filter_by_resource(
        self,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None
    ) -> "AuditQueryBuilder":
        """Filter by resource type and/or ID."""
        if resource_type:
            self.filters.append(AuditLog.resource_type == resource_type)
        if resource_id:
            self.filters.append(AuditLog.resource_id == resource_id)
        return self

    def filter_by_service(self, service_name: str) -> "AuditQueryBuilder":
        """Filter by service name."""
        self.filters.append(AuditLog.service_name == service_name)
        return self

    def filter_by_endpoint(self, endpoint: str) -> "AuditQueryBuilder":
        """Filter by endpoint."""
        self.filters.append(AuditLog.endpoint == endpoint)
        return self

    def filter_by_ip(self, ip_address: str) -> "AuditQueryBuilder":
        """Filter by IP address (or its hash if encrypted)."""
        # Try both plaintext and hash
        encryption_service = create_encryption_service(
            master_key=settings.encryption_master_key,
            key_version=settings.encryption_key_version,
            salt=settings.encryption_salt,
        )
        ip_hash = encryption_service.hash_for_search(ip_address)
        self.filters.append(
            or_(
                AuditLog.ip_address == ip_address,
                AuditLog.ip_address_hash == ip_hash
            )
        )
        return self

    def filter_by_session(self, session_id: str) -> "AuditQueryBuilder":
        """Filter by session ID."""
        self.filters.append(AuditLog.session_id == session_id)
        return self

    def filter_by_trace_id(self, trace_id: str) -> "AuditQueryBuilder":
        """Filter by trace ID (for distributed tracing)."""
        self.filters.append(AuditLog.trace_id == trace_id)
        return self

    def filter_by_time_range(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> "AuditQueryBuilder":
        """Filter by time range."""
        if start_time:
            self.filters.append(AuditLog.event_timestamp >= start_time)
        if end_time:
            self.filters.append(AuditLog.event_timestamp <= end_time)
        return self

    def filter_by_last_n_days(self, days: int) -> "AuditQueryBuilder":
        """Filter by last N days."""
        start_time = datetime.now(timezone.utc) - timedelta(days=days)
        self.filters.append(AuditLog.event_timestamp >= start_time)
        return self

    def filter_archived(self, archived: bool = False) -> "AuditQueryBuilder":
        """Filter by archived status."""
        self.filters.append(AuditLog.is_archived == archived)
        return self

    def build(self) -> Select:
        """Build the query."""
        query = select(AuditLog)
        if self.filters:
            query = query.where(and_(*self.filters))
        return query.order_by(desc(AuditLog.event_timestamp))


class AuditManager:
    """
    Manager for audit log operations including querying, export, and retention.

    Features:
    - Advanced querying with filtering
    - Decryption of encrypted fields for authorized access
    - Export to JSON, CSV, JSONL formats
    - Retention policy enforcement
    - Archival and deletion
    - Compliance reporting
    """

    def __init__(self, encryption_service: Optional[EncryptionService] = None):
        """Initialize the audit manager."""
        self.encryption_service = encryption_service or create_encryption_service(
            master_key=settings.encryption_master_key,
            key_version=settings.encryption_key_version,
            salt=settings.encryption_salt,
        )

    async def query(
        self,
        session: AsyncSession,
        query_builder: Optional[AuditQueryBuilder] = None,
        limit: int = 100,
        offset: int = 0,
        decrypt: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Query audit logs with optional decryption.

        Args:
            session: Database session
            query_builder: Query builder with filters
            limit: Maximum number of results
            offset: Offset for pagination
            decrypt: Whether to decrypt encrypted fields

        Returns:
            List of audit log records as dictionaries
        """
        # Build query
        if query_builder:
            query = query_builder.build()
        else:
            query = select(AuditLog).order_by(desc(AuditLog.event_timestamp))

        # Apply pagination
        query = query.limit(limit).offset(offset)

        # Execute query
        result = await session.execute(query)
        logs = result.scalars().all()

        # Convert to dictionaries
        audit_records = []
        for log in logs:
            record = self._audit_log_to_dict(log)

            # Decrypt if requested
            if decrypt:
                record = self._decrypt_record(record)

            audit_records.append(record)

        return audit_records

    async def count(
        self,
        session: AsyncSession,
        query_builder: Optional[AuditQueryBuilder] = None
    ) -> int:
        """
        Count audit logs matching the query.

        Args:
            session: Database session
            query_builder: Query builder with filters

        Returns:
            Number of matching audit logs
        """
        # Build query
        if query_builder:
            query = query_builder.build()
        else:
            query = select(AuditLog)

        # Convert to count query
        count_query = select(func.count()).select_from(query.subquery())

        # Execute query
        result = await session.execute(count_query)
        return result.scalar() or 0

    def _audit_log_to_dict(self, log: AuditLog) -> Dict[str, Any]:
        """Convert AuditLog model to dictionary."""
        return {
            "id": log.id,
            "event_id": log.event_id,
            "event_type": log.event_type,
            "event_category": log.event_category,
            "event_action": log.event_action,
            "event_status": log.event_status,
            "severity": log.severity,
            "user_id": log.user_id,
            "username": log.username,
            "actor_type": log.actor_type,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "resource_name": log.resource_name,
            "service_name": log.service_name,
            "endpoint": log.endpoint,
            "http_method": log.http_method,
            "http_status_code": log.http_status_code,
            "ip_address": log.ip_address,
            "ip_address_encrypted": log.ip_address_encrypted,
            "ip_address_hash": log.ip_address_hash,
            "user_agent": log.user_agent,
            "user_agent_encrypted": log.user_agent_encrypted,
            "user_agent_hash": log.user_agent_hash,
            "session_id": log.session_id,
            "trace_id": log.trace_id,
            "request_id": log.request_id,
            "geo_country": log.geo_country,
            "geo_region": log.geo_region,
            "geo_city": log.geo_city,
            "request_data": log.request_data,
            "request_data_encrypted": log.request_data_encrypted,
            "response_data": log.response_data,
            "response_data_encrypted": log.response_data_encrypted,
            "changes_before": log.changes_before,
            "changes_before_encrypted": log.changes_before_encrypted,
            "changes_after": log.changes_after,
            "changes_after_encrypted": log.changes_after_encrypted,
            "error_message": log.error_message,
            "error_code": log.error_code,
            "error_stack_trace": log.error_stack_trace,
            "duration_ms": log.duration_ms,
            "authentication_method": log.authentication_method,
            "authorization_result": log.authorization_result,
            "risk_score": log.risk_score,
            "retention_period_days": log.retention_period_days,
            "is_archived": log.is_archived,
            "archived_at": log.archived_at.isoformat() if log.archived_at else None,
            "record_hash": log.record_hash,
            "encryption_key_version": log.encryption_key_version,
            "event_timestamp": log.event_timestamp.isoformat(),
            "created_at": log.created_at.isoformat(),
        }

    def _decrypt_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Decrypt encrypted fields in an audit record."""
        try:
            # Decrypt IP address
            if record.get("ip_address_encrypted"):
                record["ip_address"] = self.encryption_service.decrypt_field(
                    record["ip_address_encrypted"],
                    associated_data=record["event_id"]
                )
                del record["ip_address_encrypted"]

            # Decrypt user agent
            if record.get("user_agent_encrypted"):
                record["user_agent"] = self.encryption_service.decrypt_field(
                    record["user_agent_encrypted"],
                    associated_data=record["event_id"]
                )
                del record["user_agent_encrypted"]

            # Decrypt request data
            if record.get("request_data_encrypted"):
                decrypted_json = self.encryption_service.decrypt_field(
                    record["request_data_encrypted"],
                    associated_data=record["event_id"]
                )
                record["request_data"] = json.loads(decrypted_json)
                del record["request_data_encrypted"]

            # Decrypt response data
            if record.get("response_data_encrypted"):
                decrypted_json = self.encryption_service.decrypt_field(
                    record["response_data_encrypted"],
                    associated_data=record["event_id"]
                )
                record["response_data"] = json.loads(decrypted_json)
                del record["response_data_encrypted"]

            # Decrypt changes_before
            if record.get("changes_before_encrypted"):
                decrypted_json = self.encryption_service.decrypt_field(
                    record["changes_before_encrypted"],
                    associated_data=record["event_id"]
                )
                record["changes_before"] = json.loads(decrypted_json)
                del record["changes_before_encrypted"]

            # Decrypt changes_after
            if record.get("changes_after_encrypted"):
                decrypted_json = self.encryption_service.decrypt_field(
                    record["changes_after_encrypted"],
                    associated_data=record["event_id"]
                )
                record["changes_after"] = json.loads(decrypted_json)
                del record["changes_after_encrypted"]

        except DecryptionError as e:
            # Log decryption failure but don't fail the entire query
            record["_decryption_error"] = str(e)

        return record

    async def export(
        self,
        session: AsyncSession,
        query_builder: Optional[AuditQueryBuilder] = None,
        format: ExportFormat = ExportFormat.JSON,
        decrypt: bool = False,
        include_sensitive: bool = False
    ) -> str:
        """
        Export audit logs to specified format.

        Args:
            session: Database session
            query_builder: Query builder with filters
            format: Export format (JSON, CSV, JSONL)
            decrypt: Whether to decrypt encrypted fields
            include_sensitive: Include sensitive fields in export

        Returns:
            Exported data as string
        """
        # Query all matching records
        records = await self.query(
            session=session,
            query_builder=query_builder,
            limit=10000,  # Max export size
            decrypt=decrypt
        )

        # Remove sensitive fields if not requested
        if not include_sensitive:
            records = self._remove_sensitive_fields(records)

        # Export based on format
        if format == ExportFormat.JSON:
            return json.dumps(records, indent=2)
        elif format == ExportFormat.JSON_LINES:
            return "\n".join(json.dumps(r) for r in records)
        elif format == ExportFormat.CSV:
            return self._export_csv(records)
        else:
            raise ValueError(f"Unsupported export format: {format}")

    def _remove_sensitive_fields(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove sensitive fields from records for export."""
        sensitive_fields = [
            "ip_address", "user_agent", "request_data", "response_data",
            "changes_before", "changes_after", "error_stack_trace",
            "ip_address_encrypted", "user_agent_encrypted",
            "request_data_encrypted", "response_data_encrypted",
            "changes_before_encrypted", "changes_after_encrypted"
        ]

        cleaned_records = []
        for record in records:
            cleaned = {k: v for k, v in record.items() if k not in sensitive_fields}
            cleaned_records.append(cleaned)

        return cleaned_records

    def _export_csv(self, records: List[Dict[str, Any]]) -> str:
        """Export records to CSV format."""
        if not records:
            return ""

        # Get all unique keys from all records
        all_keys = set()
        for record in records:
            all_keys.update(record.keys())

        # Create CSV in memory
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=sorted(all_keys))
        writer.writeheader()

        for record in records:
            # Convert complex objects to JSON strings for CSV
            csv_record = {}
            for key, value in record.items():
                if isinstance(value, (dict, list)):
                    csv_record[key] = json.dumps(value)
                else:
                    csv_record[key] = value
            writer.writerow(csv_record)

        return output.getvalue()

    async def enforce_retention(self, session: AsyncSession) -> Tuple[int, int]:
        """
        Enforce retention policies by archiving and deleting old logs.

        Returns:
            Tuple of (archived_count, deleted_count)
        """
        now = datetime.now(timezone.utc)
        archived_count = 0
        deleted_count = 0

        # Archive logs that have exceeded retention period but not yet archived
        archive_cutoff = now - timedelta(days=settings.audit_retention_days)
        archive_stmt = (
            update(AuditLog)
            .where(
                and_(
                    AuditLog.is_archived == False,
                    AuditLog.created_at < archive_cutoff
                )
            )
            .values(is_archived=True, archived_at=now)
        )
        result = await session.execute(archive_stmt)
        archived_count = result.rowcount

        # Delete archived logs older than 2x retention period
        delete_cutoff = now - timedelta(days=settings.audit_retention_days * 2)
        delete_stmt = delete(AuditLog).where(
            and_(
                AuditLog.is_archived == True,
                AuditLog.archived_at < delete_cutoff
            )
        )
        result = await session.execute(delete_stmt)
        deleted_count = result.rowcount

        await session.commit()

        return archived_count, deleted_count

    async def get_statistics(
        self,
        session: AsyncSession,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get audit log statistics for the last N days.

        Args:
            session: Database session
            days: Number of days to analyze

        Returns:
            Dictionary with various statistics
        """
        start_time = datetime.now(timezone.utc) - timedelta(days=days)

        # Total events
        total_query = select(func.count()).select_from(AuditLog).where(
            AuditLog.event_timestamp >= start_time
        )
        total_result = await session.execute(total_query)
        total_events = total_result.scalar() or 0

        # Events by type
        type_query = select(
            AuditLog.event_type,
            func.count(AuditLog.id).label('count')
        ).where(
            AuditLog.event_timestamp >= start_time
        ).group_by(AuditLog.event_type)
        type_result = await session.execute(type_query)
        events_by_type = {row.event_type: row.count for row in type_result}

        # Events by status
        status_query = select(
            AuditLog.event_status,
            func.count(AuditLog.id).label('count')
        ).where(
            AuditLog.event_timestamp >= start_time
        ).group_by(AuditLog.event_status)
        status_result = await session.execute(status_query)
        events_by_status = {row.event_status: row.count for row in status_result}

        # Failed authentication attempts
        failed_auth_query = select(func.count()).select_from(AuditLog).where(
            and_(
                AuditLog.event_timestamp >= start_time,
                AuditLog.event_category == EventCategory.authentication.value,
                AuditLog.event_status == EventStatus.failure.value
            )
        )
        failed_auth_result = await session.execute(failed_auth_query)
        failed_auth_count = failed_auth_result.scalar() or 0

        # Top users by activity
        user_query = select(
            AuditLog.user_id,
            AuditLog.username,
            func.count(AuditLog.id).label('count')
        ).where(
            and_(
                AuditLog.event_timestamp >= start_time,
                AuditLog.user_id.isnot(None)
            )
        ).group_by(
            AuditLog.user_id, AuditLog.username
        ).order_by(
            desc('count')
        ).limit(10)
        user_result = await session.execute(user_query)
        top_users = [
            {"user_id": row.user_id, "username": row.username, "count": row.count}
            for row in user_result
        ]

        return {
            "period_days": days,
            "start_time": start_time.isoformat(),
            "end_time": datetime.now(timezone.utc).isoformat(),
            "total_events": total_events,
            "events_by_type": events_by_type,
            "events_by_status": events_by_status,
            "failed_authentication_attempts": failed_auth_count,
            "top_users": top_users,
        }

    async def verify_integrity(
        self,
        session: AsyncSession,
        event_id: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify the cryptographic integrity of an audit log record.

        Args:
            session: Database session
            event_id: Event ID to verify

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Get the audit log
        query = select(AuditLog).where(AuditLog.event_id == event_id)
        result = await session.execute(query)
        log = result.scalar_one_or_none()

        if not log:
            return False, "Audit log not found"

        # Recompute the hash
        from .audit import AuditLogger
        audit_logger = AuditLogger()
        audit_data = {
            "event_id": log.event_id,
            "event_type": log.event_type,
            "event_action": log.event_action,
            "user_id": log.user_id,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "event_timestamp": log.event_timestamp,
        }
        expected_hash = audit_logger._compute_record_hash(audit_data)

        # Compare hashes
        if log.record_hash == expected_hash:
            return True, None
        else:
            return False, "Hash mismatch - record may have been tampered with"
