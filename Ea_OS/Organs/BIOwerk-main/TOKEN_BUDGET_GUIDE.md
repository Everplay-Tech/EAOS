# Enterprise Token Budget & Cost Tracking System

## Overview

BIOwerk now includes a comprehensive, production-ready token budget enforcement system with enterprise-grade features:

- **Cost Tracking**: Automatic tracking of all LLM API costs per user, project, service, and provider
- **Budget Enforcement**: Flexible budget limits with soft/hard enforcement
- **Alert System**: Real-time alerts for budget violations and cost spikes
- **Model Fallback**: Automatic fallback to cheaper models when approaching limits
- **Analytics**: Detailed cost analytics and reporting
- **Prometheus Integration**: Full metrics for monitoring and alerting

## Key Features

### 1. Real-Time Cost Tracking

Every LLM request is tracked with:
- Token usage (input/output/cached)
- Actual costs calculated from current pricing
- Provider and model details
- User and project attribution
- Performance metrics (duration, success rate)

### 2. Budget Configuration

Create flexible budgets for different scopes:

- **User-level budgets**: Per-user cost/token limits
- **Project-level budgets**: Per-project limits
- **Service-level budgets**: Per-service (osteon, myocyte, etc.) limits
- **Global budgets**: Organization-wide limits

With time periods:
- Hourly
- Daily
- Weekly
- Monthly
- Total (lifetime)

### 3. Budget Enforcement

Three enforcement modes:

1. **Tracking Only** (`is_enforced=False`): Track but don't block
2. **Soft Limits** (`hard_limit_enabled=False`): Warn but allow
3. **Hard Limits** (`hard_limit_enabled=True`): Block when exceeded

### 4. Automatic Model Fallback

When approaching budget limits, automatically switch to cheaper models:

```
User requests → GPT-4o (expensive)
↓ Budget at 90% used
→ Automatically fallback to DeepSeek (cost-effective)
```

### 5. Cost Spike Detection

Automatically detect unusual cost spikes:
- Compares recent usage to baseline
- Configurable threshold (default: 3x baseline)
- Immediate alerts via Prometheus/Alertmanager

### 6. Multi-Channel Alerts

Alerts sent via:
- Prometheus Alertmanager
- Slack
- Email
- PagerDuty (for critical alerts)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    BudgetAwareLLMClient                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Pre-Request Budget Check                               │
│     ├─ Get active budgets                                  │
│     ├─ Estimate cost                                       │
│     ├─ Check limits & thresholds                           │
│     └─ Determine fallback if needed                        │
│                                                             │
│  2. Execute LLM Request                                    │
│     ├─ Use fallback provider/model if triggered            │
│     └─ Track duration                                      │
│                                                             │
│  3. Post-Request Tracking                                  │
│     ├─ Record token usage & cost                           │
│     ├─ Update budget usage                                 │
│     ├─ Check for threshold violations                      │
│     ├─ Detect cost spikes                                  │
│     ├─ Generate alerts                                     │
│     └─ Update Prometheus metrics                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Database Schema

### TokenUsage
Tracks every LLM request:
- User, project, service attribution
- Provider and model used
- Token counts (input/output/cached)
- Costs (input/output/total)
- Budget association
- Fallback information
- Performance metrics

### BudgetConfig
Defines budget limits and policies:
- Scope (user/project/service/global)
- Limit type (cost/tokens)
- Limit period (hourly/daily/weekly/monthly/total)
- Thresholds (warning/critical/fallback)
- Fallback strategy
- Alert configuration

### CostAlert
Tracks all budget-related alerts:
- Alert type (warning/critical/exceeded/spike)
- Budget association
- Alert status (active/acknowledged/resolved)
- Notification tracking
- Deduplication

## Quick Start

### 1. Run Database Migration

```bash
# Apply the migration
alembic upgrade head
```

### 2. Configure Environment

Add to `.env`:

