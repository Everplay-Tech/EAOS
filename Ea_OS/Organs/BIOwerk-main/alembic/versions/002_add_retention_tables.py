"""Add retention policy tables

Revision ID: 002_add_retention_tables
Revises: 001_add_audit_logs_table
Create Date: 2025-11-16

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_add_retention_tables'
down_revision = '001_add_audit_logs_table'
branch_labels = None
depends_on = None


def upgrade():
    """Create retention policy tables"""

    # Create retention_policies table
    op.create_table(
        'retention_policies',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False, unique=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('data_type', sa.String(50), nullable=False),
        sa.Column('category_filter', postgresql.JSON, nullable=True),
        sa.Column('user_filter', postgresql.JSON, nullable=True),
        sa.Column('conditions', postgresql.JSON, nullable=True),
        sa.Column('retention_period_days', sa.Integer, nullable=False),
        sa.Column('action', sa.String(50), nullable=False, server_default='delete'),
        sa.Column('archive_before_delete', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('compliance_framework', sa.String(50), nullable=False),
        sa.Column('regulatory_citation', sa.Text, nullable=True),
        sa.Column('priority', sa.Integer, nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_by', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('last_enforced_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Create indexes for retention_policies
    op.create_index('idx_retention_policy_type', 'retention_policies', ['data_type', 'is_active'])
    op.create_index('idx_retention_policy_framework', 'retention_policies', ['compliance_framework', 'is_active'])
    op.create_index('idx_retention_policy_priority', 'retention_policies', ['priority', 'is_active'])

    # Create retention_schedules table
    op.create_table(
        'retention_schedules',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('data_type', sa.String(50), nullable=False),
        sa.Column('data_id', sa.String(36), nullable=False),
        sa.Column('policy_id', sa.String(36), sa.ForeignKey('retention_policies.id', ondelete='SET NULL'), nullable=True),
        sa.Column('scheduled_for', sa.DateTime(timezone=True), nullable=True),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('legal_hold', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('legal_hold_reason', sa.Text, nullable=True),
        sa.Column('legal_hold_applied_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('legal_hold_applied_by', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('legal_hold_removed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('legal_hold_removed_by', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Create indexes for retention_schedules
    op.create_index('idx_retention_schedule_data', 'retention_schedules', ['data_type', 'data_id'])
    op.create_index('idx_retention_schedule_pending', 'retention_schedules', ['status', 'scheduled_for'])
    op.create_index('idx_retention_schedule_hold', 'retention_schedules', ['legal_hold', 'data_type'])

    # Create data_archives table
    op.create_table(
        'data_archives',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('data_type', sa.String(50), nullable=False),
        sa.Column('data_id', sa.String(36), nullable=False),
        sa.Column('policy_id', sa.String(36), sa.ForeignKey('retention_policies.id', ondelete='SET NULL'), nullable=True),
        sa.Column('archived_data', postgresql.JSON, nullable=False),
        sa.Column('data_hash', sa.String(64), nullable=False),
        sa.Column('encryption_key_version', sa.Integer, nullable=True),
        sa.Column('archive_reason', sa.String(100), server_default='retention_policy'),
        sa.Column('archive_status', sa.String(50), nullable=False, server_default='completed'),
        sa.Column('restored_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('restored_by_user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('archived_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Create indexes for data_archives
    op.create_index('idx_archive_data', 'data_archives', ['data_type', 'data_id'])
    op.create_index('idx_archive_status', 'data_archives', ['archive_status', 'archived_at'])
    op.create_index('idx_archive_expiration', 'data_archives', ['expires_at'])

    # Create retention_audit_logs table
    op.create_table(
        'retention_audit_logs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('data_type', sa.String(50), nullable=False),
        sa.Column('data_id', sa.String(36), nullable=False),
        sa.Column('policy_id', sa.String(36), sa.ForeignKey('retention_policies.id', ondelete='SET NULL'), nullable=True),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('archive_id', sa.String(36), sa.ForeignKey('data_archives.id', ondelete='SET NULL'), nullable=True),
        sa.Column('executed_by', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('execution_type', sa.String(50), server_default='automated'),
        sa.Column('executed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Create indexes for retention_audit_logs
    op.create_index('idx_retention_audit_action', 'retention_audit_logs', ['action', 'executed_at'])
    op.create_index('idx_retention_audit_data', 'retention_audit_logs', ['data_type', 'data_id'])
    op.create_index('idx_retention_audit_policy', 'retention_audit_logs', ['policy_id', 'executed_at'])
    op.create_index('idx_retention_audit_status', 'retention_audit_logs', ['status', 'executed_at'])


def downgrade():
    """Drop retention policy tables"""

    # Drop tables in reverse order (to respect foreign keys)
    op.drop_table('retention_audit_logs')
    op.drop_table('data_archives')
    op.drop_table('retention_schedules')
    op.drop_table('retention_policies')
