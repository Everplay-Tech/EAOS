# Monitoring & Alerting Quick Start

**Enterprise-grade centralized logging and alerting for BIOwerk**

## What's Been Added

✅ **Centralized Logging with Loki**
- JSON structured logs with trace correlation
- 31-day retention
- Full-text search and filtering

✅ **Metrics Collection with Prometheus**
- 15-second scrape interval
- 30-day retention
- All services + infrastructure monitored

✅ **Visualization with Grafana**
- Pre-built dashboards
- Auto-provisioned datasources
- Unified metrics and logs view

✅ **Alerting with Alertmanager**
- **PagerDuty integration** for critical alerts (24/7)
- **Slack integration** for all severity levels
- **Email notifications** for team-specific alerts
- Intelligent routing and deduplication

✅ **Production-Ready Alert Rules**
- 40+ metric-based alerts (service health, latency, resources)
- 20+ log-based alerts (errors, security, compliance)
- Severity-based routing (critical → PagerDuty)

## Quick Start (5 Minutes)

### 1. Configure Alerting

Edit `.env` file:

```bash
# REQUIRED: PagerDuty Service Keys
PAGERDUTY_SERVICE_KEY=your-pagerduty-integration-key-here

# RECOMMENDED: Slack Webhook URLs
SLACK_CRITICAL_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
SLACK_WARNINGS_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# OPTIONAL: Email Alerts
SMTP_HOST=smtp.gmail.com:587
SMTP_USERNAME=alerts@yourcompany.com
SMTP_PASSWORD=your-app-password
```

**Get PagerDuty Key**: PagerDuty → Services → [Your Service] → Integrations → Events API V2

**Get Slack Webhook**: Slack → Apps → Incoming Webhooks → Add to Channel

### 2. Start Monitoring Stack

```bash
# Start all services including monitoring
docker-compose up -d

# Verify monitoring services
docker-compose ps | grep -E "loki|prometheus|grafana|alertmanager"

# Run test suite
./scripts/test-monitoring.sh
```

### 3. Access Dashboards

| Service       | URL                      | Username | Password  |
|---------------|--------------------------|----------|-----------|
| **Grafana**   | http://localhost:3000    | admin    | admin*    |
| Prometheus    | http://localhost:9090    | -        | -         |
| Alertmanager  | http://localhost:9093    | -        | -         |

*Change default password on first login

### 4. Verify Everything Works

```bash
# Check Prometheus targets are up
curl http://localhost:9090/targets

# Query logs from Loki
curl -G http://localhost:3100/loki/api/v1/query \
  --data-urlencode 'query={service_name=~".+"}' | jq

# View active alerts
curl http://localhost:9090/alerts
```

## What Gets Monitored

### Services (All BIOwerk Microservices)
- ✅ Mesh (API Gateway)
- ✅ Osteon (Document/Writer)
- ✅ Myocyte (Analysis/Spreadsheet)
- ✅ Synapse (Presentation)
- ✅ Circadian (Scheduler)
- ✅ Nucleus (Orchestrator)
- ✅ Chaperone (Import/Export)
- ✅ GDPR (Compliance)
- ✅ Larry, Moe, Harry (PHI2 Coordinators)

### Infrastructure
- ✅ PostgreSQL (via postgres-exporter)
- ✅ MongoDB (via mongodb-exporter)
- ✅ Redis (via redis-exporter)
- ✅ PgBouncer (via pgbouncer-exporter)
- ✅ System metrics (via node-exporter)
- ✅ Container metrics (via cAdvisor)

### Key Metrics Tracked
- Request rate, latency (p50, p95, p99), error rate
- Database connections, query performance, replication lag
- Memory usage, CPU usage, disk space
- Circuit breaker state, retry failures
- Authentication failures, rate limit hits
- Business metrics (traffic patterns)

## Alert Examples

### Critical Alerts (PagerDuty + Slack)
- **ServiceDown**: Service unavailable for 2+ minutes
- **HighErrorRate**: >5% error rate for 5 minutes
- **CriticalAPILatency**: p99 > 5 seconds
- **DatabaseConnectionErrors**: DB connection failures
- **OutOfMemoryErrors**: OOM errors detected
- **PotentialBruteForceAttack**: >50 auth failures/min

### Warning Alerts (Slack Only)
- **HighAPILatency**: p95 > 2 seconds
- **HighCPUUsage**: CPU > 80% for 10 minutes
- **HighMemoryUsage**: Memory > 85% for 10 minutes
- **CircuitBreakerOpen**: Circuit breaker open for 2+ minutes

### Log-Based Alerts
- **HighErrorLogRate**: >10 errors/sec in logs
- **DatabaseConnectionErrors**: DB errors in logs
- **UnauthorizedDataAccess**: Unauthorized access attempts
- **SlowQueriesDetected**: Slow query warnings

## Grafana Dashboards

### Pre-Built Dashboards

1. **BIOwerk System Overview**
   - Service health status
   - Request rate across services
   - Response time percentiles
   - HTTP status code distribution
   - Live log streaming

2. **Community Dashboards** (Import these)
   - Node Exporter Full: ID 1860
   - Docker Containers: ID 193
   - PostgreSQL Database: ID 9628
   - Redis: ID 763