```bash
# Enable budget enforcement
BUDGET_ENABLED=true
BUDGET_COST_TRACKING=true
BUDGET_ENFORCE_LIMITS=true

# Fallback configuration
BUDGET_AUTO_FALLBACK=true
BUDGET_DEFAULT_FALLBACK_PROVIDER=deepseek
BUDGET_DEFAULT_FALLBACK_MODEL=deepseek-chat

# Spike detection
BUDGET_SPIKE_DETECTION=true
BUDGET_SPIKE_MULTIPLIER=3.0
BUDGET_SPIKE_WINDOW_HOURS=1
```

### 3. Create a Budget

```python
from matrix.budget_enforcement import BudgetEnforcer
from matrix.database import get_db_session

async def create_user_budget():
    async with get_db_session() as db:
        enforcer = BudgetEnforcer(db)

        # Create a monthly $50 budget for user
        budget = await enforcer.create_budget(
            budget_name="User Monthly Budget",
            budget_type="user",
            limit_type="cost",
            limit_period="monthly",
            limit_value=50.0,  # $50
            user_id="user-123",

            # Thresholds
            warning_threshold=0.8,   # Alert at 80%
            critical_threshold=0.95,  # Critical alert at 95%

            # Fallback
            enable_fallback=True,
            fallback_provider="deepseek",
            fallback_model="deepseek-chat",
            fallback_threshold=0.9,  # Start fallback at 90%

            # Hard limit
            hard_limit_enabled=True,
            block_on_exceeded=False,  # Use fallback instead of blocking

            # Alerts
            alert_channels=["slack", "email"],
            alert_recipients=["team@company.com"]
        )

        await db.commit()
        print(f"Created budget: {budget.id}")
```

### 4. Use Budget-Aware LLM Client

```python
from matrix.budget_llm_client import get_budget_llm_client

async def generate_document():
    async with get_budget_llm_client(
        user_id="user-123",
        project_id="project-456",
        service_name="osteon"
    ) as client:

        # This request will:
        # 1. Check budgets before making request
        # 2. Use fallback model if approaching limits
        # 3. Track costs and update budgets
        # 4. Generate alerts if thresholds crossed

        response = await client.chat_completion(
            messages=[
                {"role": "user", "content": "Write a technical document about AI"}
            ],
            provider="openai",
            model="gpt-4o",
            endpoint="/draft"
        )

        return response
```

## Budget Types and Use Cases

### 1. User-Level Budget

Limit costs per user across all projects:

```python
budget = await enforcer.create_budget(
    budget_name="User Daily Limit",
    budget_type="user",
    user_id="user-123",
    limit_type="cost",
    limit_period="daily",
    limit_value=10.0  # $10/day
)
```

**Use case**: Prevent individual users from exceeding their daily/monthly allowance.

### 2. Project-Level Budget

Limit costs for a specific project:

```python
budget = await enforcer.create_budget(
    budget_name="Project Monthly Budget",
    budget_type="project",
    project_id="project-456",
    limit_type="cost",
    limit_period="monthly",
    limit_value=500.0  # $500/month
)
```

**Use case**: Track and limit costs for client projects or internal initiatives.

### 3. Service-Level Budget

Limit costs for a specific service/agent:

```python
budget = await enforcer.create_budget(
    budget_name="Osteon Service Budget",
    budget_type="service",
    scope_id="osteon",  # Service name
    limit_type="tokens",
    limit_period="hourly",
    limit_value=1000000  # 1M tokens/hour
)
```

**Use case**: Prevent runaway costs from a specific service.

### 4. Global Budget

Organization-wide cost limit:

```python
budget = await enforcer.create_budget(
    budget_name="Company Monthly Budget",
    budget_type="global",
    limit_type="cost",
    limit_period="monthly",
    limit_value=10000.0  # $10k/month
)
```

**Use case**: Hard cap on total organization spending.

## Advanced Features

### Model Fallback Strategy

Configure cascading fallbacks:

```python
budget = await enforcer.create_budget(
    # ... basic config ...

    # Fallback configuration
    enable_fallback=True,
    fallback_provider="deepseek",
    fallback_model="deepseek-chat",
    fallback_threshold=0.9,  # Start at 90%

    # Provider/model restrictions
    allowed_providers=["openai", "anthropic", "deepseek"],
    blocked_models=["gpt-4"],  # Block expensive model
)
```

### Cost Spike Detection

