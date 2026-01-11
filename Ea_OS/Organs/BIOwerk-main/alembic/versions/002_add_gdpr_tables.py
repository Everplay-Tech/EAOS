"""Add GDPR compliance tables

Revision ID: 002_gdpr_tables
Revises: 001_audit_logs
Create Date: 2025-11-16

Adds comprehensive GDPR compliance tables:
- consent_records: User consent tracking (Article 7)
- data_requests: DSAR management (Articles 15, 17, 20)
- data_retention_policies: Retention rules (Article 5)
- privacy_settings: User privacy preferences
- cookie_consents: Cookie consent tracking
- data_breach_incidents: Breach notification tracking (Articles 33/34)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


# revision identifiers, used by Alembic.
revision = '002_gdpr_tables'
down_revision = '001_audit_logs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create GDPR compliance tables."""

    # ========================================================================
    # Consent Records Table (GDPR Article 7)
    # ========================================================================
    op.create_table(
        'consent_records',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),

        # Consent details
        sa.Column('purpose', sa.String(100), nullable=False),
        sa.Column('purpose_description', sa.Text, nullable=False),
        sa.Column('consent_given', sa.Boolean, nullable=False),
        sa.Column('consent_method', sa.String(50), nullable=False),

        # Legal basis
        sa.Column('legal_basis', sa.String(50), nullable=False),
        sa.Column('consent_category', sa.String(50), nullable=False),

        # Withdrawal tracking
        sa.Column('withdrawn_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('withdrawal_method', sa.String(50), nullable=True),

        # Audit trail
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.Text, nullable=True),
        sa.Column('consent_version', sa.String(20), nullable=False),

        # Expiration
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),

        # Timestamps
        sa.Column('granted_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Indexes for consent_records
    op.create_index('idx_consent_user_id', 'consent_records', ['user_id'])
    op.create_index('idx_consent_purpose', 'consent_records', ['purpose'])
    op.create_index('idx_consent_given', 'consent_records', ['consent_given'])
    op.create_index('idx_consent_category', 'consent_records', ['consent_category'])
    op.create_index('idx_consent_withdrawn_at', 'consent_records', ['withdrawn_at'])
    op.create_index('idx_consent_expires_at', 'consent_records', ['expires_at'])
    op.create_index('idx_consent_granted_at', 'consent_records', ['granted_at'])

    # Composite indexes
    op.create_index('idx_consent_user_purpose', 'consent_records', ['user_id', 'purpose', 'consent_given'])
    op.create_index('idx_consent_active', 'consent_records', ['user_id', 'consent_given', 'withdrawn_at'])
    op.create_index('idx_consent_category_given', 'consent_records', ['consent_category', 'consent_given'])
    op.create_index('idx_consent_expiration', 'consent_records', ['expires_at', 'consent_given'])

    # ========================================================================
    # Data Requests Table (GDPR Articles 15, 17, 20)
    # ========================================================================
    op.create_table(
        'data_requests',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),

        # Request details
        sa.Column('request_type', sa.String(50), nullable=False),
        sa.Column('request_status', sa.String(50), nullable=False),
        sa.Column('priority', sa.String(20), server_default='normal'),

        # Metadata
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('requested_data_types', JSON, nullable=True),

        # Processing
        sa.Column('assigned_to', sa.String(100), nullable=True),
        sa.Column('rejection_reason', sa.Text, nullable=True),

        # Completion
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_by', sa.String(100), nullable=True),

        # Export details
        sa.Column('export_format', sa.String(20), nullable=True),
        sa.Column('export_file_path', sa.String(500), nullable=True),
        sa.Column('export_file_hash', sa.String(64), nullable=True),
        sa.Column('export_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('download_count', sa.Integer, server_default='0'),

        # Erasure details
        sa.Column('erasure_method', sa.String(50), nullable=True),
        sa.Column('data_deleted', JSON, nullable=True),
        sa.Column('anonymization_applied', sa.Boolean, server_default='false'),

        # Legal holds
        sa.Column('legal_hold', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('legal_hold_reason', sa.Text, nullable=True),
        sa.Column('legal_hold_placed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('legal_hold_released_at', sa.DateTime(timezone=True), nullable=True),

        # Verification
        sa.Column('verification_required', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('verification_method', sa.String(50), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('verified_by', sa.String(100), nullable=True),

        # Audit trail
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.Text, nullable=True),

        # SLA tracking
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sla_breached', sa.Boolean, nullable=False, server_default='false'),

        # Timestamps
        sa.Column('requested_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Indexes for data_requests
    op.create_index('idx_data_request_user_id', 'data_requests', ['user_id'])
    op.create_index('idx_data_request_type', 'data_requests', ['request_type'])
    op.create_index('idx_data_request_status', 'data_requests', ['request_status'])
    op.create_index('idx_data_request_completed_at', 'data_requests', ['completed_at'])
    op.create_index('idx_data_request_legal_hold', 'data_requests', ['legal_hold'])
    op.create_index('idx_data_request_due_date', 'data_requests', ['due_date'])
    op.create_index('idx_data_request_sla_breached', 'data_requests', ['sla_breached'])
    op.create_index('idx_data_request_requested_at', 'data_requests', ['requested_at'])

    # Composite indexes
    op.create_index('idx_data_request_user_type_status', 'data_requests', ['user_id', 'request_type', 'request_status'])
    op.create_index('idx_data_request_status_due', 'data_requests', ['request_status', 'due_date'])
    op.create_index('idx_data_request_sla_status', 'data_requests', ['sla_breached', 'request_status'])
    op.create_index('idx_data_request_legal_hold_user', 'data_requests', ['legal_hold', 'user_id'])

    # ========================================================================
    # Data Retention Policies Table (GDPR Article 5)
    # ========================================================================
    op.create_table(
        'data_retention_policies',
        sa.Column('id', sa.String(36), primary_key=True),

        # Policy details
        sa.Column('policy_name', sa.String(255), nullable=False, unique=True),
        sa.Column('data_type', sa.String(100), nullable=False),
        sa.Column('description', sa.Text, nullable=False),

        # Retention rules
        sa.Column('retention_period_days', sa.Integer, nullable=False),
        sa.Column('retention_basis', sa.String(100), nullable=False),

        # Auto-deletion
        sa.Column('auto_delete_enabled', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('delete_method', sa.String(50), nullable=False, server_default='soft_delete'),

        # Exceptions
        sa.Column('legal_hold_exempt', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('minimum_retention_days', sa.Integer, nullable=True),

        # Regulations
        sa.Column('regulations', JSON, nullable=True),

        # Status
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),

        # Archival
        sa.Column('archive_after_days', sa.Integer, nullable=True),
        sa.Column('archive_location', sa.String(255), nullable=True),

        # Approval
        sa.Column('approved_by', sa.String(100), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_review_date', sa.DateTime(timezone=True), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Indexes for data_retention_policies
    op.create_index('idx_retention_policy_name', 'data_retention_policies', ['policy_name'])
    op.create_index('idx_retention_data_type', 'data_retention_policies', ['data_type'])
    op.create_index('idx_retention_is_active', 'data_retention_policies', ['is_active'])
    op.create_index('idx_retention_next_review', 'data_retention_policies', ['next_review_date'])

    # Composite indexes
    op.create_index('idx_retention_data_type_active', 'data_retention_policies', ['data_type', 'is_active'])
    op.create_index('idx_retention_review', 'data_retention_policies', ['next_review_date', 'is_active'])

    # ========================================================================
    # Privacy Settings Table
    # ========================================================================
    op.create_table(
        'privacy_settings',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True),

        # Communication preferences
        sa.Column('email_marketing_enabled', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('email_product_updates', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('email_security_alerts', sa.Boolean, nullable=False, server_default='true'),

        # Data processing preferences
        sa.Column('analytics_enabled', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('personalization_enabled', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('third_party_sharing', sa.Boolean, nullable=False, server_default='false'),

        # AI/ML processing
        sa.Column('ai_training_opt_in', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('profiling_enabled', sa.Boolean, nullable=False, server_default='false'),

        # Data retention preferences
        sa.Column('custom_retention_period', sa.Integer, nullable=True),

        # Export preferences
        sa.Column('preferred_export_format', sa.String(20), server_default='json'),

        # Privacy level
        sa.Column('privacy_level', sa.String(20), server_default='balanced'),

        # Cookie preferences
        sa.Column('essential_cookies', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('functional_cookies', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('analytics_cookies', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('marketing_cookies', sa.Boolean, nullable=False, server_default='false'),

        # Session preferences
        sa.Column('remember_me', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('session_timeout_minutes', sa.Integer, server_default='60'),

        # Data sharing controls
        sa.Column('share_with_partners', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('share_for_research', sa.Boolean, nullable=False, server_default='false'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('last_reviewed_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Indexes for privacy_settings
    op.create_index('idx_privacy_user_id', 'privacy_settings', ['user_id'])

    # ========================================================================
    # Cookie Consents Table
    # ========================================================================
    op.create_table(
        'cookie_consents',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),

        # Session/device identification
        sa.Column('session_id', sa.String(255), nullable=True),
        sa.Column('device_fingerprint', sa.String(64), nullable=True),

        # Consent details
        sa.Column('essential_accepted', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('functional_accepted', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('analytics_accepted', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('marketing_accepted', sa.Boolean, nullable=False, server_default='false'),

        # Metadata
        sa.Column('consent_method', sa.String(50), nullable=False),
        sa.Column('banner_version', sa.String(20), nullable=False),

        # Geolocation
        sa.Column('geo_country', sa.String(2), nullable=True),
        sa.Column('geo_region', sa.String(100), nullable=True),

        # Technical details
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.Text, nullable=True),

        # Expiration
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),

        # Timestamps
        sa.Column('granted_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Indexes for cookie_consents
    op.create_index('idx_cookie_user_id', 'cookie_consents', ['user_id'])
    op.create_index('idx_cookie_session_id', 'cookie_consents', ['session_id'])
    op.create_index('idx_cookie_device', 'cookie_consents', ['device_fingerprint'])
    op.create_index('idx_cookie_expires_at', 'cookie_consents', ['expires_at'])
    op.create_index('idx_cookie_granted_at', 'cookie_consents', ['granted_at'])

    # Composite indexes
    op.create_index('idx_cookie_consent_user', 'cookie_consents', ['user_id', 'granted_at'])
    op.create_index('idx_cookie_consent_session', 'cookie_consents', ['session_id', 'expires_at'])
    op.create_index('idx_cookie_consent_device', 'cookie_consents', ['device_fingerprint', 'expires_at'])

    # ========================================================================
    # Data Breach Incidents Table (GDPR Articles 33/34)
    # ========================================================================
    op.create_table(
        'data_breach_incidents',
        sa.Column('id', sa.String(36), primary_key=True),

        # Incident details
        sa.Column('incident_id', sa.String(50), nullable=False, unique=True),
        sa.Column('severity', sa.String(20), nullable=False),
        sa.Column('status', sa.String(50), nullable=False),

        # Description
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('description', sa.Text, nullable=False),
        sa.Column('root_cause', sa.Text, nullable=True),

        # Classification
        sa.Column('breach_type', sa.String(100), nullable=False),
        sa.Column('attack_vector', sa.String(100), nullable=True),

        # Impact
        sa.Column('affected_user_count', sa.Integer, nullable=True),
        sa.Column('affected_data_types', JSON, nullable=False),
        sa.Column('risk_to_individuals', sa.String(20), nullable=False),
        sa.Column('affected_user_ids', JSON, nullable=True),

        # Containment
        sa.Column('contained_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('containment_measures', sa.Text, nullable=True),

        # Notification requirements
        sa.Column('requires_authority_notification', sa.Boolean, nullable=False),
        sa.Column('requires_individual_notification', sa.Boolean, nullable=False),

        # Authority notification
        sa.Column('authority_notified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('authority_notification_method', sa.String(50), nullable=True),
        sa.Column('authority_reference_number', sa.String(100), nullable=True),
        sa.Column('notification_deadline', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deadline_met', sa.Boolean, nullable=True),

        # Individual notifications
        sa.Column('individuals_notified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('individuals_notification_method', sa.String(50), nullable=True),
        sa.Column('notification_template_id', sa.String(100), nullable=True),

        # Remediation
        sa.Column('remediation_steps', JSON, nullable=True),
        sa.Column('remediation_completed_at', sa.DateTime(timezone=True), nullable=True),

        # Responsible parties
        sa.Column('discovered_by', sa.String(100), nullable=True),
        sa.Column('assigned_to', sa.String(100), nullable=True),
        sa.Column('dpo_notified_at', sa.DateTime(timezone=True), nullable=True),

        # Costs and impact
        sa.Column('estimated_cost', sa.Float, nullable=True),
        sa.Column('downtime_minutes', sa.Integer, nullable=True),

        # Lessons learned
        sa.Column('post_incident_review_completed', sa.Boolean, server_default='false'),
        sa.Column('lessons_learned', sa.Text, nullable=True),
        sa.Column('preventive_measures', JSON, nullable=True),

        # Timestamps
        sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Indexes for data_breach_incidents
    op.create_index('idx_breach_incident_id', 'data_breach_incidents', ['incident_id'])
    op.create_index('idx_breach_severity', 'data_breach_incidents', ['severity'])
    op.create_index('idx_breach_status', 'data_breach_incidents', ['status'])
    op.create_index('idx_breach_detected_at', 'data_breach_incidents', ['detected_at'])
    op.create_index('idx_breach_resolved_at', 'data_breach_incidents', ['resolved_at'])
    op.create_index('idx_breach_requires_auth_notify', 'data_breach_incidents', ['requires_authority_notification'])
    op.create_index('idx_breach_requires_ind_notify', 'data_breach_incidents', ['requires_individual_notification'])
    op.create_index('idx_breach_auth_notified', 'data_breach_incidents', ['authority_notified_at'])
    op.create_index('idx_breach_deadline', 'data_breach_incidents', ['notification_deadline'])
    op.create_index('idx_breach_deadline_met', 'data_breach_incidents', ['deadline_met'])
    op.create_index('idx_breach_contained_at', 'data_breach_incidents', ['contained_at'])

    # Composite indexes
    op.create_index('idx_breach_status_severity', 'data_breach_incidents', ['status', 'severity', 'detected_at'])
    op.create_index('idx_breach_notification', 'data_breach_incidents', ['requires_authority_notification', 'authority_notified_at'])
    op.create_index('idx_breach_deadline_check', 'data_breach_incidents', ['notification_deadline', 'deadline_met'])


def downgrade() -> None:
    """Drop all GDPR compliance tables."""
    op.drop_table('data_breach_incidents')
    op.drop_table('cookie_consents')
    op.drop_table('privacy_settings')
    op.drop_table('data_retention_policies')
    op.drop_table('data_requests')
    op.drop_table('consent_records')
