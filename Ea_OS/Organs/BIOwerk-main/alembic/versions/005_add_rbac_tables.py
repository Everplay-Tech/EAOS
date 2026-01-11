"""Add RBAC (Role-Based Access Control) tables

Revision ID: 005_add_rbac_tables
Revises: 004_add_token_budget_tables
Create Date: 2025-01-16

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '005_add_rbac_tables'
down_revision = '004_add_token_budget_tables'
branch_labels = None
depends_on = None


def upgrade():
    """Create RBAC tables for comprehensive role-based access control."""

    # Create roles table
    op.create_table(
        'roles',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(50), unique=True, nullable=False, index=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('is_system_role', sa.Boolean, default=False, nullable=False),
        sa.Column('is_default', sa.Boolean, default=False, nullable=False),
        sa.Column('priority', sa.Integer, default=0, nullable=False),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Create permissions table
    op.create_table(
        'permissions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('action', sa.String(50), nullable=False, index=True),
        sa.Column('resource_type', sa.String(50), nullable=False, index=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('scope', sa.String(50), default='resource', nullable=False),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Create composite indexes for permissions
    op.create_index('idx_permission_unique', 'permissions', ['action', 'resource_type'], unique=True)
    op.create_index('idx_permission_scope', 'permissions', ['scope', 'is_active'])

    # Create role_permissions table
    op.create_table(
        'role_permissions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('role_id', sa.String(36), nullable=False, index=True),
        sa.Column('permission_id', sa.String(36), nullable=False, index=True),
        sa.Column('resource_id', sa.String(36), nullable=True, index=True),
        sa.Column('conditions', postgresql.JSON, nullable=True),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False, index=True),
        sa.Column('granted_by', sa.String(100), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='CASCADE'),
    )

    # Create composite indexes for role_permissions
    op.create_index('idx_role_permission_unique', 'role_permissions', ['role_id', 'permission_id', 'resource_id'], unique=True)
    op.create_index('idx_role_permission_active', 'role_permissions', ['role_id', 'is_active'])
    op.create_index('idx_role_permission_expiry', 'role_permissions', ['expires_at', 'is_active'])

    # Create user_roles table
    op.create_table(
        'user_roles',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), nullable=False, index=True),
        sa.Column('role_id', sa.String(36), nullable=False, index=True),
        sa.Column('scope_type', sa.String(50), nullable=True, index=True),
        sa.Column('scope_id', sa.String(36), nullable=True, index=True),
        sa.Column('assigned_by', sa.String(100), nullable=True),
        sa.Column('assignment_reason', sa.Text, nullable=True),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False, index=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
    )

    # Create composite indexes for user_roles
    op.create_index('idx_user_role_unique', 'user_roles', ['user_id', 'role_id', 'scope_type', 'scope_id'], unique=True)
    op.create_index('idx_user_role_active', 'user_roles', ['user_id', 'is_active'])
    op.create_index('idx_user_role_scope', 'user_roles', ['scope_type', 'scope_id', 'is_active'])
    op.create_index('idx_user_role_expiry', 'user_roles', ['expires_at', 'is_active'])

    # Create resource_ownership table
    op.create_table(
        'resource_ownership',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('resource_type', sa.String(50), nullable=False, index=True),
        sa.Column('resource_id', sa.String(36), nullable=False, index=True),
        sa.Column('owner_id', sa.String(36), nullable=False, index=True),
        sa.Column('ownership_type', sa.String(50), default='created', nullable=False),
        sa.Column('transferred_from', sa.String(36), nullable=True),
        sa.Column('transfer_reason', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['transferred_from'], ['users.id'], ondelete='SET NULL'),
    )

    # Create composite indexes for resource_ownership
    op.create_index('idx_resource_unique', 'resource_ownership', ['resource_type', 'resource_id'], unique=True)
    op.create_index('idx_resource_owner', 'resource_ownership', ['owner_id', 'resource_type'])

    # Insert default roles
    op.execute("""
        INSERT INTO roles (id, name, description, is_system_role, is_default, priority, is_active)
        VALUES
            ('role-admin', 'admin', 'Administrator with full system access', true, false, 100, true),
            ('role-user', 'user', 'Standard user with read/write access to own resources', true, true, 50, true),
            ('role-viewer', 'viewer', 'Read-only access to permitted resources', true, false, 25, true),
            ('role-service', 'service_account', 'Service account for automated processes', true, false, 75, true)
    """)

    # Insert default permissions
    op.execute("""
        INSERT INTO permissions (id, action, resource_type, description, scope, is_active)
        VALUES
            -- Global permissions
            ('perm-admin-global', 'admin', 'global', 'Full administrative access to all resources', 'global', true),

            -- Project permissions
            ('perm-read-project', 'read', 'project', 'Read access to projects', 'resource', true),
            ('perm-write-project', 'write', 'project', 'Create and modify projects', 'resource', true),
            ('perm-delete-project', 'delete', 'project', 'Delete projects', 'resource', true),
            ('perm-admin-project', 'admin', 'project', 'Full administrative access to projects', 'resource', true),

            -- Artifact permissions
            ('perm-read-artifact', 'read', 'artifact', 'Read access to artifacts', 'resource', true),
            ('perm-write-artifact', 'write', 'artifact', 'Create and modify artifacts', 'resource', true),
            ('perm-delete-artifact', 'delete', 'artifact', 'Delete artifacts', 'resource', true),
            ('perm-admin-artifact', 'admin', 'artifact', 'Full administrative access to artifacts', 'resource', true),

            -- Execution permissions
            ('perm-read-execution', 'read', 'execution', 'Read access to execution logs', 'resource', true),
            ('perm-write-execution', 'write', 'execution', 'Create execution records', 'resource', true),
            ('perm-delete-execution', 'delete', 'execution', 'Delete execution records', 'resource', true),
            ('perm-admin-execution', 'admin', 'execution', 'Full administrative access to executions', 'resource', true),

            -- User permissions
            ('perm-read-user', 'read', 'user', 'Read user information', 'resource', true),
            ('perm-write-user', 'write', 'user', 'Create and modify users', 'resource', true),
            ('perm-delete-user', 'delete', 'user', 'Delete users', 'resource', true),
            ('perm-admin-user', 'admin', 'user', 'Full administrative access to users', 'resource', true),

            -- API Key permissions
            ('perm-read-apikey', 'read', 'api_key', 'Read API keys', 'resource', true),
            ('perm-write-apikey', 'write', 'api_key', 'Create and modify API keys', 'resource', true),
            ('perm-delete-apikey', 'delete', 'api_key', 'Delete API keys', 'resource', true),
            ('perm-admin-apikey', 'admin', 'api_key', 'Full administrative access to API keys', 'resource', true)
    """)

    # Assign permissions to admin role (all permissions)
    op.execute("""
        INSERT INTO role_permissions (id, role_id, permission_id, is_active)
        SELECT
            'rp-admin-' || substr(id, 6),
            'role-admin',
            id,
            true
        FROM permissions
    """)

    # Assign permissions to user role (read/write on project, artifact, execution)
    op.execute("""
        INSERT INTO role_permissions (id, role_id, permission_id, is_active)
        VALUES
            ('rp-user-read-project', 'role-user', 'perm-read-project', true),
            ('rp-user-write-project', 'role-user', 'perm-write-project', true),
            ('rp-user-read-artifact', 'role-user', 'perm-read-artifact', true),
            ('rp-user-write-artifact', 'role-user', 'perm-write-artifact', true),
            ('rp-user-read-execution', 'role-user', 'perm-read-execution', true),
            ('rp-user-write-execution', 'role-user', 'perm-write-execution', true)
    """)

    # Assign permissions to viewer role (read-only)
    op.execute("""
        INSERT INTO role_permissions (id, role_id, permission_id, is_active)
        VALUES
            ('rp-viewer-read-project', 'role-viewer', 'perm-read-project', true),
            ('rp-viewer-read-artifact', 'role-viewer', 'perm-read-artifact', true),
            ('rp-viewer-read-execution', 'role-viewer', 'perm-read-execution', true)
    """)

    # Assign permissions to service_account role (read/write on artifact, execution)
    op.execute("""
        INSERT INTO role_permissions (id, role_id, permission_id, is_active)
        VALUES
            ('rp-service-read-artifact', 'role-service', 'perm-read-artifact', true),
            ('rp-service-write-artifact', 'role-service', 'perm-write-artifact', true),
            ('rp-service-read-execution', 'role-service', 'perm-read-execution', true),
            ('rp-service-write-execution', 'role-service', 'perm-write-execution', true)
    """)


def downgrade():
    """Drop RBAC tables."""

    # Drop resource_ownership table and indexes
    op.drop_index('idx_resource_owner', 'resource_ownership')
    op.drop_index('idx_resource_unique', 'resource_ownership')
    op.drop_table('resource_ownership')

    # Drop user_roles table and indexes
    op.drop_index('idx_user_role_expiry', 'user_roles')
    op.drop_index('idx_user_role_scope', 'user_roles')
    op.drop_index('idx_user_role_active', 'user_roles')
    op.drop_index('idx_user_role_unique', 'user_roles')
    op.drop_table('user_roles')

    # Drop role_permissions table and indexes
    op.drop_index('idx_role_permission_expiry', 'role_permissions')
    op.drop_index('idx_role_permission_active', 'role_permissions')
    op.drop_index('idx_role_permission_unique', 'role_permissions')
    op.drop_table('role_permissions')

    # Drop permissions table and indexes
    op.drop_index('idx_permission_scope', 'permissions')
    op.drop_index('idx_permission_unique', 'permissions')
    op.drop_table('permissions')

    # Drop roles table
    op.drop_table('roles')
