# BIOwerk Observability Configuration

This directory contains all configuration files for the BIOwerk monitoring and alerting stack.

## Architecture: PLG Stack

**P**rometheus + **L**oki + **G**rafana

- **Prometheus**: Metrics collection and alerting
- **Loki**: Centralized log aggregation
- **Grafana**: Unified visualization and dashboards
- **Alertmanager**: Alert routing to PagerDuty, Slack, Email
- **Promtail**: Log shipper (Docker → Loki)
- **Exporters**: PostgreSQL, Redis, MongoDB, Node, cAdvisor metrics

## Directory Structure

```
observability/
├── README.md                           # This file
├── loki-config.yaml                    # Loki configuration
├── promtail-config.yaml                # Promtail log shipper config
├── prometheus-config.yaml              # Prometheus scrape configuration
├── alertmanager-config.yaml            # Alert routing configuration
├── prometheus-rules/
│   └── biowerk-alerts.yml              # Metric-based alert rules
├── loki-rules/
│   └── biowerk-log-alerts.yml          # Log-based alert rules
└── grafana/
    ├── provisioning/
    │   ├── datasources/
    │   │   └── datasources.yaml        # Auto-provision datasources
    │   └── dashboards/
    │       └── dashboards.yaml         # Auto-provision dashboards
    └── dashboards/
        ├── README.md                   # Dashboard documentation
        └── biowerk/
            └── biowerk-overview.json   # Main system dashboard
```

## Quick Start

### 1. Prerequisites

Ensure `.env` file is configured with:
- PagerDuty integration keys
- Slack webhook URLs
- SMTP credentials
- Grafana admin password

### 2. Start Monitoring Stack

```bash
# Start all services including monitoring
docker-compose up -d

# Check monitoring services
docker-compose ps | grep -E "loki|prometheus|grafana|alertmanager"
```

### 3. Access UIs

| Service       | URL                      | Credentials       |
|---------------|--------------------------|-------------------|
| Grafana       | http://localhost:3000    | admin / (see .env)|
| Prometheus    | http://localhost:9090    | None              |
| Alertmanager  | http://localhost:9093    | None              |
| Loki API      | http://localhost:3100    | None              |

### 4. Verify Data Collection

```bash
# Check Prometheus targets are up
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'

# Query logs from Loki
curl -G -s "http://localhost:3100/loki/api/v1/query" \
  --data-urlencode 'query={service_name=~".+"}' \
  --data-urlencode 'limit=10' | jq

# Check active alerts
curl -s http://localhost:9090/api/v1/alerts | jq '.data.alerts[] | {alertname: .labels.alertname, state: .state}'
```

## Configuration Files

### Loki (`loki-config.yaml`)

**Key Settings**:
- Retention: 31 days
- Ingestion rate: 50 MB/s
- Query limits: 10,000 entries per query
- Storage: BoltDB + filesystem

**Modify for Production**:
- Increase retention if compliance requires
- Configure S3/GCS backend for scalability
- Enable microservices mode for high load

### Promtail (`promtail-config.yaml`)

**Key Settings**:
- Scrapes all Docker containers with label `com.docker.compose.project=biowerk`
- Parses JSON logs automatically
- Extracts labels: service_name, level, trace_id, span_id
- Generates metrics from logs

**Labels Extracted**:
- `service_name`: Service identifier
- `level`: Log level (INFO, ERROR, etc.)
- `trace_id`: OpenTelemetry trace ID
- `span_id`: OpenTelemetry span ID

### Prometheus (`prometheus-config.yaml`)

**Key Settings**:
- Scrape interval: 15 seconds
- Retention: 30 days or 50GB
- Scrapes all BIOwerk services on `/metrics` endpoint
- Includes exporters for PostgreSQL, Redis, MongoDB, etc.

**Scrape Targets**:
- BIOwerk services: mesh, osteon, myocyte, synapse, circadian, nucleus, chaperone, gdpr, larry, moe, harry
- Databases: postgres-exporter, mongodb-exporter, redis-exporter, pgbouncer-exporter
- Infrastructure: node-exporter, cadvisor
- Monitoring: prometheus, loki, grafana, alertmanager, promtail

### Alertmanager (`alertmanager-config.yaml`)

**Key Settings**:
- Routes alerts by severity (critical, warning, info)
- Sends critical alerts to PagerDuty + Slack
- Sends warnings to Slack only
- Implements inhibition rules to prevent alert storms

**Notification Channels**:
1. **PagerDuty**: Critical and security alerts
2. **Slack**: All severity levels (different channels)
3. **Email**: Team-specific (database, compliance, etc.)

**Routing Logic**:
```
Critical → PagerDuty + Slack (#critical)
Warning → Slack (#warnings)
Info → Slack (#info)
Security → PagerDuty + Slack (#security)
Database → Email + Slack (#database)
```

## Alert Rules

### Metric-Based Alerts (`prometheus-rules/biowerk-alerts.yml`)

**Categories**:
1. Service Health (down, high error rate)
2. Latency & Performance (high latency, slow queries)
3. Database Health (connection exhaustion, replication lag)
4. Resource Utilization (CPU, memory, disk)
5. Circuit Breaker (open breakers, retry exhaustion)
6. Security (auth failures, brute force)
7. Business Metrics (traffic drops)

**Severity Levels**:
- `critical`: Requires immediate action (pages on-call)
- `warning`: Should be investigated soon
- `info`: Informational only

### Log-Based Alerts (`loki-rules/biowerk-log-alerts.yml`)

