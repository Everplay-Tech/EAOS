# Bio-Themed Agentic Office Suite (CODEX scaffold)

[![codecov](https://codecov.io/gh/E-TECH-PLAYTECH/BIOwerk/branch/main/graph/badge.svg)](https://codecov.io/gh/E-TECH-PLAYTECH/BIOwerk)
[![Tests](https://github.com/E-TECH-PLAYTECH/BIOwerk/workflows/Tests/badge.svg)](https://github.com/E-TECH-PLAYTECH/BIOwerk/actions)
[![Coverage](https://img.shields.io/badge/coverage-%E2%89%A580%25-brightgreen)](https://github.com/E-TECH-PLAYTECH/BIOwerk)

This repository is a production-oriented scaffold for an **agentic AI app suite** using biological/physical metaphors:

- **Nucleus** (Director/orchestrator)
- **Osteon** (Document program-agent)
- **Myocyte** (Analysis/Spreadsheet program-agent)
- **Synapse** (Presentation/Visualization program-agent)
- **Circadian** (Scheduler/Workflow program-agent)
- **Chaperone** (Adapter for import/export to external formats)
- **Matrix** (shared utilities, message envelope, canonicalization)

> Native artifact formats: `.osteon`, `.myotab`, `.synslide` (simple JSON-based containers).

## Quick start

```bash
# 1) Start all services
docker compose up --build

# 2) Open gateway (Mesh) docs:
# http://localhost:8080/docs

# 3) Try a draft with Osteon (Writer analogue) using API v1:
curl -X POST http://localhost:8080/v1/osteon/draft -H 'Content-Type: application/json' -d @examples/osteon_draft.json

# Note: Legacy unversioned endpoints still work but are deprecated:
# curl -X POST http://localhost:8080/osteon/draft ...
```

Need ongoing service insight? See [Operations](#operations) for observability and continuity guidance.

## Security Features

BIOwerk implements enterprise-grade security features for production deployments:

### 🔒 TLS/HTTPS Encryption
- **TLS 1.2/1.3 support** with secure cipher suites
- **Self-signed certificates** for development (auto-generation)
- **CA-signed certificates** for production
- **Mutual TLS (mTLS)** for client certificate verification
- **Certificate validation** and expiration monitoring

**Quick Start:**
```bash
# Generate development certificates
python scripts/generate_certs.py

# Enable TLS in .env
TLS_ENABLED=true
TLS_CERT_FILE=./certs/cert.pem
TLS_KEY_FILE=./certs/key.pem

# Restart services
docker-compose restart
```

### 🛡️ Rate Limiting
- **Redis-backed** distributed rate limiting
- **Multiple strategies**: Fixed window, Sliding window, Token bucket
- **Per-IP and per-user** rate limiting
- **Configurable burst** handling
- **Standard headers** (`X-RateLimit-*`)

**Configuration:**
```bash
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=100    # requests per window
RATE_LIMIT_WINDOW=60       # seconds
RATE_LIMIT_STRATEGY=sliding_window
```

### 🔍 Dependency Vulnerability Scanning
- **Automated scanning** with Safety and pip-audit
- **GitHub Actions** integration (CI/CD)
- **Pre-commit hooks** for local validation
- **Daily scheduled** scans
- **Docker image scanning** with Trivy

**Run Security Scan:**
```bash
# Full security audit
python scripts/security_scan.py --full

# Dependencies only
python scripts/security_scan.py --deps-only
```

### 🔐 Authentication & Authorization
- **JWT token-based** authentication (HS256/RS256)
- **API key management** with scopes and expiration
- **Role-based access control** (RBAC)
- **bcrypt password hashing**
- **Configurable token expiration**

### 📊 Security Monitoring
- **Prometheus metrics** for rate limits and auth events
- **Audit logging** with structured JSON
- **Health checks** for service availability
- **Security headers** in responses

**Comprehensive Documentation:**
- [Security Guide](docs/security.md) - Complete security documentation
- [Scripts README](scripts/README.md) - Security tools and scripts
- [GitHub Actions](.github/workflows/security.yml) - Automated scanning

## Architecture

- Each agent is a FastAPI microservice with typed endpoints.
- JSON-RPC–style payloads with canonical JSON and BLAKE3 state hashes.
- The **Mesh gateway** exposes a unified API surface and routes messages to agents.
- **Matrix** provides shared libs for canonicalization, hashing, and message schemas.

### API Versioning

BIOwerk implements comprehensive URL path-based API versioning for backward compatibility:

- **Format**: All endpoints use `/v{version}/` prefix (e.g., `/v1/osteon/draft`)
- **Current Version**: API v1 (stable)
- **Backward Compatibility**: Legacy unversioned endpoints still work with deprecation warnings
- **Auto-negotiation**: Defaults to latest version when no version specified

**Examples:**
```bash
# Versioned endpoint (recommended)
curl -X POST http://localhost:8080/v1/osteon/draft \
  -H 'Content-Type: application/json' \
  -d @examples/osteon_draft.json

# Legacy endpoint (works but deprecated)
curl -X POST http://localhost:8080/osteon/draft \
  -H 'Content-Type: application/json' \
  -d @examples/osteon_draft.json
```

**See:** [docs/API_VERSIONING.md](docs/API_VERSIONING.md) for complete versioning guide and migration instructions.

### Service Mesh Resilience

BIOwerk includes enterprise-grade resilience patterns for production deployments:

- **Circuit Breaker**: Prevents cascading failures by failing fast when services are down
- **Retry with Exponential Backoff**: Automatically retries transient failures
- **Bulkhead Pattern**: Isolates resource pools to prevent one service from exhausting connections
- **Health-Aware Routing**: Routes requests based on real-time service health

All patterns include comprehensive Prometheus metrics for observability. See [docs/SERVICE_MESH_RESILIENCE.md](docs/SERVICE_MESH_RESILIENCE.md) for detailed documentation.

**Configuration:**
```bash
# Enable all resilience patterns (default)
CIRCUIT_BREAKER_ENABLED=true
RETRY_ENABLED=true
BULKHEAD_ENABLED=true
HEALTH_CHECK_ENABLED=true
```

## Determinism

All service replies include a `state_hash = blake3-256(canonical_json(output))`.
Golden tests can assert output hashes for regression checks.

## Interop

**Chaperone** handles import/export (e.g., Office formats) without creating runtime coupling.
The core suite operates entirely on native formats.

## Operations

Production deployments should plan for consistent observability and disaster recovery. The suite’s FastAPI services run as discrete containers, so the patterns below apply uniformly across Mesh and every agent.

### Log aggregation

- **Structured logs** – Each container writes access/application logs to STDOUT. To guarantee structured JSON, extend the container command with a custom logging config:

  ```yaml
  # docker-compose.override.yml
  services:
    mesh:
      command:
        - uvicorn
        - main:app
        - --host
        - 0.0.0.0
        - --port
        - "8080"
        - --log-config
        - /config/logging.json
      volumes:
        - ./ops/logging.json:/config/logging.json:ro
  ```

- **Common tooling integration** – Ship the container logs to your preferred aggregator:
  - *Grafana Loki*: add a `promtail` sidecar that follows `/var/lib/docker/containers/*/*.log` and parses JSON.
  - *ELK / OpenSearch*: run Filebeat or Vector to tail the same Docker log files and forward them with the `json` codec.
  - *Cloud logging*: configure Fluent Bit with the Docker input (`tag mesh.*`) and forward to CloudWatch, Stackdriver, or Azure Monitor.

- **Retention** – Retain at least 7 days of INFO-level logs and 30 days of WARN+/AUDIT streams to support replaying canonical `Msg`/`Reply` envelopes when investigating incidents.

### Prometheus scraping

- **Metrics endpoints** – Mesh and each agent expose Prometheus-compatible metrics at `http://<service-host>:<port>/metrics`. For a local stack you can confirm with:

  ```bash
  curl http://localhost:8080/metrics    # Mesh gateway
  curl http://localhost:8001/metrics    # Osteon agent
  ```

- **Scrape configuration** – Point Prometheus at every container (adjust the hostnames when deploying outside of Compose):

  ```yaml
  scrape_configs:
    - job_name: "bio-suite"
      metrics_path: /metrics
      static_configs:
        - targets:
            - mesh:8080
            - osteon:8001
            - myocyte:8002
            - synapse:8003
            - circadian:8004
            - nucleus:8005
            - chaperone:8006
  ```

- **Dashboards** – Import Grafana dashboards for FastAPI/Uvicorn or build panels around `http_requests_total`, `http_request_duration_seconds_*`, and custom gauges emitted by each agent.

### Alert thresholds

- **Latency** – Page when the 95th percentile of `http_request_duration_seconds` exceeds 500 ms for five consecutive minutes (higher thresholds for heavy exports).
- **Error budget** – Alert on `increase(http_requests_total{status=~"5.."}[5m]) / increase(http_requests_total[5m]) > 0.02` to keep the aggregate error rate below 2%.
- **Availability** – Track a synthetic `up` gauge per container; raise a ticket if any agent is down for longer than 60 seconds.
- **Queue pressure** – Monitor application-specific counters (for example, `osteon_drafts_in_flight`) if you add them; pair alerts with Slack / PagerDuty routes in Alertmanager.

### Backup procedures

- **Configuration snapshots** – Version-control-sensitive files (`suite.yaml`, `schemas/`, `matrix/`) already live in Git. Take weekly tarball snapshots for operations by running `tar -czf backups/suite-config-$(date +%F).tgz suite.yaml schemas matrix` from the repository root.
- **Artifact exports** – Mount a persistent host directory (e.g., `./artifacts:/data/artifacts`) in Compose so generated `.osteon`, `.myotab`, and `.synslide` files are captured. Schedule nightly rsync (or cloud storage sync) of that directory.
- **Database / external stores** – If you attach external stateful services (PostgreSQL, object storage), follow their native backup tooling and document credentials in your runbook.
- **Disaster recovery drill** – Quarterly, rebuild the stack from backups (`docker compose up --build`), replay a representative set of artifacts through Mesh, and confirm `/metrics` plus structured logging are operational.

## License


