"""
Data Retention Policy Manager

Provides high-level API for managing retention policies, schedules, and archives.
Handles policy CRUD operations, validation, conflict resolution, and compliance reporting.

Author: BIOwerk Security Team
Version: 1.0.0
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from uuid import UUID, uuid4

from sqlalchemy import select, and_, or_, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from matrix.db_models import (
    RetentionPolicy,
    RetentionSchedule,
    DataArchive,
    RetentionAuditLog,
    User,
)
from matrix.retention_policy import (
    DataType,
    RetentionAction,
    ComplianceFramework,
    RetentionPolicyEngine,
)
from matrix.audit import AuditLogger, EventType, EventCategory, EventAction, EventStatus, Severity


logger = logging.getLogger(__name__)


class RetentionPolicyManager:
    """
    Manager for retention policies and schedules.

    Provides:
    - Policy CRUD operations
    - Policy validation and conflict detection
    - Schedule management
    - Archive access and cleanup
    - Compliance reporting
    """

    def __init__(
        self,
        db_session: AsyncSession,
        audit_logger: AuditLogger,
    ):
        self.db = db_session
        self.audit = audit_logger
        self.logger = logging.getLogger(f"{__name__}.RetentionPolicyManager")

    async def create_policy(
        self,
        name: str,
        data_type: DataType,
        retention_period_days: int,
        action: RetentionAction,
        compliance_framework: ComplianceFramework,
        created_by_user_id: UUID,
        description: Optional[str] = None,
        category_filter: Optional[List[str]] = None,
        user_filter: Optional[List[str]] = None,
        conditions: Optional[Dict[str, Any]] = None,
        archive_before_delete: bool = True,
        regulatory_citation: Optional[str] = None,
        priority: int = 0,
    ) -> RetentionPolicy:
        """Create a new retention policy"""

        # Validate policy
        await self._validate_policy(
            name=name,
            data_type=data_type,
            retention_period_days=retention_period_days,
            compliance_framework=compliance_framework,
        )

        # Create policy
        policy = RetentionPolicy(
            id=uuid4(),
            name=name,
            description=description,
            data_type=data_type,
            category_filter=category_filter,
            user_filter=user_filter,
            conditions=conditions,
            retention_period_days=retention_period_days,
            action=action,
            archive_before_delete=archive_before_delete,
            compliance_framework=compliance_framework,
            regulatory_citation=regulatory_citation,
            priority=priority,
            is_active=True,
            created_by=created_by_user_id,
        )

        self.db.add(policy)
        await self.db.commit()
        await self.db.refresh(policy)

        # Log audit event
        await self.audit.log_event(
            event_type=EventType.ADMIN,
            event_category=EventCategory.DATA_RETENTION,
            event_action=EventAction.CREATE,
            event_status=EventStatus.SUCCESS,
            severity=Severity.INFO,
            resource_type="retention_policy",
            resource_id=str(policy.id),
            resource_name=policy.name,
            details={
                "data_type": data_type,
                "retention_period_days": retention_period_days,
                "action": action,
                "compliance_framework": compliance_framework,
            },
            user_id=created_by_user_id,
        )

        self.logger.info(
            f"Created retention policy '{name}' (id={policy.id}) "
            f"by user {created_by_user_id}"
        )

        return policy

    async def _validate_policy(
        self,
        name: str,
        data_type: DataType,
        retention_period_days: int,
        compliance_framework: ComplianceFramework,
        policy_id: Optional[UUID] = None,
    ) -> None:
        """Validate a retention policy"""

        # Check for name uniqueness
        stmt = select(RetentionPolicy).where(RetentionPolicy.name == name)
        if policy_id:
            stmt = stmt.where(RetentionPolicy.id != policy_id)

        result = await self.db.execute(stmt)
        if result.scalar_one_or_none():
            raise ValueError(f"Policy with name '{name}' already exists")

        # Validate retention period
        if retention_period_days < 0:
            raise ValueError("Retention period must be non-negative")

        # Check minimum retention for compliance framework
        min_retention = self._get_minimum_retention(compliance_framework, data_type)
        if retention_period_days < min_retention:
            raise ValueError(
                f"Retention period {retention_period_days} days is less than "
                f"minimum {min_retention} days required for {compliance_framework} "
                f"framework for {data_type} data"
            )

    def _get_minimum_retention(
        self,
        framework: ComplianceFramework,
        data_type: DataType,
    ) -> int:
        """Get minimum retention period for a framework and data type"""

        # Standard compliance requirements
        requirements = {
            ComplianceFramework.SOC2: {
                DataType.AUDIT_LOG: 365,  # 1 year
                DataType.USER: 90,
                DataType.EXECUTION: 90,
                DataType.API_KEY: 90,
            },
            ComplianceFramework.HIPAA: {
                DataType.AUDIT_LOG: 2555,  # 7 years
                DataType.USER: 2555,
                DataType.EXECUTION: 2555,
                DataType.PROJECT: 2555,
                DataType.ARTIFACT: 2555,
            },
            ComplianceFramework.GDPR: {
                DataType.USER: 30,  # Right to be forgotten (30 days for processing)
                DataType.AUDIT_LOG: 730,  # 2 years
                DataType.SESSION: 1,  # Minimal retention
            },
            ComplianceFramework.PCI_DSS: {
                DataType.AUDIT_LOG: 365,  # 1 year minimum, 3 years recommended
                DataType.EXECUTION: 90,
                DataType.API_KEY: 90,
            },
            ComplianceFramework.CCPA: {
                DataType.USER: 30,  # Similar to GDPR
                DataType.AUDIT_LOG: 730,  # 2 years
            },
            ComplianceFramework.ISO27001: {
                DataType.AUDIT_LOG: 365,  # 1 year
                DataType.EXECUTION: 90,
            },
        }

        return requirements.get(framework, {}).get(data_type, 0)

    async def update_policy(
        self,
        policy_id: UUID,
        updated_by_user_id: UUID,
        **updates: Any,
    ) -> RetentionPolicy:
        """Update an existing retention policy"""

        # Get policy
        stmt = select(RetentionPolicy).where(RetentionPolicy.id == policy_id)
        result = await self.db.execute(stmt)
        policy = result.scalar_one_or_none()

        if not policy:
            raise ValueError(f"Policy {policy_id} not found")

        # Track changes for audit
        changes_before = {
            "name": policy.name,
            "retention_period_days": policy.retention_period_days,
            "action": policy.action,
            "is_active": policy.is_active,
        }

        # Validate if name or retention period is being updated
        if "name" in updates or "retention_period_days" in updates:
            await self._validate_policy(
                name=updates.get("name", policy.name),
                data_type=policy.data_type,
                retention_period_days=updates.get("retention_period_days", policy.retention_period_days),
                compliance_framework=policy.compliance_framework,
                policy_id=policy_id,
            )

        # Apply updates
        for field, value in updates.items():
            if hasattr(policy, field):
                setattr(policy, field, value)

        policy.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(policy)

        # Track changes for audit
        changes_after = {
            "name": policy.name,
            "retention_period_days": policy.retention_period_days,
            "action": policy.action,
            "is_active": policy.is_active,
        }

        # Log audit event
        await self.audit.log_event(
            event_type=EventType.ADMIN,
            event_category=EventCategory.DATA_RETENTION,
            event_action=EventAction.UPDATE,
            event_status=EventStatus.SUCCESS,
            severity=Severity.INFO,
            resource_type="retention_policy",
            resource_id=str(policy.id),
            resource_name=policy.name,
            details={
                "changes": updates,
                "before": changes_before,
                "after": changes_after,
            },
            user_id=updated_by_user_id,
        )

        self.logger.info(
            f"Updated retention policy {policy_id} by user {updated_by_user_id}"
        )

        return policy

    async def delete_policy(
        self,
        policy_id: UUID,
        deleted_by_user_id: UUID,
    ) -> None:
        """Delete a retention policy"""

        # Get policy
        stmt = select(RetentionPolicy).where(RetentionPolicy.id == policy_id)
        result = await self.db.execute(stmt)
        policy = result.scalar_one_or_none()

        if not policy:
            raise ValueError(f"Policy {policy_id} not found")

        policy_name = policy.name

        # Delete policy
        await self.db.delete(policy)
        await self.db.commit()

        # Log audit event
        await self.audit.log_event(
            event_type=EventType.ADMIN,
            event_category=EventCategory.DATA_RETENTION,
            event_action=EventAction.DELETE,
            event_status=EventStatus.SUCCESS,
            severity=Severity.WARNING,
            resource_type="retention_policy",
            resource_id=str(policy_id),
            resource_name=policy_name,
            user_id=deleted_by_user_id,
        )

        self.logger.info(
            f"Deleted retention policy {policy_id} by user {deleted_by_user_id}"
        )

    async def get_policy(
        self,
        policy_id: UUID,
    ) -> Optional[RetentionPolicy]:
        """Get a retention policy by ID"""

        stmt = select(RetentionPolicy).where(RetentionPolicy.id == policy_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_policies(
        self,
        data_type: Optional[DataType] = None,
        compliance_framework: Optional[ComplianceFramework] = None,
        is_active: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[RetentionPolicy]:
        """List retention policies with optional filters"""

        stmt = select(RetentionPolicy)

        if data_type:
            stmt = stmt.where(RetentionPolicy.data_type == data_type)
        if compliance_framework:
            stmt = stmt.where(RetentionPolicy.compliance_framework == compliance_framework)
        if is_active is not None:
            stmt = stmt.where(RetentionPolicy.is_active == is_active)

        stmt = stmt.order_by(RetentionPolicy.priority.desc(), RetentionPolicy.created_at.desc())
        stmt = stmt.limit(limit).offset(offset)

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_policies_by_data_type(
        self,
        data_type: DataType,
    ) -> List[RetentionPolicy]:
        """Get all active policies for a specific data type, ordered by priority"""

        stmt = select(RetentionPolicy).where(
            and_(
                RetentionPolicy.data_type == data_type,
                RetentionPolicy.is_active == True,
            )
        ).order_by(RetentionPolicy.priority.desc())

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_schedules_for_data(
        self,
        data_type: DataType,
        data_id: UUID,
    ) -> List[RetentionSchedule]:
        """Get retention schedules for specific data"""

        stmt = select(RetentionSchedule).where(
            and_(
                RetentionSchedule.data_type == data_type,
                RetentionSchedule.data_id == str(data_id),
            )
        ).order_by(RetentionSchedule.created_at.desc())

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_pending_schedules(
        self,
        limit: int = 100,
    ) -> List[RetentionSchedule]:
        """Get pending retention schedules that are due for execution"""

        now = datetime.utcnow()

        stmt = select(RetentionSchedule).where(
            and_(
                RetentionSchedule.status == "pending",
                RetentionSchedule.scheduled_for <= now,
                RetentionSchedule.legal_hold == False,
            )
        ).order_by(RetentionSchedule.scheduled_for).limit(limit)

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_legal_holds(
        self,
        data_type: Optional[DataType] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[RetentionSchedule]:
        """Get all data under legal hold"""

        stmt = select(RetentionSchedule).where(
            RetentionSchedule.legal_hold == True
        )

        if data_type:
            stmt = stmt.where(RetentionSchedule.data_type == data_type)

        stmt = stmt.order_by(RetentionSchedule.legal_hold_applied_at.desc())
        stmt = stmt.limit(limit).offset(offset)

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_archives(
        self,
        data_type: Optional[DataType] = None,
        archive_status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[DataArchive]:
        """Get archived data with optional filters"""

        stmt = select(DataArchive)

        if data_type:
            stmt = stmt.where(DataArchive.data_type == data_type)
        if archive_status:
            stmt = stmt.where(DataArchive.archive_status == archive_status)

        stmt = stmt.order_by(DataArchive.archived_at.desc())
        stmt = stmt.limit(limit).offset(offset)

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_archive(
        self,
        archive_id: UUID,
    ) -> Optional[DataArchive]:
        """Get a specific archive by ID"""

        stmt = select(DataArchive).where(DataArchive.id == archive_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def cleanup_expired_archives(
        self,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Delete archives that have passed their expiration date"""

        now = datetime.utcnow()

        results = {
            "deleted_count": 0,
            "dry_run": dry_run,
            "deleted_archives": [],
            "errors": [],
        }

        # Find expired archives
        stmt = select(DataArchive).where(
            and_(
                DataArchive.expires_at <= now,
                DataArchive.archive_status == "completed",
            )
        )

        result = await self.db.execute(stmt)
        expired_archives = result.scalars().all()

        for archive in expired_archives:
            try:
                results["deleted_archives"].append({
                    "id": str(archive.id),
                    "data_type": archive.data_type,
                    "data_id": archive.data_id,
                    "archived_at": archive.archived_at.isoformat(),
                    "expires_at": archive.expires_at.isoformat(),
                })

                if not dry_run:
                    await self.db.delete(archive)
                    results["deleted_count"] += 1

            except Exception as e:
                error_msg = f"Error deleting archive {archive.id}: {str(e)}"
                self.logger.error(error_msg, exc_info=True)
                results["errors"].append(error_msg)

        if not dry_run:
            await self.db.commit()

        # Log audit event
        await self.audit.log_event(
            event_type=EventType.SYSTEM,
            event_category=EventCategory.DATA_RETENTION,
            event_action=EventAction.DELETE,
            event_status=EventStatus.SUCCESS,
            severity=Severity.INFO,
            resource_type="archive",
            details={
                "deleted_count": results["deleted_count"],
                "dry_run": dry_run,
            },
            user_id=None,  # System-initiated
        )

        self.logger.info(
            f"Cleaned up {results['deleted_count']} expired archives "
            f"(dry_run={dry_run})"
        )

        return results

    async def get_retention_statistics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get retention statistics for reporting"""

        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        stats = {
            "report_period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "policies": {},
            "schedules": {},
            "archives": {},
            "retention_actions": {},
            "legal_holds": 0,
        }

        # Policy statistics
        stmt = select(
            RetentionPolicy.compliance_framework,
            func.count(RetentionPolicy.id).label("count")
        ).where(
            RetentionPolicy.is_active == True
        ).group_by(RetentionPolicy.compliance_framework)

        result = await self.db.execute(stmt)
        for row in result:
            stats["policies"][row.compliance_framework] = row.count

        # Schedule statistics by status
        stmt = select(
            RetentionSchedule.status,
            func.count(RetentionSchedule.id).label("count")
        ).group_by(RetentionSchedule.status)

        result = await self.db.execute(stmt)
        for row in result:
            stats["schedules"][row.status] = row.count

        # Archive statistics by data type
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
            stats["archives"][row.data_type] = row.count

        # Retention action statistics
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
            stats["retention_actions"][row.action] = row.count

        # Legal hold count
        stmt = select(func.count(RetentionSchedule.id)).where(
            RetentionSchedule.legal_hold == True
        )
        result = await self.db.execute(stmt)
        stats["legal_holds"] = result.scalar()

        return stats

    async def detect_policy_conflicts(
        self,
    ) -> List[Dict[str, Any]]:
        """Detect conflicts between retention policies"""

        conflicts = []

        # Get all active policies grouped by data type
        stmt = select(RetentionPolicy).where(
            RetentionPolicy.is_active == True
        ).order_by(RetentionPolicy.data_type, RetentionPolicy.priority.desc())

        result = await self.db.execute(stmt)
        policies = result.scalars().all()

        # Group by data type
        policies_by_type: Dict[DataType, List[RetentionPolicy]] = {}
        for policy in policies:
            if policy.data_type not in policies_by_type:
                policies_by_type[policy.data_type] = []
            policies_by_type[policy.data_type].append(policy)

        # Check for conflicts within each data type
        for data_type, type_policies in policies_by_type.items():
            for i, policy1 in enumerate(type_policies):
                for policy2 in type_policies[i + 1:]:
                    # Check for overlapping conditions
                    if self._policies_overlap(policy1, policy2):
                        # Check for conflicting actions
                        if policy1.action != policy2.action:
                            conflicts.append({
                                "type": "action_conflict",
                                "data_type": data_type,
                                "policy1": {
                                    "id": str(policy1.id),
                                    "name": policy1.name,
                                    "action": policy1.action,
                                    "priority": policy1.priority,
                                },
                                "policy2": {
                                    "id": str(policy2.id),
                                    "name": policy2.name,
                                    "action": policy2.action,
                                    "priority": policy2.priority,
                                },
                                "message": f"Policies '{policy1.name}' and '{policy2.name}' have overlapping conditions but different actions",
                            })

                        # Check for significantly different retention periods
                        if abs(policy1.retention_period_days - policy2.retention_period_days) > 90:
                            conflicts.append({
                                "type": "retention_period_conflict",
                                "data_type": data_type,
                                "policy1": {
                                    "id": str(policy1.id),
                                    "name": policy1.name,
                                    "retention_period_days": policy1.retention_period_days,
                                    "priority": policy1.priority,
                                },
                                "policy2": {
                                    "id": str(policy2.id),
                                    "name": policy2.name,
                                    "retention_period_days": policy2.retention_period_days,
                                    "priority": policy2.priority,
                                },
                                "message": f"Policies '{policy1.name}' and '{policy2.name}' have significantly different retention periods",
                            })

        return conflicts

    def _policies_overlap(
        self,
        policy1: RetentionPolicy,
        policy2: RetentionPolicy,
    ) -> bool:
        """Check if two policies have overlapping conditions"""

        # If both have no filters, they overlap
        if (not policy1.category_filter and not policy1.user_filter and
            not policy2.category_filter and not policy2.user_filter):
            return True

        # Check category filter overlap
        if policy1.category_filter and policy2.category_filter:
            set1 = set(policy1.category_filter)
            set2 = set(policy2.category_filter)
            if set1 & set2:  # Intersection
                return True

        # Check user filter overlap
        if policy1.user_filter and policy2.user_filter:
            set1 = set(policy1.user_filter)
            set2 = set(policy2.user_filter)
            if set1 & set2:  # Intersection
                return True

        return False
