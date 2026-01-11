"""Add token usage, budget, and cost alert tables

Revision ID: 004_add_token_budget_tables
Revises: 002_add_retention_tables
Create Date: 2025-01-16

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004_add_token_budget_tables'
down_revision = '002_add_retention_tables'
branch_labels = None
depends_on = None


def upgrade():
    """Create token usage, budget config, and cost alert tables."""

    # Create token_usage table
    op.create_table(
        'token_usage',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('request_id', sa.String(100), nullable=True, index=True),
        sa.Column('trace_id', sa.String(100), nullable=True, index=True),
        sa.Column('execution_id', sa.String(36), nullable=True, index=True),
        sa.Column('user_id', sa.String(36), nullable=True, index=True),
        sa.Column('project_id', sa.String(36), nullable=True, index=True),
        sa.Column('service_name', sa.String(100), nullable=True, index=True),
        sa.Column('endpoint', sa.String(255), nullable=True, index=True),
        sa.Column('agent_type', sa.String(50), nullable=True, index=True),
        sa.Column('provider', sa.String(50), nullable=False, index=True),
        sa.Column('model', sa.String(100), nullable=False, index=True),
        sa.Column('model_version', sa.String(100), nullable=True),
        sa.Column('input_tokens', sa.Integer, nullable=False, default=0),
        sa.Column('output_tokens', sa.Integer, nullable=False, default=0),
        sa.Column('total_tokens', sa.Integer, nullable=False, default=0),
        sa.Column('cached_tokens', sa.Integer, nullable=True, default=0),
        sa.Column('input_cost', sa.Float, nullable=False, default=0.0),
        sa.Column('output_cost', sa.Float, nullable=False, default=0.0),
        sa.Column('total_cost', sa.Float, nullable=False, default=0.0, index=True),
        sa.Column('currency', sa.String(3), default='USD'),
        sa.Column('input_price_per_million', sa.Float, nullable=True),
        sa.Column('output_price_per_million', sa.Float, nullable=True),
        sa.Column('prompt_length', sa.Integer, nullable=True),
        sa.Column('completion_length', sa.Integer, nullable=True),
        sa.Column('duration_ms', sa.Float, nullable=True),
        sa.Column('success', sa.Boolean, nullable=False, default=True, index=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('budget_id', sa.String(36), nullable=True, index=True),
        sa.Column('budget_exceeded', sa.Boolean, default=False, index=True),
        sa.Column('fallback_used', sa.Boolean, default=False, index=True),
        sa.Column('original_provider', sa.String(50), nullable=True),
        sa.Column('original_model', sa.String(100), nullable=True),
        sa.Column('json_mode', sa.Boolean, default=False),
        sa.Column('temperature', sa.Float, nullable=True),
        sa.Column('max_tokens_requested', sa.Integer, nullable=True),
        sa.Column('date', sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column('hour', sa.Integer, nullable=True, index=True),
        sa.Column('day_of_week', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.ForeignKeyConstraint(['execution_id'], ['executions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
    )

    # Create composite indexes for token_usage
    op.create_index('idx_token_usage_user_date', 'token_usage', ['user_id', 'date', 'total_cost'])
    op.create_index('idx_token_usage_project_date', 'token_usage', ['project_id', 'date', 'total_cost'])
    op.create_index('idx_token_usage_provider_model', 'token_usage', ['provider', 'model', 'date'])
    op.create_index('idx_token_usage_service', 'token_usage', ['service_name', 'endpoint', 'date'])
    op.create_index('idx_token_usage_hourly', 'token_usage', ['date', 'hour', 'total_cost'])
    op.create_index('idx_token_usage_budget', 'token_usage', ['budget_id', 'date', 'budget_exceeded'])
    op.create_index('idx_token_usage_fallback', 'token_usage', ['fallback_used', 'original_provider', 'date'])
    op.create_index('idx_token_usage_success', 'token_usage', ['success', 'provider', 'date'])

    # Create budget_configs table
    op.create_table(
        'budget_configs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('budget_name', sa.String(255), nullable=False),
        sa.Column('budget_type', sa.String(50), nullable=False, index=True),
        sa.Column('scope_id', sa.String(36), nullable=True, index=True),
        sa.Column('user_id', sa.String(36), nullable=True, index=True),
        sa.Column('project_id', sa.String(36), nullable=True, index=True),
        sa.Column('limit_type', sa.String(50), nullable=False, index=True),
        sa.Column('limit_period', sa.String(50), nullable=False, index=True),
        sa.Column('limit_value', sa.Float, nullable=False),
        sa.Column('currency', sa.String(3), default='USD'),
        sa.Column('warning_threshold', sa.Float, default=0.8),
        sa.Column('critical_threshold', sa.Float, default=0.95),
        sa.Column('hard_limit_enabled', sa.Boolean, default=True),
        sa.Column('block_on_exceeded', sa.Boolean, default=False),
        sa.Column('enable_fallback', sa.Boolean, default=True),
        sa.Column('fallback_provider', sa.String(50), nullable=True),
        sa.Column('fallback_model', sa.String(100), nullable=True),
        sa.Column('fallback_threshold', sa.Float, default=0.9),
        sa.Column('allowed_providers', postgresql.JSON, nullable=True),
        sa.Column('allowed_models', postgresql.JSON, nullable=True),
        sa.Column('blocked_providers', postgresql.JSON, nullable=True),
        sa.Column('blocked_models', postgresql.JSON, nullable=True),
        sa.Column('prefer_cheaper_models', sa.Boolean, default=False),
        sa.Column('max_cost_per_request', sa.Float, nullable=True),
        sa.Column('enable_spike_detection', sa.Boolean, default=True),
        sa.Column('spike_threshold_multiplier', sa.Float, default=3.0),
        sa.Column('spike_window_hours', sa.Integer, default=1),
        sa.Column('auto_reset', sa.Boolean, default=True),
        sa.Column('last_reset_at', sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column('next_reset_at', sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column('current_usage', sa.Float, default=0.0),
        sa.Column('current_percentage', sa.Float, default=0.0, index=True),
        sa.Column('alert_on_warning', sa.Boolean, default=True),
        sa.Column('alert_on_critical', sa.Boolean, default=True),
        sa.Column('alert_on_exceeded', sa.Boolean, default=True),
        sa.Column('alert_on_spike', sa.Boolean, default=True),
        sa.Column('alert_channels', postgresql.JSON, nullable=True),
        sa.Column('alert_recipients', postgresql.JSON, nullable=True),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False, index=True),
        sa.Column('is_enforced', sa.Boolean, default=True, nullable=False),
        sa.Column('suspended_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('created_by', sa.String(100), nullable=True),
        sa.Column('approved_by', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    )

    # Create composite indexes for budget_configs
    op.create_index('idx_budget_type_active', 'budget_configs', ['budget_type', 'is_active', 'is_enforced'])
    op.create_index('idx_budget_user', 'budget_configs', ['user_id', 'is_active'])
    op.create_index('idx_budget_project', 'budget_configs', ['project_id', 'is_active'])
    op.create_index('idx_budget_scope', 'budget_configs', ['budget_type', 'scope_id', 'is_active'])
    op.create_index('idx_budget_usage', 'budget_configs', ['current_percentage', 'is_active'])
    op.create_index('idx_budget_reset', 'budget_configs', ['next_reset_at', 'auto_reset', 'is_active'])
    op.create_index('idx_budget_unique', 'budget_configs', ['budget_type', 'scope_id', 'limit_period'], unique=True)

    # Add foreign key from token_usage to budget_configs
    op.create_foreign_key(
        'fk_token_usage_budget_id',
        'token_usage', 'budget_configs',
        ['budget_id'], ['id'],
        ondelete='SET NULL'
    )

    # Create cost_alerts table
    op.create_table(
        'cost_alerts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('alert_type', sa.String(50), nullable=False, index=True),
        sa.Column('severity', sa.String(20), nullable=False, index=True),
        sa.Column('status', sa.String(50), nullable=False, index=True),
        sa.Column('budget_id', sa.String(36), nullable=True, index=True),
        sa.Column('user_id', sa.String(36), nullable=True, index=True),
        sa.Column('project_id', sa.String(36), nullable=True, index=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('message', sa.Text, nullable=False),
        sa.Column('details', postgresql.JSON, nullable=True),
        sa.Column('budget_limit', sa.Float, nullable=True),
        sa.Column('current_usage', sa.Float, nullable=True),
        sa.Column('usage_percentage', sa.Float, nullable=True, index=True),
        sa.Column('threshold_exceeded', sa.String(50), nullable=True),
        sa.Column('is_spike', sa.Boolean, default=False, index=True),
        sa.Column('baseline_cost', sa.Float, nullable=True),
        sa.Column('spike_cost', sa.Float, nullable=True),
        sa.Column('spike_multiplier', sa.Float, nullable=True),
        sa.Column('tokens_used', sa.Integer, nullable=True),
        sa.Column('cost_incurred', sa.Float, nullable=True),
        sa.Column('provider', sa.String(50), nullable=True, index=True),
        sa.Column('model', sa.String(100), nullable=True),
        sa.Column('action_taken', sa.String(100), nullable=True),
        sa.Column('fallback_triggered', sa.Boolean, default=False),
        sa.Column('request_blocked', sa.Boolean, default=False),
        sa.Column('notifications_sent', postgresql.JSON, nullable=True),
        sa.Column('notification_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notification_success', sa.Boolean, nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_by', sa.String(100), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column('resolved_by', sa.String(100), nullable=True),
        sa.Column('resolution_notes', sa.Text, nullable=True),
        sa.Column('auto_resolved', sa.Boolean, default=False),
        sa.Column('auto_resolved_reason', sa.String(255), nullable=True),
        sa.Column('alert_hash', sa.String(64), nullable=True, index=True),
        sa.Column('duplicate_count', sa.Integer, default=1),
        sa.Column('last_occurrence', sa.DateTime(timezone=True), nullable=True),
        sa.Column('triggered_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['budget_id'], ['budget_configs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
    )

    # Create composite indexes for cost_alerts
    op.create_index('idx_alert_type_status', 'cost_alerts', ['alert_type', 'status', 'triggered_at'])
    op.create_index('idx_alert_user', 'cost_alerts', ['user_id', 'status', 'triggered_at'])
    op.create_index('idx_alert_project', 'cost_alerts', ['project_id', 'status', 'triggered_at'])
    op.create_index('idx_alert_budget', 'cost_alerts', ['budget_id', 'status', 'triggered_at'])
    op.create_index('idx_alert_spike', 'cost_alerts', ['is_spike', 'status', 'triggered_at'])
    op.create_index('idx_alert_severity', 'cost_alerts', ['severity', 'status', 'triggered_at'])
    op.create_index('idx_alert_dedup', 'cost_alerts', ['alert_hash', 'status', 'triggered_at'])
    op.create_index('idx_alert_unresolved', 'cost_alerts', ['status', 'severity', 'triggered_at'])


def downgrade():
    """Drop token usage, budget config, and cost alert tables."""

    # Drop cost_alerts table and indexes
    op.drop_index('idx_alert_unresolved', 'cost_alerts')
    op.drop_index('idx_alert_dedup', 'cost_alerts')
    op.drop_index('idx_alert_severity', 'cost_alerts')
    op.drop_index('idx_alert_spike', 'cost_alerts')
    op.drop_index('idx_alert_budget', 'cost_alerts')
    op.drop_index('idx_alert_project', 'cost_alerts')
    op.drop_index('idx_alert_user', 'cost_alerts')
    op.drop_index('idx_alert_type_status', 'cost_alerts')
    op.drop_table('cost_alerts')

    # Drop foreign key and indexes from token_usage
    op.drop_constraint('fk_token_usage_budget_id', 'token_usage', type_='foreignkey')
    op.drop_index('idx_token_usage_success', 'token_usage')
    op.drop_index('idx_token_usage_fallback', 'token_usage')
    op.drop_index('idx_token_usage_budget', 'token_usage')
    op.drop_index('idx_token_usage_hourly', 'token_usage')
    op.drop_index('idx_token_usage_service', 'token_usage')
    op.drop_index('idx_token_usage_provider_model', 'token_usage')
    op.drop_index('idx_token_usage_project_date', 'token_usage')
    op.drop_index('idx_token_usage_user_date', 'token_usage')

    # Drop budget_configs table and indexes
    op.drop_index('idx_budget_unique', 'budget_configs')
    op.drop_index('idx_budget_reset', 'budget_configs')
    op.drop_index('idx_budget_usage', 'budget_configs')
    op.drop_index('idx_budget_scope', 'budget_configs')
    op.drop_index('idx_budget_project', 'budget_configs')
    op.drop_index('idx_budget_user', 'budget_configs')
    op.drop_index('idx_budget_type_active', 'budget_configs')
    op.drop_table('budget_configs')

    # Drop token_usage table
    op.drop_table('token_usage')
