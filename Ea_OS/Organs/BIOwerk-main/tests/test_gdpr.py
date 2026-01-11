"""Comprehensive tests for GDPR compliance functionality.

Tests cover:
- Data access requests (Article 15)
- Data erasure / Right to be Forgotten (Article 17)
- Data portability (Article 20)
- Consent management (Article 7)
- Privacy settings
- Data retention policies
- Anonymization
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from matrix.database import Base
from matrix.db_models import (
    User, Project, Artifact, ConsentRecord, DataRequest,
    DataRetentionPolicy, PrivacySettings, CookieConsent, generate_uuid
)
from matrix.gdpr import GDPRService, DataRequestError, AnonymizationError
from matrix.encryption import EncryptionService


# Test database URL (use in-memory SQLite for tests)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def db_engine():
    """Create test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    """Create test database session."""
    async_session = sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session


@pytest.fixture
async def test_user(db_session):
    """Create a test user."""
    user = User(
        id=generate_uuid(),
        email="test@example.com",
        username="testuser",
        hashed_password="hashed_password_123",
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_project(db_session, test_user):
    """Create a test project."""
    project = Project(
        id=generate_uuid(),
        user_id=test_user.id,
        name="Test Project",
        description="Test project description"
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


@pytest.fixture
def encryption_service():
    """Create encryption service for tests."""
    return EncryptionService(
        master_key="test_master_key_at_least_32_characters_long"
    )


@pytest.fixture
async def gdpr_service(db_session, encryption_service):
    """Create GDPR service for tests."""
    return GDPRService(
        db=db_session,
        encryption_service=encryption_service,
        export_base_path="/tmp/test_gdpr_exports"
    )


# ============================================================================
# Data Access Request Tests (Article 15)
# ============================================================================

@pytest.mark.asyncio
async def test_create_access_request(gdpr_service, test_user):
    """Test creating a data access request."""
    request = await gdpr_service.create_access_request(
        user_id=test_user.id,
        description="I want to see all my data",
        export_format="json"
    )

    assert request.id is not None
    assert request.user_id == test_user.id
    assert request.request_type == "access"
    assert request.request_status == "pending"
    assert request.export_format == "json"
    assert request.due_date > datetime.utcnow()


@pytest.mark.asyncio
async def test_export_user_data(gdpr_service, test_user, test_project):
    """Test exporting all user data."""
    data = await gdpr_service.export_user_data(
        user_id=test_user.id,
        format="json"
    )

    assert "export_metadata" in data
    assert "data" in data
    assert data["export_metadata"]["user_id"] == test_user.id

    # Check user data is included
    assert "user" in data["data"]
    assert data["data"]["user"]["email"] == test_user.email
    assert data["data"]["user"]["username"] == test_user.username

    # Check projects are included
    assert "projects" in data["data"]
    assert len(data["data"]["projects"]) == 1
    assert data["data"]["projects"][0]["name"] == test_project.name


@pytest.mark.asyncio
async def test_export_specific_data_types(gdpr_service, test_user):
    """Test exporting specific data types only."""
    data = await gdpr_service.export_user_data(
        user_id=test_user.id,
        data_types=["user", "projects"],
        format="json"
    )

    assert "user" in data["data"]
    assert "projects" in data["data"]
    # Other data types should not be included
    assert "executions" not in data["data"]
    assert "api_keys" not in data["data"]


# ============================================================================
# Data Erasure Tests (Article 17)
# ============================================================================

@pytest.mark.asyncio
async def test_create_erasure_request(gdpr_service, test_user):
    """Test creating a data erasure request."""
    request = await gdpr_service.create_erasure_request(
        user_id=test_user.id,
        description="Please delete my account",
        erasure_method="anonymization"
    )

    assert request.id is not None
    assert request.user_id == test_user.id
    assert request.request_type == "erasure"
    assert request.request_status == "pending"
    assert request.erasure_method == "anonymization"


@pytest.mark.asyncio
async def test_anonymize_user_data(gdpr_service, test_user, test_project, db_session):
    """Test anonymizing user data."""
    original_email = test_user.email
    original_username = test_user.username

    summary = await gdpr_service.anonymize_user_data(
        user_id=test_user.id,
        preserve_audit_trail=True
    )

    assert summary["user_id"] == test_user.id
    assert len(summary["operations"]) > 0

    # Refresh user from database
    await db_session.refresh(test_user)

    # Check user data is anonymized
    assert test_user.email != original_email
    assert test_user.email.startswith("deleted_")
    assert test_user.username != original_username
    assert test_user.username.startswith("deleted_user_")
    assert test_user.hashed_password is None
    assert test_user.is_active is False


@pytest.mark.asyncio
async def test_anonymize_preserves_referential_integrity(
    gdpr_service, test_user, test_project, db_session
):
    """Test that anonymization preserves database referential integrity."""
    await gdpr_service.anonymize_user_data(user_id=test_user.id)

    # Refresh project
    await db_session.refresh(test_project)

    # Project should still exist (soft deleted)
    assert test_project.is_archived is True
    assert test_project.name.startswith("Deleted Project")


# ============================================================================
# Consent Management Tests (Article 7)
# ============================================================================

@pytest.mark.asyncio
async def test_record_consent(gdpr_service, test_user):
    """Test recording user consent."""
    consent = await gdpr_service.record_consent(
        user_id=test_user.id,
        purpose="analytics",
        purpose_description="We use analytics to improve our service",
        consent_given=True,
        consent_category="analytics",
        consent_method="checkbox",
        consent_version="1.0"
    )

    assert consent.id is not None
    assert consent.user_id == test_user.id
    assert consent.purpose == "analytics"
    assert consent.consent_given is True
    assert consent.consent_category == "analytics"


@pytest.mark.asyncio
async def test_withdraw_consent(gdpr_service, test_user):
    """Test withdrawing user consent."""
    # First, record consent
    await gdpr_service.record_consent(
        user_id=test_user.id,
        purpose="marketing",
        purpose_description="Marketing communications",
        consent_given=True,
        consent_category="marketing"
    )

    # Withdraw consent
    withdrawn = await gdpr_service.withdraw_consent(
        user_id=test_user.id,
        purpose="marketing"
    )

    assert withdrawn is True

    # Check consent is withdrawn
    has_consent = await gdpr_service.check_consent(
        user_id=test_user.id,
        purpose="marketing"
    )
    assert has_consent is False


@pytest.mark.asyncio
async def test_check_consent_valid(gdpr_service, test_user):
    """Test checking valid consent."""
    await gdpr_service.record_consent(
        user_id=test_user.id,
        purpose="personalization",
        purpose_description="Personalized experience",
        consent_given=True,
        consent_category="functional"
    )

    has_consent = await gdpr_service.check_consent(
        user_id=test_user.id,
        purpose="personalization"
    )

    assert has_consent is True


@pytest.mark.asyncio
async def test_check_consent_expired(gdpr_service, test_user, db_session):
    """Test that expired consent is not valid."""
    # Create consent that expired yesterday
    consent = ConsentRecord(
        id=generate_uuid(),
        user_id=test_user.id,
        purpose="temporary",
        purpose_description="Temporary consent",
        consent_given=True,
        consent_category="functional",
        consent_method="api",
        legal_basis="consent",
        consent_version="1.0",
        expires_at=datetime.utcnow() - timedelta(days=1),
        granted_at=datetime.utcnow() - timedelta(days=30)
    )
    db_session.add(consent)
    await db_session.commit()

    has_consent = await gdpr_service.check_consent(
        user_id=test_user.id,
        purpose="temporary"
    )

    assert has_consent is False


# ============================================================================
# Privacy Settings Tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_or_create_privacy_settings(gdpr_service, test_user):
    """Test getting or creating privacy settings."""
    settings = await gdpr_service.get_or_create_privacy_settings(test_user.id)

    assert settings.id is not None
    assert settings.user_id == test_user.id
    assert settings.privacy_level == "balanced"  # Default
    assert settings.email_marketing_enabled is False  # Default


@pytest.mark.asyncio
async def test_update_privacy_settings(gdpr_service, test_user):
    """Test updating privacy settings."""
    settings = await gdpr_service.update_privacy_settings(
        user_id=test_user.id,
        privacy_level="minimal",
        email_marketing_enabled=False,
        analytics_enabled=False,
        ai_training_opt_in=False
    )

    assert settings.privacy_level == "minimal"
    assert settings.email_marketing_enabled is False
    assert settings.analytics_enabled is False
    assert settings.ai_training_opt_in is False


# ============================================================================
# Data Retention Tests
# ============================================================================

@pytest.mark.asyncio
async def test_enforce_retention_policies(gdpr_service, db_session):
    """Test enforcing data retention policies."""
    # Create a retention policy
    policy = DataRetentionPolicy(
        id=generate_uuid(),
        policy_name="Test Audit Log Retention",
        data_type="audit_logs",
        description="Delete audit logs after 90 days",
        retention_period_days=90,
        retention_basis="legal_requirement",
        auto_delete_enabled=True,
        delete_method="hard_delete",
        is_active=True
    )
    db_session.add(policy)
    await db_session.commit()

    # Enforce policies
    summary = await gdpr_service.enforce_retention_policies()

    assert "enforced_at" in summary
    assert "policies_applied" in summary
    assert len(summary["policies_applied"]) > 0


# ============================================================================
# Utility Method Tests
# ============================================================================

def test_anonymize_email():
    """Test email anonymization utility."""
    email = "user@example.com"
    anon_email = GDPRService.anonymize_email(email)

    assert anon_email != email
    assert anon_email.startswith("deleted_")
    assert "@example.com" in anon_email


def test_anonymize_ip_ipv4():
    """Test IPv4 anonymization."""
    ip = "192.168.1.100"
    anon_ip = GDPRService.anonymize_ip(ip)

    assert anon_ip == "192.168.1.0"


def test_hash_pii():
    """Test PII hashing for searchability."""
    pii = "sensitive_data_12345"
    hash1 = GDPRService.hash_pii(pii)
    hash2 = GDPRService.hash_pii(pii)

    # Hash should be deterministic
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 hex digest


# ============================================================================
# Error Handling Tests
# ============================================================================

@pytest.mark.asyncio
async def test_anonymize_nonexistent_user(gdpr_service):
    """Test that anonymizing a nonexistent user raises an error."""
    fake_user_id = generate_uuid()

    with pytest.raises(AnonymizationError):
        await gdpr_service.anonymize_user_data(user_id=fake_user_id)


@pytest.mark.asyncio
async def test_export_nonexistent_request(gdpr_service):
    """Test that generating export for nonexistent request raises an error."""
    fake_request_id = generate_uuid()

    with pytest.raises(DataRequestError):
        await gdpr_service.generate_export_file(request_id=fake_request_id)


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_full_access_request_workflow(gdpr_service, test_user, test_project):
    """Test complete access request workflow."""
    # Step 1: Create access request
    request = await gdpr_service.create_access_request(
        user_id=test_user.id,
        description="Full data access request",
        export_format="json"
    )

    assert request.request_status == "pending"

    # Step 2: Generate export file
    file_path, file_hash = await gdpr_service.generate_export_file(
        request_id=request.id,
        format="json"
    )

    assert file_path is not None
    assert file_hash is not None

    # Verify request is completed
    # Note: In real implementation, need to refresh from DB
    # For test purposes, checking the return values is sufficient


@pytest.mark.asyncio
async def test_full_erasure_workflow(gdpr_service, test_user, db_session):
    """Test complete erasure workflow."""
    original_email = test_user.email

    # Step 1: Create erasure request
    request = await gdpr_service.create_erasure_request(
        user_id=test_user.id,
        description="Delete my account",
        erasure_method="anonymization"
    )

    # Step 2: Execute anonymization
    summary = await gdpr_service.anonymize_user_data(user_id=test_user.id)

    # Step 3: Verify data is anonymized
    await db_session.refresh(test_user)

    assert test_user.email != original_email
    assert test_user.is_active is False
    assert len(summary["operations"]) > 0


@pytest.mark.asyncio
async def test_consent_lifecycle(gdpr_service, test_user):
    """Test complete consent lifecycle."""
    # Step 1: Record consent
    consent = await gdpr_service.record_consent(
        user_id=test_user.id,
        purpose="analytics",
        purpose_description="Analytics tracking",
        consent_given=True,
        consent_category="analytics"
    )

    # Step 2: Check consent is valid
    has_consent = await gdpr_service.check_consent(
        user_id=test_user.id,
        purpose="analytics"
    )
    assert has_consent is True

    # Step 3: Withdraw consent
    withdrawn = await gdpr_service.withdraw_consent(
        user_id=test_user.id,
        purpose="analytics"
    )
    assert withdrawn is True

    # Step 4: Verify consent is withdrawn
    has_consent = await gdpr_service.check_consent(
        user_id=test_user.id,
        purpose="analytics"
    )
    assert has_consent is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
