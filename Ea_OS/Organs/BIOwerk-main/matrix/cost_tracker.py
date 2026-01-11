"""
Enterprise-grade cost tracking service for LLM token usage.

This module provides comprehensive cost tracking, budget management, and analytics
for LLM API usage across all providers (OpenAI, Anthropic, DeepSeek, Ollama, Local).

Features:
- Real-time cost calculation based on up-to-date pricing
- Token usage tracking per user, project, service, and provider
- Budget enforcement with soft/hard limits
- Cost spike detection and anomaly analysis
- Historical usage analytics and reporting
- Prometheus metrics integration
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.sql import extract

from matrix.db_models import TokenUsage, BudgetConfig, CostAlert, User, Project
from matrix.config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# LLM Pricing Tables (Updated as of January 2025)
# ============================================================================

class LLMPricing:
    """
    Centralized pricing information for all LLM providers.

    Prices are per 1 million tokens in USD.
    Updated regularly to reflect current pricing.
    """

    # OpenAI Pricing (per 1M tokens)
    OPENAI_PRICING = {
        "gpt-4o": {
            "input": 2.50,
            "output": 10.00,
            "cached_input": 1.25,  # 50% discount for cached tokens
        },
        "gpt-4o-mini": {
            "input": 0.15,
            "output": 0.60,
            "cached_input": 0.075,
        },
        "gpt-4-turbo": {
            "input": 10.00,
            "output": 30.00,
        },
        "gpt-4": {
            "input": 30.00,
            "output": 60.00,
        },
        "gpt-3.5-turbo": {
            "input": 0.50,
            "output": 1.50,
        },
        "o1-preview": {
            "input": 15.00,
            "output": 60.00,
        },
        "o1-mini": {
            "input": 3.00,
            "output": 12.00,
        },
    }

    # Anthropic Claude Pricing (per 1M tokens)
    ANTHROPIC_PRICING = {
        "claude-3-5-sonnet-20241022": {
            "input": 3.00,
            "output": 15.00,
            "cached_input": 0.30,  # 90% discount for prompt caching
        },
        "claude-3-5-sonnet-20240620": {
            "input": 3.00,
            "output": 15.00,
            "cached_input": 0.30,
        },
        "claude-3-opus-20240229": {
            "input": 15.00,
            "output": 75.00,
            "cached_input": 1.50,
        },
        "claude-3-sonnet-20240229": {
            "input": 3.00,
            "output": 15.00,
            "cached_input": 0.30,
        },
        "claude-3-haiku-20240307": {
            "input": 0.25,
            "output": 1.25,
            "cached_input": 0.025,
        },
    }

    # DeepSeek Pricing (per 1M tokens) - Very cost-effective
    DEEPSEEK_PRICING = {
        "deepseek-chat": {
            "input": 0.14,
            "output": 0.28,
        },
        "deepseek-coder": {
            "input": 0.14,
            "output": 0.28,
        },
    }

    # Ollama/Local models - Free (self-hosted)
    # But we track infrastructure costs if configured
    OLLAMA_PRICING = {
        "default": {
            "input": 0.0,
            "output": 0.0,
            "infrastructure_cost_per_hour": 0.0,  # Can be configured for instance costs
        }
    }

    LOCAL_PRICING = {
        "default": {
            "input": 0.0,
            "output": 0.0,
            "infrastructure_cost_per_hour": 0.0,
        }
    }

    @classmethod
    def get_pricing(cls, provider: str, model: str) -> Dict[str, float]:
        """
        Get pricing for a specific provider and model.

        Args:
            provider: Provider name (openai, anthropic, deepseek, ollama, local)
            model: Model name

        Returns:
            Dict with 'input' and 'output' prices per million tokens
        """
        provider = provider.lower()

        if provider == "openai":
            return cls.OPENAI_PRICING.get(model, cls.OPENAI_PRICING.get("gpt-4o", {"input": 2.50, "output": 10.00}))
        elif provider == "anthropic":
            return cls.ANTHROPIC_PRICING.get(model, cls.ANTHROPIC_PRICING.get("claude-3-5-sonnet-20241022", {"input": 3.00, "output": 15.00}))
        elif provider == "deepseek":
            return cls.DEEPSEEK_PRICING.get(model, cls.DEEPSEEK_PRICING.get("deepseek-chat", {"input": 0.14, "output": 0.28}))
        elif provider == "ollama":
            return cls.OLLAMA_PRICING.get(model, cls.OLLAMA_PRICING["default"])
        elif provider == "local":
            return cls.LOCAL_PRICING.get(model, cls.LOCAL_PRICING["default"])
        else:
            logger.warning(f"Unknown provider '{provider}', using default pricing")
            return {"input": 0.0, "output": 0.0}

    @classmethod
    def calculate_cost(
        cls,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0
    ) -> Tuple[float, float, float, Dict[str, float]]:
        """
        Calculate cost for a specific LLM request.

        Args:
            provider: Provider name
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            cached_tokens: Number of cached input tokens (if supported)

        Returns:
            Tuple of (input_cost, output_cost, total_cost, pricing_info)
        """
        pricing = cls.get_pricing(provider, model)

        # Calculate regular input tokens (excluding cached)
        regular_input_tokens = max(0, input_tokens - cached_tokens)

        # Calculate input cost
        input_cost = (regular_input_tokens / 1_000_000) * pricing.get("input", 0.0)

        # Add cached token cost if applicable
        if cached_tokens > 0 and "cached_input" in pricing:
            input_cost += (cached_tokens / 1_000_000) * pricing["cached_input"]

        # Calculate output cost
        output_cost = (output_tokens / 1_000_000) * pricing.get("output", 0.0)

        # Total cost
        total_cost = input_cost + output_cost

        return (
            round(input_cost, 6),
            round(output_cost, 6),
            round(total_cost, 6),
            pricing
        )

    @classmethod
    def estimate_cost(
        cls,
        provider: str,
        model: str,
        estimated_input_tokens: int,
        estimated_output_tokens: int
    ) -> float:
        """
        Estimate cost before making a request.

        Args:
            provider: Provider name
            model: Model name
            estimated_input_tokens: Estimated input tokens
            estimated_output_tokens: Estimated output tokens

        Returns:
            Estimated total cost in USD
        """
        _, _, total_cost, _ = cls.calculate_cost(
            provider, model, estimated_input_tokens, estimated_output_tokens
        )
        return total_cost


class CostTracker:
    """
    Enterprise cost tracking service for LLM usage.

    Provides comprehensive tracking, analytics, and budget management.
    """

    def __init__(self, db_session: AsyncSession):
        """Initialize cost tracker with database session."""
        self.db = db_session
        self.pricing = LLMPricing()

    async def record_usage(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
        service_name: Optional[str] = None,
        endpoint: Optional[str] = None,
        request_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        cached_tokens: int = 0,
        duration_ms: Optional[float] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        budget_id: Optional[str] = None,
        fallback_used: bool = False,
        original_provider: Optional[str] = None,
        original_model: Optional[str] = None,
        **metadata
    ) -> TokenUsage:
        """
        Record token usage and cost for an LLM request.

        Args:
            provider: LLM provider (openai, anthropic, deepseek, etc.)
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            user_id: User who made the request
            project_id: Project context
            service_name: Service making the request (osteon, myocyte, etc.)
            endpoint: API endpoint called
            request_id: Request correlation ID
            trace_id: Distributed tracing ID
            execution_id: Execution record ID
            cached_tokens: Cached tokens (if supported)
            duration_ms: Request duration in milliseconds
            success: Whether request succeeded
            error_message: Error details if failed
            budget_id: Associated budget configuration
            fallback_used: Whether model fallback was used
            original_provider: Original provider if fallback occurred
            original_model: Original model if fallback occurred
            **metadata: Additional metadata

        Returns:
            TokenUsage record
        """
        # Calculate costs
        input_cost, output_cost, total_cost, pricing_info = self.pricing.calculate_cost(
            provider, model, input_tokens, output_tokens, cached_tokens
        )

        total_tokens = input_tokens + output_tokens

        # Get current timestamp
        now = datetime.utcnow()

        # Create usage record
        usage = TokenUsage(
            request_id=request_id,
            trace_id=trace_id,
            execution_id=execution_id,
            user_id=user_id,
            project_id=project_id,
            service_name=service_name,
            endpoint=endpoint,
            provider=provider.lower(),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cached_tokens=cached_tokens,
            input_cost=input_cost,
            output_cost=output_cost,
            total_cost=total_cost,
            input_price_per_million=pricing_info.get("input"),
            output_price_per_million=pricing_info.get("output"),
            duration_ms=duration_ms,
            success=success,
            error_message=error_message,
            budget_id=budget_id,
            fallback_used=fallback_used,
            original_provider=original_provider,
            original_model=original_model,
            date=now.replace(hour=0, minute=0, second=0, microsecond=0),
            hour=now.hour,
            day_of_week=now.weekday(),
            **{k: v for k, v in metadata.items() if hasattr(TokenUsage, k)}
        )

        self.db.add(usage)
        await self.db.flush()  # Flush to get the ID

        logger.info(
            f"Recorded token usage: provider={provider}, model={model}, "
            f"tokens={total_tokens}, cost=${total_cost:.4f}, user={user_id}, project={project_id}"
        )

        return usage

    async def get_user_usage(
        self,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        group_by: str = "day"
    ) -> List[Dict[str, Any]]:
        """
        Get usage statistics for a user.

        Args:
            user_id: User ID
            start_date: Start date for query (default: 30 days ago)
            end_date: End date for query (default: now)
            group_by: Aggregation level ('hour', 'day', 'week', 'month')

        Returns:
            List of usage records with aggregated statistics
        """
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=30)
        if not end_date:
            end_date = datetime.utcnow()

        query = select(
            func.date_trunc(group_by, TokenUsage.date).label("period"),
            func.count(TokenUsage.id).label("request_count"),
            func.sum(TokenUsage.input_tokens).label("total_input_tokens"),
            func.sum(TokenUsage.output_tokens).label("total_output_tokens"),
            func.sum(TokenUsage.total_tokens).label("total_tokens"),
            func.sum(TokenUsage.total_cost).label("total_cost"),
            func.avg(TokenUsage.duration_ms).label("avg_duration_ms")
        ).where(
            and_(
                TokenUsage.user_id == user_id,
                TokenUsage.date >= start_date,
                TokenUsage.date <= end_date
            )
        ).group_by("period").order_by("period")

        result = await self.db.execute(query)
        rows = result.all()

        return [
            {
                "period": row.period,
                "request_count": row.request_count,
                "total_input_tokens": row.total_input_tokens or 0,
                "total_output_tokens": row.total_output_tokens or 0,
                "total_tokens": row.total_tokens or 0,
                "total_cost": float(row.total_cost or 0),
                "avg_duration_ms": float(row.avg_duration_ms or 0)
            }
            for row in rows
        ]

    async def get_project_usage(
        self,
        project_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get usage statistics for a project."""
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=30)
        if not end_date:
            end_date = datetime.utcnow()

        query = select(
            func.count(TokenUsage.id).label("request_count"),
            func.sum(TokenUsage.total_tokens).label("total_tokens"),
            func.sum(TokenUsage.total_cost).label("total_cost"),
            func.avg(TokenUsage.total_cost).label("avg_cost_per_request")
        ).where(
            and_(
                TokenUsage.project_id == project_id,
                TokenUsage.date >= start_date,
                TokenUsage.date <= end_date
            )
        )

        result = await self.db.execute(query)
        row = result.first()

        if not row:
            return {
                "request_count": 0,
                "total_tokens": 0,
                "total_cost": 0.0,
                "avg_cost_per_request": 0.0
            }

        return {
            "request_count": row.request_count or 0,
            "total_tokens": row.total_tokens or 0,
            "total_cost": float(row.total_cost or 0),
            "avg_cost_per_request": float(row.avg_cost_per_request or 0)
        }

    async def get_provider_breakdown(
        self,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Get cost breakdown by provider and model."""
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=30)
        if not end_date:
            end_date = datetime.utcnow()

        conditions = [
            TokenUsage.date >= start_date,
            TokenUsage.date <= end_date
        ]

        if user_id:
            conditions.append(TokenUsage.user_id == user_id)
        if project_id:
            conditions.append(TokenUsage.project_id == project_id)

        query = select(
            TokenUsage.provider,
            TokenUsage.model,
            func.count(TokenUsage.id).label("request_count"),
            func.sum(TokenUsage.total_tokens).label("total_tokens"),
            func.sum(TokenUsage.total_cost).label("total_cost")
        ).where(
            and_(*conditions)
        ).group_by(
            TokenUsage.provider,
            TokenUsage.model
        ).order_by(
            func.sum(TokenUsage.total_cost).desc()
        )

        result = await self.db.execute(query)
        rows = result.all()

        return [
            {
                "provider": row.provider,
                "model": row.model,
                "request_count": row.request_count,
                "total_tokens": row.total_tokens or 0,
                "total_cost": float(row.total_cost or 0)
            }
            for row in rows
        ]

    async def detect_cost_spike(
        self,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
        window_hours: int = 1,
        threshold_multiplier: float = 3.0
    ) -> Optional[Dict[str, Any]]:
        """
        Detect unusual cost spikes using statistical analysis.

        Args:
            user_id: User to check
            project_id: Project to check
            window_hours: Time window for spike detection (hours)
            threshold_multiplier: How many times above baseline is a spike

        Returns:
            Spike details if detected, None otherwise
        """
        now = datetime.utcnow()
        window_start = now - timedelta(hours=window_hours)
        baseline_start = now - timedelta(hours=window_hours * 24)  # Last 24 periods for baseline

        conditions = [TokenUsage.success == True]
        if user_id:
            conditions.append(TokenUsage.user_id == user_id)
        if project_id:
            conditions.append(TokenUsage.project_id == project_id)

        # Get recent cost (last window)
        recent_query = select(
            func.sum(TokenUsage.total_cost).label("recent_cost")
        ).where(
            and_(
                TokenUsage.date >= window_start,
                *conditions
            )
        )
        recent_result = await self.db.execute(recent_query)
        recent_cost = recent_result.scalar() or 0.0

        # Get baseline average cost
        baseline_query = select(
            func.avg(TokenUsage.total_cost).label("avg_cost")
        ).where(
            and_(
                TokenUsage.date >= baseline_start,
                TokenUsage.date < window_start,
                *conditions
            )
        )
        baseline_result = await self.db.execute(baseline_query)
        baseline_cost = baseline_result.scalar() or 0.0

        # Calculate spike
        if baseline_cost > 0 and recent_cost > baseline_cost * threshold_multiplier:
            multiplier = recent_cost / baseline_cost
            return {
                "spike_detected": True,
                "recent_cost": float(recent_cost),
                "baseline_cost": float(baseline_cost),
                "multiplier": round(multiplier, 2),
                "window_hours": window_hours,
                "threshold_multiplier": threshold_multiplier
            }

        return None
