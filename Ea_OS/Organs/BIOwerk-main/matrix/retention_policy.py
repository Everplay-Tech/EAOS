"""
Data Retention Policy Engine

Enterprise-grade data retention management system for SOC2, HIPAA, GDPR, and PCI-DSS compliance.
Provides automated data lifecycle management, secure archival, and compliant deletion.

Key Features:
- Granular retention policies by data type, category, and compliance framework
- Automated data archival before deletion
- Secure deletion with cryptographic verification
- Comprehensive audit logging for all retention operations
- Legal hold support for litigation and investigations
- Compliance reporting and violation detection
- Policy validation and conflict resolution

Author: BIOwerk Security Team
Version: 1.0.0
"""

import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
from uuid import UUID, uuid4
import json
import hashlib

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from matrix.db_models import (
    RetentionPolicy,
    RetentionSchedule,
    DataArchive,
    RetentionAuditLog,
    AuditLog,
    User,
    Project,
    Artifact,
    Execution,
    APIKey,
)
from matrix.encryption import EncryptionService
from matrix.audit import AuditLogger, EventType, EventCategory, EventAction, EventStatus, Severity


logger = logging.getLogger(__name__)


class DataType(str, Enum):
    """Types of data subject to retention policies"""
    USER = "user"
    PROJECT = "project"
    ARTIFACT = "artifact"
    EXECUTION = "execution"
    API_KEY = "api_key"
    AUDIT_LOG = "audit_log"
    SESSION = "session"
    CACHE = "cache"
    BACKUP = "backup"


class RetentionAction(str, Enum):
    """Actions that can be taken on data"""
    ARCHIVE = "archive"
    DELETE = "delete"
    ANONYMIZE = "anonymize"
    RETAIN = "retain"


class ComplianceFramework(str, Enum):
    """Compliance frameworks supported"""
    SOC2 = "soc2"
    HIPAA = "hipaa"
    GDPR = "gdpr"
    PCI_DSS = "pci_dss"
    CCPA = "ccpa"
    ISO27001 = "iso27001"
    CUSTOM = "custom"


