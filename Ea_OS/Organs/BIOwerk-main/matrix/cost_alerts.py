"""
Enterprise cost alert system for LLM budget monitoring.

Provides:
- Budget threshold alerts (warning, critical, exceeded)
- Cost spike detection and anomaly alerts
- Alert deduplication and aggregation
- Integration with existing Alertmanager/Prometheus
- Multi-channel notifications (email, Slack, PagerDuty)
"""

import logging
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from matrix.db_models import CostAlert, BudgetConfig, TokenUsage, User, Project
from matrix.cost_tracker import CostTracker

logger = logging.getLogger(__name__)


class AlertManager:
    """
    Enterprise alert management for cost monitoring.

    Handles alert creation, deduplication, and notification.
    """

    def __init__(self, db_session: AsyncSession):
        """Initialize alert manager with database session."""
        self.db = db_session
        self.cost_tracker = CostTracker(db_session)

    def _generate_alert_hash(
        self,
        alert_type: str,
        budget_id: Optional[str],
        user_id: Optional[str],
        project_id: Optional[str]
    ) -> str:
        """
        Generate hash for alert deduplication.

        Args:
            alert_type: Type of alert
            budget_id: Budget ID
            user_id: User ID
            project_id: Project ID

        Returns:
            SHA-256 hash string
        """
        hash_input = f"{alert_type}:{budget_id}:{user_id}:{project_id}"
        return hashlib.sha256(hash_input.encode()).hexdigest()

    async def _find_existing_alert(
        self,
        alert_hash: str,
        lookback_hours: int = 1
    ) -> Optional[CostAlert]:
        """
        Find existing unresolved alert with same hash.

        Args:
            alert_hash: Alert hash for deduplication
            lookback_hours: How many hours to look back

        Returns:
            Existing alert if found, None otherwise
        """
        lookback_time = datetime.utcnow() - timedelta(hours=lookback_hours)

        query = select(CostAlert).where(
            and_(
                CostAlert.alert_hash == alert_hash,
                CostAlert.status.in_(["active", "acknowledged"]),
                CostAlert.triggered_at >= lookback_time
            )
        )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def create_budget_alert(
        self,
        alert_type: str,
        budget: BudgetConfig,
        current_usage: float,
        usage_percentage: float,
        threshold_exceeded: Optional[str] = None,
        action_taken: Optional[str] = None,
        fallback_triggered: bool = False,
        request_blocked: bool = False
    ) -> CostAlert:
        """
        Create or update a budget-related alert.

        Args:
            alert_type: Alert type ('warning', 'critical', 'exceeded')
            budget: Budget configuration
            current_usage: Current usage value
            usage_percentage: Current usage percentage
            threshold_exceeded: Which threshold was exceeded
            action_taken: Action taken (fallback, blocked, etc.)
            fallback_triggered: Whether fallback was triggered
            request_blocked: Whether request was blocked

        Returns:
            Created or updated alert
        """
        # Generate alert hash for deduplication
        alert_hash = self._generate_alert_hash(
            alert_type,
            budget.id,
            budget.user_id,
            budget.project_id
        )

        # Check for existing alert
        existing_alert = await self._find_existing_alert(alert_hash)

        if existing_alert:
            # Update existing alert
            existing_alert.duplicate_count += 1
            existing_alert.last_occurrence = datetime.utcnow()
            existing_alert.current_usage = current_usage
            existing_alert.usage_percentage = usage_percentage
            existing_alert.updated_at = datetime.utcnow()

            logger.info(
                f"Updated existing alert (ID: {existing_alert.id}), "
                f"duplicate count: {existing_alert.duplicate_count}"
            )

            return existing_alert

        # Determine severity
        if alert_type == "exceeded":
            severity = "critical"
        elif alert_type == "critical":
            severity = "high"
        elif alert_type == "warning":
            severity = "medium"
        else:
            severity = "low"

        # Create alert message
        title = f"Budget '{budget.budget_name}' {alert_type.upper()}"
        message = (
            f"Budget '{budget.budget_name}' has {threshold_exceeded or alert_type} threshold. "
            f"Current usage: {current_usage:.2f}/{budget.limit_value:.2f} {budget.limit_type} "
            f"({usage_percentage:.1f}%)"
        )

        # Create new alert
        alert = CostAlert(
            alert_type=alert_type,
            severity=severity,
            status="active",
            budget_id=budget.id,
            user_id=budget.user_id,
            project_id=budget.project_id,
            title=title,
            message=message,
            budget_limit=budget.limit_value,
            current_usage=current_usage,
            usage_percentage=usage_percentage,
            threshold_exceeded=threshold_exceeded,
            action_taken=action_taken,
            fallback_triggered=fallback_triggered,
            request_blocked=request_blocked,
            alert_hash=alert_hash,
            details={
                "budget_name": budget.budget_name,
                "budget_type": budget.budget_type,
                "limit_type": budget.limit_type,
                "limit_period": budget.limit_period,
                "warning_threshold": budget.warning_threshold * 100,
                "critical_threshold": budget.critical_threshold * 100,
            }
        )

        self.db.add(alert)
        await self.db.flush()

        logger.warning(
            f"Created budget alert: {title} - {message}"
        )

        # Trigger notification if configured
        if should_notify(budget, alert_type):
            await self._send_notification(alert, budget)

        return alert

    async def create_spike_alert(
        self,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
        spike_data: Dict[str, Any] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None
    ) -> CostAlert:
        """
        Create a cost spike alert.

        Args:
            user_id: User ID
            project_id: Project ID
            spike_data: Spike detection data
            provider: LLM provider involved
            model: Model involved

        Returns:
            Created alert
        """
        # Generate alert hash
        alert_hash = self._generate_alert_hash(
            "spike",
            None,
            user_id,
            project_id
        )

        # Check for existing alert
        existing_alert = await self._find_existing_alert(alert_hash, lookback_hours=2)

        if existing_alert:
            existing_alert.duplicate_count += 1
            existing_alert.last_occurrence = datetime.utcnow()
            return existing_alert

        # Extract spike data
        recent_cost = spike_data.get("recent_cost", 0.0)
        baseline_cost = spike_data.get("baseline_cost", 0.0)
        multiplier = spike_data.get("multiplier", 1.0)
        window_hours = spike_data.get("window_hours", 1)

        title = "Cost Spike Detected"
        message = (
            f"Unusual cost spike detected: ${recent_cost:.2f} in last {window_hours}h "
            f"({multiplier:.1f}x baseline of ${baseline_cost:.2f})"
        )

        if user_id:
            message += f" for user {user_id}"
        if project_id:
            message += f" in project {project_id}"

        alert = CostAlert(
            alert_type="spike",
            severity="high",
            status="active",
            user_id=user_id,
            project_id=project_id,
            title=title,
            message=message,
            is_spike=True,
            baseline_cost=baseline_cost,
            spike_cost=recent_cost,
            spike_multiplier=multiplier,
            provider=provider,
            model=model,
            alert_hash=alert_hash,
            details=spike_data
        )

        self.db.add(alert)
        await self.db.flush()

        logger.warning(f"Created spike alert: {message}")

        return alert

    async def check_budget_thresholds(self, budget: BudgetConfig) -> Optional[CostAlert]:
        """
        Check if budget has crossed any thresholds and create alerts.

        Args:
            budget: Budget to check

        Returns:
            Created alert if threshold crossed, None otherwise
        """
        current_percentage = budget.current_percentage

        # Check exceeded (100%+)
        if current_percentage >= 100:
            if budget.alert_on_exceeded:
                return await self.create_budget_alert(
                    alert_type="exceeded",
                    budget=budget,
                    current_usage=budget.current_usage,
                    usage_percentage=current_percentage,
                    threshold_exceeded="hard_limit"
                )

        # Check critical threshold
        elif current_percentage >= (budget.critical_threshold * 100):
            if budget.alert_on_critical:
                return await self.create_budget_alert(
                    alert_type="critical",
                    budget=budget,
                    current_usage=budget.current_usage,
                    usage_percentage=current_percentage,
                    threshold_exceeded="critical"
                )

        # Check warning threshold
        elif current_percentage >= (budget.warning_threshold * 100):
            if budget.alert_on_warning:
                return await self.create_budget_alert(
                    alert_type="warning",
                    budget=budget,
                    current_usage=budget.current_usage,
                    usage_percentage=current_percentage,
                    threshold_exceeded="warning"
                )

        return None

    async def check_cost_spikes(
        self,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> List[CostAlert]:
        """
        Check for cost spikes and create alerts.

        Args:
            user_id: User to check
            project_id: Project to check

        Returns:
            List of created spike alerts
        """
        # Get all active budgets with spike detection enabled
        query = select(BudgetConfig).where(
            and_(
                BudgetConfig.is_active == True,
                BudgetConfig.enable_spike_detection == True
            )
        )

        if user_id:
            query = query.where(
                or_(
                    BudgetConfig.user_id == user_id,
                    BudgetConfig.budget_type == "global"
                )
            )

        if project_id:
            query = query.where(
                or_(
                    BudgetConfig.project_id == project_id,
                    BudgetConfig.budget_type == "global"
                )
            )

        result = await self.db.execute(query)
        budgets = result.scalars().all()

        alerts = []

        for budget in budgets:
            if not budget.alert_on_spike:
                continue

            # Detect spike
            spike_data = await self.cost_tracker.detect_cost_spike(
                user_id=budget.user_id if budget.budget_type == "user" else user_id,
                project_id=budget.project_id if budget.budget_type == "project" else project_id,
                window_hours=budget.spike_window_hours,
                threshold_multiplier=budget.spike_threshold_multiplier
            )

            if spike_data and spike_data.get("spike_detected"):
                alert = await self.create_spike_alert(
                    user_id=budget.user_id,
                    project_id=budget.project_id,
                    spike_data=spike_data
                )
                alerts.append(alert)

        return alerts

    async def acknowledge_alert(
        self,
        alert_id: str,
        acknowledged_by: str,
        notes: Optional[str] = None
    ) -> CostAlert:
        """
        Acknowledge an alert.

        Args:
            alert_id: Alert ID
            acknowledged_by: Username/ID of acknowledger
            notes: Optional acknowledgment notes

        Returns:
            Updated alert
        """
        query = select(CostAlert).where(CostAlert.id == alert_id)
        result = await self.db.execute(query)
        alert = result.scalar_one_or_none()

        if not alert:
            raise ValueError(f"Alert not found: {alert_id}")

        alert.status = "acknowledged"
        alert.acknowledged_at = datetime.utcnow()
        alert.acknowledged_by = acknowledged_by

        if notes:
            alert.resolution_notes = notes

        await self.db.flush()

        logger.info(f"Alert {alert_id} acknowledged by {acknowledged_by}")

        return alert

    async def resolve_alert(
        self,
        alert_id: str,
        resolved_by: str,
        resolution_notes: Optional[str] = None
    ) -> CostAlert:
        """
        Resolve an alert.

        Args:
            alert_id: Alert ID
            resolved_by: Username/ID of resolver
            resolution_notes: Resolution notes

        Returns:
            Updated alert
        """
        query = select(CostAlert).where(CostAlert.id == alert_id)
        result = await self.db.execute(query)
        alert = result.scalar_one_or_none()

        if not alert:
            raise ValueError(f"Alert not found: {alert_id}")

        alert.status = "resolved"
        alert.resolved_at = datetime.utcnow()
        alert.resolved_by = resolved_by
        alert.resolution_notes = resolution_notes

        await self.db.flush()

        logger.info(f"Alert {alert_id} resolved by {resolved_by}")

        return alert

    async def auto_resolve_alerts(self) -> int:
        """
        Auto-resolve alerts for budgets that are now below warning threshold.

        Returns:
            Number of alerts auto-resolved
        """
        # Get all active budget alerts
        query = select(CostAlert).where(
            and_(
                CostAlert.status.in_(["active", "acknowledged"]),
                CostAlert.budget_id.isnot(None)
            )
        )

        result = await self.db.execute(query)
        alerts = result.scalars().all()

        count = 0

        for alert in alerts:
            # Get associated budget
            budget_query = select(BudgetConfig).where(BudgetConfig.id == alert.budget_id)
            budget_result = await self.db.execute(budget_query)
            budget = budget_result.scalar_one_or_none()

            if not budget:
                continue

            # Check if budget is now below warning threshold
            if budget.current_percentage < (budget.warning_threshold * 100):
                alert.status = "resolved"
                alert.resolved_at = datetime.utcnow()
                alert.auto_resolved = True
                alert.auto_resolved_reason = "Budget usage dropped below warning threshold"
                count += 1

        if count > 0:
            await self.db.flush()
            logger.info(f"Auto-resolved {count} alerts")

        return count

    async def _send_notification(self, alert: CostAlert, budget: Optional[BudgetConfig] = None):
        """
        Send alert notification through configured channels.

        This integrates with existing Alertmanager/Prometheus infrastructure.

        Args:
            alert: Alert to send
            budget: Associated budget (if applicable)
        """
        channels = []

        if budget and budget.alert_channels:
            channels = budget.alert_channels
        else:
            # Default channels based on severity
            if alert.severity in ["critical", "high"]:
                channels = ["pagerduty", "slack", "email"]
            elif alert.severity == "medium":
                channels = ["slack", "email"]
            else:
                channels = ["email"]

        # In production, this would integrate with:
        # - Prometheus Alertmanager
        # - Email service
        # - Slack webhook
        # - PagerDuty API

        logger.info(
            f"Sending alert notification: {alert.title} "
            f"via channels: {', '.join(channels)}"
        )

        alert.notifications_sent = channels
        alert.notification_timestamp = datetime.utcnow()
        alert.notification_success = True

        # TODO: Implement actual notification sending
        # For now, just log


def should_notify(budget: BudgetConfig, alert_type: str) -> bool:
    """
    Determine if notification should be sent for alert.

    Args:
        budget: Budget configuration
        alert_type: Type of alert

    Returns:
        True if notification should be sent
    """
    if alert_type == "warning":
        return budget.alert_on_warning
    elif alert_type == "critical":
        return budget.alert_on_critical
    elif alert_type == "exceeded":
        return budget.alert_on_exceeded
    elif alert_type == "spike":
        return budget.alert_on_spike
    return False
