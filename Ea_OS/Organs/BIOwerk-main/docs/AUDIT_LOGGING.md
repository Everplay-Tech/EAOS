# Enterprise Audit Logging with Encryption at Rest

## Overview

BIOwerk implements comprehensive enterprise-grade audit logging with encryption at rest for all sensitive data. This system provides complete audit trails for compliance requirements (SOC2, HIPAA, GDPR, PCI-DSS) while protecting sensitive information using military-grade encryption.

## Table of Contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [Configuration](#configuration)
4. [Usage](#usage)
5. [Security](#security)
6. [Compliance](#compliance)
7. [API Reference](#api-reference)
8. [Best Practices](#best-practices)

## Features

### Comprehensive Audit Trails

- **Authentication Events**: Login, logout, token refresh, MFA, failed attempts
- **Authorization Events**: Permission checks, access grants/denials
- **Data Access**: Read operations, queries, exports
- **Data Modifications**: Create, update, delete operations with change tracking
- **Administrative Actions**: User management, configuration changes, role assignments
- **Security Events**: Suspicious activity, rate limit violations, intrusion attempts

### Encryption at Rest

- **AES-256-GCM** authenticated encryption for all sensitive fields
- **Envelope encryption** pattern (DEK + KEK) for key management
- **Field-level encryption** for granular access control
- **Key versioning** and rotation support
- **Cryptographic integrity** verification with SHA-256 hashing
- **FIPS 140-2** compliant algorithms

### Advanced Capabilities

- **Tamper detection** using cryptographic hashes
- **Retention policies** based on event category (authentication, data, security)
- **Export capabilities** (JSON, CSV, JSON Lines)
- **Advanced querying** with filtering and pagination
- **Performance metrics** (request duration, response times)
- **Distributed tracing** support with correlation IDs
- **Geolocation tracking** (optional)
- **Automated archival** and deletion

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                  FastAPI Application                         │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           AuditMiddleware (Automatic)                 │   │
│  │  - Captures all HTTP requests/responses               │   │
│  │  - Extracts user/session context                      │   │
│  │  - Records performance metrics                        │   │
│  └────────────────┬─────────────────────────────────────┘   │
│                   │                                           │
│  ┌────────────────▼─────────────────────────────────────┐   │
│  │              AuditLogger Service                      │   │
│  │  - Categorizes events (AUTH, DATA, ADMIN, etc.)      │   │
│  │  - Encrypts sensitive fields                          │   │
│  │  - Computes integrity hashes                          │   │
│  │  - Applies retention policies                         │   │
│  └────────────────┬─────────────────────────────────────┘   │
│                   │                                           │
│                   ├──────────────┐                            │
│                   │              │                            │
│  ┌────────────────▼────┐  ┌─────▼──────────────────────┐    │
│  │ EncryptionService   │  │    Database (PostgreSQL)    │    │
│  │  - AES-256-GCM      │  │  ┌──────────────────────┐   │    │
│  │  - Envelope crypto  │  │  │   audit_logs table   │   │    │
│  │  - Key rotation     │  │  │  - 40+ indexed fields │   │    │
│  └─────────────────────┘  │  │  - Encrypted columns  │   │    │
│                            │  └──────────────────────┘   │    │
│                            └──────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘

         ┌──────────────────────────────────────┐
         │       AuditManager (Query/Export)     │
         │  - Advanced querying with filters     │
         │  - Decryption for authorized access   │
         │  - Export to JSON/CSV                 │
         │  - Statistics and reporting           │
         │  - Retention enforcement              │
         └──────────────────────────────────────┘
```

### Database Schema

The `audit_logs` table includes:

**Identification**
- `id`, `event_id`: Unique identifiers
- `event_type`, `event_category`, `event_action`: Event classification
- `event_status`, `severity`: Outcome and importance

**Actor (Who)**
- `user_id`, `username`: User performing the action
- `actor_type`: user, service, system, anonymous

**Subject (What)**
- `resource_type`, `resource_id`, `resource_name`: Affected resource

**Context (How/Where)**
- `service_name`, `endpoint`, `http_method`, `http_status_code`
- `ip_address` (encrypted), `user_agent` (encrypted)
- `session_id`, `trace_id`, `request_id`

**Data Changes**
- `request_data` (encrypted), `response_data` (encrypted)
- `changes_before` (encrypted), `changes_after` (encrypted)

**Security**
- `authentication_method`, `authorization_result`, `risk_score`
- `record_hash`: SHA-256 for tamper detection
- `encryption_key_version`: Key rotation tracking

**Compliance**
- `retention_period_days`: Custom retention per event
- `is_archived`, `archived_at`: Archival status

## Configuration

### Environment Variables

Add to your `.env` file:

```bash
# Audit Logging Configuration
AUDIT_ENABLED=true
AUDIT_LOG_REQUESTS=true
AUDIT_LOG_RESPONSES=true
AUDIT_ENCRYPT_SENSITIVE=true
AUDIT_RETENTION_DAYS=365
AUDIT_RETENTION_AUTH_DAYS=90
AUDIT_RETENTION_DATA_DAYS=2555    # 7 years for data modifications
AUDIT_RETENTION_SECURITY_DAYS=730  # 2 years for security events
AUDIT_COLLECT_GEO=false
AUDIT_MAX_FIELD_SIZE=65536
AUDIT_BATCH_SIZE=100
AUDIT_ASYNC_WRITE=true

# Encryption Configuration
ENCRYPTION_ENABLED=true
ENCRYPTION_MASTER_KEY=your-secure-master-key-minimum-32-characters
ENCRYPTION_KEY_VERSION=1
ENCRYPTION_KEY_ROTATION_DAYS=90
ENCRYPTION_ALGORITHM=AES-256-GCM

# Sensitive field patterns to always encrypt
AUDIT_SENSITIVE_FIELDS=password,token,api_key,secret,credential,authorization
```

### Key Management

**Development:**
```bash
# Generate a secure master key
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Production:**
Use a Key Management Service (KMS):
- **AWS KMS**: Use AWS Secrets Manager or Parameter Store
- **Azure Key Vault**: Store encryption keys securely
- **HashiCorp Vault**: Centralized secret management
- **Google Cloud KMS**: Managed encryption keys

Example with AWS Secrets Manager:
```python
import boto3

def get_master_key():
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId='biowerk/encryption/master-key')
    return response['SecretString']
```

## Usage

### 1. Database Migration

Run the migration to create the `audit_logs` table:

```bash
# Using Python with alembic
python -m alembic upgrade head

# Or using Docker
docker-compose exec api python -m alembic upgrade head
```

### 2. Enable Middleware

Add audit middleware to your FastAPI application:

```python
from fastapi import FastAPI
from matrix.audit_middleware import create_audit_middleware

app = FastAPI()

# Add audit middleware (automatically logs all requests)
app.add_middleware(
    create_audit_middleware(
        service_name="osteon",
        exclude_paths=["/internal", "/debug"]
    )
)
```

### 3. Manual Logging

For custom audit events:

```python
from matrix.audit import get_audit_logger, AuditContext, EventType, EventCategory, EventStatus
from matrix.database import get_db

audit_logger = get_audit_logger()

async def create_project(user_id: str, project_data: dict):
    # Create audit context
    context = AuditContext(
        user_id=user_id,
        service_name="osteon"
    )

    # Your business logic
    project = await save_project(project_data)

    # Log the audit event
    async for session in get_db():
        await audit_logger.log_data_write(
            action="create_project",
            status=EventStatus.success,
            context=context,
            resource_type="project",
            resource_id=project.id,
            resource_name=project.name,
            changes_after=project_data,
            session=session
        )
        break
```

### 4. Querying Audit Logs

```python
from matrix.audit_manager import AuditManager, AuditQueryBuilder
from matrix.audit import EventType, EventStatus
from datetime import datetime, timedelta

manager = AuditManager()

# Query with filters
query = (
    AuditQueryBuilder()
    .filter_by_user("user-123")
    .filter_by_event_type(EventType.DATA_WRITE)
    .filter_by_last_n_days(30)
    .filter_by_status(EventStatus.success)
)

async with get_db_session() as session:
    # Get audit logs (decrypted)
    logs = await manager.query(
        session=session,
        query_builder=query,
        limit=100,
        decrypt=True
    )

    # Get count
    count = await manager.count(session, query_builder=query)

    print(f"Found {count} audit logs")
    for log in logs:
        print(f"{log['event_timestamp']}: {log['event_action']} - {log['event_status']}")
```

### 5. Exporting Audit Logs

```python
from matrix.audit_manager import AuditManager, ExportFormat

manager = AuditManager()

async with get_db_session() as session:
    # Export to JSON
    json_export = await manager.export(
        session=session,
        format=ExportFormat.JSON,
        decrypt=True,
        include_sensitive=False  # Exclude sensitive fields from export
    )

    # Save to file
    with open("audit_logs.json", "w") as f:
        f.write(json_export)

    # Export to CSV for spreadsheet analysis
    csv_export = await manager.export(
        session=session,
        format=ExportFormat.CSV
    )

    with open("audit_logs.csv", "w") as f:
        f.write(csv_export)
```

### 6. Retention Policy Enforcement

Set up a periodic task to enforce retention policies:

```python
from matrix.audit_manager import AuditManager

async def enforce_audit_retention():
    """Run this daily via cron or scheduled task."""
    manager = AuditManager()

    async with get_db_session() as session:
        archived, deleted = await manager.enforce_retention(session)
        print(f"Archived: {archived}, Deleted: {deleted}")

# Schedule with APScheduler, Celery, or cron
```

### 7. Statistics and Monitoring

```python
from matrix.audit_manager import AuditManager

manager = AuditManager()

async with get_db_session() as session:
    stats = await manager.get_statistics(session, days=30)

    print(f"Total events: {stats['total_events']}")
    print(f"Failed auth attempts: {stats['failed_authentication_attempts']}")
    print(f"Events by type: {stats['events_by_type']}")
    print(f"Top users: {stats['top_users']}")
```

## Security

### Encryption Details

**Algorithm**: AES-256-GCM (Galois/Counter Mode)
- **Confidentiality**: 256-bit AES encryption
- **Integrity**: Built-in authentication tag
- **Authenticity**: AEAD (Authenticated Encryption with Associated Data)

**Key Derivation**: PBKDF2-HMAC-SHA256
- **Iterations**: 600,000 (OWASP 2023 recommendation)
- **Salt**: 256-bit random salt per installation
- **Output**: 256-bit encryption key

**Envelope Encryption**:
1. **Data Encryption Key (DEK)**: Random 256-bit key per field
2. **Key Encryption Key (KEK)**: Derived from master key
3. DEK encrypts the data, KEK encrypts the DEK
4. Provides key rotation without re-encrypting data

### Access Control

**Decryption Authorization**:
- Only administrators should have access to decrypted audit logs
- Use RBAC to control who can query with `decrypt=True`
- Implement separate audit viewer roles

```python
from fastapi import Depends
from matrix.auth import require_admin

@app.get("/audit/logs")
async def get_audit_logs(
    user = Depends(require_admin),  # Only admins
    decrypt: bool = False
):
    if decrypt and not user.is_super_admin:
        raise HTTPException(403, "Decryption requires super admin")

    # Query audit logs...
```

### Tamper Detection

Every audit log record includes a cryptographic hash of critical fields:

```python
from matrix.audit_manager import AuditManager

manager = AuditManager()

async with get_db_session() as session:
    is_valid, error = await manager.verify_integrity(
        session=session,
        event_id="event-uuid-here"
    )

    if not is_valid:
        print(f"ALERT: Audit log tampering detected! {error}")
        # Send alert to security team
```

### Key Rotation

```python
from matrix.encryption import create_encryption_service

# Check if rotation is needed
encryption_service = create_encryption_service(
    master_key=settings.encryption_master_key,
    key_version=settings.encryption_key_version
)

if encryption_service.needs_rotation():
    # 1. Generate new master key
    new_master_key = generate_new_key()

    # 2. Update configuration
    # ENCRYPTION_MASTER_KEY=new_key
    # ENCRYPTION_KEY_VERSION=2

    # 3. Old data remains encrypted with old key (envelope encryption allows this)
    # 4. New data uses new key version
    # 5. Optionally re-encrypt old data in background
```

## Compliance

### SOC 2 Type II

**Control Requirements Met**:
- ✅ CC6.1: Logical and physical access controls
- ✅ CC6.2: System access is removed when no longer required
- ✅ CC6.3: Encryption of confidential data
- ✅ CC7.2: Detection of security events through monitoring
- ✅ CC7.3: Security incident evaluation and response

**Audit Evidence**:
```python
# Generate SOC2 compliance report
query = (
    AuditQueryBuilder()
    .filter_by_event_category(EventCategory.authentication)
    .filter_by_last_n_days(365)
)

logs = await manager.export(session, query_builder=query, format=ExportFormat.CSV)
# Provide to auditor
```

### HIPAA Compliance

**Requirements Met**:
- ✅ §164.312(a)(1): Access control
- ✅ §164.312(a)(2)(i): Unique user identification
- ✅ §164.312(b): Audit controls
- ✅ §164.312(c): Integrity controls
- ✅ §164.312(d): Encryption and decryption
- ✅ §164.312(e): Transmission security

**Retention**: 7 years for healthcare data (configured via `AUDIT_RETENTION_DATA_DAYS=2555`)

### GDPR Compliance

**Requirements Met**:
- ✅ Article 5(1)(f): Security of processing
- ✅ Article 32: Security of processing (encryption)
- ✅ Article 33: Breach notification (via audit logs)
- ✅ Article 30: Records of processing activities

**Data Subject Rights**:
```python
# Right to access (Article 15)
query = AuditQueryBuilder().filter_by_user(user_id)
user_audit_trail = await manager.export(session, query_builder=query)

# Right to erasure (Article 17)
# Note: Audit logs may be retained for legal compliance
```

### PCI-DSS

**Requirements Met**:
- ✅ 10.1: Implement audit trails
- ✅ 10.2: Automated audit trails for all system components
- ✅ 10.3: Record required audit trail entries
- ✅ 10.5: Secure audit trails (encryption + integrity)
- ✅ 10.6: Review logs and security events
- ✅ 10.7: Retain audit trail history for at least one year

## API Reference

### AuditLogger Methods

```python
# Log authentication events
await audit_logger.log_authentication(
    action: str,              # "login", "logout", "token_refresh"
    status: EventStatus,      # success, failure, error
    context: AuditContext,    # User/session context
    authentication_method: str,  # "jwt", "api_key", "oauth2"
    error_message: Optional[str] = None,
    session: AsyncSession
)

# Log access/authorization events
await audit_logger.log_access(
    action: str,
    status: EventStatus,
    context: AuditContext,
    resource_type: str,
    resource_id: Optional[str] = None,
    authorization_result: str = "allowed",  # or "denied"
    session: AsyncSession
)

# Log data read operations
await audit_logger.log_data_read(
    action: str,
    status: EventStatus,
    context: AuditContext,
    resource_type: str,
    resource_id: Optional[str] = None,
    response_data: Optional[dict] = None,
    session: AsyncSession
)

# Log data write operations
await audit_logger.log_data_write(
    action: str,
    status: EventStatus,
    context: AuditContext,
    resource_type: str,
    resource_id: Optional[str] = None,
    changes_before: Optional[dict] = None,
    changes_after: Optional[dict] = None,
    session: AsyncSession
)

# Log data deletions
await audit_logger.log_data_delete(
    action: str,
    status: EventStatus,
    context: AuditContext,
    resource_type: str,
    resource_id: Optional[str] = None,
    changes_before: Optional[dict] = None,
    session: AsyncSession
)

# Log administrative actions
await audit_logger.log_admin(
    action: str,
    status: EventStatus,
    context: AuditContext,
    resource_type: str,
    resource_id: Optional[str] = None,
    changes_before: Optional[dict] = None,
    changes_after: Optional[dict] = None,
    session: AsyncSession
)

# Log security events
await audit_logger.log_security(
    action: str,
    status: EventStatus,
    context: AuditContext,
    severity: Severity = Severity.WARNING,
    error_message: Optional[str] = None,
    risk_score: Optional[int] = None,
    session: AsyncSession
)
```

### AuditQueryBuilder Methods

```python
query = (
    AuditQueryBuilder()
    .filter_by_user(user_id)
    .filter_by_event_type(EventType.AUTH)
    .filter_by_event_category(EventCategory.authentication)
    .filter_by_status(EventStatus.failure)
    .filter_by_severity(Severity.WARNING, min_severity=True)
    .filter_by_resource(resource_type="project", resource_id="proj-123")
    .filter_by_service("osteon")
    .filter_by_endpoint("/api/projects")
    .filter_by_ip("192.168.1.100")
    .filter_by_session(session_id)
    .filter_by_trace_id(trace_id)
    .filter_by_time_range(start_time, end_time)
    .filter_by_last_n_days(30)
    .filter_archived(False)
)
```

## Best Practices

### 1. Separation of Duties

- **Developers**: Can view aggregate statistics, not individual logs
- **Operations**: Can view logs but not decrypt sensitive fields
- **Security Team**: Can decrypt and analyze all logs
- **Auditors**: Read-only access to exported logs

### 2. Regular Review

```python
# Weekly security review
async def weekly_security_review():
    manager = AuditManager()
    async with get_db_session() as session:
        stats = await manager.get_statistics(session, days=7)

        # Alert on anomalies
        if stats['failed_authentication_attempts'] > 100:
            send_alert("High number of failed login attempts")

        # Review high-risk events
        query = AuditQueryBuilder().filter_by_severity(Severity.CRITICAL)
        critical_logs = await manager.query(session, query_builder=query)

        for log in critical_logs:
            review_critical_event(log)
```

### 3. Performance Optimization

- Enable async batch writing for high-volume systems
- Use indexes for common query patterns
- Archive old logs to separate storage
- Consider partitioning by date for very large datasets

### 4. Monitoring and Alerts

```python
# Set up Prometheus metrics
from prometheus_client import Counter, Histogram

audit_events_total = Counter(
    'audit_events_total',
    'Total audit events',
    ['event_type', 'status']
)

audit_encryption_duration = Histogram(
    'audit_encryption_duration_seconds',
    'Time spent encrypting audit data'
)

# In audit logger
audit_events_total.labels(
    event_type=event_type.value,
    status=event_status.value
).inc()
```

### 5. Backup and Disaster Recovery

```bash
# Backup audit logs separately from application data
pg_dump -t audit_logs biowerk > audit_logs_backup.sql

# Encrypt backups
gpg --encrypt --recipient security@company.com audit_logs_backup.sql

# Store in secure, immutable storage (S3 with object lock)
aws s3 cp audit_logs_backup.sql.gpg s3://company-audit-backups/ \
    --storage-class GLACIER \
    --metadata "retention=7years"
```

### 6. Testing

```bash
# Run audit logging tests
pytest tests/test_audit_logging.py -v

# Test encryption performance
pytest tests/test_audit_logging.py::TestEncryptionService -v --benchmark

# Verify compliance requirements
pytest tests/test_audit_logging.py -k compliance -v
```

## Troubleshooting

### Issue: Encryption key rotation failed

```python
# Check current key version
from matrix.encryption import create_encryption_service

service = create_encryption_service(...)
info = service.get_key_info()
print(f"Current version: {info['key_version']}")
print(f"Needs rotation: {info['needs_rotation']}")
```

### Issue: Audit logs not appearing

1. Check if audit middleware is enabled
2. Verify `AUDIT_ENABLED=true` in configuration
3. Check database connection
4. Review application logs for errors

### Issue: Decryption failures

1. Verify master key hasn't changed
2. Check key version matches encrypted data
3. Ensure salt is consistent
4. Review error logs for specific decryption errors

---

## Summary

BIOwerk's audit logging system provides:

✅ **Complete audit trails** for all system activity
✅ **Military-grade encryption** (AES-256-GCM) for sensitive data
✅ **Compliance support** for SOC2, HIPAA, GDPR, PCI-DSS
✅ **Tamper detection** with cryptographic integrity verification
✅ **Flexible retention** policies based on event category
✅ **Advanced querying** and export capabilities
✅ **Production-ready** performance with async batch writing

For additional support or questions, consult the API documentation or contact the security team.
