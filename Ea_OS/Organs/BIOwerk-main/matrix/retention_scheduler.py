"""
Data Retention Scheduler

Automated background jobs for enforcing data retention policies.
Provides scheduled cleanup, monitoring, and compliance checks.

Author: BIOwerk Security Team
Version: 1.0.0
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from matrix.database import get_db_session
from matrix.retention_policy import (
    RetentionPolicyEngine,
    DataType,
    ComplianceFramework,
)
from matrix.retention_manager import RetentionPolicyManager
from matrix.encryption import EncryptionService
from matrix.audit import AuditLogger, EventType, EventCategory, EventAction, EventStatus, Severity


logger = logging.getLogger(__name__)


class RetentionScheduler:
    """
    Background scheduler for automated retention policy enforcement.

    Responsibilities:
    - Periodic policy evaluation
    - Automated data archival and deletion
    - Legal hold monitoring
    - Archive cleanup
    - Compliance violation detection
    - Alerting for retention issues
    """

    def __init__(
        self,
        session_maker: async_sessionmaker,
        encryption_service: EncryptionService,
        audit_logger: AuditLogger,
        evaluation_interval_hours: int = 24,
        archive_cleanup_interval_hours: int = 168,  # Weekly
    ):
        self.session_maker = session_maker
        self.encryption = encryption_service
        self.audit = audit_logger
        self.evaluation_interval_hours = evaluation_interval_hours
        self.archive_cleanup_interval_hours = archive_cleanup_interval_hours
        self.logger = logging.getLogger(f"{__name__}.RetentionScheduler")
        self._running = False
        self._tasks = []

    async def start(self):
        """Start all scheduler tasks"""
        if self._running:
            self.logger.warning("Scheduler already running")
            return

        self._running = True
        self.logger.info("Starting retention scheduler")

        # Start scheduled tasks
        self._tasks = [
            asyncio.create_task(self._periodic_policy_evaluation()),
            asyncio.create_task(self._periodic_archive_cleanup()),
            asyncio.create_task(self._periodic_compliance_check()),
            asyncio.create_task(self._periodic_metrics_collection()),
        ]

        self.logger.info("Retention scheduler started")

    async def stop(self):
        """Stop all scheduler tasks"""
        if not self._running:
            return

        self._running = False
        self.logger.info("Stopping retention scheduler")

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks = []
        self.logger.info("Retention scheduler stopped")

    async def _periodic_policy_evaluation(self):
        """Periodically evaluate and enforce retention policies"""
        self.logger.info(
            f"Starting periodic policy evaluation "
            f"(interval: {self.evaluation_interval_hours} hours)"
        )

        while self._running:
            try:
                await self._evaluate_all_policies()
            except Exception as e:
                self.logger.error(
                    f"Error in periodic policy evaluation: {str(e)}",
                    exc_info=True
                )

            # Sleep until next evaluation
            await asyncio.sleep(self.evaluation_interval_hours * 3600)

    async def _evaluate_all_policies(self):
        """Evaluate retention policies for all data types"""
        self.logger.info("Evaluating retention policies for all data types")

        start_time = datetime.utcnow()
        total_results = {
            "start_time": start_time.isoformat(),
            "data_types_evaluated": 0,
            "total_records_archived": 0,
            "total_records_deleted": 0,
            "total_records_anonymized": 0,
            "total_errors": 0,
            "data_type_results": {},
        }

        async with self.session_maker() as session:
            engine = RetentionPolicyEngine(
                db_session=session,
                encryption_service=self.encryption,
                audit_logger=self.audit,
            )

            # Evaluate each data type
            for data_type in DataType:
                try:
                    self.logger.info(f"Evaluating retention policies for {data_type}")

                    results = await engine.evaluate_retention_policies(
                        data_type=data_type,
                        dry_run=False,
                    )

                    total_results["data_types_evaluated"] += 1
                    total_results["total_records_archived"] += results["records_to_archive"]
                    total_results["total_records_deleted"] += results["records_to_delete"]
                    total_results["total_records_anonymized"] += results["records_to_anonymize"]
                    total_results["total_errors"] += len(results["errors"])
                    total_results["data_type_results"][data_type] = results

                except Exception as e:
                    error_msg = f"Error evaluating {data_type}: {str(e)}"
                    self.logger.error(error_msg, exc_info=True)
                    total_results["total_errors"] += 1
                    total_results["data_type_results"][data_type] = {"error": error_msg}

        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        total_results["end_time"] = end_time.isoformat()
        total_results["duration_seconds"] = duration

        # Log summary
        self.logger.info(
            f"Retention policy evaluation completed in {duration:.2f}s: "
            f"Archived={total_results['total_records_archived']}, "
            f"Deleted={total_results['total_records_deleted']}, "
            f"Anonymized={total_results['total_records_anonymized']}, "
            f"Errors={total_results['total_errors']}"
        )

        # Log audit event
        await self.audit.log_event(
            event_type=EventType.SYSTEM,
            event_category=EventCategory.DATA_RETENTION,
            event_action=EventAction.EVALUATE,
            event_status=EventStatus.SUCCESS if total_results["total_errors"] == 0 else EventStatus.WARNING,
            severity=Severity.INFO,
            resource_type="retention_policies",
            details=total_results,
            user_id=None,  # System-initiated
        )

        return total_results

    async def _periodic_archive_cleanup(self):
        """Periodically clean up expired archives"""
        self.logger.info(
            f"Starting periodic archive cleanup "
            f"(interval: {self.archive_cleanup_interval_hours} hours)"
        )

        while self._running:
            try:
                await self._cleanup_expired_archives()
            except Exception as e:
                self.logger.error(
                    f"Error in periodic archive cleanup: {str(e)}",
                    exc_info=True
                )

            # Sleep until next cleanup
            await asyncio.sleep(self.archive_cleanup_interval_hours * 3600)

    async def _cleanup_expired_archives(self):
        """Clean up expired archives"""
        self.logger.info("Cleaning up expired archives")

        async with self.session_maker() as session:
            manager = RetentionPolicyManager(
                db_session=session,
                audit_logger=self.audit,
            )

            results = await manager.cleanup_expired_archives(dry_run=False)

        self.logger.info(
            f"Archive cleanup completed: "
            f"Deleted={results['deleted_count']}, "
            f"Errors={len(results['errors'])}"
        )

        return results

    async def _periodic_compliance_check(self):
        """Periodically check for compliance violations"""
        self.logger.info("Starting periodic compliance checks (interval: 24 hours)")

        while self._running:
            try:
                await self._check_compliance()
            except Exception as e:
                self.logger.error(
                    f"Error in periodic compliance check: {str(e)}",
                    exc_info=True
                )

            # Sleep until next check (daily)
            await asyncio.sleep(24 * 3600)

    async def _check_compliance(self):
        """Check for compliance violations and policy conflicts"""
        self.logger.info("Checking for compliance violations")

        violations = []

        async with self.session_maker() as session:
            manager = RetentionPolicyManager(
                db_session=session,
                audit_logger=self.audit,
            )

            # Check for policy conflicts
            conflicts = await manager.detect_policy_conflicts()
            if conflicts:
                violations.extend([
                    {
                        "type": "policy_conflict",
                        "severity": "warning",
                        "details": conflict,
                    }
                    for conflict in conflicts
                ])

            # Generate compliance reports for each framework
            engine = RetentionPolicyEngine(
                db_session=session,
                encryption_service=self.encryption,
                audit_logger=self.audit,
            )

            for framework in ComplianceFramework:
                try:
                    report = await engine.get_compliance_report(framework)

                    # Check for violations in the report
                    if report.get("compliance_violations"):
                        violations.extend([
                            {
                                "type": "compliance_violation",
                                "framework": framework,
                                "severity": "error",
                                "details": violation,
                            }
                            for violation in report["compliance_violations"]
                        ])

                except Exception as e:
                    self.logger.error(
                        f"Error generating compliance report for {framework}: {str(e)}",
                        exc_info=True
                    )

        # Log violations
        if violations:
            self.logger.warning(
                f"Found {len(violations)} compliance violations/conflicts"
            )

            # Log audit event
            await self.audit.log_event(
                event_type=EventType.SECURITY,
                event_category=EventCategory.DATA_RETENTION,
                event_action=EventAction.EVALUATE,
                event_status=EventStatus.WARNING,
                severity=Severity.WARNING,
                resource_type="compliance",
                details={
                    "violation_count": len(violations),
                    "violations": violations,
                },
                user_id=None,
            )
        else:
            self.logger.info("No compliance violations found")

        return violations

    async def _periodic_metrics_collection(self):
        """Periodically collect retention metrics"""
        self.logger.info("Starting periodic metrics collection (interval: 1 hour)")

        while self._running:
            try:
                await self._collect_metrics()
            except Exception as e:
                self.logger.error(
                    f"Error in periodic metrics collection: {str(e)}",
                    exc_info=True
                )

            # Sleep until next collection (hourly)
            await asyncio.sleep(3600)

    async def _collect_metrics(self):
        """Collect retention metrics for monitoring"""
        async with self.session_maker() as session:
            manager = RetentionPolicyManager(
                db_session=session,
                audit_logger=self.audit,
            )

            stats = await manager.get_retention_statistics()

        self.logger.debug(f"Collected retention metrics: {stats}")

        # In production, these metrics would be sent to Prometheus/monitoring system
        # For now, just log them
        return stats

    async def run_manual_evaluation(
        self,
        data_type: Optional[DataType] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Manually trigger retention policy evaluation"""
        self.logger.info(
            f"Manual retention policy evaluation triggered "
            f"(data_type={data_type}, dry_run={dry_run})"
        )

        results = {}

        async with self.session_maker() as session:
            engine = RetentionPolicyEngine(
                db_session=session,
                encryption_service=self.encryption,
                audit_logger=self.audit,
            )

            if data_type:
                # Evaluate specific data type
                results[data_type] = await engine.evaluate_retention_policies(
                    data_type=data_type,
                    dry_run=dry_run,
                )
            else:
                # Evaluate all data types
                for dt in DataType:
                    try:
                        results[dt] = await engine.evaluate_retention_policies(
                            data_type=dt,
                            dry_run=dry_run,
                        )
                    except Exception as e:
                        self.logger.error(
                            f"Error evaluating {dt}: {str(e)}",
                            exc_info=True
                        )
                        results[dt] = {"error": str(e)}

        return results

    async def run_manual_compliance_check(
        self,
        framework: Optional[ComplianceFramework] = None,
    ) -> Dict[str, Any]:
        """Manually trigger compliance check"""
        self.logger.info(f"Manual compliance check triggered (framework={framework})")

        results = {}

        async with self.session_maker() as session:
            engine = RetentionPolicyEngine(
                db_session=session,
                encryption_service=self.encryption,
                audit_logger=self.audit,
            )

            if framework:
                # Check specific framework
                results[framework] = await engine.get_compliance_report(framework)
            else:
                # Check all frameworks
                for fw in ComplianceFramework:
                    try:
                        results[fw] = await engine.get_compliance_report(fw)
                    except Exception as e:
                        self.logger.error(
                            f"Error generating report for {fw}: {str(e)}",
                            exc_info=True
                        )
                        results[fw] = {"error": str(e)}

        return results


# Global scheduler instance
_scheduler_instance: Optional[RetentionScheduler] = None


async def get_retention_scheduler(
    session_maker: async_sessionmaker,
    encryption_service: EncryptionService,
    audit_logger: AuditLogger,
) -> RetentionScheduler:
    """Get or create the global retention scheduler instance"""
    global _scheduler_instance

    if _scheduler_instance is None:
        _scheduler_instance = RetentionScheduler(
            session_maker=session_maker,
            encryption_service=encryption_service,
            audit_logger=audit_logger,
        )

    return _scheduler_instance


async def start_retention_scheduler(
    session_maker: async_sessionmaker,
    encryption_service: EncryptionService,
    audit_logger: AuditLogger,
):
    """Start the global retention scheduler"""
    scheduler = await get_retention_scheduler(
        session_maker=session_maker,
        encryption_service=encryption_service,
        audit_logger=audit_logger,
    )
    await scheduler.start()
    return scheduler


async def stop_retention_scheduler():
    """Stop the global retention scheduler"""
    global _scheduler_instance

    if _scheduler_instance:
        await _scheduler_instance.stop()
        _scheduler_instance = None
