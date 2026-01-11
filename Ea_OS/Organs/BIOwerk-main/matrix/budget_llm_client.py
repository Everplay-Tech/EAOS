"""
Budget-aware LLM client wrapper with cost tracking and enforcement.

This module provides an enterprise-grade wrapper around the base LLM client
that adds:
- Budget checking before requests
- Automatic model fallback when approaching limits
- Cost and token usage tracking
- Alert generation for budget violations
- Integration with Prometheus metrics
"""

import logging
import time
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession

from matrix.llm_client import LLMClient
from matrix.cost_tracker import CostTracker, LLMPricing
from matrix.budget_enforcement import BudgetEnforcer, BudgetExceededError
from matrix.cost_alerts import AlertManager
from matrix.database import get_db_session

logger = logging.getLogger(__name__)


class BudgetAwareLLMClient:
    """
    Enterprise LLM client with budget enforcement and cost tracking.

    Wraps the base LLMClient and adds:
    - Pre-request budget validation
    - Automatic model fallback
    - Post-request cost tracking
    - Alert generation
    - Prometheus metrics
    """

    def __init__(
        self,
        db_session: AsyncSession,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
        service_name: Optional[str] = None
    ):
        """
        Initialize budget-aware LLM client.

        Args:
            db_session: Database session for cost tracking
            user_id: User ID for budget enforcement
            project_id: Project ID for budget tracking
            service_name: Service name (osteon, myocyte, etc.)
        """
        self.llm_client = LLMClient()
        self.db = db_session
        self.user_id = user_id
        self.project_id = project_id
        self.service_name = service_name

        # Initialize services
        self.cost_tracker = CostTracker(db_session)
        self.budget_enforcer = BudgetEnforcer(db_session)
        self.alert_manager = AlertManager(db_session)
        self.pricing = LLMPricing()

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        json_mode: bool = False,
        endpoint: Optional[str] = None,
        request_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        bypass_budget: bool = False
    ) -> str:
        """
        Generate chat completion with budget enforcement and cost tracking.

        Args:
            messages: List of message dicts
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            provider: LLM provider (optional override)
            model: Model name (optional override)
            json_mode: Enable JSON response mode
            endpoint: API endpoint being called
            request_id: Request correlation ID
            trace_id: Distributed tracing ID
            execution_id: Execution record ID
            bypass_budget: Skip budget enforcement (admin override)

        Returns:
            Generated text response

        Raises:
            BudgetExceededError: If budget hard limit is exceeded and blocking is enabled
        """
        start_time = time.time()

        # Use configured defaults if not specified
        provider = provider or self.llm_client.provider
        model = model or self._get_default_model(provider)

        # Estimate tokens for budget check
        estimated_input_tokens = self._estimate_tokens(messages, system_prompt)
        estimated_output_tokens = max_tokens or 1000  # Default estimate

        original_provider = provider
        original_model = model
        fallback_used = False
        budget_check_result = None

        try:
            # Check budget (unless bypassed)
            if not bypass_budget:
                budget_check_result = await self.budget_enforcer.check_budget(
                    provider=provider,
                    model=model,
                    estimated_input_tokens=estimated_input_tokens,
                    estimated_output_tokens=estimated_output_tokens,
                    user_id=self.user_id,
                    project_id=self.project_id,
                    service_name=self.service_name
                )

                # Log warnings
                for warning in budget_check_result.get("warnings", []):
                    logger.warning(f"Budget warning: {warning}")

                # Check if request is allowed
                if not budget_check_result["allowed"]:
                    error_msg = "Budget limit exceeded: " + "; ".join(budget_check_result["warnings"])
                    logger.error(error_msg)

                    # Record failed attempt
                    await self.cost_tracker.record_usage(
                        provider=provider,
                        model=model,
                        input_tokens=0,
                        output_tokens=0,
                        user_id=self.user_id,
                        project_id=self.project_id,
                        service_name=self.service_name,
                        endpoint=endpoint,
                        request_id=request_id,
                        trace_id=trace_id,
                        execution_id=execution_id,
                        success=False,
                        error_message=error_msg
                    )

                    # Create alert for the most restrictive budget
                    if budget_check_result.get("budgets"):
                        most_restrictive = max(
                            budget_check_result["budgets"],
                            key=lambda b: b["current_percentage"]
                        )
                        budget_id = most_restrictive["budget_id"]

                        # Get budget for alert
                        from matrix.db_models import BudgetConfig
                        from sqlalchemy import select
                        budget_query = select(BudgetConfig).where(BudgetConfig.id == budget_id)
                        budget_result = await self.db.execute(budget_query)
                        budget = budget_result.scalar_one_or_none()

                        if budget:
                            await self.alert_manager.create_budget_alert(
                                alert_type="exceeded",
                                budget=budget,
                                current_usage=most_restrictive["current_usage"],
                                usage_percentage=most_restrictive["current_percentage"],
                                threshold_exceeded="hard_limit",
                                action_taken="blocked",
                                request_blocked=True
                            )

                    await self.db.commit()

                    raise BudgetExceededError(
                        error_msg,
                        budget=None,
                        current_usage=0
                    )

                # Check if fallback is required
                if budget_check_result["fallback_required"]:
                    provider = budget_check_result["fallback_provider"]
                    model = budget_check_result["fallback_model"] or self._get_default_model(provider)
                    fallback_used = True

                    logger.info(
                        f"Using fallback model: {provider}/{model} "
                        f"(original: {original_provider}/{original_model})"
                    )

            # Make LLM request
            logger.info(
                f"Making LLM request: provider={provider}, model={model}, "
                f"user={self.user_id}, project={self.project_id}"
            )

            response = await self.llm_client.chat_completion(
                messages=messages,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                provider=provider,
                model=model,
                json_mode=json_mode
            )

            # Extract token usage from response
            # Note: This is provider-specific and would need to be extracted from response metadata
            # For now, we'll estimate based on response length
            actual_input_tokens, actual_output_tokens = await self._extract_token_usage(
                provider, model, messages, system_prompt, response
            )

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Record usage
            budget_id = None
            if budget_check_result and budget_check_result.get("budgets"):
                budget_id = budget_check_result["budgets"][0]["budget_id"]

            usage_record = await self.cost_tracker.record_usage(
                provider=provider,
                model=model,
                input_tokens=actual_input_tokens,
                output_tokens=actual_output_tokens,
                user_id=self.user_id,
                project_id=self.project_id,
                service_name=self.service_name,
                endpoint=endpoint,
                request_id=request_id,
                trace_id=trace_id,
                execution_id=execution_id,
                duration_ms=duration_ms,
                success=True,
                budget_id=budget_id,
                fallback_used=fallback_used,
                original_provider=original_provider if fallback_used else None,
                original_model=original_model if fallback_used else None,
                json_mode=json_mode,
                temperature=temperature,
                max_tokens_requested=max_tokens
            )

            # Update budget usage and check thresholds
            if budget_check_result and budget_check_result.get("budgets"):
                for budget_info in budget_check_result["budgets"]:
                    from matrix.db_models import BudgetConfig
                    from sqlalchemy import select

                    budget_query = select(BudgetConfig).where(BudgetConfig.id == budget_info["budget_id"])
                    budget_result = await self.db.execute(budget_query)
                    budget = budget_result.scalar_one_or_none()

                    if budget:
                        # Update cached usage
                        await self.budget_enforcer.update_budget_usage(budget)

                        # Check for threshold alerts
                        await self.alert_manager.check_budget_thresholds(budget)

            # Check for cost spikes
            await self.alert_manager.check_cost_spikes(
                user_id=self.user_id,
                project_id=self.project_id
            )

            # Commit all changes
            await self.db.commit()

            logger.info(
                f"LLM request successful: tokens={actual_input_tokens + actual_output_tokens}, "
                f"cost=${usage_record.total_cost:.4f}, duration={duration_ms:.0f}ms"
            )

            return response

        except BudgetExceededError:
            # Re-raise budget errors
            raise

        except Exception as e:
            # Record error
            duration_ms = (time.time() - start_time) * 1000

            logger.error(f"LLM request failed: {str(e)}", exc_info=True)

            try:
                await self.cost_tracker.record_usage(
                    provider=provider,
                    model=model,
                    input_tokens=0,
                    output_tokens=0,
                    user_id=self.user_id,
                    project_id=self.project_id,
                    service_name=self.service_name,
                    endpoint=endpoint,
                    request_id=request_id,
                    trace_id=trace_id,
                    execution_id=execution_id,
                    duration_ms=duration_ms,
                    success=False,
                    error_message=str(e)
                )
                await self.db.commit()
            except Exception as tracking_error:
                logger.error(f"Failed to record error usage: {tracking_error}")

            raise

    def _get_default_model(self, provider: str) -> str:
        """Get default model for provider."""
        from matrix.config import settings

        if provider == "openai":
            return settings.openai_model
        elif provider == "anthropic":
            return settings.anthropic_model
        elif provider == "deepseek":
            return settings.deepseek_model
        elif provider == "ollama":
            return settings.ollama_model
        elif provider == "local":
            return settings.local_model_name
        return "unknown"

    def _estimate_tokens(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None
    ) -> int:
        """
        Estimate token count for messages.

        Uses a simple heuristic: ~4 characters per token.
        For production, use tiktoken or similar.
        """
        total_chars = 0

        if system_prompt:
            total_chars += len(system_prompt)

        for msg in messages:
            total_chars += len(msg.get("content", ""))

        # Rough estimate: 4 chars per token
        estimated_tokens = total_chars // 4

        return max(estimated_tokens, 1)

    async def _extract_token_usage(
        self,
        provider: str,
        model: str,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str],
        response: str
    ) -> tuple[int, int]:
        """
        Extract actual token usage from response.

        In production, this should parse the actual usage data from the API response.
        For now, we estimate based on content length.

        Args:
            provider: LLM provider
            model: Model name
            messages: Input messages
            system_prompt: System prompt
            response: Generated response

        Returns:
            Tuple of (input_tokens, output_tokens)
        """
        # Estimate input tokens
        input_tokens = self._estimate_tokens(messages, system_prompt)

        # Estimate output tokens
        output_tokens = len(response) // 4  # Rough estimate

        return (input_tokens, max(output_tokens, 1))


@asynccontextmanager
async def get_budget_llm_client(
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    service_name: Optional[str] = None
):
    """
    Async context manager for budget-aware LLM client.

    Usage:
        async with get_budget_llm_client(user_id="user123") as client:
            response = await client.chat_completion(messages=[...])

    Args:
        user_id: User ID for budget enforcement
        project_id: Project ID for cost tracking
        service_name: Service name

    Yields:
        BudgetAwareLLMClient instance
    """
    async with get_db_session() as db_session:
        client = BudgetAwareLLMClient(
            db_session=db_session,
            user_id=user_id,
            project_id=project_id,
            service_name=service_name
        )
        yield client
