# BIOwerk Backup & DR - Quick Start Guide

## Overview

This guide provides quick reference for common backup and disaster recovery operations in BIOwerk.

## Prerequisites

- Docker and Docker Compose installed
- BIOwerk services running
- Sufficient disk space for backups (recommend 3x database size)

## Quick Reference

### Service Endpoints

- **Backup Orchestrator API**: http://localhost:8090
- **Backup Orchestrator Health**: http://localhost:8090/health
- **Backup Orchestrator Metrics**: http://localhost:8090/metrics
- **Backup Status**: http://localhost:8090/status

### Backup Locations

```bash
# Local backups
/var/backups/biowerk/
├── postgres/     # PostgreSQL backups
├── mongodb/      # MongoDB backups
└── redis/        # Redis backups

# Inside container
docker exec biowerk-backup-orchestrator ls -lh /var/backups/biowerk/postgres/daily/
```

## Common Operations

### 1. Trigger Manual Backup

#### PostgreSQL
```bash
# Via API
curl -X POST http://localhost:8090/backup \
  -H "Content-Type: application/json" \
  -d '{"database_type": "postgres", "verify": true}'

# Via script (inside container)
docker exec biowerk-backup-orchestrator /app/scripts/backup_postgres.sh
```

#### MongoDB
```bash
# Via API
curl -X POST http://localhost:8090/backup \
  -H "Content-Type: application/json" \
  -d '{"database_type": "mongodb", "verify": true}'

# Via script
docker exec biowerk-backup-orchestrator /app/scripts/backup_mongodb.sh
```

#### Redis
```bash
# Via API
curl -X POST http://localhost:8090/backup \
  -H "Content-Type: application/json" \
  -d '{"database_type": "redis", "verify": true}'

# Via script
docker exec biowerk-backup-orchestrator /app/scripts/backup_redis.sh
```

### 2. Check Backup Status

```bash
# All databases
curl http://localhost:8090/status | jq

# Specific database
curl http://localhost:8090/status?database_type=postgres | jq

# Via Docker logs
docker-compose logs backup-orchestrator
```

### 3. Verify Backup

```bash
# Verify latest backup
curl -X POST http://localhost:8090/verify/postgres
curl -X POST http://localhost:8090/verify/mongodb
curl -X POST http://localhost:8090/verify/redis

# Manual verification
docker exec biowerk-backup-orchestrator \
  /app/scripts/backup_postgres.sh verify \
  /var/backups/biowerk/postgres/daily/postgres_20240115_020000.dump.zst.enc
```

### 4. Restore Database

#### PostgreSQL Full Restore

```bash
# Find backup file
docker exec biowerk-backup-orchestrator \
  ls -lht /var/backups/biowerk/postgres/daily/ | head -5

# Restore (dry run first)
docker exec biowerk-backup-orchestrator \
  /app/scripts/restore_postgres.sh --dry-run \
  /var/backups/biowerk/postgres/daily/postgres_20240115_020000.dump.zst.enc

# Actual restore
docker exec biowerk-backup-orchestrator \
  /app/scripts/restore_postgres.sh \
  /var/backups/biowerk/postgres/daily/postgres_20240115_020000.dump.zst.enc
```

#### MongoDB Full Restore

```bash
# Find backup file
docker exec biowerk-backup-orchestrator \
  ls -lht /var/backups/biowerk/mongodb/daily/ | head -5

# Restore
docker exec biowerk-backup-orchestrator \
  /app/scripts/restore_mongodb.sh \
  /var/backups/biowerk/mongodb/daily/mongodb_20240115_023000.tar.zst.enc
```

#### Redis Full Restore

```bash
# Find backup file
docker exec biowerk-backup-orchestrator \
  ls -lht /var/backups/biowerk/redis/daily/ | head -5

# Restore
docker exec biowerk-backup-orchestrator \
  /app/scripts/restore_redis.sh \
  /var/backups/biowerk/redis/daily/redis_20240115_030000.tar.zst.enc
```

### 5. Point-in-Time Recovery (PostgreSQL)

```bash
# Restore to specific time
docker exec biowerk-backup-orchestrator \
  /app/scripts/restore_postgres.sh \
  --target-time "2024-01-15 14:30:00" \
  /var/backups/biowerk/postgres/daily/postgres_20240115_020000.dump.zst.enc
```

### 6. View Backup Schedule

```bash
# View scheduled jobs
curl http://localhost:8090/schedule | jq

# Expected output:
# {
#   "jobs": [
#     {
#       "id": "backup_postgres",
#       "name": "Backup postgres",
#       "next_run": "2024-01-16T02:00:00",
#       "trigger": "cron[0 2 * * *]"
#     },
#     ...
#   ]
# }
```

## Configuration

### Environment Variables

Key backup configuration variables (set in `.env`):

```bash
# Backup schedules (cron format)
POSTGRES_BACKUP_SCHEDULE=0 2 * * *     # 2 AM daily
MONGODB_BACKUP_SCHEDULE=30 2 * * *     # 2:30 AM daily
REDIS_BACKUP_SCHEDULE=0 3 * * *        # 3 AM daily

# Retention policies
BACKUP_RETENTION_DAYS=30               # Daily backups
BACKUP_RETENTION_WEEKLY=12             # Weekly backups (weeks)
BACKUP_RETENTION_MONTHLY=12            # Monthly backups (months)

# Backup options
BACKUP_COMPRESSION=zstd                # gzip, zstd, or none
BACKUP_ENCRYPTION_ENABLED=true         # Enable encryption
BACKUP_VERIFY=true                     # Verify after backup

# S3/Cloud storage
BACKUP_S3_ENABLED=false                # Enable S3 uploads
BACKUP_S3_BUCKET=biowerk-backups       # S3 bucket name
BACKUP_S3_REGION=us-east-1            # AWS region
```