**Categories**:
1. Error Log Patterns (high error rate, OOM, DB errors)
2. Security Log Patterns (SQL injection, XSS, suspicious IPs)
3. Application Errors (timeouts, circuit breakers, dependencies)
4. GDPR & Compliance (unusual exports, unauthorized access)
5. Performance (slow queries, cache misses)
6. Service Health (restarts, health check failures)

## Grafana Dashboards

### Pre-built Dashboards

1. **BIOwerk System Overview** (`biowerk-overview.json`)
   - Services up/down
   - Request rate by service
   - Response time (p95, p99)
   - HTTP status codes
   - Live service logs

### Adding Custom Dashboards

1. Create dashboard in Grafana UI
2. Export as JSON (Settings → JSON Model)
3. Save to `grafana/dashboards/biowerk/<name>.json`
4. Restart Grafana to load

### Community Dashboards

Import these popular dashboards (Grafana → Import):
- Node Exporter Full: ID 1860
- Docker Container Metrics: ID 193
- PostgreSQL Database: ID 9628
- Redis Dashboard: ID 763

## Testing Alert Pipeline

### 1. Send Test Alert

```bash
# Send test alert to Alertmanager
curl -X POST http://localhost:9093/api/v1/alerts -H "Content-Type: application/json" -d '[
  {
    "labels": {
      "alertname": "TestAlert",
      "severity": "critical",
      "service": "test",
      "category": "test"
    },
    "annotations": {
      "summary": "This is a test alert",
      "description": "Testing the alerting pipeline"
    },
    "startsAt": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'",
    "endsAt": "'"$(date -u -d '+5 minutes' +%Y-%m-%dT%H:%M:%SZ)"'"
  }
]'
```

### 2. Verify Alert Delivery

- **Alertmanager**: http://localhost:9093/#/alerts
- **PagerDuty**: Check for incident
- **Slack**: Check configured channel
- **Email**: Check inbox

### 3. Silence Alert

```bash
# Create silence
curl -X POST http://localhost:9093/api/v1/silences -H "Content-Type: application/json" -d '{
  "matchers": [
    {
      "name": "alertname",
      "value": "TestAlert",
      "isRegex": false
    }
  ],
  "startsAt": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'",
  "endsAt": "'"$(date -u -d '+1 hour' +%Y-%m-%dT%H:%M:%SZ)"'",
  "createdBy": "api-test",
  "comment": "Testing silence functionality"
}'
```

## Troubleshooting

### No Metrics in Prometheus

```bash
# Check Prometheus targets
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.health != "up")'

# Check service metrics endpoint
curl http://localhost:8080/metrics  # mesh service example

# Check Prometheus logs
docker logs biowerk-prometheus
```

### No Logs in Loki

```bash
# Check Promtail is running
docker-compose ps promtail

# Check Promtail logs
docker logs biowerk-promtail

# Query Loki directly
curl -G -s "http://localhost:3100/loki/api/v1/label/service_name/values" | jq
```

### Alerts Not Firing

```bash
# Check alert rules loaded
curl -s http://localhost:9090/api/v1/rules | jq '.data.groups[] | {name: .name, rules: .rules | length}'

# Test alert expression
curl -G -s "http://localhost:9090/api/v1/query" \
  --data-urlencode 'query=up{job=~"biowerk-.*"}' | jq

# Check Alertmanager logs
docker logs biowerk-alertmanager
```

## Production Deployment

### Security Hardening

1. **Enable Authentication**
   - Grafana: OAuth/LDAP integration
   - Prometheus: Basic auth via reverse proxy
   - Alertmanager: Basic auth via reverse proxy

2. **Enable TLS/HTTPS**
   - Configure reverse proxy (nginx, Traefik)
   - Obtain SSL certificates (Let's Encrypt)
   - Update all URLs in configuration

3. **Network Isolation**
   - Use Docker networks for service isolation
   - Expose only Grafana externally
   - Internal services behind VPN/firewall

### High Availability

1. **Prometheus**
   - Run 2+ instances with same config
   - Use remote storage (Thanos, Cortex)
   - Configure federation if needed

2. **Loki**
   - Switch to microservices mode
   - Use S3/GCS for chunks and index
   - Run multiple queriers and ingesters

3. **Alertmanager**
   - Run 3+ instances in cluster mode
   - Configure `--cluster.peer` addresses
   - Use shared storage for silences

4. **Grafana**
   - Use PostgreSQL for database (not SQLite)
   - Run multiple instances behind load balancer
   - Share configuration via provisioning

### Backup & Recovery

```bash
# Backup Prometheus data
docker run --rm -v prometheus_data:/data -v $(pwd):/backup ubuntu tar czf /backup/prometheus-backup.tar.gz /data

# Backup Loki data
docker run --rm -v loki_data:/data -v $(pwd):/backup ubuntu tar czf /backup/loki-backup.tar.gz /data

# Backup Grafana dashboards
curl -u admin:password http://localhost:3000/api/search | jq -r '.[].uid' | \
  xargs -I {} curl -u admin:password http://localhost:3000/api/dashboards/uid/{} > grafana-dashboards-backup.json
```

## Additional Resources

- **Full Documentation**: `../docs/MONITORING_AND_ALERTING.md`
- **Prometheus Docs**: https://prometheus.io/docs/
- **Loki Docs**: https://grafana.com/docs/loki/
- **Grafana Docs**: https://grafana.com/docs/grafana/
- **Alertmanager Docs**: https://prometheus.io/docs/alerting/

## Support

For issues:
1. Check service logs: `docker-compose logs <service>`
2. Verify configuration syntax
3. Test connectivity between components
4. Review full documentation
5. Create issue in repository
