"""Add audit_logs table with encryption support

Revision ID: 001_audit_logs
Revises:
Create Date: 2025-11-16

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


# revision identifiers, used by Alembic.
revision = '001_audit_logs'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the audit_logs table with comprehensive tracking and encryption support."""

    op.create_table(
        'audit_logs',
        # Primary identifiers
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('event_id', sa.String(36), nullable=False, unique=True),

        # Event classification
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('event_category', sa.String(50), nullable=False),
        sa.Column('event_action', sa.String(100), nullable=False),
        sa.Column('event_status', sa.String(20), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False, server_default='INFO'),

        # Actor (who performed the action)
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('username', sa.String(100), nullable=True),
        sa.Column('actor_type', sa.String(50), server_default='user'),

        # Subject (what was acted upon)
        sa.Column('resource_type', sa.String(100), nullable=True),
        sa.Column('resource_id', sa.String(36), nullable=True),
        sa.Column('resource_name', sa.String(500), nullable=True),

        # Request context
        sa.Column('service_name', sa.String(100), nullable=True),
        sa.Column('endpoint', sa.String(255), nullable=True),
        sa.Column('http_method', sa.String(10), nullable=True),
        sa.Column('http_status_code', sa.Integer, nullable=True),

        # Network context
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('ip_address_hash', sa.String(64), nullable=True),
        sa.Column('user_agent', sa.Text, nullable=True),
        sa.Column('user_agent_hash', sa.String(64), nullable=True),

        # Session context
        sa.Column('session_id', sa.String(255), nullable=True),
        sa.Column('trace_id', sa.String(100), nullable=True),
        sa.Column('request_id', sa.String(100), nullable=True),

        # Geolocation context
        sa.Column('geo_country', sa.String(2), nullable=True),
        sa.Column('geo_region', sa.String(100), nullable=True),
        sa.Column('geo_city', sa.String(100), nullable=True),

        # Data changes (plaintext or encrypted based on configuration)
        sa.Column('changes_before', JSON, nullable=True),
        sa.Column('changes_after', JSON, nullable=True),
        sa.Column('request_data', JSON, nullable=True),
        sa.Column('response_data', JSON, nullable=True),

        # Encrypted sensitive fields
        sa.Column('changes_before_encrypted', JSON, nullable=True),
        sa.Column('changes_after_encrypted', JSON, nullable=True),
        sa.Column('request_data_encrypted', JSON, nullable=True),
        sa.Column('response_data_encrypted', JSON, nullable=True),
        sa.Column('ip_address_encrypted', JSON, nullable=True),
        sa.Column('user_agent_encrypted', JSON, nullable=True),

        # Error details
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('error_code', sa.String(100), nullable=True),
        sa.Column('error_stack_trace', sa.Text, nullable=True),

        # Performance metrics
        sa.Column('duration_ms', sa.Float, nullable=True),

        # Security context
        sa.Column('authentication_method', sa.String(50), nullable=True),
        sa.Column('authorization_result', sa.String(50), nullable=True),
        sa.Column('risk_score', sa.Integer, nullable=True),

        # Compliance and retention
        sa.Column('retention_period_days', sa.Integer, nullable=True),
        sa.Column('is_archived', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),

        # Cryptographic integrity
        sa.Column('record_hash', sa.String(64), nullable=True),
        sa.Column('encryption_key_version', sa.Integer, nullable=True),

        # Timestamps
        sa.Column('event_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Create indexes for common query patterns
    op.create_index('idx_audit_event_id', 'audit_logs', ['event_id'])
    op.create_index('idx_audit_event_type', 'audit_logs', ['event_type'])
    op.create_index('idx_audit_event_category', 'audit_logs', ['event_category'])
    op.create_index('idx_audit_event_action', 'audit_logs', ['event_action'])
    op.create_index('idx_audit_event_status', 'audit_logs', ['event_status'])
    op.create_index('idx_audit_severity', 'audit_logs', ['severity'])
    op.create_index('idx_audit_user_id', 'audit_logs', ['user_id'])
    op.create_index('idx_audit_resource_type', 'audit_logs', ['resource_type'])
    op.create_index('idx_audit_resource_id', 'audit_logs', ['resource_id'])
    op.create_index('idx_audit_service_name', 'audit_logs', ['service_name'])
    op.create_index('idx_audit_endpoint', 'audit_logs', ['endpoint'])
    op.create_index('idx_audit_ip_address', 'audit_logs', ['ip_address'])
    op.create_index('idx_audit_ip_address_hash', 'audit_logs', ['ip_address_hash'])
    op.create_index('idx_audit_user_agent_hash', 'audit_logs', ['user_agent_hash'])
    op.create_index('idx_audit_session_id', 'audit_logs', ['session_id'])
    op.create_index('idx_audit_trace_id', 'audit_logs', ['trace_id'])
    op.create_index('idx_audit_request_id', 'audit_logs', ['request_id'])
    op.create_index('idx_audit_is_archived', 'audit_logs', ['is_archived'])
    op.create_index('idx_audit_event_timestamp', 'audit_logs', ['event_timestamp'])
    op.create_index('idx_audit_created_at', 'audit_logs', ['created_at'])

    # Composite indexes for common query patterns
    op.create_index('idx_audit_user_time', 'audit_logs', ['user_id', 'event_timestamp'])
    op.create_index('idx_audit_event_status_time', 'audit_logs', ['event_type', 'event_status', 'event_timestamp'])
    op.create_index('idx_audit_resource', 'audit_logs', ['resource_type', 'resource_id', 'event_timestamp'])
    op.create_index('idx_audit_service', 'audit_logs', ['service_name', 'endpoint', 'event_timestamp'])
    op.create_index('idx_audit_security', 'audit_logs', ['event_category', 'severity', 'event_timestamp'])
    op.create_index('idx_audit_ip', 'audit_logs', ['ip_address', 'event_timestamp'])
    op.create_index('idx_audit_session', 'audit_logs', ['session_id', 'event_timestamp'])
    op.create_index('idx_audit_archive', 'audit_logs', ['is_archived', 'created_at'])
    op.create_index('idx_audit_compliance', 'audit_logs', ['event_category', 'event_action', 'user_id', 'event_timestamp'])


def downgrade() -> None:
    """Drop the audit_logs table and all its indexes."""
    op.drop_table('audit_logs')