Automatic anomaly detection:

```python
budget = await enforcer.create_budget(
    # ... basic config ...

    # Spike detection
    enable_spike_detection=True,
    spike_threshold_multiplier=3.0,  # 3x baseline
    spike_window_hours=1,  # Look at last hour

    # Alert on spikes
    alert_on_spike=True
)
```

### Per-Request Limits

Limit individual request costs:

```python
budget = await enforcer.create_budget(
    # ... basic config ...

    # Maximum $0.50 per request
    max_cost_per_request=0.50
)
```

## Analytics & Reporting

### Get User Usage

```python
from matrix.cost_tracker import CostTracker

async def get_user_analytics(user_id: str):
    async with get_db_session() as db:
        tracker = CostTracker(db)

        # Get daily usage for last 30 days
        usage = await tracker.get_user_usage(
            user_id=user_id,
            group_by="day"
        )

        for day in usage:
            print(f"{day['period']}: "
                  f"{day['total_tokens']} tokens, "
                  f"${day['total_cost']:.2f}")
```

### Get Provider Breakdown

```python
async def cost_breakdown(user_id: str):
    async with get_db_session() as db:
        tracker = CostTracker(db)

        breakdown = await tracker.get_provider_breakdown(
            user_id=user_id
        )

        for item in breakdown:
            print(f"{item['provider']}/{item['model']}: "
                  f"${item['total_cost']:.2f} "
                  f"({item['request_count']} requests)")
```

## Prometheus Metrics

The system exposes comprehensive metrics:

```prometheus
# Token usage
biowerk_llm_tokens_total{user_id, project_id, provider, model, service, token_type}
biowerk_llm_cost_usd_total{user_id, project_id, provider, model, service}
biowerk_llm_requests_total{user_id, project_id, provider, model, service, status}

# Budget metrics
biowerk_budget_usage_percentage{budget_id, budget_name, budget_type, limit_period}
biowerk_budget_usage_value{budget_id, budget_name, budget_type, limit_type, limit_period}
biowerk_budget_exceeded_total{budget_id, budget_name, budget_type, threshold}
biowerk_budget_fallback_total{original_provider, original_model, fallback_provider, fallback_model}

# Alerts
biowerk_cost_alerts_total{alert_type, severity, budget_type}
biowerk_cost_spike_detected_total{user_id, project_id}
biowerk_cost_spike_multiplier{user_id, project_id}

# Provider performance
biowerk_llm_provider_success_rate{provider, model}
biowerk_llm_provider_avg_cost_usd{provider, model}
biowerk_llm_provider_avg_tokens{provider, model}
```

### Example Prometheus Queries

```prometheus
# Total cost today
sum(increase(biowerk_llm_cost_usd_total[24h]))

# Cost by provider
sum by (provider) (increase(biowerk_llm_cost_usd_total[7d]))

# Budgets over 80%
biowerk_budget_usage_percentage > 80

# Cost spike rate
rate(biowerk_cost_spike_detected_total[1h])

# Average cost per request
rate(biowerk_llm_cost_usd_total[5m]) / rate(biowerk_llm_requests_total{status="success"}[5m])
```

## Alerting

### Grafana Dashboard Example

Create alerts for:

1. **Budget Warning** (80% usage)
2. **Budget Critical** (95% usage)
3. **Budget Exceeded** (100% usage)
4. **Cost Spike** (3x baseline)
5. **High Error Rate** (>5% failures)

### Slack Notification Example

Configure budget alerts to Slack:

```python
budget = await enforcer.create_budget(
    # ... config ...
    alert_channels=["slack"],
    alert_recipients=["#cost-alerts"]
)
```

Alerts will include:
- Budget name and type
- Current usage vs. limit
- Percentage used
- Action taken (fallback, blocked, etc.)
- Provider and model involved

## Pricing Table (Updated January 2025)

### OpenAI
| Model | Input (per 1M) | Output (per 1M) |
|-------|----------------|-----------------|
| GPT-4o | $2.50 | $10.00 |
| GPT-4o-mini | $0.15 | $0.60 |
| GPT-4-turbo | $10.00 | $30.00 |