### Edit Configuration

```bash
# Edit backup configuration
docker exec -it biowerk-backup-orchestrator vi /etc/biowerk/backup.conf

# Restart service to apply changes
docker-compose restart backup-orchestrator
```

## Monitoring

### Prometheus Metrics

```bash
# View backup metrics
curl http://localhost:8090/metrics | grep biowerk_backup

# Key metrics:
# - biowerk_backup_total{database_type, status}
# - biowerk_backup_duration_seconds{database_type}
# - biowerk_backup_size_bytes{database_type, backup_type}
# - biowerk_backup_last_success_timestamp{database_type}
```

### Grafana Dashboard

Access the backup monitoring dashboard:

```
http://localhost:3000/d/backups/backup-monitoring
```

### Alerts

Backup alerts are configured in Prometheus:

```bash
# View active alerts
curl http://localhost:9090/api/v1/alerts | jq

# View alert rules
curl http://localhost:9090/api/v1/rules | jq
```

## Troubleshooting

### Backup Failures

```bash
# Check service logs
docker-compose logs backup-orchestrator

# Check specific backup logs
docker exec biowerk-backup-orchestrator tail -f /var/log/biowerk/backup-postgres.log
docker exec biowerk-backup-orchestrator tail -f /var/log/biowerk/backup-mongodb.log
docker exec biowerk-backup-orchestrator tail -f /var/log/biowerk/backup-redis.log

# Check disk space
docker exec biowerk-backup-orchestrator df -h /var/backups/biowerk

# Check service health
curl http://localhost:8090/health
```

### Restore Issues

```bash
# Verify backup file integrity
docker exec biowerk-backup-orchestrator \
  sha256sum -c /var/backups/biowerk/postgres/daily/postgres_20240115_020000.dump.zst.enc.sha256

# Check restore logs
docker exec biowerk-backup-orchestrator tail -f /var/log/biowerk/restore-postgres.log

# Test restore with dry-run
docker exec biowerk-backup-orchestrator \
  /app/scripts/restore_postgres.sh --dry-run <backup-file>
```

### Missing Encryption Key

```bash
# Check if encryption key exists
docker exec biowerk-backup-orchestrator ls -l /etc/biowerk/backup-encryption.key

# Generate new key (WARNING: old backups won't be recoverable)
docker exec biowerk-backup-orchestrator openssl rand -base64 32 > /etc/biowerk/backup-encryption.key
docker exec biowerk-backup-orchestrator chmod 600 /etc/biowerk/backup-encryption.key
```

## S3/Cloud Storage Setup

### Configure S3 Backups

1. Create S3 bucket:
```bash
aws s3 mb s3://biowerk-backups --region us-east-1
```

2. Configure bucket lifecycle:
```bash
aws s3api put-bucket-lifecycle-configuration \
  --bucket biowerk-backups \
  --lifecycle-configuration file://s3-lifecycle.json
```

3. Update `.env`:
```bash
BACKUP_S3_ENABLED=true
BACKUP_S3_BUCKET=biowerk-backups
BACKUP_S3_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
```

4. Restart backup service:
```bash
docker-compose restart backup-orchestrator
```

### Verify S3 Upload

```bash
# List backups in S3
aws s3 ls s3://biowerk-backups/postgres/

# Download from S3
aws s3 cp s3://biowerk-backups/postgres/postgres_20240115_020000.dump.zst.enc ./
```

## Testing

### Automated DR Test

```bash
# Trigger automated DR test (weekly)
curl -X POST http://localhost:8090/verify/postgres
curl -X POST http://localhost:8090/verify/mongodb
curl -X POST http://localhost:8090/verify/redis

# Check test results
curl http://localhost:8090/status | jq
```

### Manual DR Drill

See [DISASTER_RECOVERY.md](./DISASTER_RECOVERY.md) for complete DR drill procedures.

## Best Practices

1. **Regular Testing**: Test restores monthly, not just when disaster strikes
2. **Monitor Alerts**: Configure PagerDuty/Slack alerts for backup failures
3. **Off-site Backups**: Always maintain off-site backups (S3, Azure, GCP)
4. **Encryption Keys**: Store encryption keys in secure vault, separate from backups
5. **Documentation**: Keep DR procedures up-to-date and accessible
6. **Access Control**: Limit backup/restore access to authorized personnel only
7. **Verify Backups**: Always verify backup integrity before trusting them
8. **Retention Policy**: Balance storage costs with compliance requirements

## Emergency Contacts

- **Backup Service Issues**: ops@example.com
- **DR Coordinator**: dr-lead@example.com
- **24/7 On-Call**: +1-XXX-XXX-XXXX

## Additional Resources

- [Full Disaster Recovery Plan](./DISASTER_RECOVERY.md)
- [Backup Configuration Reference](../backup-service/config/backup.conf)
- [Prometheus Alert Rules](../observability/prometheus-rules/backup-alerts.yml)
- [API Documentation](http://localhost:8090/docs)
