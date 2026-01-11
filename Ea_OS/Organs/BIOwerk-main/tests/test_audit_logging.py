"""Tests for audit logging with encryption at rest."""

import pytest
import json
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from matrix.encryption import EncryptionService, create_encryption_service, DecryptionError
from matrix.audit import (
    AuditLogger,
    AuditContext,
    EventType,
    EventCategory,
    EventStatus,
    Severity
)
from matrix.audit_manager import AuditManager, AuditQueryBuilder, ExportFormat
from matrix.db_models import Base, AuditLog
from matrix.config import settings


# Test database URL (use in-memory SQLite for tests)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def test_db():
    """Create a test database."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def encryption_service():
    """Create a test encryption service."""
    return create_encryption_service(
        master_key="test-master-key-with-sufficient-length-32chars",
        key_version=1
    )


@pytest.fixture
def audit_logger(encryption_service):
    """Create a test audit logger."""
    return AuditLogger(
        encryption_service=encryption_service,
        enable_encryption=True,
        async_write=False  # Disable async for easier testing
    )


@pytest.fixture
def audit_context():
    """Create a test audit context."""
    return AuditContext(
        user_id="test-user-123",
        username="testuser",
        session_id="test-session-456",
        ip_address="192.168.1.100",
        user_agent="Mozilla/5.0 Test Browser",
        service_name="test-service"
    )


class TestEncryptionService:
    """Test the encryption service."""

    def test_encrypt_decrypt_field(self, encryption_service):
        """Test field encryption and decryption."""
        plaintext = "sensitive data here"
        encrypted = encryption_service.encrypt_field(plaintext)

        assert "ciphertext" in encrypted
        assert "nonce" in encrypted
        assert "dek_metadata" in encrypted
        assert encrypted["algorithm"] == "AES-256-GCM"

        decrypted = encryption_service.decrypt_field(encrypted)
        assert decrypted == plaintext

    def test_encrypt_with_associated_data(self, encryption_service):
        """Test encryption with associated authenticated data."""
        plaintext = "secret message"
        aad = "record-id-12345"

        encrypted = encryption_service.encrypt_field(plaintext, associated_data=aad)
        decrypted = encryption_service.decrypt_field(encrypted, associated_data=aad)

        assert decrypted == plaintext

    def test_decrypt_with_wrong_aad_fails(self, encryption_service):
        """Test that decryption fails with wrong AAD."""
        plaintext = "secret message"
        aad = "record-id-12345"

        encrypted = encryption_service.encrypt_field(plaintext, associated_data=aad)

        with pytest.raises(DecryptionError):
            encryption_service.decrypt_field(encrypted, associated_data="wrong-aad")

    def test_encrypt_json(self, encryption_service):
        """Test JSON encryption."""
        data = {
            "username": "john",
            "email": "john@example.com",
            "password": "secret123",
            "api_key": "key-12345"
        }

        encrypted = encryption_service.encrypt_json(
            data,
            fields_to_encrypt=["password", "api_key"],
            record_id="user-789"
        )

        # Original fields should be None
        assert encrypted["password"] is None
        assert encrypted["api_key"] is None

        # Encrypted fields should exist
        assert "password_encrypted" in encrypted
        assert "api_key_encrypted" in encrypted

        # Non-encrypted fields should remain
        assert encrypted["username"] == "john"
        assert encrypted["email"] == "john@example.com"

        # Decrypt
        decrypted = encryption_service.decrypt_json(
            encrypted,
            fields_to_decrypt=["password", "api_key"],
            record_id="user-789"
        )

        assert decrypted["password"] == "secret123"
        assert decrypted["api_key"] == "key-12345"

    def test_hash_for_search(self, encryption_service):
        """Test deterministic hashing for search."""
        value = "192.168.1.100"

        hash1 = encryption_service.hash_for_search(value)
        hash2 = encryption_service.hash_for_search(value)

        # Same input should produce same hash
        assert hash1 == hash2

        # Different input should produce different hash
        hash3 = encryption_service.hash_for_search("192.168.1.101")
        assert hash1 != hash3

    def test_key_rotation_detection(self, encryption_service):
        """Test key rotation detection."""
        assert not encryption_service.needs_rotation()

        # Simulate old key
        encryption_service.key_created_at = datetime.utcnow() - timedelta(days=100)
        assert encryption_service.needs_rotation()

    def test_envelope_encryption(self, encryption_service):
        """Test envelope encryption (DEK + KEK)."""
        # Generate and encrypt a DEK
        dek = encryption_service.generate_dek()
        assert len(dek) == 32  # 256 bits

        encrypted_dek = encryption_service.encrypt_dek(dek)
        assert "encrypted_dek" in encrypted_dek
        assert "nonce" in encrypted_dek
        assert encrypted_dek["key_version"] == 1
        assert encrypted_dek["algorithm"] == "AES-256-GCM"

        # Decrypt DEK
        decrypted_dek = encryption_service.decrypt_dek(encrypted_dek)
        assert decrypted_dek == dek


class TestAuditLogger:
    """Test the audit logger."""

    @pytest.mark.asyncio
    async def test_log_authentication_event(self, test_db, audit_logger, audit_context):
        """Test logging an authentication event."""
        event_id = await audit_logger.log_authentication(
            action="login",
            status=EventStatus.success,
            context=audit_context,
            authentication_method="jwt",
            session=test_db
        )

        assert event_id == audit_context.event_id

        # Verify log was created
        logs = await test_db.execute(
            "SELECT * FROM audit_logs WHERE event_id = ?", (event_id,)
        )
        log = logs.fetchone()
        assert log is not None

    @pytest.mark.asyncio
    async def test_log_data_write_with_changes(self, test_db, audit_logger, audit_context):
        """Test logging a data write event with change tracking."""
        changes_before = {"status": "draft", "version": 1}
        changes_after = {"status": "published", "version": 2}

        event_id = await audit_logger.log_data_write(
            action="publish_article",
            status=EventStatus.success,
            context=audit_context,
            resource_type="article",
            resource_id="article-123",
            resource_name="My Article",
            changes_before=changes_before,
            changes_after=changes_after,
            session=test_db
        )

        assert event_id is not None

    @pytest.mark.asyncio
    async def test_encryption_of_sensitive_fields(self, test_db, audit_logger, audit_context):
        """Test that sensitive fields are encrypted."""
        request_data = {
            "username": "john",
            "password": "secret123",
            "api_key": "key-12345"
        }

        event_id = await audit_logger.log(
            event_type=EventType.AUTH,
            event_category=EventCategory.authentication,
            event_action="login",
            event_status=EventStatus.success,
            context=audit_context,
            request_data=request_data,
            session=test_db
        )

        # Query the log
        from sqlalchemy import select
        result = await test_db.execute(
            select(AuditLog).where(AuditLog.event_id == event_id)
        )
        log = result.scalar_one()

        # IP address should be encrypted
        assert log.ip_address is None
        assert log.ip_address_encrypted is not None
        assert log.ip_address_hash is not None

        # User agent should be encrypted
        assert log.user_agent is None
        assert log.user_agent_encrypted is not None

        # Request data should be encrypted
        assert log.request_data is None
        assert log.request_data_encrypted is not None

    @pytest.mark.asyncio
    async def test_record_hash_for_integrity(self, test_db, audit_logger, audit_context):
        """Test that record hash is computed for integrity verification."""
        event_id = await audit_logger.log(
            event_type=EventType.DATA_WRITE,
            event_category=EventCategory.data,
            event_action="create",
            event_status=EventStatus.success,
            context=audit_context,
            resource_type="project",
            resource_id="proj-123",
            session=test_db
        )

        # Query the log
        from sqlalchemy import select
        result = await test_db.execute(
            select(AuditLog).where(AuditLog.event_id == event_id)
        )
        log = result.scalar_one()

        assert log.record_hash is not None
        assert len(log.record_hash) == 64  # SHA-256 hex


class TestAuditManager:
    """Test the audit manager."""

    @pytest.mark.asyncio
    async def test_query_audit_logs(self, test_db, audit_logger, audit_context, encryption_service):
        """Test querying audit logs."""
        # Create some test logs
        await audit_logger.log_authentication(
            action="login",
            status=EventStatus.success,
            context=audit_context,
            authentication_method="jwt",
            session=test_db
        )

        await audit_logger.log_data_read(
            action="read_project",
            status=EventStatus.success,
            context=audit_context,
            resource_type="project",
            resource_id="proj-123",
            session=test_db
        )

        # Query logs
        manager = AuditManager(encryption_service=encryption_service)
        logs = await manager.query(test_db)

        assert len(logs) >= 2

    @pytest.mark.asyncio
    async def test_query_with_filters(self, test_db, audit_logger, audit_context, encryption_service):
        """Test querying with filters."""
        # Create logs with different event types
        await audit_logger.log_authentication(
            action="login",
            status=EventStatus.success,
            context=audit_context,
            authentication_method="jwt",
            session=test_db
        )

        await audit_logger.log_data_write(
            action="create_project",
            status=EventStatus.success,
            context=audit_context,
            resource_type="project",
            resource_id="proj-123",
            session=test_db
        )

        # Query only authentication events
        manager = AuditManager(encryption_service=encryption_service)
        query = AuditQueryBuilder().filter_by_event_type(EventType.AUTH)
        logs = await manager.query(test_db, query_builder=query)

        assert all(log["event_type"] == EventType.AUTH.value for log in logs)

    @pytest.mark.asyncio
    async def test_decrypt_audit_logs(self, test_db, audit_logger, audit_context, encryption_service):
        """Test decrypting audit logs."""
        # Create a log with encrypted data
        await audit_logger.log_authentication(
            action="login",
            status=EventStatus.success,
            context=audit_context,
            authentication_method="jwt",
            session=test_db
        )

        # Query with decryption
        manager = AuditManager(encryption_service=encryption_service)
        logs = await manager.query(test_db, decrypt=True)

        assert len(logs) > 0
        log = logs[0]

        # IP address should be decrypted
        assert log["ip_address"] == audit_context.ip_address
        assert "ip_address_encrypted" not in log

    @pytest.mark.asyncio
    async def test_export_to_json(self, test_db, audit_logger, audit_context, encryption_service):
        """Test exporting audit logs to JSON."""
        # Create test logs
        await audit_logger.log_authentication(
            action="login",
            status=EventStatus.success,
            context=audit_context,
            authentication_method="jwt",
            session=test_db
        )

        # Export
        manager = AuditManager(encryption_service=encryption_service)
        exported = await manager.export(
            test_db,
            format=ExportFormat.JSON
        )

        # Verify JSON is valid
        data = json.loads(exported)
        assert isinstance(data, list)
        assert len(data) > 0

    @pytest.mark.asyncio
    async def test_export_to_csv(self, test_db, audit_logger, audit_context, encryption_service):
        """Test exporting audit logs to CSV."""
        # Create test logs
        await audit_logger.log_authentication(
            action="login",
            status=EventStatus.success,
            context=audit_context,
            authentication_method="jwt",
            session=test_db
        )

        # Export
        manager = AuditManager(encryption_service=encryption_service)
        exported = await manager.export(
            test_db,
            format=ExportFormat.CSV
        )

        # Verify CSV format
        lines = exported.strip().split('\n')
        assert len(lines) >= 2  # Header + at least one row
        assert ',' in lines[0]  # CSV header

    @pytest.mark.asyncio
    async def test_statistics(self, test_db, audit_logger, audit_context, encryption_service):
        """Test audit log statistics."""
        # Create various logs
        await audit_logger.log_authentication(
            action="login",
            status=EventStatus.success,
            context=audit_context,
            authentication_method="jwt",
            session=test_db
        )

        await audit_logger.log_authentication(
            action="login",
            status=EventStatus.failure,
            context=audit_context,
            authentication_method="jwt",
            error_message="Invalid password",
            session=test_db
        )

        # Get statistics
        manager = AuditManager(encryption_service=encryption_service)
        stats = await manager.get_statistics(test_db, days=30)

        assert stats["total_events"] >= 2
        assert "events_by_type" in stats
        assert "events_by_status" in stats
        assert "failed_authentication_attempts" in stats
        assert stats["failed_authentication_attempts"] >= 1

    @pytest.mark.asyncio
    async def test_verify_integrity(self, test_db, audit_logger, audit_context, encryption_service):
        """Test cryptographic integrity verification."""
        # Create a log
        event_id = await audit_logger.log_authentication(
            action="login",
            status=EventStatus.success,
            context=audit_context,
            authentication_method="jwt",
            session=test_db
        )

        # Verify integrity
        manager = AuditManager(encryption_service=encryption_service)
        is_valid, error = await manager.verify_integrity(test_db, event_id)

        assert is_valid
        assert error is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