### Anthropic Claude
| Model | Input (per 1M) | Output (per 1M) |
|-------|----------------|-----------------|
| Claude 3.5 Sonnet | $3.00 | $15.00 |
| Claude 3 Opus | $15.00 | $75.00 |
| Claude 3 Haiku | $0.25 | $1.25 |

### DeepSeek
| Model | Input (per 1M) | Output (per 1M) |
|-------|----------------|-----------------|
| DeepSeek Chat | $0.14 | $0.28 |
| DeepSeek Coder | $0.14 | $0.28 |

### Ollama/Local
- **Cost**: FREE (self-hosted)
- Infrastructure costs can be tracked separately

## Best Practices

### 1. Layered Budgets

Use multiple budget levels for defense-in-depth:

```python
# Global monthly cap
global_budget = await enforcer.create_budget(
    budget_type="global",
    limit_period="monthly",
    limit_value=10000.0  # $10k/month
)

# Per-user daily limit
user_budget = await enforcer.create_budget(
    budget_type="user",
    user_id=user_id,
    limit_period="daily",
    limit_value=50.0  # $50/day
)

# Per-project weekly limit
project_budget = await enforcer.create_budget(
    budget_type="project",
    project_id=project_id,
    limit_period="weekly",
    limit_value=500.0  # $500/week
)
```

### 2. Gradual Fallback

Configure cascade of cheaper models:

```python
# Primary budget: Use GPT-4o, fallback to DeepSeek at 90%
budget_primary = await enforcer.create_budget(
    fallback_threshold=0.9,
    fallback_provider="deepseek"
)

# If DeepSeek budget also reached, fallback to local Ollama
budget_deepseek = await enforcer.create_budget(
    budget_type="global",
    allowed_providers=["deepseek"],
    fallback_provider="ollama",
    fallback_threshold=0.95
)
```

### 3. Monitor & Adjust

- Review cost reports weekly
- Adjust budgets based on actual usage
- Set up Grafana dashboards for real-time monitoring
- Configure PagerDuty for critical budget violations

### 4. Cost Optimization

- Prefer cached tokens (90% discount for Claude)
- Use cheaper models for simple tasks
- Implement request batching
- Set reasonable max_tokens limits

## Troubleshooting

### Budget Not Enforcing

Check:
1. `BUDGET_ENABLED=true` in `.env`
2. `BUDGET_ENFORCE_LIMITS=true`
3. Budget `is_active=true` and `is_enforced=true`
4. Using `BudgetAwareLLMClient` not base `LLMClient`

### Costs Not Tracked

Check:
1. `BUDGET_COST_TRACKING=true`
2. Database migration applied (`alembic upgrade head`)
3. Database connection working

### Fallback Not Working

Check:
1. `enable_fallback=true` on budget
2. `fallback_provider` and `fallback_model` configured
3. Fallback provider API keys configured
4. `fallback_threshold` < 1.0

## Migration from Previous Setup

If upgrading from a system without budget tracking:

```bash
# 1. Backup database
pg_dump biowerk > backup.sql

# 2. Run migration
alembic upgrade head

# 3. Configure budgets for existing users
python scripts/setup_default_budgets.py

# 4. Enable in .env
echo "BUDGET_ENABLED=true" >> .env

# 5. Restart services
docker-compose restart
```

## API Endpoints

### Get Budget Status

```bash
GET /api/budgets/{budget_id}
```

### Get User Usage

```bash
GET /api/usage/user/{user_id}?period=monthly
```

### Get Cost Breakdown

```bash
GET /api/usage/breakdown?user_id={user_id}&start_date={start}&end_date={end}
```

### Get Active Alerts

```bash
GET /api/alerts?status=active&severity=critical
```

## Support

For questions or issues:

1. Check this documentation
2. Review Prometheus metrics
3. Check application logs
4. Review Grafana dashboards
5. Contact platform team

## Changelog

### v1.0 (2025-01-16)

- Initial release
- Complete cost tracking system
- Budget enforcement with fallback
- Alert system integration
- Prometheus metrics
- Spike detection
- Multi-level budgets (user/project/service/global)
- Multiple time periods (hourly/daily/weekly/monthly/total)
