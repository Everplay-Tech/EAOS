"""
Enterprise budget enforcement service for LLM token usage.

Provides:
- Pre-request budget validation
- Automatic model fallback when approaching limits
- Hard limit enforcement
- Budget reset scheduling
- Real-time budget tracking
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from dateutil.relativedelta import relativedelta

from matrix.db_models import BudgetConfig, TokenUsage, User, Project
from matrix.cost_tracker import LLMPricing
from matrix.errors import BudgetExceededError, BudgetWarning

logger = logging.getLogger(__name__)


class BudgetExceededError(Exception):
    """Raised when a budget hard limit is exceeded."""
    def __init__(self, message: str, budget: BudgetConfig, current_usage: float):
        self.message = message
        self.budget = budget
        self.current_usage = current_usage
        super().__init__(message)


class BudgetWarning(Warning):
    """Warning raised when approaching budget limits."""
    pass


class BudgetEnforcer:
    """
    Enterprise budget enforcement service.

    Validates requests against budgets, enforces limits, and triggers fallbacks.
    """

    def __init__(self, db_session: AsyncSession):
        """Initialize budget enforcer with database session."""
        self.db = db_session
        self.pricing = LLMPricing()

    async def get_active_budgets(
        self,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
        service_name: Optional[str] = None
    ) -> list[BudgetConfig]:
        """
        Get all active and enforced budgets for a given context.

        Args:
            user_id: User ID
            project_id: Project ID
            service_name: Service name

        Returns:
            List of applicable budget configurations
        """
        conditions = [
            BudgetConfig.is_active == True,
            BudgetConfig.is_enforced == True,
            or_(
                BudgetConfig.suspended_until == None,
                BudgetConfig.suspended_until < datetime.utcnow()
            )
        ]

        # Build query for all applicable budgets
        budget_conditions = []

        # User-level budgets
        if user_id:
            budget_conditions.append(
                and_(
                    BudgetConfig.budget_type == "user",
                    BudgetConfig.user_id == user_id
                )
            )

        # Project-level budgets
        if project_id:
            budget_conditions.append(
                and_(
                    BudgetConfig.budget_type == "project",
                    BudgetConfig.project_id == project_id
                )
            )

        # Service-level budgets
        if service_name:
            budget_conditions.append(
                and_(
                    BudgetConfig.budget_type == "service",
                    BudgetConfig.scope_id == service_name
                )
            )

        # Global budgets
        budget_conditions.append(BudgetConfig.budget_type == "global")

        if budget_conditions:
            conditions.append(or_(*budget_conditions))

        query = select(BudgetConfig).where(and_(*conditions))
        result = await self.db.execute(query)
        budgets = result.scalars().all()

        return list(budgets)

    async def _calculate_period_usage(
        self,
        budget: BudgetConfig,
        now: Optional[datetime] = None
    ) -> float:
        """
        Calculate current usage for a budget period.

        Args:
            budget: Budget configuration
            now: Current time (default: utcnow)

        Returns:
            Current usage value (cost or tokens)
        """
        if now is None:
            now = datetime.utcnow()

        # Determine period start based on limit_period
        if budget.limit_period == "hourly":
            period_start = now.replace(minute=0, second=0, microsecond=0)
        elif budget.limit_period == "daily":
            period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif budget.limit_period == "weekly":
            # Start of week (Monday)
            days_since_monday = now.weekday()
            period_start = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif budget.limit_period == "monthly":
            period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif budget.limit_period == "total":
            period_start = budget.created_at
        else:
            logger.warning(f"Unknown limit_period: {budget.limit_period}, using daily")
            period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Build query conditions based on budget type
        conditions = [
            TokenUsage.date >= period_start,
            TokenUsage.success == True
        ]

        if budget.budget_type == "user" and budget.user_id:
            conditions.append(TokenUsage.user_id == budget.user_id)
        elif budget.budget_type == "project" and budget.project_id:
            conditions.append(TokenUsage.project_id == budget.project_id)
        elif budget.budget_type == "service" and budget.scope_id:
            conditions.append(TokenUsage.service_name == budget.scope_id)
        # Global budget has no additional filters

        # Aggregate based on limit_type
        if budget.limit_type == "cost":
            aggregate_field = func.sum(TokenUsage.total_cost)
        else:  # tokens
            aggregate_field = func.sum(TokenUsage.total_tokens)

        query = select(aggregate_field).where(and_(*conditions))
        result = await self.db.execute(query)
        usage = result.scalar() or 0.0

        return float(usage)

    async def update_budget_usage(self, budget: BudgetConfig) -> BudgetConfig:
        """
        Update cached usage and percentage for a budget.

        Args:
            budget: Budget configuration to update

        Returns:
            Updated budget configuration
        """
        current_usage = await self._calculate_period_usage(budget)
        current_percentage = (current_usage / budget.limit_value * 100) if budget.limit_value > 0 else 0

        budget.current_usage = current_usage
        budget.current_percentage = current_percentage

        await self.db.flush()

        return budget

    async def check_budget(
        self,
        provider: str,
        model: str,
        estimated_input_tokens: int,
        estimated_output_tokens: int,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
        service_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Check if request is within budget limits.

        Args:
            provider: LLM provider
            model: Model name
            estimated_input_tokens: Estimated input tokens
            estimated_output_tokens: Estimated output tokens
            user_id: User ID
            project_id: Project ID
            service_name: Service name

        Returns:
            Dict with:
            - allowed: bool - Whether request is allowed
            - fallback_required: bool - Whether fallback should be used
            - fallback_provider: str - Fallback provider (if applicable)
            - fallback_model: str - Fallback model (if applicable)
            - budget_exceeded: bool - Whether any budget is exceeded
            - budgets: List of budget status dicts
            - warnings: List of warning messages
        """
        # Get all applicable budgets
        budgets = await self.get_active_budgets(user_id, project_id, service_name)

        if not budgets:
            # No budgets configured, allow request
            return {
                "allowed": True,
                "fallback_required": False,
                "budget_exceeded": False,
                "budgets": [],
                "warnings": []
            }

        # Estimate cost of this request
        estimated_cost = self.pricing.estimate_cost(
            provider, model, estimated_input_tokens, estimated_output_tokens
        )
        estimated_tokens = estimated_input_tokens + estimated_output_tokens

        result = {
            "allowed": True,
            "fallback_required": False,
            "fallback_provider": None,
            "fallback_model": None,
            "budget_exceeded": False,
            "budgets": [],
            "warnings": []
        }

        # Check each budget
        for budget in budgets:
            # Update current usage
            await self.update_budget_usage(budget)

            # Determine estimated usage for this request
            if budget.limit_type == "cost":
                request_usage = estimated_cost
            else:  # tokens
                request_usage = estimated_tokens

            # Calculate what usage would be after this request
            projected_usage = budget.current_usage + request_usage
            projected_percentage = (projected_usage / budget.limit_value * 100) if budget.limit_value > 0 else 0

            # Check if provider/model is allowed
            if budget.blocked_providers and provider.lower() in [p.lower() for p in budget.blocked_providers]:
                result["allowed"] = False
                result["budget_exceeded"] = True
                result["warnings"].append(f"Provider '{provider}' is blocked by budget '{budget.budget_name}'")
                continue

            if budget.blocked_models and model in budget.blocked_models:
                result["allowed"] = False
                result["budget_exceeded"] = True
                result["warnings"].append(f"Model '{model}' is blocked by budget '{budget.budget_name}'")
                continue

            if budget.allowed_providers and provider.lower() not in [p.lower() for p in budget.allowed_providers]:
                result["allowed"] = False
                result["budget_exceeded"] = True
                result["warnings"].append(f"Provider '{provider}' not in allowed list for budget '{budget.budget_name}'")
                continue

            if budget.allowed_models and model not in budget.allowed_models:
                result["allowed"] = False
                result["budget_exceeded"] = True
                result["warnings"].append(f"Model '{model}' not in allowed list for budget '{budget.budget_name}'")
                continue

            # Check per-request maximum
            if budget.max_cost_per_request and estimated_cost > budget.max_cost_per_request:
                result["allowed"] = False
                result["budget_exceeded"] = True
                result["warnings"].append(
                    f"Request cost (${estimated_cost:.4f}) exceeds per-request limit "
                    f"(${budget.max_cost_per_request:.4f}) for budget '{budget.budget_name}'"
                )
                continue

            # Check if hard limit would be exceeded
            if projected_usage > budget.limit_value:
                if budget.hard_limit_enabled:
                    if budget.block_on_exceeded:
                        # Completely block request
                        result["allowed"] = False
                        result["budget_exceeded"] = True
                        result["warnings"].append(
                            f"Budget '{budget.budget_name}' hard limit exceeded: "
                            f"{projected_usage:.2f}/{budget.limit_value:.2f} {budget.limit_type}"
                        )
                    elif budget.enable_fallback and budget.fallback_provider:
                        # Use fallback model
                        result["fallback_required"] = True
                        result["fallback_provider"] = budget.fallback_provider
                        result["fallback_model"] = budget.fallback_model
                        result["warnings"].append(
                            f"Budget '{budget.budget_name}' limit exceeded, using fallback model"
                        )
                else:
                    # Soft limit - allow but warn
                    result["warnings"].append(
                        f"Budget '{budget.budget_name}' soft limit exceeded (continuing): "
                        f"{projected_usage:.2f}/{budget.limit_value:.2f} {budget.limit_type}"
                    )

            # Check fallback threshold
            elif projected_percentage >= (budget.fallback_threshold * 100):
                if budget.enable_fallback and budget.fallback_provider:
                    result["fallback_required"] = True
                    result["fallback_provider"] = budget.fallback_provider
                    result["fallback_model"] = budget.fallback_model
                    result["warnings"].append(
                        f"Budget '{budget.budget_name}' fallback threshold reached: {projected_percentage:.1f}%"
                    )

            # Check warning threshold
            elif projected_percentage >= (budget.warning_threshold * 100):
                result["warnings"].append(
                    f"Budget '{budget.budget_name}' warning threshold: {projected_percentage:.1f}% used"
                )

            # Add budget status
            result["budgets"].append({
                "budget_id": budget.id,
                "budget_name": budget.budget_name,
                "budget_type": budget.budget_type,
                "limit_type": budget.limit_type,
                "limit_period": budget.limit_period,
                "limit_value": budget.limit_value,
                "current_usage": budget.current_usage,
                "current_percentage": budget.current_percentage,
                "projected_usage": projected_usage,
                "projected_percentage": projected_percentage,
                "warning_threshold": budget.warning_threshold * 100,
                "critical_threshold": budget.critical_threshold * 100,
                "fallback_threshold": budget.fallback_threshold * 100,
            })

        return result

    async def reset_budget(self, budget: BudgetConfig) -> BudgetConfig:
        """
        Reset a budget for a new period.

        Args:
            budget: Budget to reset

        Returns:
            Updated budget
        """
        now = datetime.utcnow()

        # Calculate next reset time
        if budget.limit_period == "hourly":
            next_reset = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        elif budget.limit_period == "daily":
            next_reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif budget.limit_period == "weekly":
            days_until_monday = (7 - now.weekday()) % 7
            if days_until_monday == 0:
                days_until_monday = 7
            next_reset = (now + timedelta(days=days_until_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif budget.limit_period == "monthly":
            next_reset = (now + relativedelta(months=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            next_reset = None

        budget.current_usage = 0.0
        budget.current_percentage = 0.0
        budget.last_reset_at = now
        budget.next_reset_at = next_reset

        await self.db.flush()

        logger.info(f"Reset budget '{budget.budget_name}' (ID: {budget.id})")

        return budget

    async def reset_expired_budgets(self) -> int:
        """
        Reset all budgets that have passed their reset time.

        Returns:
            Number of budgets reset
        """
        now = datetime.utcnow()

        query = select(BudgetConfig).where(
            and_(
                BudgetConfig.is_active == True,
                BudgetConfig.auto_reset == True,
                BudgetConfig.next_reset_at <= now
            )
        )

        result = await self.db.execute(query)
        budgets = result.scalars().all()

        count = 0
        for budget in budgets:
            await self.reset_budget(budget)
            count += 1

        if count > 0:
            await self.db.commit()
            logger.info(f"Reset {count} expired budgets")

        return count

    async def create_budget(
        self,
        budget_name: str,
        budget_type: str,
        limit_type: str,
        limit_period: str,
        limit_value: float,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
        scope_id: Optional[str] = None,
        **kwargs
    ) -> BudgetConfig:
        """
        Create a new budget configuration.

        Args:
            budget_name: Friendly name for the budget
            budget_type: Type ('user', 'project', 'service', 'global')
            limit_type: Type of limit ('cost', 'tokens')
            limit_period: Time period ('hourly', 'daily', 'weekly', 'monthly', 'total')
            limit_value: Limit value (dollars or tokens)
            user_id: User ID (for user-level budgets)
            project_id: Project ID (for project-level budgets)
            scope_id: Scope identifier (for service-level budgets)
            **kwargs: Additional budget configuration

        Returns:
            Created budget configuration
        """
        now = datetime.utcnow()

        # Calculate initial next_reset_at
        if limit_period == "hourly":
            next_reset = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        elif limit_period == "daily":
            next_reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif limit_period == "weekly":
            days_until_monday = (7 - now.weekday()) % 7
            if days_until_monday == 0:
                days_until_monday = 7
            next_reset = (now + timedelta(days=days_until_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif limit_period == "monthly":
            next_reset = (now + relativedelta(months=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            next_reset = None

        budget = BudgetConfig(
            budget_name=budget_name,
            budget_type=budget_type,
            limit_type=limit_type,
            limit_period=limit_period,
            limit_value=limit_value,
            user_id=user_id,
            project_id=project_id,
            scope_id=scope_id,
            last_reset_at=now,
            next_reset_at=next_reset,
            **kwargs
        )

        self.db.add(budget)
        await self.db.flush()

        logger.info(f"Created budget '{budget_name}' (ID: {budget.id})")

        return budget
