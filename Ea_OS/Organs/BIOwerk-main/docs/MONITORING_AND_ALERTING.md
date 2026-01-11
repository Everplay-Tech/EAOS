# Monitoring and Alerting Guide

**Enterprise-Grade Observability for BIOwerk Platform**

This document describes the comprehensive monitoring and alerting infrastructure for the BIOwerk microservices platform, including centralized logging (Loki), metrics (Prometheus), visualization (Grafana), and alerting (Alertmanager with PagerDuty integration).

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Quick Start](#quick-start)
- [Components](#components)
- [Configuration](#configuration)
- [Alert Rules](#alert-rules)
- [Dashboards](#dashboards)
- [PagerDuty Integration](#pagerduty-integration)
- [Production Deployment](#production-deployment)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)

---

## Architecture Overview

### The PLG Stack (Prometheus, Loki, Grafana)

```
┌─────────────────────────────────────────────────────────────┐
│                     BIOwerk Services                          │
│  (Mesh, Osteon, Myocyte, Synapse, Circadian, Nucleus, etc.) │
│                                                               │
│  ┌──────────────┐              ┌──────────────┐             │
│  │ Structured   │              │  Prometheus  │             │
│  │ JSON Logs    │              │   Metrics    │             │
│  │ (stdout)     │              │  /metrics    │             │
│  └──────┬───────┘              └──────┬───────┘             │
└─────────┼──────────────────────────────┼────────────────────┘
          │                              │
          ▼                              ▼
    ┌─────────┐                    ┌──────────┐
    │Promtail │                    │Prometheus│
    │(Shipper)│                    │ Server   │
    └────┬────┘                    └────┬─────┘
         │                              │
         │                              ├─────► Evaluate Alert Rules
         ▼                              │
    ┌────────┐                          ▼
    │  Loki  │◄────────────────────┬────────────┐
    │ Server │                     │Alertmanager│
    └───┬────┘                     └─────┬──────┘
        │                                │
        │                                ├──► PagerDuty (Critical)
        │                                ├──► Slack (All Levels)
        │                                └──► Email (Teams)
        │
        └──────────┬─────────────────────┘
                   │
                   ▼
            ┌──────────┐
            │ Grafana  │
            │Dashboard │
            └──────────┘
```

### Data Flow

1. **Metrics Collection**
   - All services expose `/metrics` endpoints (Prometheus format)
   - Prometheus scrapes metrics every 15 seconds
   - Infrastructure exporters provide database, Redis, and system metrics

2. **Log Aggregation**
   - Services output structured JSON logs to stdout
   - Promtail reads Docker container logs
   - Logs are shipped to Loki with extracted labels
   - Trace IDs correlate logs with distributed traces (OpenTelemetry)

3. **Alerting**
   - Prometheus evaluates metric-based alert rules every 15 seconds
   - Loki evaluates log-based alert rules every 1 minute
   - Alerts sent to Alertmanager
   - Alertmanager routes, groups, and deduplicates alerts
   - Notifications sent to PagerDuty, Slack, and Email based on severity

4. **Visualization**
   - Grafana queries both Prometheus (metrics) and Loki (logs)
   - Pre-built dashboards for system overview, services, and infrastructure
   - Alerts visualized in Grafana with drill-down capabilities

---

## Quick Start

### 1. Copy Environment Configuration

```bash
cp .env.example .env
```

### 2. Configure Alerting Integrations

Edit `.env` and set the following:

```bash
# PagerDuty Integration Keys
PAGERDUTY_SERVICE_KEY=your-actual-service-key
PAGERDUTY_SECURITY_SERVICE_KEY=your-security-service-key

# Slack Webhook URLs
SLACK_CRITICAL_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
SLACK_WARNINGS_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
# ... (configure all webhook URLs)

# Email Configuration
SMTP_HOST=smtp.gmail.com:587
SMTP_USERNAME=your-email@example.com
SMTP_PASSWORD=your-app-password
DEFAULT_EMAIL_TO=ops-team@example.com
```

### 3. Start the Monitoring Stack

```bash
# Start all services including monitoring
docker-compose up -d

# Verify monitoring services are running
docker-compose ps | grep -E "loki|promtail|prometheus|alertmanager|grafana"

# Check health
curl http://localhost:3100/ready  # Loki
curl http://localhost:9090/-/healthy  # Prometheus
curl http://localhost:9093/-/healthy  # Alertmanager
curl http://localhost:3000/api/health  # Grafana
```

### 4. Access Monitoring UIs

- **Grafana**: http://localhost:3000 (admin / admin - change on first login)
- **Prometheus**: http://localhost:9090
- **Alertmanager**: http://localhost:9093
- **Loki**: http://localhost:3100

### 5. Verify Data Collection

```bash
# Check Prometheus targets
open http://localhost:9090/targets

# Check Loki logs
curl -G -s "http://localhost:3100/loki/api/v1/query" \
  --data-urlencode 'query={service_name=~".+"}' | jq

# View alerts
open http://localhost:9090/alerts
```

---

## Components

### Loki (Centralized Logging)

**Purpose**: Horizontally-scalable log aggregation system inspired by Prometheus

**Configuration**: `observability/loki-config.yaml`

**Features**:
- 31-day log retention (configurable)
- Automatic log indexing by labels
- Full-text search capabilities
- Integration with Grafana for visualization
- Alert rules based on log patterns

**Key Endpoints**:
- Query API: `http://loki:3100/loki/api/v1/query`
- Health: `http://loki:3100/ready`
- Metrics: `http://loki:3100/metrics`

**Storage**: `/loki` volume (Docker volume: `loki_data`)

### Promtail (Log Shipper)

**Purpose**: Agent that ships logs from Docker containers to Loki

**Configuration**: `observability/promtail-config.yaml`

**Features**:
- Automatic service discovery via Docker labels
- JSON log parsing with field extraction
- Label extraction (service, level, trace_id, etc.)
- Log metrics generation (errors, warnings, etc.)

**Log Labels Extracted**:
- `service_name` - Service identifier
- `level` - Log level (INFO, WARNING, ERROR)
- `trace_id` - OpenTelemetry trace correlation
- `span_id` - OpenTelemetry span correlation

### Prometheus (Metrics)

**Purpose**: Time-series database for metrics collection and alerting

**Configuration**: `observability/prometheus-config.yaml`

**Features**:
- 30-day metric retention (50GB limit)
- 15-second scrape interval
- Alert rule evaluation
- Service discovery for all BIOwerk services

**Scraped Services**:
- All BIOwerk microservices (mesh, osteon, myocyte, etc.)
- PostgreSQL (via postgres-exporter)
- MongoDB (via mongodb-exporter)
- Redis (via redis-exporter)
- PgBouncer (via pgbouncer-exporter)
- System metrics (via node-exporter)
- Container metrics (via cAdvisor)

**Key Endpoints**:
- Metrics Query: `http://prometheus:9090/api/v1/query`
- Targets: `http://prometheus:9090/targets`
- Alerts: `http://prometheus:9090/alerts`

### Alertmanager (Alert Routing)

**Purpose**: Alert deduplication, grouping, and routing

**Configuration**: `observability/alertmanager-config.yaml`

**Features**:
- Multi-channel routing (PagerDuty, Slack, Email)
- Alert grouping and deduplication
- Inhibition rules (prevent alert storms)
- Silence management
- Time-based routing (business hours, maintenance windows)

**Notification Channels**:
- **PagerDuty**: Critical and security alerts (24/7)
- **Slack**: All severity levels (different channels)
- **Email**: Team-specific alerts (database, compliance, etc.)

**Routing Logic**:
```
Critical Alerts → PagerDuty + Slack (#critical)
Security Alerts → PagerDuty + Slack (#security)
Warnings → Slack (#warnings)
Info → Slack (#info)
Database Issues → Email (database-team) + Slack (#database)
Compliance → Email (compliance-team) + Slack (#compliance)
```

### Grafana (Visualization)

**Purpose**: Unified dashboard and visualization platform

**Configuration**:
- Provisioning: `observability/grafana/provisioning/`
- Dashboards: `observability/grafana/dashboards/`

**Features**:
- Pre-configured datasources (Prometheus, Loki, Alertmanager)
- Auto-provisioned dashboards
- Alert visualization
- Log-to-trace correlation (via trace_id)
- User management and RBAC

**Pre-built Dashboards**:
- **BIOwerk Overview**: System-wide health and metrics
- **Service Details**: Per-service deep dive
- **Infrastructure**: Host and container metrics
- **Database Performance**: PostgreSQL, MongoDB, Redis metrics

---

## Configuration

### Environment Variables

All monitoring configuration is managed via environment variables in `.env`:

```bash
# Logging
LOG_FORMAT=json              # json or text
LOG_LEVEL=INFO               # DEBUG, INFO, WARNING, ERROR, CRITICAL

# Deployment
ENVIRONMENT=production       # Used as label in metrics/logs
REGION=us-east-1            # Multi-region deployments

# PagerDuty
PAGERDUTY_SERVICE_KEY=xxx   # Primary service key
PAGERDUTY_SECURITY_SERVICE_KEY=xxx  # Security team key

# SMTP
SMTP_HOST=smtp.gmail.com:587
SMTP_USERNAME=alerts@company.com
SMTP_PASSWORD=app-password

# Slack
SLACK_CRITICAL_WEBHOOK_URL=https://hooks.slack.com/...
SLACK_CRITICAL_CHANNEL=#biowerk-critical-alerts

# Grafana
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=secure-password-here
GRAFANA_SECRET_KEY=32-char-random-string
```

### Structured Logging

All services use structured JSON logging with automatic trace correlation:

```python
from matrix.logging_config import setup_logging

logger = setup_logging("my-service")
logger.info("Processing request", extra={"user_id": 123, "action": "create"})
```

**Log Output** (JSON):
```json
{
  "timestamp": "2024-01-15T10:30:45.123456Z",
  "level": "INFO",
  "logger": "my-service",
  "message": "Processing request",
  "service_name": "my-service",
  "trace_id": "a1b2c3d4e5f6g7h8",
  "span_id": "1234567890abcdef",
  "user_id": 123,
  "action": "create"
}
```

---

## Alert Rules

### Metric-Based Alerts (Prometheus)

**Location**: `observability/prometheus-rules/biowerk-alerts.yml`

**Categories**:
1. **Service Health** - Service down, high error rates
2. **Latency & Performance** - High API latency, slow queries
3. **Database Health** - Connection pool exhaustion, replication lag
4. **Resource Utilization** - High CPU, memory, disk usage
5. **Circuit Breaker** - Open circuit breakers, retry exhaustion
6. **Rate Limiting** - High rate limit hits
7. **Security** - Authentication failures, brute force attacks
8. **Business Metrics** - Traffic drops, no requests

**Example Alert**:
```yaml
- alert: HighErrorRate
  expr: |
    (
      sum by (service) (rate(http_requests_total{status=~"5.."}[5m]))
      /
      sum by (service) (rate(http_requests_total[5m]))
    ) > 0.05
  for: 5m
  labels:
    severity: critical
    category: error_rate
  annotations:
    summary: "High error rate on {{ $labels.service }}"
    description: "{{ $labels.service }} has {{ $value | humanizePercentage }} errors"
```

### Log-Based Alerts (Loki)

**Location**: `observability/loki-rules/biowerk-log-alerts.yml`

**Categories**:
1. **Error Log Patterns** - High error rates, OOM errors, DB connection failures
2. **Security Log Patterns** - SQL injection attempts, XSS attempts, suspicious IPs
3. **Application Errors** - Timeouts, circuit breaker triggers, dependency failures
4. **GDPR & Compliance** - Unusual data exports, unauthorized access
5. **Performance** - Slow queries, high cache miss rates
6. **Service Health** - Service restarts, health check failures

**Example Alert**:
```yaml
- alert: DatabaseConnectionErrors
  expr: |
    sum by (service_name) (
      rate({service_name=~".+"} |~ "(?i)database.*connection.*error" [5m])
    ) > 1
  for: 3m
  labels:
    severity: critical
    category: database
  annotations:
    summary: "Database connection errors in {{ $labels.service_name }}"
```

---

## Dashboards

### BIOwerk System Overview

**Access**: Grafana → Dashboards → BIOwerk → System Overview

**Panels**:
- Services Up (stat)
- Request Rate by Service (timeseries)
- Response Time p95/p99 (timeseries)
- HTTP Status Codes (timeseries)
- Service Logs (live log stream)

### Custom Dashboards

Create custom dashboards and export as JSON:

1. Build dashboard in Grafana UI
2. Settings → JSON Model → Copy JSON
3. Save to `observability/grafana/dashboards/biowerk/your-dashboard.json`
4. Restart Grafana: `docker-compose restart grafana`

---

## PagerDuty Integration

### Setup Steps

1. **Create PagerDuty Services**

   Go to PagerDuty → Services → New Service:

   - **BIOwerk Critical**: For all critical alerts
   - **BIOwerk Security**: For security-specific alerts
   - **BIOwerk Database**: For database-specific alerts (optional)

2. **Get Integration Keys**

   For each service:
   - Settings → Integrations → Add Integration
   - Integration Type: **Events API V2**
   - Copy the **Integration Key**

3. **Configure Environment Variables**

   ```bash
   # .env file
   PAGERDUTY_SERVICE_KEY=<integration-key-for-critical>
   PAGERDUTY_SECURITY_SERVICE_KEY=<integration-key-for-security>
   ```

4. **Configure Escalation Policies**

   PagerDuty → Escalation Policies:
   - Level 1: On-call engineer (immediate)
   - Level 2: Team lead (15 minutes)
   - Level 3: Engineering manager (30 minutes)

5. **Test Integration**

   ```bash
   # Send test alert
   curl -X POST http://localhost:9093/api/v1/alerts -d '[
     {
       "labels": {
         "alertname": "TestAlert",
         "severity": "critical",
         "service": "test"
       },
       "annotations": {
         "summary": "This is a test alert"
       }
     }
   ]'
   ```

6. **Verify in PagerDuty**

   Check Incidents → Should see test incident

### Alert Severity Mapping

| Prometheus Severity | PagerDuty Action | Response Time |
|---------------------|------------------|---------------|
| `critical`          | Trigger incident | Immediate     |
| `warning`           | No PagerDuty     | N/A           |
| `info`              | No PagerDuty     | N/A           |

### On-Call Best Practices

1. **Runbooks**: Link to runbooks in alert annotations
2. **Escalation**: Configure 3-level escalation
3. **Maintenance Windows**: Schedule during deployments
4. **Postmortems**: Create incidents for all pages
5. **Alert Tuning**: Review and reduce false positives monthly

---

## Production Deployment

### Checklist

- [ ] Update all default passwords
  - `GRAFANA_ADMIN_PASSWORD`
  - PostgreSQL passwords

- [ ] Configure PagerDuty integration keys
  - `PAGERDUTY_SERVICE_KEY`
  - `PAGERDUTY_SECURITY_SERVICE_KEY`

- [ ] Set up Slack webhooks
  - Create dedicated channels (#biowerk-critical-alerts, etc.)
  - Configure webhook URLs in `.env`

- [ ] Configure SMTP for email alerts
  - Use dedicated alert email (alerts@company.com)
  - Configure SPF/DKIM records

- [ ] Enable TLS/HTTPS
  - Generate SSL certificates
  - Configure reverse proxy (nginx/Traefik)

- [ ] Set appropriate log retention
  - Development: 7 days
  - Production: 31-90 days (compliance dependent)

- [ ] Configure remote storage (optional but recommended)
  - Prometheus: Thanos/Cortex for long-term metrics
  - Loki: S3/GCS backend for scalability

- [ ] Enable authentication
  - Grafana: LDAP/OAuth integration
  - Prometheus/Alertmanager: Basic auth or OAuth proxy

- [ ] Set up backup and disaster recovery
  - Backup Grafana database
  - Backup Alertmanager silences and configuration

- [ ] Implement high availability
  - Multiple Prometheus replicas
  - Alertmanager clustering (3+ instances)
  - Loki in microservices mode

### Scaling Considerations

**Small Deployment** (< 10 services)
- Single Prometheus instance
- Single Loki instance
- Single Alertmanager
- SQLite for Grafana

**Medium Deployment** (10-50 services)
- 2x Prometheus instances (HA)
- Loki single-binary with object storage
- 3x Alertmanager cluster
- PostgreSQL for Grafana

**Large Deployment** (> 50 services)
- Prometheus federation + remote storage (Thanos)
- Loki microservices mode (separate read/write)
- 5+ Alertmanager cluster
- Grafana HA with load balancer

---

## Troubleshooting

### No Metrics in Prometheus

**Check**:
1. Service is running: `docker-compose ps <service>`
2. Metrics endpoint is accessible: `curl http://<service>:8001/metrics`
3. Prometheus can reach service: Check Prometheus → Targets
4. Scrape config is correct: `observability/prometheus-config.yaml`

### No Logs in Loki

**Check**:
1. Promtail is running: `docker-compose ps promtail`
2. Promtail can reach Loki: `docker logs biowerk-promtail`
3. Docker socket is mounted: `docker-compose.yml` volumes
4. Log format is correct: Check service logs are JSON

### Alerts Not Firing

**Check**:
1. Alert rule syntax: Prometheus → Alerts → Check for errors
2. Alert expression returns data: Test in Prometheus → Graph
3. Alert duration: Check `for:` clause (e.g., `for: 5m`)
4. Alertmanager is receiving: Check Alertmanager UI

### PagerDuty Not Receiving Alerts

**Check**:
1. Integration key is correct: `.env` file
2. Alertmanager can reach PagerDuty: `docker logs biowerk-alertmanager`
3. Route configuration: `observability/alertmanager-config.yaml`
4. Test with API: Send test alert via Alertmanager API

### Grafana Dashboard Empty

**Check**:
1. Time range: Top-right corner, ensure it covers recent data
2. Datasource: Configuration → Data Sources → Test
3. Query: Edit panel → Check query syntax
4. Data exists: Run query in Explore

---

## Best Practices

### Alert Design

1. **Alert on Symptoms, Not Causes**
   - ✅ "High API latency" (symptom)
   - ❌ "High CPU usage" (cause)

2. **Make Alerts Actionable**
   - Include runbook link
   - Describe expected action
   - Add context (affected users, impact)

3. **Avoid Alert Fatigue**
   - Use appropriate severity levels
   - Implement inhibition rules
   - Group related alerts
   - Review and tune regularly

4. **SLO-Based Alerting**
   - Define SLIs (latency, error rate, availability)
   - Set SLOs (99.9% uptime, p95 < 200ms)
   - Alert on SLO violations

### Dashboard Design

1. **Use the RED Method**
   - **R**ate: Request rate
   - **E**rrors: Error rate
   - **D**uration: Response time

2. **Include Context**
   - Show both current and historical data
   - Add annotations for deployments
   - Link to related dashboards

3. **Optimize for Glanceability**
   - Use stat panels for key metrics
   - Color-code by severity
   - Limit panels per dashboard (< 20)

### Log Management

1. **Use Structured Logging**
   - JSON format for machine parsing
   - Consistent field names
   - Include trace correlation

2. **Log Levels**
   - ERROR: Requires immediate attention
   - WARNING: Potential issue, monitor
   - INFO: Normal operation, business events
   - DEBUG: Detailed debugging (dev only)

3. **Avoid Logging Sensitive Data**
   - Passwords, API keys, tokens
   - PII without encryption
   - Full credit card numbers

### Metric Collection

1. **Metric Naming**
   - Use Prometheus conventions: `<namespace>_<name>_<unit>`
   - Examples: `http_requests_total`, `db_query_duration_seconds`

2. **Label Cardinality**
   - Keep cardinality low (< 1000 unique combinations)
   - Avoid high-cardinality labels (user_id, request_id)
   - Use aggregation for high-cardinality data

3. **Metric Types**
   - Counter: Monotonically increasing (requests, errors)
   - Gauge: Current value (connections, memory)
   - Histogram: Distribution (latency, size)
   - Summary: Similar to histogram with quantiles

---

## Additional Resources

- **Prometheus**: https://prometheus.io/docs/
- **Loki**: https://grafana.com/docs/loki/latest/
- **Grafana**: https://grafana.com/docs/grafana/latest/
- **Alertmanager**: https://prometheus.io/docs/alerting/latest/alertmanager/
- **PagerDuty**: https://support.pagerduty.com/docs/services-and-integrations

---

## Support

For issues or questions:
1. Check logs: `docker-compose logs <service>`
2. Review configuration files in `observability/`
3. Test connectivity between components
4. Consult this documentation and official docs
5. Create an issue in the repository

**Monitoring the Monitoring System**

Remember: Your monitoring infrastructure needs monitoring too!
- Set up external uptime monitoring (Pingdom, StatusCake, etc.)
- Monitor Prometheus/Loki disk usage
- Alert on monitoring component failures
- Regularly test alert delivery (monthly)
- Backup monitoring configurations and data
