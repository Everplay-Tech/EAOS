"""
Example usage of the Token Budget Enforcement system.

This demonstrates:
1. Creating budgets
2. Using the budget-aware LLM client
3. Checking usage statistics
4. Managing alerts
"""

import asyncio
from datetime import datetime, timedelta

from matrix.database import get_db_session
from matrix.budget_enforcement import BudgetEnforcer
from matrix.cost_tracker import CostTracker
from matrix.cost_alerts import AlertManager
from matrix.budget_llm_client import get_budget_llm_client


async def example_create_budgets():
    """Example: Create various budget configurations."""
    print("=" * 60)
    print("EXAMPLE 1: Creating Budgets")
    print("=" * 60)

    async with get_db_session() as db:
        enforcer = BudgetEnforcer(db)

        # 1. User-level monthly budget
        user_budget = await enforcer.create_budget(
            budget_name="User Monthly Budget",
            budget_type="user",
            limit_type="cost",
            limit_period="monthly",
            limit_value=100.0,  # $100/month
            user_id="user-123",
            warning_threshold=0.8,
            critical_threshold=0.95,
            enable_fallback=True,
            fallback_provider="deepseek",
            fallback_model="deepseek-chat",
            alert_channels=["slack", "email"]
        )
        print(f"✓ Created user budget: {user_budget.id}")

        # 2. Project-level daily budget
        project_budget = await enforcer.create_budget(
            budget_name="Project Daily Budget",
            budget_type="project",
            limit_type="cost",
            limit_period="daily",
            limit_value=50.0,  # $50/day
            project_id="project-456",
            hard_limit_enabled=True,
            block_on_exceeded=False,  # Use fallback instead
            enable_fallback=True,
            fallback_provider="deepseek"
        )
        print(f"✓ Created project budget: {project_budget.id}")

        # 3. Service-level hourly token budget
        service_budget = await enforcer.create_budget(
            budget_name="Osteon Hourly Token Limit",
            budget_type="service",
            limit_type="tokens",
            limit_period="hourly",
            limit_value=500000,  # 500k tokens/hour
            scope_id="osteon",
            enable_spike_detection=True,
            spike_threshold_multiplier=5.0,
            spike_window_hours=1
        )
        print(f"✓ Created service budget: {service_budget.id}")

        # 4. Global organization budget
        global_budget = await enforcer.create_budget(
            budget_name="Company Monthly Cap",
            budget_type="global",
            limit_type="cost",
            limit_period="monthly",
            limit_value=10000.0,  # $10k/month
            hard_limit_enabled=True,
            block_on_exceeded=False,
            alert_channels=["pagerduty", "slack", "email"]
        )
        print(f"✓ Created global budget: {global_budget.id}")

        await db.commit()

    print("\n✓ All budgets created successfully!\n")


async def example_use_budget_client():
    """Example: Using the budget-aware LLM client."""
    print("=" * 60)
    print("EXAMPLE 2: Using Budget-Aware LLM Client")
    print("=" * 60)

    # Use the budget-aware client
    async with get_budget_llm_client(
        user_id="user-123",
        project_id="project-456",
        service_name="osteon"
    ) as client:

        print("\nMaking LLM request with budget enforcement...")

        # This will:
        # - Check all applicable budgets
        # - Use fallback if approaching limits
        # - Track costs automatically
        # - Generate alerts if needed
        response = await client.chat_completion(
            messages=[
                {"role": "user", "content": "Explain quantum computing in 50 words"}
            ],
            provider="openai",
            model="gpt-4o",
            endpoint="/draft",
            request_id="example-request-001"
        )

        print(f"\n✓ Response received: {response[:100]}...")

    print("\n✓ Request completed with budget enforcement!\n")


async def example_check_usage():
    """Example: Check usage statistics."""
    print("=" * 60)
    print("EXAMPLE 3: Checking Usage Statistics")
    print("=" * 60)

    async with get_db_session() as db:
        tracker = CostTracker(db)

        # Get user usage for last 30 days
        print("\nUser usage (last 30 days):")
        usage = await tracker.get_user_usage(
            user_id="user-123",
            group_by="day"
        )

        for day in usage[-7:]:  # Last 7 days
            print(f"  {day['period'].strftime('%Y-%m-%d')}: "
                  f"{day['request_count']} requests, "
                  f"{day['total_tokens']:,} tokens, "
                  f"${day['total_cost']:.4f}")

        # Get provider breakdown
        print("\nCost breakdown by provider:")
        breakdown = await tracker.get_provider_breakdown(
            user_id="user-123"
        )

        for item in breakdown:
            print(f"  {item['provider']:10s} {item['model']:25s} "
                  f"{item['request_count']:4d} requests  "
                  f"${item['total_cost']:8.4f}")

        # Get project usage
        print("\nProject usage:")
        project_usage = await tracker.get_project_usage(
            project_id="project-456"
        )

        print(f"  Requests: {project_usage['request_count']}")
        print(f"  Tokens: {project_usage['total_tokens']:,}")
        print(f"  Total Cost: ${project_usage['total_cost']:.4f}")
        print(f"  Avg Cost/Request: ${project_usage['avg_cost_per_request']:.4f}")

    print("\n✓ Usage statistics retrieved!\n")


