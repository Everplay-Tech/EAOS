# BIOwerk Disaster Recovery Plan

## Executive Summary

This document provides comprehensive disaster recovery (DR) procedures for the BIOwerk platform. It defines Recovery Time Objectives (RTO), Recovery Point Objectives (RPO), backup strategies, and step-by-step recovery procedures.

**Document Version:** 1.0
**Last Updated:** 2024-01-15
**Review Frequency:** Quarterly

---

## Table of Contents

1. [Overview](#overview)
2. [Recovery Objectives](#recovery-objectives)
3. [Backup Strategy](#backup-strategy)
4. [Disaster Scenarios](#disaster-scenarios)
5. [Recovery Procedures](#recovery-procedures)
6. [Verification and Testing](#verification-and-testing)
7. [Roles and Responsibilities](#roles-and-responsibilities)
8. [Appendix](#appendix)

---

## Overview

### Scope

This DR plan covers all critical components of the BIOwerk platform:

- **Databases**: PostgreSQL, MongoDB, Redis
- **Application Services**: All microservices (mesh, osteon, myocyte, synapse, etc.)
- **Configuration**: Docker Compose, environment files, certificates
- **Data**: User data, GDPR exports, audit logs
- **Observability**: Prometheus, Grafana, Loki data

### DR Principles

1. **Automated Backups**: All critical data is backed up automatically
2. **Encryption**: All backups are encrypted at rest with AES-256
3. **Off-site Storage**: Critical backups are replicated to cloud storage
4. **Regular Testing**: DR procedures are tested monthly
5. **Documentation**: All procedures are documented and version-controlled

---

## Recovery Objectives

### Recovery Time Objective (RTO)

**Target RTO: 4 hours**

| Component | RTO Target | Priority |
|-----------|------------|----------|
| PostgreSQL Database | 2 hours | Critical |
| MongoDB Database | 2 hours | Critical |
| Redis Cache | 1 hour | High |
| Application Services | 3 hours | Critical |
| Observability Stack | 4 hours | Medium |

### Recovery Point Objective (RPO)

**Target RPO: 1 hour**

| Component | RPO Target | Backup Frequency |
|-----------|------------|------------------|
| PostgreSQL | 1 hour | Continuous (WAL) + Daily full |
| MongoDB | 1 hour | Daily full + Oplog |
| Redis | 1 hour | Every 3 hours |
| Configuration | 0 (Git) | Continuous |

---

## Backup Strategy

### Backup Types

#### 1. Full Backups

- **PostgreSQL**: Daily at 2:00 AM UTC via `pg_dump`
- **MongoDB**: Daily at 2:30 AM UTC via `mongodump`
- **Redis**: Every 3 hours via RDB snapshot
- **Retention**: 30 days daily, 12 weeks weekly, 12 months monthly

#### 2. Incremental Backups

- **PostgreSQL WAL**: Continuous archiving for point-in-time recovery
- **MongoDB Oplog**: Continuous for replica set deployments
- **Retention**: 7 days

#### 3. Configuration Backups

- **Git Repository**: All configuration files version-controlled
- **Secrets**: Encrypted and stored in secure vault
- **Certificates**: Backed up with restricted access

### Backup Locations

#### Primary: Local Storage

```
/var/backups/biowerk/
├── postgres/
│   ├── daily/
│   ├── weekly/
│   ├── monthly/
│   └── wal/
├── mongodb/
│   ├── daily/
│   ├── weekly/
│   ├── monthly/
│   └── oplog/
└── redis/
    ├── daily/
    ├── weekly/
    └── monthly/
```

#### Secondary: Cloud Storage (S3/Azure/GCS)

- **S3 Bucket**: `s3://biowerk-backups-production/`
- **Storage Class**: STANDARD_IA (Infrequent Access)
- **Encryption**: SSE-S3 or SSE-KMS
- **Lifecycle**: Glacier after 90 days, delete after 1 year

### Backup Verification

All backups are automatically verified:

1. **Checksum Validation**: SHA-256 checksums generated and verified
2. **Restore Testing**: Weekly automated restore tests to staging environment
3. **Integrity Checks**: Database-specific integrity validation (pg_restore --list, mongorestore --dryRun)
4. **Monitoring**: Prometheus alerts for backup failures

---

## Disaster Scenarios

### Scenario 1: Database Corruption

**Indicators:**
- Database errors in application logs
- Data inconsistencies
- Failed integrity checks

**Recovery Procedure:** [See Database Recovery](#database-recovery)

### Scenario 2: Complete System Failure

**Indicators:**
- All services down
- Infrastructure unavailable
- Data center outage

**Recovery Procedure:** [See Full System Recovery](#full-system-recovery)

### Scenario 3: Partial Service Failure

**Indicators:**
- Specific microservice failures
- Degraded performance
- Service unavailable

**Recovery Procedure:** [See Service Recovery](#service-recovery)

### Scenario 4: Data Loss / Corruption

**Indicators:**
- Missing data
- Corrupted files
- User reports of data loss

**Recovery Procedure:** [See Point-in-Time Recovery](#point-in-time-recovery)

### Scenario 5: Security Breach / Ransomware

**Indicators:**
- Unauthorized access
- Encrypted files
- Unusual system behavior

**Recovery Procedure:** [See Security Incident Recovery](#security-incident-recovery)

---

## Recovery Procedures

### Database Recovery

#### PostgreSQL Recovery

##### Full Database Restore

```bash
# 1. Stop the application services
docker-compose stop mesh osteon myocyte synapse circadian nucleus chaperone

# 2. Find the backup file
ls -lh /var/backups/biowerk/postgres/daily/

# 3. Run restore script
docker exec -it biowerk-backup-orchestrator \
  /app/scripts/restore_postgres.sh \
  /var/backups/biowerk/postgres/daily/postgres_YYYYMMDD_HHMMSS.dump.zst.enc

# 4. Verify restoration
docker exec -it biowerk-postgres psql -U biowerk -d biowerk -c "SELECT COUNT(*) FROM pg_tables;"

# 5. Restart services
docker-compose start mesh osteon myocyte synapse circadian nucleus chaperone

# 6. Verify application functionality
curl http://localhost:8080/health
```

##### Point-in-Time Recovery (PITR)

```bash
# 1. Stop PostgreSQL
docker-compose stop postgres

# 2. Run PITR restore
docker exec -it biowerk-backup-orchestrator \
  /app/scripts/restore_postgres.sh \
  --target-time "2024-01-15 14:30:00" \
  /var/backups/biowerk/postgres/daily/postgres_20240115_020000.dump.zst.enc

# 3. Start PostgreSQL
docker-compose start postgres

# 4. Verify data
docker exec -it biowerk-postgres psql -U biowerk -d biowerk
```

#### MongoDB Recovery

```bash
# 1. Stop application services
docker-compose stop mesh osteon myocyte synapse circadian nucleus chaperone

# 2. Run restore script
docker exec -it biowerk-backup-orchestrator \
  /app/scripts/restore_mongodb.sh \
  /var/backups/biowerk/mongodb/daily/mongodb_YYYYMMDD_HHMMSS.tar.zst.enc

# 3. Verify restoration
docker exec -it biowerk-mongodb mongosh --eval "db.getCollectionNames()"

# 4. Restart services
docker-compose start mesh osteon myocyte synapse circadian nucleus chaperone
```

#### Redis Recovery

```bash
# 1. Stop Redis
docker-compose stop redis

# 2. Run restore script
docker exec -it biowerk-backup-orchestrator \
  /app/scripts/restore_redis.sh \
  /var/backups/biowerk/redis/daily/redis_YYYYMMDD_HHMMSS.tar.zst.enc

# 3. Start Redis
docker-compose start redis

# 4. Verify data
docker exec -it biowerk-redis redis-cli DBSIZE
```

### Full System Recovery

#### Prerequisites

- Access to backup storage (local or S3)
- Docker and Docker Compose installed
- Git repository access
- Encryption keys available

#### Recovery Steps

```bash
# 1. Clone repository
git clone https://github.com/your-org/biowerk.git
cd biowerk
git checkout production  # or specific tag/commit

# 2. Restore configuration files
# Ensure .env file is configured with production settings
cp .env.production .env

# 3. Restore encryption keys
# Copy encryption key from secure vault
mkdir -p /etc/biowerk
echo "YOUR_ENCRYPTION_KEY" > /etc/biowerk/backup-encryption.key
chmod 600 /etc/biowerk/backup-encryption.key

# 4. Start infrastructure services first
docker-compose up -d postgres mongodb redis

# Wait for health checks to pass
docker-compose ps

# 5. Restore databases
# PostgreSQL
docker exec -it biowerk-backup-orchestrator \
  /app/scripts/restore_postgres.sh \
  /var/backups/biowerk/postgres/daily/postgres_latest.dump.zst.enc

# MongoDB
docker exec -it biowerk-backup-orchestrator \
  /app/scripts/restore_mongodb.sh \
  /var/backups/biowerk/mongodb/daily/mongodb_latest.tar.zst.enc

# Redis
docker exec -it biowerk-backup-orchestrator \
  /app/scripts/restore_redis.sh \
  /var/backups/biowerk/redis/daily/redis_latest.tar.zst.enc

# 6. Start application services
docker-compose up -d mesh osteon myocyte synapse circadian nucleus chaperone gdpr

# 7. Start observability stack
docker-compose up -d prometheus grafana loki alertmanager

# 8. Start backup service
docker-compose up -d backup-orchestrator

# 9. Verify all services
docker-compose ps
curl http://localhost:8080/health

# 10. Check metrics and logs
curl http://localhost:9090/-/healthy  # Prometheus
curl http://localhost:3000/api/health  # Grafana
```

### Service Recovery

For individual microservice failures:

```bash
# 1. Identify failed service
docker-compose ps

# 2. Check logs
docker-compose logs <service-name>

# 3. Restart service
docker-compose restart <service-name>

# 4. If restart fails, rebuild
docker-compose up -d --build <service-name>

# 5. Verify
curl http://localhost:<port>/health
```

### Point-in-Time Recovery

When you need to recover to a specific point in time:

```bash
# 1. Identify the target time
TARGET_TIME="2024-01-15 14:30:00"

# 2. Find closest backup before target time
ls -lt /var/backups/biowerk/postgres/daily/

# 3. Restore with target time
docker exec -it biowerk-backup-orchestrator \
  /app/scripts/restore_postgres.sh \
  --target-time "${TARGET_TIME}" \
  /var/backups/biowerk/postgres/daily/postgres_20240115_020000.dump.zst.enc
```

### Security Incident Recovery

In case of security breach or ransomware:

```bash
# 1. IMMEDIATELY isolate the system
docker-compose down
# Disconnect from network if needed

# 2. Preserve evidence
docker-compose logs > incident_logs_$(date +%Y%m%d_%H%M%S).txt
# Take disk snapshots if possible

# 3. Assess the breach
# - Identify compromised components
# - Determine attack vector
# - Check backup integrity

# 4. Restore from clean backup
# Use backup from BEFORE the breach occurred
# Verify backup was taken before breach time

# 5. Rebuild system in clean environment
# Follow Full System Recovery procedure

# 6. Apply security patches
# Update all components
# Rotate all credentials
# Review and enhance security measures

# 7. Monitor for suspicious activity
# Enhanced logging
# Security scanning
```

---

## Verification and Testing

### Automated Testing

The backup system includes automated testing:

```bash
# Weekly automated restore test
# Runs every Sunday at 4 AM UTC
# Configured in backup-orchestrator

# Manual trigger
curl -X POST http://localhost:8090/verify/postgres
curl -X POST http://localhost:8090/verify/mongodb
curl -X POST http://localhost:8090/verify/redis
```

### Monthly DR Drill

Perform a full DR drill monthly:

1. **Week 1**: Test database restoration
2. **Week 2**: Test full system recovery
3. **Week 3**: Test point-in-time recovery
4. **Week 4**: Review and update procedures

### Checklist for DR Testing

- [ ] All backup files are accessible
- [ ] Encryption keys are available
- [ ] Restore scripts execute successfully
- [ ] Data integrity verified post-restore
- [ ] Application functionality confirmed
- [ ] RTO/RPO targets met
- [ ] Monitoring and alerting operational
- [ ] Documentation updated with findings

---

## Roles and Responsibilities

### Incident Commander

- **Role**: Overall DR coordination
- **Responsibilities**:
  - Declare disaster
  - Coordinate recovery efforts
  - Communicate with stakeholders
  - Make critical decisions

### Database Administrator

- **Role**: Database recovery
- **Responsibilities**:
  - Execute database restore procedures
  - Verify data integrity
  - Optimize post-recovery performance
  - Document recovery process

### Infrastructure Lead

- **Role**: System recovery
- **Responsibilities**:
  - Restore infrastructure
  - Configure networking
  - Manage cloud resources
  - Coordinate with vendors

### Application Lead

- **Role**: Application recovery
- **Responsibilities**:
  - Restore application services
  - Verify functionality
  - Coordinate testing
  - Communicate with users

### Security Officer

- **Role**: Security validation
- **Responsibilities**:
  - Verify system security
  - Review access logs
  - Ensure compliance
  - Coordinate with legal if needed

---

## Appendix

### A. Contact Information

#### Emergency Contacts

| Role | Name | Phone | Email |
|------|------|-------|-------|
| Incident Commander | TBD | +1-XXX-XXX-XXXX | ic@example.com |
| Database Admin | TBD | +1-XXX-XXX-XXXX | dba@example.com |
| Infrastructure Lead | TBD | +1-XXX-XXX-XXXX | infra@example.com |
| Security Officer | TBD | +1-XXX-XXX-XXXX | security@example.com |

#### Vendor Contacts

| Vendor | Service | Support Phone | Support Email |
|--------|---------|---------------|---------------|
| AWS | Cloud Infrastructure | 1-800-XXX-XXXX | aws-support@example.com |
| PagerDuty | Alerting | 1-800-XXX-XXXX | support@pagerduty.com |

### B. Backup File Naming Convention

```
<database>_<YYYYMMDD>_<HHMMSS>.<format>.<compression>.<encryption>

Examples:
postgres_20240115_020000.dump.zst.enc
mongodb_20240115_023000.tar.zst.enc
redis_20240115_030000.tar.zst.enc
```

### C. Encryption Key Management

**Key Location**: Secure vault (e.g., AWS Secrets Manager, HashiCorp Vault)

**Key Rotation**: Every 90 days

**Key Recovery**: Contact Security Officer

**Backup Key Storage**: Offline in secure location

### D. S3 Bucket Structure

```
s3://biowerk-backups-production/
├── postgres/
│   ├── daily/
│   ├── weekly/
│   ├── monthly/
│   └── wal/
├── mongodb/
│   ├── daily/
│   ├── weekly/
│   └── monthly/
├── redis/
│   ├── daily/
│   ├── weekly/
│   └── monthly/
└── config/
    ├── docker-compose/
    ├── certs/
    └── env-files/
```

### E. Monitoring Dashboards

- **Backup Status**: http://grafana:3000/d/backups/backup-monitoring
- **System Health**: http://grafana:3000/d/health/system-health
- **Prometheus**: http://prometheus:9090
- **Alertmanager**: http://alertmanager:9093

### F. Compliance and Auditing

- **GDPR**: All backups include GDPR export data
- **Audit Logs**: Retained for 1 year minimum
- **Backup Logs**: Retained for 90 days
- **Compliance Officer**: compliance@example.com

### G. Recovery Time Estimates

| Operation | Estimated Time |
|-----------|----------------|
| PostgreSQL Full Restore (100GB) | 1-2 hours |
| MongoDB Full Restore (50GB) | 45-90 minutes |
| Redis Full Restore (10GB) | 15-30 minutes |
| Full System Recovery | 3-4 hours |
| Service Restart | 5-10 minutes |
| Network Configuration | 30-60 minutes |

### H. References

- [Backup Configuration](../backup-service/config/backup.conf)
- [Prometheus Alerting Rules](../observability/prometheus-rules/backup-alerts.yml)
- [Docker Compose Configuration](../docker-compose.yml)
- [Security Documentation](./security.md)
- [GDPR Compliance](../AUDIT_LOGGING_IMPLEMENTATION.md)

---

## Document Maintenance

### Review Schedule

- **Monthly**: Technical accuracy review
- **Quarterly**: Full DR drill and documentation update
- **Annually**: Complete DR plan revision

### Change Log

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2024-01-15 | 1.0 | Initial version | BIOwerk Team |

### Approval

| Role | Name | Signature | Date |
|------|------|-----------|------|
| CTO | TBD | _________ | _____ |
| Security Officer | TBD | _________ | _____ |
| Compliance Officer | TBD | _________ | _____ |

---

**END OF DOCUMENT**