### Import Community Dashboard

1. Open Grafana → Dashboards → Import
2. Enter dashboard ID (e.g., 1860)
3. Select Prometheus datasource
4. Click Import

## Testing the Alert Pipeline

### Send Test Alert

```bash
# Send test critical alert
curl -X POST http://localhost:9093/api/v1/alerts -H "Content-Type: application/json" -d '[
  {
    "labels": {
      "alertname": "TestAlert",
      "severity": "critical",
      "service": "test"
    },
    "annotations": {
      "summary": "Test alert - please ignore",
      "description": "Testing alerting pipeline"
    }
  }
]'
```

**Expected Result**:
- Alert visible in Alertmanager: http://localhost:9093
- PagerDuty incident created (if configured)
- Slack message in #biowerk-critical-alerts (if configured)

## Directory Structure

```
BIOwerk/
├── observability/                      # All monitoring config
│   ├── loki-config.yaml               # Loki settings
│   ├── promtail-config.yaml           # Log shipper
│   ├── prometheus-config.yaml         # Metrics collection
│   ├── alertmanager-config.yaml       # Alert routing
│   ├── prometheus-rules/              # Metric-based alerts
│   │   └── biowerk-alerts.yml         # 40+ alert rules
│   ├── loki-rules/                    # Log-based alerts
│   │   └── biowerk-log-alerts.yml     # 20+ log alerts
│   └── grafana/                       # Dashboards
│       ├── provisioning/              # Auto-config
│       └── dashboards/                # Dashboard JSON
├── docs/
│   └── MONITORING_AND_ALERTING.md     # Full documentation
├── scripts/
│   └── test-monitoring.sh             # Verification script
└── docker-compose.yml                 # Updated with monitoring stack
```

## Components Added to docker-compose.yml

```yaml
services:
  loki:                    # Log aggregation
  promtail:               # Log shipper
  prometheus:             # Metrics database
  alertmanager:           # Alert routing
  grafana:                # Visualization
  postgres-exporter:      # PostgreSQL metrics
  redis-exporter:         # Redis metrics
  mongodb-exporter:       # MongoDB metrics
  pgbouncer-exporter:     # PgBouncer metrics
  node-exporter:          # Host metrics
  cadvisor:               # Container metrics
```

## Production Checklist

Before deploying to production:

- [ ] **Change default passwords**
  - Grafana admin password
  - PostgreSQL passwords (if using Grafana DB)

- [ ] **Configure PagerDuty**
  - Create separate services for Critical, Security, Database
  - Set up escalation policies
  - Add on-call schedules

- [ ] **Set up Slack channels**
  - #biowerk-critical-alerts
  - #biowerk-warnings
  - #biowerk-database
  - #biowerk-security
  - Configure webhooks for each

- [ ] **Configure SMTP**
  - Use dedicated alerts email
  - Configure SPF/DKIM
  - Test email delivery

- [ ] **Enable TLS/HTTPS**
  - Set up reverse proxy
  - Obtain SSL certificates
  - Update all URLs

- [ ] **Tune alert thresholds**
  - Monitor for false positives
  - Adjust thresholds based on baseline
  - Document changes

- [ ] **Set up backup**
  - Backup Grafana database
  - Backup Prometheus data
  - Backup alert configurations

## Troubleshooting

### No metrics showing in Grafana
1. Check Prometheus targets: http://localhost:9090/targets
2. Verify service `/metrics` endpoints are accessible
3. Check Prometheus logs: `docker logs biowerk-prometheus`

### No logs in Loki
1. Verify Promtail is running: `docker-compose ps promtail`
2. Check Promtail logs: `docker logs biowerk-promtail`
3. Verify services are logging JSON to stdout

### Alerts not firing
1. Check alert rules syntax: http://localhost:9090/rules
2. Test alert expression in Prometheus UI
3. Verify Alertmanager configuration

### PagerDuty not receiving alerts
1. Verify integration key is correct in `.env`
2. Check Alertmanager logs for errors
3. Test with manual alert (see "Testing" section above)

## Documentation

- **Quick Reference**: `observability/README.md`
- **Full Guide**: `docs/MONITORING_AND_ALERTING.md`
- **Alert Rules**: `observability/prometheus-rules/biowerk-alerts.yml`
- **Log Alerts**: `observability/loki-rules/biowerk-log-alerts.yml`

## Support

- **Test Script**: `./scripts/test-monitoring.sh`
- **View Logs**: `docker-compose logs <service>`
- **Restart Service**: `docker-compose restart <service>`

## Next Steps

1. ✅ Review and adjust alert thresholds for your environment
2. ✅ Create custom Grafana dashboards for your KPIs
3. ✅ Set up long-term storage (Thanos/Cortex for metrics, S3 for logs)
4. ✅ Implement runbook links in alert annotations
5. ✅ Schedule regular alert rule reviews (quarterly)
6. ✅ Set up meta-monitoring (monitor the monitoring system)

---

**Need Help?**

- Consult `docs/MONITORING_AND_ALERTING.md` for detailed documentation
- Run `./scripts/test-monitoring.sh` to diagnose issues
- Check service logs: `docker-compose logs <service-name>`
