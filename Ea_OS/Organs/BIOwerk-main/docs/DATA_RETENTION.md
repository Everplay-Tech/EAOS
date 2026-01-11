# Data Retention Policy Management

**Enterprise-Grade Data Lifecycle Management for SOC2, HIPAA, GDPR, and PCI-DSS Compliance**

Version: 1.0.0
Last Updated: 2025-11-16
Author: BIOwerk Security Team

---

## Table of Contents

1. [Overview](#overview)
2. [Compliance Framework Support](#compliance-framework-support)
3. [Architecture](#architecture)
4. [Key Features](#key-features)
5. [Getting Started](#getting-started)
6. [Policy Configuration](#policy-configuration)
7. [API Reference](#api-reference)
8. [Automated Enforcement](#automated-enforcement)
9. [Legal Holds](#legal-holds)
10. [Archival and Recovery](#archival-and-recovery)
11. [Compliance Reporting](#compliance-reporting)
12. [Monitoring and Alerting](#monitoring-and-alerting)
13. [Best Practices](#best-practices)
14. [Troubleshooting](#troubleshooting)
15. [Security Considerations](#security-considerations)

---

## Overview

BIOwerk's Data Retention Policy Management system provides automated, enterprise-grade data lifecycle management to ensure compliance with regulatory requirements including SOC2, HIPAA, GDPR, PCI-DSS, CCPA, and ISO 27001.

### What Does It Do?

- **Automated Policy Enforcement**: Automatically archives, deletes, or anonymizes data based on configurable retention policies
- **Compliance Tracking**: Maintains complete audit trails for all retention operations
- **Legal Hold Support**: Prevents deletion of data under legal hold for litigation/investigation
- **Secure Archival**: Encrypts archived data before deletion with integrity verification
- **Conflict Detection**: Identifies and reports policy conflicts and compliance violations
- **Flexible Scheduling**: Configurable evaluation intervals and manual trigger support

### Why Is It Important?

1. **Regulatory Compliance**: Meet legal requirements for data retention and deletion
2. **Risk Mitigation**: Reduce liability by not retaining data longer than necessary
3. **Cost Optimization**: Minimize storage costs by removing obsolete data
4. **Data Governance**: Maintain control over data lifecycle across the organization
5. **Audit Readiness**: Comprehensive logging for compliance audits and investigations

---

## Compliance Framework Support

### SOC2 (Service Organization Control 2)

**Requirements:**
- Audit logs: 365 days minimum
- User data: 90 days minimum
- Execution logs: 90 days minimum

**Implementation:**
```python
RetentionPolicy(
    name="SOC2 Audit Log Retention",
    data_type=DataType.AUDIT_LOG,
    retention_period_days=365,
    action=RetentionAction.ARCHIVE,
    compliance_framework=ComplianceFramework.SOC2,
    regulatory_citation="SOC2 CC7.2",
)
```

### HIPAA (Health Insurance Portability and Accountability Act)

**Requirements:**
- Medical records: 7 years (2,555 days)
- Audit logs: 7 years
- All patient data: 7 years

**Implementation:**
```python
RetentionPolicy(
    name="HIPAA Patient Data Retention",
    data_type=DataType.USER,
    retention_period_days=2555,
    action=RetentionAction.ARCHIVE,
    compliance_framework=ComplianceFramework.HIPAA,
    regulatory_citation="HIPAA 164.530(j)(2)",
)
```

### GDPR (General Data Protection Regulation)

**Requirements:**
- Right to be forgotten: 30 days maximum processing time
- Audit logs: 2 years minimum
- Minimal data retention by default

**Implementation:**
```python
RetentionPolicy(
    name="GDPR User Data Deletion",
    data_type=DataType.USER,
    retention_period_days=30,
    action=RetentionAction.ANONYMIZE,
    compliance_framework=ComplianceFramework.GDPR,
    regulatory_citation="GDPR Article 17",
)
```

### PCI-DSS (Payment Card Industry Data Security Standard)

**Requirements:**
- Audit logs: 365 days minimum, 3 years recommended
- Transaction logs: 90 days minimum
- Access logs: 365 days minimum

**Implementation:**
```python
RetentionPolicy(
    name="PCI-DSS Audit Log Retention",
    data_type=DataType.AUDIT_LOG,
    retention_period_days=365,
    action=RetentionAction.ARCHIVE,
    compliance_framework=ComplianceFramework.PCI_DSS,
    regulatory_citation="PCI-DSS Requirement 10.7",
)
```

---

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Retention Service API                     │
│                     (retention_service.py)                   │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
┌────────────────┐ ┌──────────────┐ ┌────────────────┐
│ Retention      │ │  Retention   │ │   Retention    │
│ Policy Engine  │ │   Manager    │ │   Scheduler    │
│                │ │              │ │                │
│ - Evaluation   │ │ - Policy CRUD│ │ - Automated    │
│ - Enforcement  │ │ - Validation │ │   Execution    │
│ - Legal Holds  │ │ - Reporting  │ │ - Monitoring   │
└────────┬───────┘ └──────┬───────┘ └────────┬───────┘
         │                │                  │
         └────────────────┼──────────────────┘
                          │
         ┌────────────────┴────────────────┐
         │                                 │
         ▼                                 ▼
┌─────────────────┐              ┌──────────────────┐
│   Database      │              │   Encryption     │
│   Models        │              │   Service        │
│                 │              │                  │
│ - Policies      │              │ - AES-256-GCM    │
│ - Schedules     │              │ - Key Rotation   │
│ - Archives      │              │ - Integrity      │
│ - Audit Logs    │              │   Verification   │
└─────────────────┘              └──────────────────┘
```

### Database Schema

#### retention_policies
Defines retention rules for different data types.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| name | String | Unique policy name |
| data_type | Enum | Type of data (user, project, artifact, etc.) |
| retention_period_days | Integer | Days to retain data |
| action | Enum | Action to take (archive, delete, anonymize) |
| compliance_framework | Enum | Framework (SOC2, HIPAA, GDPR, etc.) |
| priority | Integer | Evaluation priority (higher = first) |
| is_active | Boolean | Policy enabled status |

#### retention_schedules
Tracks scheduled retention actions and legal holds.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| data_type | Enum | Type of data |
| data_id | UUID | ID of specific data record |
| scheduled_for | DateTime | When to execute action |
| legal_hold | Boolean | Prevent deletion flag |
| legal_hold_reason | Text | Reason for hold |

#### data_archives
Stores encrypted snapshots of archived data.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| data_type | Enum | Type of data |
| data_id | UUID | Original data ID |
| archived_data | JSON | Encrypted data snapshot |
| data_hash | String | SHA-256 integrity hash |
| archive_status | Enum | Status (completed, restored, etc.) |

#### retention_audit_logs
Complete audit trail for all retention operations.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| data_type | Enum | Type of data |
| data_id | UUID | ID of affected data |
| action | Enum | Action taken |
| status | String | Execution status |
| executed_at | DateTime | When action was executed |

---

## Key Features

### 1. Granular Policy Control

- **Data Type Filtering**: Apply policies to specific data types
- **Category Filtering**: Target specific subcategories
- **User Filtering**: Apply to specific users or groups
- **Custom Conditions**: Complex filtering with JSON conditions
- **Priority Ordering**: Control policy evaluation order

### 2. Multiple Retention Actions

- **ARCHIVE**: Encrypt and store data before deletion
- **DELETE**: Permanently remove data (with optional archival)
- **ANONYMIZE**: Remove PII while keeping statistical data
- **RETAIN**: Keep data (for legal holds)

### 3. Legal Hold Management

- **Litigation Support**: Prevent deletion during legal proceedings
- **Investigation Holds**: Preserve data for security investigations
- **Compliance Holds**: Maintain data for regulatory reviews
- **Audit Trail**: Track who applied/removed holds and why

### 4. Secure Archival

- **AES-256-GCM Encryption**: Military-grade encryption
- **Integrity Verification**: SHA-256 hash validation
- **Key Versioning**: Support for key rotation
- **Restoration Support**: Decrypt and restore archived data

### 5. Automated Enforcement

- **Scheduled Evaluation**: Periodic policy checking
- **Background Processing**: Non-blocking execution
- **Error Recovery**: Automatic retry with exponential backoff
- **Dry Run Mode**: Test policies without data modification

### 6. Compliance Reporting

- **Framework Reports**: SOC2, HIPAA, GDPR, PCI-DSS
- **Violation Detection**: Identify non-compliant policies
- **Conflict Detection**: Find overlapping or contradictory policies
- **Statistics Dashboard**: Real-time retention metrics

---

## Getting Started

### Prerequisites

- Python 3.9+
- PostgreSQL 14+
- Redis 6+
- Alembic (database migrations)
- Properly configured encryption service

### Installation

1. **Apply Database Migration**

```bash
# Run the retention tables migration
alembic upgrade head
```

2. **Configure Environment Variables**

Add to your `.env` file:

```bash
# Enable retention policy enforcement
RETENTION_ENABLED=true

# Evaluation interval (hours)
RETENTION_EVALUATION_INTERVAL_HOURS=24

# Archive cleanup interval (hours)
RETENTION_ARCHIVE_CLEANUP_INTERVAL_HOURS=168

# Default retention periods (days)
RETENTION_DEFAULT_AUDIT_LOG_DAYS=365
RETENTION_DEFAULT_USER_DATA_DAYS=2555
RETENTION_DEFAULT_EXECUTION_DAYS=90

# Archive expiration (days, 0 = indefinite)
RETENTION_ARCHIVE_EXPIRATION_DAYS=2555

# Require archival before deletion
RETENTION_REQUIRE_ARCHIVE_BEFORE_DELETE=true

# Enable legal hold support
RETENTION_LEGAL_HOLD_ENABLED=true
```

3. **Start the Retention Service**

```bash
# Start as standalone service
python retention_service.py

# Or add to docker-compose.yml
```

4. **Verify Installation**

```bash
# Check health endpoint
curl http://localhost:8010/health

# Response:
# {
#   "status": "healthy",
#   "service": "retention",
#   "timestamp": "2025-11-16T12:00:00Z"
# }
```

---

## Policy Configuration

### Creating a Retention Policy

**Example: SOC2 Compliance Policy for Audit Logs**

```bash
curl -X POST http://localhost:8010/api/v1/retention/policies \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "SOC2 Audit Log Retention",
    "description": "Retain audit logs for 1 year per SOC2 requirements",
    "data_type": "audit_log",
    "retention_period_days": 365,
    "action": "archive",
    "compliance_framework": "soc2",
    "regulatory_citation": "SOC2 CC7.2",
    "archive_before_delete": true,
    "priority": 100
  }'
```

**Example: HIPAA Compliance Policy for User Data**

```bash
curl -X POST http://localhost:8010/api/v1/retention/policies \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "HIPAA Patient Data Retention",
    "description": "Retain patient data for 7 years per HIPAA requirements",
    "data_type": "user",
    "retention_period_days": 2555,
    "action": "archive",
    "compliance_framework": "hipaa",
    "regulatory_citation": "HIPAA 164.530(j)(2)",
    "archive_before_delete": true,
    "priority": 100
  }'
```

**Example: GDPR Right to be Forgotten**

```bash
curl -X POST http://localhost:8010/api/v1/retention/policies \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "GDPR User Data Anonymization",
    "description": "Anonymize user data after 30 days of deletion request",
    "data_type": "user",
    "retention_period_days": 30,
    "action": "anonymize",
    "compliance_framework": "gdpr",
    "regulatory_citation": "GDPR Article 17",
    "archive_before_delete": true,
    "priority": 90
  }'
```

### Policy Priority

Policies are evaluated in **descending priority order** (highest priority first). If multiple policies apply to the same data, the first matching policy determines the action.

**Example Priority Setup:**

- Priority 100: Legal/Regulatory requirements (HIPAA, SOC2)
- Priority 50: Business requirements
- Priority 10: Default cleanup policies

---

## API Reference

### Authentication

All API endpoints require JWT authentication. Admin-only endpoints require the `is_admin` flag.

**Headers:**
```
Authorization: Bearer YOUR_JWT_TOKEN
Content-Type: application/json
```

### Endpoints

#### Policy Management

**POST /api/v1/retention/policies** (Admin)
Create a new retention policy

**GET /api/v1/retention/policies**
List all policies with optional filters

**GET /api/v1/retention/policies/{policy_id}**
Get specific policy details

**PUT /api/v1/retention/policies/{policy_id}** (Admin)
Update an existing policy

**DELETE /api/v1/retention/policies/{policy_id}** (Admin)
Delete a policy

#### Policy Evaluation

**POST /api/v1/retention/evaluate** (Admin)
Manually trigger policy evaluation

Request body:
```json
{
  "data_type": "audit_log",  // Optional: specific type
  "dry_run": true            // If true, no data is modified
}
```

#### Legal Holds

**POST /api/v1/retention/legal-holds/{data_type}/{data_id}** (Admin)
Apply legal hold to prevent deletion

Request body:
```json
{
  "reason": "Investigation case #12345"
}
```

**DELETE /api/v1/retention/legal-holds/{data_type}/{data_id}** (Admin)
Remove legal hold

**GET /api/v1/retention/legal-holds**
List all data under legal hold

#### Archives

**GET /api/v1/retention/archives** (Admin)
List archived data

**POST /api/v1/retention/archives/{archive_id}/restore** (Admin)
Restore data from archive

#### Compliance

**POST /api/v1/retention/compliance/report** (Admin)
Generate compliance report

Request body:
```json
{
  "framework": "soc2",              // Optional: specific framework
  "start_date": "2025-01-01T00:00:00Z",  // Optional
  "end_date": "2025-11-16T00:00:00Z"     // Optional
}
```

**GET /api/v1/retention/statistics**
Get retention statistics

**GET /api/v1/retention/conflicts** (Admin)
Detect policy conflicts

---

## Automated Enforcement

### Scheduler Configuration

The retention scheduler runs automated background tasks:

1. **Policy Evaluation** (Default: Every 24 hours)
   - Evaluates all retention policies
   - Identifies data for archival/deletion
   - Executes retention actions

2. **Archive Cleanup** (Default: Weekly)
   - Deletes expired archives
   - Frees up storage space

3. **Compliance Checking** (Default: Daily)
   - Detects policy conflicts
   - Identifies compliance violations
   - Sends alerts

4. **Metrics Collection** (Default: Hourly)
   - Collects retention statistics
   - Updates monitoring dashboards

### Manual Triggering

You can manually trigger evaluation at any time:

```bash
# Dry run (no changes)
curl -X POST http://localhost:8010/api/v1/retention/evaluate \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'

# Execute retention actions
curl -X POST http://localhost:8010/api/v1/retention/evaluate \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}'
```

---

## Legal Holds

### When to Use Legal Holds

- Litigation or lawsuit involving the organization
- Regulatory investigation or audit
- Internal security investigation
- Compliance review or assessment

### Applying a Legal Hold

```bash
curl -X POST http://localhost:8010/api/v1/retention/legal-holds/user/123e4567-e89b-12d3-a456-426614174000 \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "Litigation case #2025-12345 - Jones v. Company"
  }'
```

### Legal Hold Best Practices

1. **Document Everything**: Always provide detailed reason
2. **Track Duration**: Review holds periodically
3. **Coordinate with Legal**: Consult legal counsel before applying
4. **Audit Trail**: Monitor who applies/removes holds
5. **Scope Appropriately**: Don't over-preserve data

---

## Archival and Recovery

### How Archival Works

1. **Serialization**: Data converted to JSON format
2. **Encryption**: AES-256-GCM encryption applied
3. **Integrity Hash**: SHA-256 hash calculated
4. **Storage**: Encrypted data stored in database
5. **Original Deletion**: Original data deleted (if policy specifies)

### Restoring from Archive

```bash
curl -X POST http://localhost:8010/api/v1/retention/archives/456e7890-e89b-12d3-a456-426614174000/restore \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Important**: Restoration only retrieves the data. You must manually restore it to the database.

### Archive Expiration

Archives can be configured to expire after a certain period:

```bash
# In .env
RETENTION_ARCHIVE_EXPIRATION_DAYS=2555  # 7 years

# Or set to 0 for indefinite retention
RETENTION_ARCHIVE_EXPIRATION_DAYS=0
```

---

## Compliance Reporting

### Generate SOC2 Report

```bash
curl -X POST http://localhost:8010/api/v1/retention/compliance/report \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "framework": "soc2",
    "start_date": "2025-01-01T00:00:00Z",
    "end_date": "2025-11-16T00:00:00Z"
  }'
```

**Report Contents:**
- Active policies for the framework
- Retention actions executed
- Legal holds by data type
- Archive statistics
- Compliance violations (if any)

### Detecting Violations

```bash
curl http://localhost:8010/api/v1/retention/conflicts \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Violation Types:**
- **Policy Conflicts**: Overlapping policies with different actions
- **Retention Period Conflicts**: Significantly different retention periods
- **Minimum Retention Violations**: Retention periods below regulatory minimums

---

## Monitoring and Alerting

### Key Metrics

1. **Policy Execution**
   - Policies evaluated
   - Records archived
   - Records deleted
   - Records anonymized
   - Errors encountered

2. **Archive Status**
   - Total archives
   - Archive size
   - Expired archives
   - Restoration requests

3. **Legal Holds**
   - Active holds by data type
   - Hold duration
   - Holds applied/removed

4. **Compliance**
   - Violations detected
   - Policy conflicts
   - Framework coverage

### Statistics Endpoint

```bash
curl http://localhost:8010/api/v1/retention/statistics \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

## Best Practices

### 1. Policy Design

- **Start Conservative**: Begin with longer retention periods
- **Align with Regulations**: Reference specific compliance requirements
- **Use Priorities**: Order policies by regulatory importance
- **Document Everything**: Include descriptions and citations
- **Test First**: Use dry-run mode before enforcement

### 2. Legal Holds

- **Coordinate with Legal**: Always consult legal counsel
- **Be Specific**: Provide detailed reasons
- **Regular Review**: Check holds periodically
- **Audit Trail**: Monitor all hold operations

### 3. Archive Management

- **Set Expiration**: Don't keep archives indefinitely
- **Monitor Size**: Track archive storage usage
- **Test Restoration**: Periodically verify archives are recoverable
- **Secure Storage**: Ensure archives are encrypted

### 4. Compliance

- **Regular Audits**: Review policies quarterly
- **Conflict Detection**: Monitor for policy conflicts
- **Update Policies**: Keep policies current with regulations
- **Maintain Documentation**: Keep compliance documentation up-to-date

### 5. Operations

- **Monitor Logs**: Review retention audit logs regularly
- **Set Alerts**: Configure alerts for failures
- **Test Recovery**: Practice data restoration procedures
- **Capacity Planning**: Monitor storage and performance

---

## Troubleshooting

### Common Issues

#### Policy Not Being Enforced

**Symptoms**: Data not being deleted despite policy

**Checks:**
1. Is the policy active? (`is_active = true`)
2. Is retention enabled? (`RETENTION_ENABLED=true`)
3. Is the scheduler running?
4. Are there any legal holds on the data?
5. Check retention audit logs for errors

**Solution:**
```bash
# Check policy status
curl http://localhost:8010/api/v1/retention/policies/{policy_id}

# Check legal holds
curl http://localhost:8010/api/v1/retention/legal-holds

# Review audit logs
curl http://localhost:8010/api/v1/retention/statistics
```

#### Archive Restoration Fails

**Symptoms**: "Archive data integrity check failed"

**Cause**: Data corruption or tampering

**Solution:**
- Contact security team immediately
- Review audit logs for unauthorized access
- Do not attempt to modify archive manually

#### High Memory Usage

**Symptoms**: Service consuming excessive memory

**Cause**: Processing large datasets

**Solution:**
1. Adjust batch size in configuration
2. Increase evaluation interval
3. Use pagination for large result sets
4. Consider scaling horizontally

---

## Security Considerations

### Encryption

- All archived data is encrypted with AES-256-GCM
- Encryption keys should be stored in KMS (production)
- Key rotation supported with versioning
- Integrity verification with SHA-256 hashing

### Access Control

- Policy management: Admin only
- Legal holds: Admin only
- Archive restoration: Admin only
- Read operations: Authenticated users

### Audit Logging

- All retention operations are logged
- Audit logs include actor, action, and timestamp
- Logs are encrypted at rest
- Retention period: 7 years (HIPAA compliant)

### Data Protection

- Archives are encrypted before storage
- Integrity hashes prevent tampering
- Legal holds prevent accidental deletion
- Restoration requires admin authorization

---

## Support and Contact

For questions, issues, or feature requests:

- **Email**: security@biowerk.com
- **Documentation**: https://docs.biowerk.com/retention
- **Issue Tracker**: https://github.com/biowerk/issues

---

## Appendix

### Regulatory Requirements Summary

| Framework | Audit Logs | User Data | Transaction Logs |
|-----------|-----------|-----------|------------------|
| SOC2      | 365 days  | 90 days   | 90 days          |
| HIPAA     | 2555 days | 2555 days | 2555 days        |
| GDPR      | 730 days  | 30 days*  | 730 days         |
| PCI-DSS   | 365 days  | 90 days   | 90 days          |

*Right to be forgotten - must respond within 30 days

### Data Type Reference

| Data Type | Description | Default Retention |
|-----------|-------------|-------------------|
| user | User accounts and profiles | 2555 days (HIPAA) |
| project | Project metadata | 730 days |
| artifact | Generated documents | 730 days |
| execution | API execution logs | 90 days |
| api_key | API keys | 90 days |
| audit_log | Security audit logs | 365 days |
| session | User sessions | 30 days |
| cache | Cached data | 7 days |

### Compliance Framework Mapping

**SOC2 Controls:**
- CC7.2: Monitoring Activities
- CC7.3: Evaluation of Results
- CC8.1: Information Security

**HIPAA Regulations:**
- 164.530(j)(2): Documentation retention
- 164.308(a)(1)(ii)(D): Information system activity review

**GDPR Articles:**
- Article 17: Right to erasure
- Article 25: Data protection by design

**PCI-DSS Requirements:**
- 10.7: Retention of audit trail history
- 3.1: Data retention and disposal

---

**Document Version**: 1.0.0
**Last Review**: 2025-11-16
**Next Review**: 2026-02-16
