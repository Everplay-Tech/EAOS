# GDPR Compliance Guide for BIOwerk

**Version:** 1.0.0
**Last Updated:** November 16, 2025
**Compliance Standards:** GDPR, CCPA, HIPAA, PCI-DSS

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [GDPR Rights Implementation](#gdpr-rights-implementation)
4. [API Reference](#api-reference)
5. [Database Schema](#database-schema)
6. [Configuration](#configuration)
7. [Operational Procedures](#operational-procedures)
8. [Compliance Checklist](#compliance-checklist)
9. [Data Protection Impact Assessment](#data-protection-impact-assessment)
10. [Appendix](#appendix)

---

## Overview

BIOwerk implements comprehensive GDPR (General Data Protection Regulation) compliance controls to protect user privacy and ensure regulatory compliance. This implementation provides:

### Key Features

- **✅ Right to Access** (Article 15) - Users can request and download all their personal data
- **✅ Right to Erasure** (Article 17) - Users can request deletion/anonymization of their data
- **✅ Right to Portability** (Article 20) - Export data in machine-readable formats (JSON, CSV)
- **✅ Right to Rectification** (Article 16) - Users can update incorrect data
- **✅ Consent Management** (Article 7) - Granular consent tracking and withdrawal
- **✅ Data Retention** (Article 5) - Automated policy enforcement
- **✅ Breach Notification** (Articles 33/34) - 72-hour notification tracking
- **✅ Privacy by Design** - Built-in privacy controls and encryption
- **✅ Audit Trail** - Comprehensive logging of all GDPR-related activities

### Compliance Timeline

| Requirement | Response Time | Implementation |
|-------------|---------------|----------------|
| Data Access Request | 30 days | Automated export generation |
| Data Erasure Request | 30 days | Automated anonymization |
| Breach Notification (Authority) | 72 hours | Automated tracking and alerts |
| Breach Notification (Individual) | Without undue delay | Templated notifications |
| Consent Withdrawal | Immediate | Real-time processing |

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                      GDPR Service (Port 8010)               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  API Endpoints                                        │  │
│  │  - /request/access   - /consent/record                │  │
│  │  - /request/erasure  - /consent/withdraw              │  │
│  │  - /export/data      - /privacy/settings              │  │
│  │  - /anonymize        - /retention/enforce             │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  GDPR Service Layer (matrix/gdpr.py)                  │  │
│  │  - Data export                                         │  │
│  │  - Anonymization engine                               │  │
│  │  - Consent management                                 │  │
│  │  - Retention enforcement                              │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    PostgreSQL Database                       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  GDPR Tables                                          │  │
│  │  - consent_records                                    │  │
│  │  - data_requests (access, erasure, portability)      │  │
│  │  - data_retention_policies                           │  │
│  │  - privacy_settings                                   │  │
│  │  - cookie_consents                                    │  │
│  │  - data_breach_incidents                             │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│               Encryption & Audit Services                    │
│  - AES-256-GCM encryption for sensitive data                │
│  - Comprehensive audit logging                              │
│  - Tamper-detection via hashing                             │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **User Request** → GDPR API Endpoint
2. **Request Validation** → Authentication & Authorization
3. **Service Processing** → GDPR Service Layer
4. **Data Operations** → Database + Encryption
5. **Audit Logging** → Compliance Trail
6. **Response** → User Notification

---

## GDPR Rights Implementation

### 1. Right to Access (Article 15)

**What It Means:** Users have the right to obtain confirmation of whether their personal data is being processed and access to that data.

**Implementation:**

#### Creating an Access Request

```bash
# Via API
curl -X POST http://localhost:8010/request/access \
  -H "Content-Type: application/json" \
  -d '{
    "id": "req-001",
    "ts": 1234567890,
    "origin": "user-app",
    "target": "gdpr",
    "intent": "create_access_request",
    "input": {
      "user_id": "user-uuid",
      "description": "I want a copy of all my personal data",
      "format": "json",
      "data_types": ["user", "projects", "artifacts", "consents"]
    }
  }'
```

**Response:**
```json
{
  "id": "req-001",
  "ts": 1234567890.5,
  "agent": "gdpr",
  "ok": true,
  "output": {
    "request_id": "dar-123456",
    "request_type": "access",
    "status": "pending",
    "due_date": "2025-12-16T12:00:00Z",
    "message": "Access request created. You will be notified when your data is ready (within 30 days)."
  }
}
```

#### Exported Data Structure

```json
{
  "export_metadata": {
    "user_id": "user-uuid",
    "export_date": "2025-11-16T12:00:00Z",
    "format": "json",
    "gdpr_basis": "Article 15 - Right to Access, Article 20 - Right to Portability"
  },
  "data": {
    "user": {
      "id": "user-uuid",
      "email": "user@example.com",
      "username": "johndoe",
      "created_at": "2025-01-01T00:00:00Z",
      ...
    },
    "projects": [...],
    "artifacts": [...],
    "executions": [...],
    "consents": [...],
    "privacy_settings": {...},
    "cookie_consents": [...],
    "audit_logs": [...]
  }
}
```

**SLA:** 30 days maximum response time

---

### 2. Right to Erasure / Right to be Forgotten (Article 17)

**What It Means:** Users have the right to request deletion or anonymization of their personal data.

**Implementation:**

#### Creating an Erasure Request

```bash
curl -X POST http://localhost:8010/request/erasure \
  -H "Content-Type: application/json" \
  -d '{
    "id": "req-002",
    "input": {
      "user_id": "user-uuid",
      "description": "Please delete my account and all associated data",
      "method": "anonymization"
    }
  }'
```

**Erasure Methods:**

1. **Anonymization** (Recommended)
   - Replaces PII with anonymized values
   - Preserves referential integrity
   - Maintains audit trails for legal compliance
   - Keeps aggregate statistics

2. **Soft Delete**
   - Marks records as deleted
   - Hides data from normal queries
   - Allows recovery if needed
   - Maintains referential integrity

3. **Hard Delete**
   - Permanently removes data
   - Cannot be undone
   - Use only when legally required
   - Checks for legal holds first

#### Anonymization Process

The anonymization engine:

1. ✅ Replaces email with `deleted_xxxxxxxx@anonymized.local`
2. ✅ Replaces username with `deleted_user_xxxxxx`
3. ✅ Removes password hash
4. ✅ Deactivates account
5. ✅ Anonymizes projects (renames to "Deleted Project xxxx")
6. ✅ Deletes API keys
7. ✅ Anonymizes consent records (removes IP/user agent)
8. ✅ Anonymizes audit logs (removes PII while preserving compliance trail)

**Legal Hold Protection:** Erasure requests are automatically blocked if a legal hold exists on the user's data.

---

### 3. Right to Data Portability (Article 20)

**What It Means:** Users have the right to receive their personal data in a structured, commonly used, and machine-readable format.

**Supported Formats:**

- **JSON** (default) - Structured, hierarchical data
- **CSV** - Tabular format for spreadsheet import
- **PDF** (future) - Human-readable format with formatted output

**Example Usage:**

```bash
curl -X POST http://localhost:8010/export/data \
  -H "Content-Type: application/json" \
  -d '{
    "id": "req-003",
    "input": {
      "user_id": "user-uuid",
      "format": "json",
      "data_types": null
    }
  }'
```

---

### 4. Consent Management (Article 7)

**What It Means:** Processing of personal data requires freely given, specific, informed, and unambiguous consent.

**Consent Categories:**

- **Essential** - Required for service functionality (always true)
- **Functional** - Enhanced features and user experience
- **Analytics** - Usage analytics and performance monitoring
- **Marketing** - Marketing communications and promotions
- **Third Party** - Sharing with third-party partners

**Legal Basis Options:**

- `consent` - User has given explicit consent
- `contract` - Processing necessary for contract performance
- `legal_obligation` - Required by law
- `vital_interest` - Protection of vital interests
- `public_task` - Performance of public interest task
- `legitimate_interest` - Legitimate business interests

#### Recording Consent

```bash
curl -X POST http://localhost:8010/consent/record \
  -H "Content-Type: application/json" \
  -d '{
    "id": "req-004",
    "input": {
      "user_id": "user-uuid",
      "purpose": "analytics",
      "purpose_description": "We use analytics to improve our service and user experience",
      "consent_given": true,
      "category": "analytics",
      "legal_basis": "consent",
      "method": "checkbox",
      "version": "1.0",
      "expires_in_days": 365
    }
  }'
```

#### Withdrawing Consent

```bash
curl -X POST http://localhost:8010/consent/withdraw \
  -H "Content-Type: application/json" \
  -d '{
    "id": "req-005",
    "input": {
      "user_id": "user-uuid",
      "purpose": "analytics",
      "method": "user_request"
    }
  }'
```

**Important:** When consent is withdrawn, all processing based on that consent must cease immediately.

#### Checking Consent

```bash
curl -X POST http://localhost:8010/consent/check \
  -H "Content-Type: application/json" \
  -d '{
    "id": "req-006",
    "input": {
      "user_id": "user-uuid",
      "purpose": "analytics"
    }
  }'
```

**Consent Expiration:** Consents can be configured to expire after a specified period (e.g., 12 months), requiring re-consent.

---

### 5. Privacy Settings

**What It Means:** Users can control how their data is used and shared.

#### Getting Privacy Settings

```bash
curl -X POST http://localhost:8010/privacy/settings/get \
  -H "Content-Type: application/json" \
  -d '{
    "id": "req-007",
    "input": {
      "user_id": "user-uuid"
    }
  }'
```

#### Updating Privacy Settings

```bash
curl -X POST http://localhost:8010/privacy/settings/update \
  -H "Content-Type: application/json" \
  -d '{
    "id": "req-008",
    "input": {
      "user_id": "user-uuid",
      "privacy_level": "minimal",
      "email_marketing_enabled": false,
      "analytics_enabled": false,
      "third_party_sharing": false,
      "ai_training_opt_in": false,
      "profiling_enabled": false
    }
  }'
```

**Privacy Level Presets:**

- **Minimal** - Maximum privacy, minimal data collection
- **Balanced** (default) - Balance between privacy and functionality
- **Convenience** - Enhanced features, more data sharing

---

### 6. Data Retention (Article 5)

**What It Means:** Personal data shall be kept no longer than necessary for the purposes for which it is processed.

#### Default Retention Policies

| Data Type | Retention Period | Basis | Method |
|-----------|-----------------|-------|--------|
| User Data | Indefinite | Service provision | Until account deletion |
| Audit Logs (AUTH) | 90 days | Security | Hard delete |
| Audit Logs (DATA_MODIFY) | 7 years | HIPAA compliance | Hard delete |
| Audit Logs (SECURITY) | 2 years | Security compliance | Hard delete |
| Executions | 1 year | Business need | Hard delete |
| Cookie Consents | Until expiration | GDPR requirement | Hard delete |
| Data Requests | 3 years | Legal requirement | Archive |

#### Enforcing Retention Policies

```bash
# Admin endpoint - run via cron job
curl -X POST http://localhost:8010/retention/enforce \
  -H "Content-Type: application/json" \
  -d '{
    "id": "req-009",
    "input": {}
  }'
```

**Automated Enforcement:** Set up a cron job to run retention enforcement daily:

```bash
# Add to crontab
0 2 * * * curl -X POST http://localhost:8010/retention/enforce
```

---

### 7. Breach Notification (Articles 33 & 34)

**Article 33:** Notify supervisory authority within 72 hours of becoming aware of a breach.

**Article 34:** Notify affected individuals without undue delay if high risk to rights and freedoms.

**Database Schema:** `data_breach_incidents` table tracks:

- Incident details and timeline
- Affected users and data types
- Containment measures
- Authority notification (72-hour deadline tracking)
- Individual notification
- Remediation steps
- Post-incident review

**Severity Levels:**

- **Low** - Minimal risk, no notification required
- **Medium** - Some risk, notify authority
- **High** - Significant risk, notify authority and individuals
- **Critical** - Severe risk, immediate notification required

---

## API Reference

### Endpoints

| Endpoint | Method | Purpose | Auth Required |
|----------|--------|---------|---------------|
| `/request/access` | POST | Create data access request | Yes |
| `/request/erasure` | POST | Create data erasure request | Yes |
| `/export/data` | POST | Export user data directly | Yes |
| `/export/generate` | POST | Generate export file for request | Admin |
| `/anonymize` | POST | Anonymize user data | Admin |
| `/consent/record` | POST | Record user consent | Yes |
| `/consent/withdraw` | POST | Withdraw consent | Yes |
| `/consent/check` | POST | Check consent status | Yes |
| `/privacy/settings/get` | POST | Get privacy settings | Yes |
| `/privacy/settings/update` | POST | Update privacy settings | Yes |
| `/retention/enforce` | POST | Enforce retention policies | Admin |
| `/health` | GET | Service health check | No |

### Request Format

All endpoints (except `/health`) use the standard BIOwerk `Msg` format:

```json
{
  "id": "unique-request-id",
  "ts": 1234567890.123,
  "origin": "client-id",
  "target": "gdpr",
  "intent": "action-name",
  "input": {
    "param1": "value1",
    "param2": "value2"
  }
}
```

### Response Format

All endpoints return the standard BIOwerk `Reply` format:

```json
{
  "id": "matching-request-id",
  "ts": 1234567890.456,
  "agent": "gdpr",
  "ok": true,
  "output": {
    "result": "..."
  },
  "state_hash": "blake3-hash"
}
```

---

## Database Schema

### consent_records

Tracks user consent for data processing activities.

```sql
CREATE TABLE consent_records (
  id VARCHAR(36) PRIMARY KEY,
  user_id VARCHAR(36) REFERENCES users(id) ON DELETE CASCADE,
  purpose VARCHAR(100) NOT NULL,           -- analytics, marketing, etc.
  purpose_description TEXT NOT NULL,
  consent_given BOOLEAN NOT NULL,
  consent_method VARCHAR(50) NOT NULL,     -- checkbox, api, email
  legal_basis VARCHAR(50) NOT NULL,        -- consent, contract, etc.
  consent_category VARCHAR(50) NOT NULL,   -- essential, functional, etc.
  withdrawn_at TIMESTAMP WITH TIME ZONE,
  withdrawal_method VARCHAR(50),
  ip_address VARCHAR(45),
  user_agent TEXT,
  consent_version VARCHAR(20) NOT NULL,
  expires_at TIMESTAMP WITH TIME ZONE,
  granted_at TIMESTAMP WITH TIME ZONE NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

**Key Indexes:**
- `(user_id, purpose, consent_given)` - Check consent status
- `(user_id, consent_given, withdrawn_at)` - Active consents
- `(expires_at, consent_given)` - Expired consents

### data_requests

Tracks data subject access requests (DSAR).

```sql
CREATE TABLE data_requests (
  id VARCHAR(36) PRIMARY KEY,
  user_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
  request_type VARCHAR(50) NOT NULL,       -- access, erasure, portability
  request_status VARCHAR(50) NOT NULL,     -- pending, in_progress, completed
  priority VARCHAR(20) DEFAULT 'normal',
  description TEXT,
  requested_data_types JSON,
  assigned_to VARCHAR(100),
  rejection_reason TEXT,
  completed_at TIMESTAMP WITH TIME ZONE,
  completed_by VARCHAR(100),

  -- Export details (for access/portability)
  export_format VARCHAR(20),               -- json, csv, pdf
  export_file_path VARCHAR(500),
  export_file_hash VARCHAR(64),
  export_expires_at TIMESTAMP WITH TIME ZONE,
  download_count INTEGER DEFAULT 0,

  -- Erasure details
  erasure_method VARCHAR(50),              -- soft_delete, anonymization, hard_delete
  data_deleted JSON,
  anonymization_applied BOOLEAN DEFAULT FALSE,

  -- Legal holds
  legal_hold BOOLEAN NOT NULL DEFAULT FALSE,
  legal_hold_reason TEXT,
  legal_hold_placed_at TIMESTAMP WITH TIME ZONE,
  legal_hold_released_at TIMESTAMP WITH TIME ZONE,

  -- Verification
  verification_required BOOLEAN NOT NULL DEFAULT TRUE,
  verification_method VARCHAR(50),
  verified_at TIMESTAMP WITH TIME ZONE,
  verified_by VARCHAR(100),

  -- SLA tracking (30-day deadline)
  due_date TIMESTAMP WITH TIME ZONE NOT NULL,
  sla_breached BOOLEAN NOT NULL DEFAULT FALSE,

  -- Audit
  ip_address VARCHAR(45),
  user_agent TEXT,
  requested_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

**Key Indexes:**
- `(user_id, request_type, request_status)` - User request history
- `(request_status, due_date)` - SLA monitoring
- `(legal_hold, user_id)` - Legal hold tracking

### Other Tables

- **data_retention_policies** - Retention rules by data type
- **privacy_settings** - User privacy preferences
- **cookie_consents** - Cookie consent tracking
- **data_breach_incidents** - Breach notification tracking

See migration file `002_add_gdpr_tables.py` for complete schema.

---

## Configuration

### Environment Variables

```bash
# Encryption (CRITICAL - Use KMS in production!)
ENCRYPTION_MASTER_KEY="<32+ character key>"
ENCRYPTION_KEY_ROTATION_DAYS=90

# GDPR Service
GDPR_EXPORT_BASE_PATH="/var/gdpr_exports"
GDPR_SLA_DAYS=30                        # Response time for DSARs
GDPR_EXPORT_EXPIRY_DAYS=30              # How long export files are available
GDPR_AUTO_RETENTION_ENABLED=true        # Enable automated retention enforcement

# Audit Configuration
AUDIT_ENABLED=true
AUDIT_ENCRYPT_SENSITIVE=true
AUDIT_RETENTION_DAYS=365
```

### Docker Compose

Add GDPR service to `docker-compose.yml`:

```yaml
gdpr:
  build: ./services/gdpr
  container_name: biowerk_gdpr
  ports:
    - "8010:8010"
  environment:
    - DATABASE_URL=postgresql://user:pass@postgres:5432/biowerk
    - ENCRYPTION_MASTER_KEY=${ENCRYPTION_MASTER_KEY}
    - GDPR_EXPORT_BASE_PATH=/var/gdpr_exports
  volumes:
    - gdpr_exports:/var/gdpr_exports
  depends_on:
    - postgres
    - redis
  networks:
    - biowerk_network

volumes:
  gdpr_exports:
```

---

## Operational Procedures

### Daily Operations

#### 1. Monitor Pending Requests

```sql
-- Check pending DSARs
SELECT id, user_id, request_type, request_status, due_date,
       EXTRACT(DAY FROM (due_date - NOW())) as days_remaining
FROM data_requests
WHERE request_status IN ('pending', 'in_progress')
ORDER BY due_date ASC;
```

#### 2. Enforce Retention Policies

```bash
# Run daily via cron (2 AM)
0 2 * * * curl -X POST http://localhost:8010/retention/enforce
```

#### 3. Check SLA Breaches

```sql
-- Find SLA breaches
SELECT id, user_id, request_type, requested_at, due_date
FROM data_requests
WHERE sla_breached = TRUE
  AND request_status != 'completed'
ORDER BY requested_at DESC;
```

### Weekly Operations

#### 1. Review Consent Withdrawals

```sql
-- Recently withdrawn consents
SELECT user_id, purpose, withdrawn_at, withdrawal_method
FROM consent_records
WHERE withdrawn_at >= NOW() - INTERVAL '7 days'
ORDER BY withdrawn_at DESC;
```

#### 2. Audit Privacy Settings Changes

```sql
-- Users who changed privacy settings
SELECT user_id, privacy_level, updated_at
FROM privacy_settings
WHERE updated_at >= NOW() - INTERVAL '7 days'
ORDER BY updated_at DESC;
```

### Monthly Operations

#### 1. GDPR Compliance Report

```sql
-- Monthly GDPR metrics
SELECT
  (SELECT COUNT(*) FROM data_requests WHERE request_type = 'access' AND created_at >= DATE_TRUNC('month', NOW())) as access_requests,
  (SELECT COUNT(*) FROM data_requests WHERE request_type = 'erasure' AND created_at >= DATE_TRUNC('month', NOW())) as erasure_requests,
  (SELECT COUNT(*) FROM data_requests WHERE sla_breached = TRUE AND created_at >= DATE_TRUNC('month', NOW())) as sla_breaches,
  (SELECT COUNT(*) FROM consent_records WHERE withdrawn_at >= DATE_TRUNC('month', NOW())) as consent_withdrawals;
```

#### 2. Review Retention Policies

```sql
-- Policies needing review
SELECT policy_name, data_type, next_review_date
FROM data_retention_policies
WHERE next_review_date <= NOW() + INTERVAL '30 days'
  AND is_active = TRUE
ORDER BY next_review_date ASC;
```

---

## Compliance Checklist

### GDPR Requirements

- [x] **Article 5** - Data minimization and storage limitation
  - ✅ Retention policies implemented
  - ✅ Automated enforcement

- [x] **Article 6** - Lawfulness of processing
  - ✅ Legal basis tracking in consent records

- [x] **Article 7** - Conditions for consent
  - ✅ Granular consent management
  - ✅ Easy withdrawal mechanism
  - ✅ Consent versioning

- [x] **Article 12** - Transparent information
  - ✅ Clear privacy settings UI
  - ✅ Purpose descriptions for consent

- [x] **Article 15** - Right to access
  - ✅ Data export in machine-readable format
  - ✅ 30-day SLA tracking

- [x] **Article 16** - Right to rectification
  - ✅ User profile update capabilities

- [x] **Article 17** - Right to erasure
  - ✅ Anonymization engine
  - ✅ Legal hold protection

- [x] **Article 20** - Right to data portability
  - ✅ JSON and CSV export formats

- [x] **Article 25** - Privacy by design
  - ✅ Privacy settings by default
  - ✅ Encryption at rest

- [x] **Article 30** - Records of processing
  - ✅ Comprehensive audit logging

- [x] **Article 32** - Security of processing
  - ✅ AES-256-GCM encryption
  - ✅ Access controls
  - ✅ Audit trails

- [x] **Article 33** - Breach notification (authority)
  - ✅ 72-hour deadline tracking
  - ✅ Incident management system

- [x] **Article 34** - Breach notification (individuals)
  - ✅ Individual notification tracking
  - ✅ Template system

### Additional Compliance

- [x] **CCPA** (California Consumer Privacy Act)
- [x] **HIPAA** (7-year audit log retention)
- [x] **PCI-DSS** (1-year minimum audit retention)

---

## Data Protection Impact Assessment (DPIA)

### Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Unauthorized data access | Low | High | Encryption, access controls, audit logs |
| Data breach | Low | Critical | Monitoring, incident response, notification system |
| Consent violation | Medium | High | Automated consent checking, withdrawal process |
| Excessive data retention | Medium | Medium | Automated retention enforcement |
| SLA breach (DSAR) | Low | Medium | Automated tracking, alerts |

### Privacy Measures

1. **Encryption at Rest** - AES-256-GCM for sensitive data
2. **Encryption in Transit** - TLS 1.3 for all communications
3. **Access Controls** - Role-based access control (RBAC)
4. **Audit Logging** - Comprehensive activity tracking
5. **Data Minimization** - Collect only necessary data
6. **Anonymization** - Privacy-preserving data transformation
7. **Retention Policies** - Automated data cleanup

### Regular Reviews

- **Quarterly** - Review and update retention policies
- **Bi-annually** - DPIA update and risk reassessment
- **Annually** - Full GDPR compliance audit

---

## Appendix

### A. Glossary

- **DSAR** - Data Subject Access Request
- **DPO** - Data Protection Officer
- **PII** - Personally Identifiable Information
- **KEK** - Key Encryption Key
- **DEK** - Data Encryption Key
- **SLA** - Service Level Agreement

### B. Legal Basis Types

- **Consent** - User has given clear consent
- **Contract** - Processing necessary for contract
- **Legal Obligation** - Required by law
- **Vital Interest** - Protect vital interests
- **Public Task** - Perform task in public interest
- **Legitimate Interest** - Legitimate business interest

### C. References

- [GDPR Official Text](https://gdpr-info.eu/)
- [ICO GDPR Guide](https://ico.org.uk/for-organisations/guide-to-data-protection/guide-to-the-general-data-protection-regulation-gdpr/)
- [NIST Privacy Framework](https://www.nist.gov/privacy-framework)

### D. Contact

For GDPR-related inquiries:
- **Data Protection Officer (DPO)**: dpo@biowerk.com
- **Privacy Team**: privacy@biowerk.com
- **Security Team**: security@biowerk.com

---

**Document Version Control:**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2025-11-16 | Claude AI | Initial comprehensive GDPR implementation |

