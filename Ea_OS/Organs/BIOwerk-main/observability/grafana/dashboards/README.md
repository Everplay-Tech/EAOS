# Grafana Dashboards

This directory contains pre-configured Grafana dashboards for monitoring the BIOwerk platform.

## Dashboard Categories

### BIOwerk Application Dashboards (`biowerk/`)
- **biowerk-overview.json** - System-wide overview with key metrics
  - Service health and availability
  - Request rates across all services
  - Response time percentiles (p95, p99)
  - HTTP status code distribution
  - Live service logs

### Infrastructure Dashboards (`infrastructure/`)
- Node metrics (CPU, memory, disk, network)
- Container metrics (Docker/cAdvisor)
- System resource utilization

### Database Dashboards (`database/`)
- PostgreSQL performance and health
- MongoDB metrics
- Redis cache performance
- PgBouncer connection pooling

## Adding Custom Dashboards

1. Create your dashboard in Grafana UI
2. Export as JSON (Settings → JSON Model)
3. Save to appropriate directory:
   - Application: `biowerk/`
   - Infrastructure: `infrastructure/`
   - Database: `database/`
4. Commit to repository

## Dashboard Import

Dashboards are automatically provisioned on Grafana startup via the configuration in:
```
observability/grafana/provisioning/dashboards/dashboards.yaml
```

## Pre-built Dashboard Sources

Consider importing these community dashboards:

1. **Node Exporter Full** - ID: 1860
2. **Docker Container Metrics** - ID: 193
3. **PostgreSQL Database** - ID: 9628
4. **Redis Dashboard** - ID: 763
5. **Loki Dashboard** - ID: 13639
6. **Prometheus 2.0 Stats** - ID: 3662

Import via: Grafana UI → Dashboards → Import → Enter Dashboard ID

## Key Metrics to Monitor

### Service Health
- `up{job=~"biowerk-.*"}` - Service availability
- `http_requests_total` - Request volume
- `http_request_duration_seconds` - Latency

### Errors
- `http_requests_total{status=~"5.."}` - Server errors
- `circuit_breaker_state` - Circuit breaker status
- `resilience_retry_exhausted_total` - Retry failures

### Resources
- `node_memory_MemAvailable_bytes` - Available memory
- `node_cpu_seconds_total` - CPU usage
- `node_filesystem_avail_bytes` - Disk space

### Database
- `pg_stat_database_numbackends` - PostgreSQL connections
- `redis_memory_used_bytes` - Redis memory
- `mongodb_connections` - MongoDB connections

## Alert Integration

Dashboards are integrated with Alertmanager. Active alerts are displayed in:
- Alert State History panel
- Alert List panel (filter by severity)

## Dashboard Variables

Most dashboards support template variables for filtering:
- `$service` - Filter by service name
- `$instance` - Filter by instance
- `$environment` - Filter by environment (dev/staging/prod)

## Troubleshooting

### Dashboard not loading
1. Check Grafana logs: `docker logs biowerk-grafana`
2. Verify datasource connection: Configuration → Data Sources
3. Test Prometheus/Loki connectivity

### Missing metrics
1. Verify service is exposing `/metrics` endpoint
2. Check Prometheus targets: `http://localhost:9090/targets`
3. Verify scrape configuration in `prometheus-config.yaml`

### Panel shows "No data"
1. Adjust time range (top-right)
2. Verify query in panel edit mode
3. Check if metric exists: Explore → Prometheus → Metrics browser