async def example_check_budgets():
    """Example: Check budget status."""
    print("=" * 60)
    print("EXAMPLE 4: Checking Budget Status")
    print("=" * 60)

    async with get_db_session() as db:
        enforcer = BudgetEnforcer(db)

        # Get active budgets for a user
        budgets = await enforcer.get_active_budgets(
            user_id="user-123",
            project_id="project-456"
        )

        print(f"\nFound {len(budgets)} active budgets:\n")

        for budget in budgets:
            # Update usage
            await enforcer.update_budget_usage(budget)

            status = "✓ OK"
            if budget.current_percentage >= 100:
                status = "✗ EXCEEDED"
            elif budget.current_percentage >= budget.critical_threshold * 100:
                status = "⚠ CRITICAL"
            elif budget.current_percentage >= budget.warning_threshold * 100:
                status = "⚡ WARNING"

            print(f"{status} {budget.budget_name}")
            print(f"   Type: {budget.budget_type}, Period: {budget.limit_period}")
            print(f"   Usage: {budget.current_usage:.2f}/{budget.limit_value:.2f} "
                  f"{budget.limit_type} ({budget.current_percentage:.1f}%)")

            if budget.enable_fallback and budget.current_percentage >= budget.fallback_threshold * 100:
                print(f"   🔄 Fallback active: {budget.fallback_provider}/{budget.fallback_model}")
            print()

    print("✓ Budget status checked!\n")


async def example_spike_detection():
    """Example: Detect cost spikes."""
    print("=" * 60)
    print("EXAMPLE 5: Cost Spike Detection")
    print("=" * 60)

    async with get_db_session() as db:
        tracker = CostTracker(db)

        # Check for spikes
        spike_data = await tracker.detect_cost_spike(
            user_id="user-123",
            window_hours=1,
            threshold_multiplier=3.0
        )

        if spike_data:
            print("\n⚠️  COST SPIKE DETECTED!")
            print(f"   Recent cost: ${spike_data['recent_cost']:.4f}")
            print(f"   Baseline: ${spike_data['baseline_cost']:.4f}")
            print(f"   Multiplier: {spike_data['multiplier']:.1f}x")
            print(f"   Window: {spike_data['window_hours']} hour(s)")
        else:
            print("\n✓ No cost spikes detected")

    print("\n✓ Spike detection complete!\n")


async def example_manage_alerts():
    """Example: Manage cost alerts."""
    print("=" * 60)
    print("EXAMPLE 6: Managing Alerts")
    print("=" * 60)

    async with get_db_session() as db:
        from matrix.db_models import CostAlert
        from sqlalchemy import select

        # Get active alerts
        query = select(CostAlert).where(CostAlert.status == "active").limit(5)
        result = await db.execute(query)
        alerts = result.scalars().all()

        print(f"\nActive alerts: {len(alerts)}\n")

        for alert in alerts:
            severity_icon = {
                "low": "ℹ️",
                "medium": "⚡",
                "high": "⚠️",
                "critical": "🚨"
            }.get(alert.severity, "❓")

            print(f"{severity_icon} {alert.title}")
            print(f"   Type: {alert.alert_type}, Severity: {alert.severity}")
            print(f"   Message: {alert.message}")
            print(f"   Triggered: {alert.triggered_at.strftime('%Y-%m-%d %H:%M:%S')}")

            if alert.action_taken:
                print(f"   Action: {alert.action_taken}")
            print()

        # Example: Acknowledge an alert
        if alerts:
            alert_manager = AlertManager(db)
            acknowledged = await alert_manager.acknowledge_alert(
                alert_id=alerts[0].id,
                acknowledged_by="admin",
                notes="Reviewing cost spike with team"
            )
            print(f"✓ Acknowledged alert: {acknowledged.id}\n")

        await db.commit()

    print("✓ Alert management complete!\n")


async def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("Token Budget Enforcement System - Examples")
    print("=" * 60 + "\n")

    try:
        # Run examples
        await example_create_budgets()
        await example_use_budget_client()
        await example_check_usage()
        await example_check_budgets()
        await example_spike_detection()
        await example_manage_alerts()

        print("=" * 60)
        print("✓ All examples completed successfully!")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\n❌ Error running examples: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