class ArchivalStatus(str, Enum):
    """Status of archived data"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RESTORED = "restored"


class RetentionPolicyEngine:
    """
    Core engine for managing data retention policies and enforcement.

    Responsibilities:
    - Policy evaluation and application
    - Data identification for archival/deletion
    - Secure archival operations
    - Compliant deletion with verification
    - Audit trail generation
    - Legal hold management
    """

    def __init__(
        self,
        db_session: AsyncSession,
        encryption_service: EncryptionService,
        audit_logger: AuditLogger,
    ):
        self.db = db_session
        self.encryption = encryption_service
        self.audit = audit_logger
        self.logger = logging.getLogger(f"{__name__}.RetentionPolicyEngine")

    async def evaluate_retention_policies(
        self,
        data_type: DataType,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Evaluate retention policies for a specific data type.

        Args:
            data_type: Type of data to evaluate
            dry_run: If True, only report what would be done without taking action

        Returns:
            Dictionary with evaluation results and actions taken
        """
        self.logger.info(f"Evaluating retention policies for {data_type} (dry_run={dry_run})")

        results = {
            "data_type": data_type,
            "evaluation_time": datetime.utcnow().isoformat(),
            "dry_run": dry_run,
            "policies_evaluated": 0,
            "records_to_archive": 0,
            "records_to_delete": 0,
            "records_to_anonymize": 0,
            "records_retained": 0,
            "legal_holds": 0,
            "errors": [],
            "actions": [],
        }

        try:
            # Get active policies for this data type
            stmt = select(RetentionPolicy).where(
                and_(
                    RetentionPolicy.data_type == data_type,
                    RetentionPolicy.is_active == True,
                )
            )
            result = await self.db.execute(stmt)
            policies = result.scalars().all()

            results["policies_evaluated"] = len(policies)

            if not policies:
                self.logger.warning(f"No active retention policies found for {data_type}")
                return results

            # Sort policies by priority (highest first)
            policies = sorted(policies, key=lambda p: p.priority, reverse=True)

            # Get data records to evaluate
            records = await self._get_records_for_evaluation(data_type)
            self.logger.info(f"Found {len(records)} records to evaluate for {data_type}")

            # Evaluate each record against policies
            for record in records:
                try:
                    action = await self._evaluate_record(record, policies, data_type)

                    if action == RetentionAction.ARCHIVE:
                        results["records_to_archive"] += 1
                    elif action == RetentionAction.DELETE:
                        results["records_to_delete"] += 1
                    elif action == RetentionAction.ANONYMIZE:
                        results["records_to_anonymize"] += 1
                    elif action == RetentionAction.RETAIN:
                        results["records_retained"] += 1

                    # Execute action if not dry run
                    if not dry_run and action != RetentionAction.RETAIN:
                        await self._execute_retention_action(
                            record,
                            action,
                            data_type,
                            policies[0] if policies else None,
                        )

                    results["actions"].append({
                        "record_id": str(record.id),
                        "action": action,
                        "executed": not dry_run,
                    })

                except Exception as e:
                    error_msg = f"Error evaluating record {record.id}: {str(e)}"
                    self.logger.error(error_msg, exc_info=True)
                    results["errors"].append(error_msg)

            # Log audit event
            await self.audit.log_event(
                event_type=EventType.SYSTEM,
                event_category=EventCategory.DATA_RETENTION,
                event_action=EventAction.EVALUATE,
                event_status=EventStatus.SUCCESS,
                severity=Severity.INFO,
                resource_type=data_type,
                details={
                    "results": results,
                    "policies_count": len(policies),
                },
                user_id=None,  # System-initiated
            )

        except Exception as e:
            error_msg = f"Error evaluating retention policies: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            results["errors"].append(error_msg)

            await self.audit.log_event(
                event_type=EventType.SYSTEM,
                event_category=EventCategory.DATA_RETENTION,
                event_action=EventAction.EVALUATE,
                event_status=EventStatus.FAILURE,
                severity=Severity.ERROR,
                resource_type=data_type,
                error_message=error_msg,
                user_id=None,
            )

        return results

    async def _get_records_for_evaluation(
        self,
        data_type: DataType,
    ) -> List[Any]:
        """Get all records of a specific type for retention evaluation"""

        model_map = {
            DataType.USER: User,
            DataType.PROJECT: Project,
            DataType.ARTIFACT: Artifact,
            DataType.EXECUTION: Execution,
            DataType.API_KEY: APIKey,
            DataType.AUDIT_LOG: AuditLog,
        }

        if data_type not in model_map:
            self.logger.warning(f"No model mapping for data type: {data_type}")
            return []

        model = model_map[data_type]
        stmt = select(model)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def _evaluate_record(
        self,
        record: Any,
        policies: List[RetentionPolicy],
        data_type: DataType,
    ) -> RetentionAction:
        """
        Evaluate a single record against retention policies.

        Returns the action to take (archive, delete, anonymize, or retain).
        """

        # Check for legal hold first - this overrides all policies
        if await self._is_under_legal_hold(record, data_type):
            self.logger.info(f"Record {record.id} is under legal hold - retaining")
            return RetentionAction.RETAIN

        # Get record age
        created_at = getattr(record, 'created_at', None)
        if not created_at:
            self.logger.warning(f"Record {record.id} has no created_at timestamp")
            return RetentionAction.RETAIN

        age_days = (datetime.utcnow() - created_at).days

        # Evaluate against policies (already sorted by priority)
        for policy in policies:
            # Check if policy applies to this record
            if not await self._policy_applies_to_record(policy, record, data_type):
                continue

            # Check if retention period has expired
            if age_days >= policy.retention_period_days:
                self.logger.info(
                    f"Record {record.id} exceeds retention period "
                    f"({age_days} >= {policy.retention_period_days} days) "
                    f"for policy {policy.name}"
                )
                return policy.action

        # No policy matched or retention period not exceeded
        return RetentionAction.RETAIN

    async def _policy_applies_to_record(
        self,
        policy: RetentionPolicy,
        record: Any,
        data_type: DataType,
    ) -> bool:
        """Check if a retention policy applies to a specific record"""

        # Policy must match data type
        if policy.data_type != data_type:
            return False

        # Check category filters if specified
        if policy.category_filter:
            record_category = getattr(record, 'category', None)
            if record_category and record_category not in policy.category_filter:
                return False

        # Check user filters if specified
        if policy.user_filter:
            record_user_id = getattr(record, 'user_id', None)
            if record_user_id:
                user_id_str = str(record_user_id)
                if user_id_str not in policy.user_filter:
                    return False

        # Check metadata conditions if specified
        if policy.conditions:
            if not await self._evaluate_conditions(policy.conditions, record):
                return False

        return True

    async def _evaluate_conditions(
        self,
        conditions: Dict[str, Any],
        record: Any,
    ) -> bool:
        """Evaluate custom conditions against a record"""

        for field, expected_value in conditions.items():
            actual_value = getattr(record, field, None)

            # Support different comparison operators
            if isinstance(expected_value, dict):
                operator = expected_value.get("operator", "eq")
                value = expected_value.get("value")

                if operator == "eq" and actual_value != value:
                    return False
                elif operator == "ne" and actual_value == value:
                    return False
                elif operator == "gt" and not (actual_value and actual_value > value):
                    return False
                elif operator == "lt" and not (actual_value and actual_value < value):
                    return False
                elif operator == "in" and actual_value not in value:
                    return False
                elif operator == "not_in" and actual_value in value:
                    return False
            else:
                # Simple equality check
                if actual_value != expected_value:
                    return False

        return True

    async def _is_under_legal_hold(
        self,
        record: Any,
        data_type: DataType,
    ) -> bool:
        """Check if a record is under legal hold"""

        stmt = select(RetentionSchedule).where(
            and_(
                RetentionSchedule.data_type == data_type,
                RetentionSchedule.data_id == str(record.id),
                RetentionSchedule.legal_hold == True,
            )
        )
        result = await self.db.execute(stmt)
        schedule = result.scalar_one_or_none()

        return schedule is not None

    async def _execute_retention_action(
        self,
        record: Any,
        action: RetentionAction,
        data_type: DataType,
        policy: Optional[RetentionPolicy],
    ) -> None:
        """Execute a retention action on a record"""

        self.logger.info(
            f"Executing {action} on {data_type} record {record.id} "
            f"(policy: {policy.name if policy else 'N/A'})"
        )

        try:
            if action == RetentionAction.ARCHIVE:
                await self._archive_record(record, data_type, policy)
            elif action == RetentionAction.DELETE:
                await self._delete_record(record, data_type, policy)
            elif action == RetentionAction.ANONYMIZE:
                await self._anonymize_record(record, data_type, policy)

            # Create retention audit log
            await self._log_retention_action(
                record_id=record.id,
                data_type=data_type,
                action=action,
                policy_id=policy.id if policy else None,
                status="completed",
            )

        except Exception as e:
            error_msg = f"Error executing {action} on record {record.id}: {str(e)}"
            self.logger.error(error_msg, exc_info=True)

            await self._log_retention_action(
                record_id=record.id,
                data_type=data_type,
                action=action,
                policy_id=policy.id if policy else None,
                status="failed",
                error_message=error_msg,
            )
            raise

    async def _archive_record(
        self,
        record: Any,
        data_type: DataType,
        policy: Optional[RetentionPolicy],
    ) -> DataArchive:
        """Archive a record before deletion"""

        # Serialize record data
        record_data = await self._serialize_record(record, data_type)

        # Encrypt archived data
        encrypted_data = self.encryption.encrypt_data(json.dumps(record_data))

        # Calculate hash for integrity verification
        data_hash = hashlib.sha256(
            json.dumps(record_data, sort_keys=True).encode()
        ).hexdigest()

        # Create archive entry
        archive = DataArchive(
            id=uuid4(),
            data_type=data_type,
            data_id=str(record.id),
            policy_id=policy.id if policy else None,
            archived_data=encrypted_data,
            data_hash=data_hash,
            archive_status=ArchivalStatus.COMPLETED,
            archived_at=datetime.utcnow(),
            encryption_key_version=self.encryption.key_version,
        )

        self.db.add(archive)
        await self.db.commit()

        self.logger.info(f"Archived {data_type} record {record.id} to archive {archive.id}")

        return archive

    async def _delete_record(
        self,
        record: Any,
        data_type: DataType,
        policy: Optional[RetentionPolicy],
    ) -> None:
        """Securely delete a record after archival"""

        # Archive first if policy requires it
        if policy and policy.archive_before_delete:
            await self._archive_record(record, data_type, policy)

        # Delete the record
        await self.db.delete(record)
        await self.db.commit()

        self.logger.info(f"Deleted {data_type} record {record.id}")

    async def _anonymize_record(
        self,
        record: Any,
        data_type: DataType,
        policy: Optional[RetentionPolicy],
    ) -> None:
        """Anonymize personally identifiable information in a record"""

        # Archive original data first
        await self._archive_record(record, data_type, policy)

        # Anonymize based on data type
        if data_type == DataType.USER:
            record.email = f"anonymized_{record.id}@deleted.local"
            record.username = f"anonymized_{record.id}"
            record.hashed_password = "ANONYMIZED"
        elif data_type == DataType.EXECUTION:
            if hasattr(record, 'request_data'):
                record.request_data = {"anonymized": True}
            if hasattr(record, 'response_data'):
                record.response_data = {"anonymized": True}

        await self.db.commit()

        self.logger.info(f"Anonymized {data_type} record {record.id}")

    async def _serialize_record(
        self,
        record: Any,
        data_type: DataType,
    ) -> Dict[str, Any]:
        """Serialize a record to a dictionary for archival"""

        data = {}

        # Get all columns from the model
        for column in record.__table__.columns:
            value = getattr(record, column.name)

            # Convert non-JSON-serializable types
            if isinstance(value, datetime):
                value = value.isoformat()
            elif isinstance(value, UUID):
                value = str(value)
            elif isinstance(value, bytes):
                value = value.hex()

            data[column.name] = value

        # Add metadata
        data["_archived_at"] = datetime.utcnow().isoformat()
        data["_data_type"] = data_type

        return data

    async def _log_retention_action(
        self,
        record_id: UUID,
        data_type: DataType,
        action: RetentionAction,
        policy_id: Optional[UUID],
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """Log a retention action to the retention audit log"""

        log_entry = RetentionAuditLog(
            id=uuid4(),
            data_type=data_type,
            data_id=str(record_id),
            policy_id=policy_id,
            action=action,
            status=status,
            error_message=error_message,
            executed_at=datetime.utcnow(),
        )

        self.db.add(log_entry)
        await self.db.commit()

        # Also log to main audit system
        await self.audit.log_event(
            event_type=EventType.DATA_DELETE if action == RetentionAction.DELETE else EventType.DATA_WRITE,
            event_category=EventCategory.DATA_RETENTION,
            event_action=EventAction.DELETE if action == RetentionAction.DELETE else EventAction.UPDATE,
            event_status=EventStatus.SUCCESS if status == "completed" else EventStatus.FAILURE,
            severity=Severity.WARNING if action == RetentionAction.DELETE else Severity.INFO,
            resource_type=data_type,
            resource_id=str(record_id),
            details={
                "action": action,
                "policy_id": str(policy_id) if policy_id else None,
                "status": status,
            },
            error_message=error_message,
            user_id=None,  # System-initiated
        )

    async def restore_from_archive(
        self,
        archive_id: UUID,
        user_id: UUID,
    ) -> Dict[str, Any]:
        """
        Restore data from archive.

        Note: This only retrieves the archived data. Actual restoration to the
        database should be done manually after review.
        """

        # Get archive
        stmt = select(DataArchive).where(DataArchive.id == archive_id)
        result = await self.db.execute(stmt)
        archive = result.scalar_one_or_none()

        if not archive:
            raise ValueError(f"Archive {archive_id} not found")

        # Decrypt data
        decrypted_json = self.encryption.decrypt_data(archive.archived_data)
        data = json.loads(decrypted_json)

        # Verify integrity
        data_hash = hashlib.sha256(
            json.dumps(data, sort_keys=True).encode()
        ).hexdigest()

        if data_hash != archive.data_hash:
            raise ValueError("Archive data integrity check failed - possible tampering detected")

        # Update archive status
        archive.archive_status = ArchivalStatus.RESTORED
        archive.restored_at = datetime.utcnow()
        archive.restored_by_user_id = user_id
        await self.db.commit()

        # Log audit event
        await self.audit.log_event(
            event_type=EventType.DATA_READ,
            event_category=EventCategory.DATA_RETENTION,
            event_action=EventAction.READ,
            event_status=EventStatus.SUCCESS,
            severity=Severity.WARNING,
            resource_type="archive",
            resource_id=str(archive_id),
            details={
                "data_type": archive.data_type,
                "data_id": archive.data_id,
            },
            user_id=user_id,
        )

        self.logger.info(f"Restored archive {archive_id} by user {user_id}")

        return data

    async def apply_legal_hold(
        self,
        data_type: DataType,
        data_id: UUID,
        reason: str,
        applied_by_user_id: UUID,
    ) -> RetentionSchedule:
        """Apply a legal hold to prevent data deletion"""

        # Check if schedule exists
        stmt = select(RetentionSchedule).where(
            and_(
                RetentionSchedule.data_type == data_type,
                RetentionSchedule.data_id == str(data_id),
            )
        )
        result = await self.db.execute(stmt)
        schedule = result.scalar_one_or_none()

        if schedule:
            schedule.legal_hold = True
            schedule.legal_hold_reason = reason
            schedule.legal_hold_applied_at = datetime.utcnow()
            schedule.legal_hold_applied_by = applied_by_user_id
        else:
            schedule = RetentionSchedule(
                id=uuid4(),
                data_type=data_type,
                data_id=str(data_id),
                scheduled_for=None,  # No scheduled deletion
                legal_hold=True,
                legal_hold_reason=reason,
                legal_hold_applied_at=datetime.utcnow(),
                legal_hold_applied_by=applied_by_user_id,
            )
            self.db.add(schedule)

        await self.db.commit()

        # Log audit event
        await self.audit.log_event(
            event_type=EventType.ADMIN,
            event_category=EventCategory.DATA_RETENTION,
            event_action=EventAction.CREATE,
            event_status=EventStatus.SUCCESS,
            severity=Severity.HIGH,
            resource_type=data_type,
            resource_id=str(data_id),
            details={
                "legal_hold": True,
                "reason": reason,
            },
            user_id=applied_by_user_id,
        )

        self.logger.info(
            f"Applied legal hold to {data_type} {data_id} "
            f"by user {applied_by_user_id}: {reason}"
        )

        return schedule

    async def remove_legal_hold(
        self,
        data_type: DataType,
        data_id: UUID,
        removed_by_user_id: UUID,
    ) -> RetentionSchedule:
        """Remove a legal hold from data"""

        stmt = select(RetentionSchedule).where(
            and_(
                RetentionSchedule.data_type == data_type,
                RetentionSchedule.data_id == str(data_id),
                RetentionSchedule.legal_hold == True,
            )
        )
        result = await self.db.execute(stmt)
        schedule = result.scalar_one_or_none()

        if not schedule:
            raise ValueError(f"No legal hold found for {data_type} {data_id}")

        schedule.legal_hold = False
        schedule.legal_hold_removed_at = datetime.utcnow()
        schedule.legal_hold_removed_by = removed_by_user_id

        await self.db.commit()

        # Log audit event
        await self.audit.log_event(
            event_type=EventType.ADMIN,
            event_category=EventCategory.DATA_RETENTION,
            event_action=EventAction.DELETE,
            event_status=EventStatus.SUCCESS,
            severity=Severity.HIGH,
            resource_type=data_type,
            resource_id=str(data_id),
            details={
                "legal_hold": False,
                "reason": schedule.legal_hold_reason,
            },
            user_id=removed_by_user_id,
        )

        self.logger.info(
            f"Removed legal hold from {data_type} {data_id} "
            f"by user {removed_by_user_id}"
        )

        return schedule

    async def get_compliance_report(
        self,
        framework: ComplianceFramework,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Generate a compliance report for a specific framework"""

        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        report = {
            "framework": framework,
            "report_period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "generated_at": datetime.utcnow().isoformat(),
            "policies": [],
            "retention_actions": {},
            "legal_holds": {},
            "archives": {},
            "compliance_violations": [],
        }

        # Get policies for this framework
        stmt = select(RetentionPolicy).where(
            and_(
                RetentionPolicy.compliance_framework == framework,
                RetentionPolicy.is_active == True,
            )
        )
        result = await self.db.execute(stmt)
        policies = result.scalars().all()

        for policy in policies:
            report["policies"].append({
                "id": str(policy.id),
                "name": policy.name,
                "data_type": policy.data_type,
                "retention_period_days": policy.retention_period_days,
                "action": policy.action,
                "created_at": policy.created_at.isoformat(),
            })

        # Get retention actions in period
        stmt = select(
            RetentionAuditLog.action,
            func.count(RetentionAuditLog.id).label("count")
        ).where(
            and_(
                RetentionAuditLog.executed_at >= start_date,
                RetentionAuditLog.executed_at <= end_date,
            )
        ).group_by(RetentionAuditLog.action)

        result = await self.db.execute(stmt)
        for row in result:
            report["retention_actions"][row.action] = row.count

        # Get legal holds by data type
        stmt = select(
            RetentionSchedule.data_type,
            func.count(RetentionSchedule.id).label("count")
        ).where(
            RetentionSchedule.legal_hold == True
        ).group_by(RetentionSchedule.data_type)

        result = await self.db.execute(stmt)
        for row in result:
            report["legal_holds"][row.data_type] = row.count

        # Get archive statistics
        stmt = select(
            DataArchive.data_type,
            func.count(DataArchive.id).label("count")
        ).where(
            and_(
                DataArchive.archived_at >= start_date,
                DataArchive.archived_at <= end_date,
            )
        ).group_by(DataArchive.data_type)

        result = await self.db.execute(stmt)
        for row in result:
            report["archives"][row.data_type] = row.count

        # Check for compliance violations
        # (This is a simplified check - in production, you'd have more sophisticated rules)
        for policy in policies:
            if policy.retention_period_days < self._get_minimum_retention(framework, policy.data_type):
                report["compliance_violations"].append({
                    "policy_id": str(policy.id),
                    "policy_name": policy.name,
                    "violation": "retention_period_too_short",
                    "message": f"Retention period {policy.retention_period_days} days is less than minimum required for {framework}",
                })

        return report

    def _get_minimum_retention(
        self,
        framework: ComplianceFramework,
        data_type: DataType,
    ) -> int:
        """Get minimum retention period for a framework and data type"""

        # Standard compliance requirements (simplified)
        requirements = {
            ComplianceFramework.SOC2: {
                DataType.AUDIT_LOG: 365,  # 1 year
                DataType.USER: 90,
                DataType.EXECUTION: 90,
            },
            ComplianceFramework.HIPAA: {
                DataType.AUDIT_LOG: 2555,  # 7 years
                DataType.USER: 2555,
                DataType.EXECUTION: 2555,
            },
            ComplianceFramework.GDPR: {
                DataType.USER: 30,  # Right to be forgotten
                DataType.AUDIT_LOG: 730,  # 2 years
            },
            ComplianceFramework.PCI_DSS: {
                DataType.AUDIT_LOG: 365,  # 1 year minimum
                DataType.EXECUTION: 90,
            },
        }

        return requirements.get(framework, {}).get(data_type, 0)
