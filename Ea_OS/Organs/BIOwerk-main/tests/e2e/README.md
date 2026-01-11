# E2E Workflow Tests

## Overview

This directory contains comprehensive end-to-end (E2E) tests for the BIOwerk microservices platform. These tests validate complete workflows across multiple services to ensure the entire system functions correctly under realistic scenarios.

## Test Structure

```
tests/e2e/
├── __init__.py                    # Package initialization
├── conftest.py                    # Shared fixtures and configuration
├── test_complete_workflows.py     # Core workflow tests
├── test_security.py               # Security and authentication tests
└── test_resilience.py            # Resilience and fault tolerance tests
```

## Test Categories

### 1. Complete Workflows (`test_complete_workflows.py`)

Tests end-to-end business workflows across services:

- **Document Generation** (Osteon service)
  - Draft creation
  - Document editing
  - Content summarization

- **Data Analysis** (Myocyte service)
  - Table data ingestion
  - Formula evaluation
  - Model forecasting

- **Presentation Creation** (Synapse service)
  - Storyboard generation
  - Slide creation
  - Visualization export

- **Task Planning** (Circadian service)
  - Timeline planning
  - Task assignment
  - Progress tracking

- **Multi-Service Orchestration** (Nucleus service)
  - Workflow planning
  - Agent routing
  - Result finalization

### 2. Security Tests (`test_security.py`)

Validates security features and controls:

- **Authentication & Authorization**
  - Health endpoint accessibility
  - Security headers verification

- **Input Validation**
  - SQL injection prevention
  - XSS prevention
  - Command injection prevention
  - Oversized payload handling

- **Rate Limiting**
  - Burst request handling
  - Throttling behavior

- **Data Protection**
  - Error message sanitization
  - CORS configuration
  - GDPR compliance

- **Logging & Auditing**
  - Request tracking
  - Distributed tracing

### 3. Resilience Tests (`test_resilience.py`)

Ensures system reliability and fault tolerance:

- **Circuit Breaker**
  - Service failure handling
  - Graceful degradation

- **Retry Mechanism**
  - Transient failure recovery
  - Exponential backoff

- **Timeout Handling**
  - Request timeout configuration
  - Long-running request management

- **Concurrency**
  - Parallel request handling
  - Load distribution

- **Connection Pooling**
  - Database connection efficiency
  - PgBouncer integration

- **Health Checks**
  - Endpoint responsiveness
  - Readiness probes

## Running Tests

### Prerequisites

1. **Start Services**:
   ```bash
   # Start all required services
   docker compose up -d

   # Wait for services to be healthy
   docker compose ps
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

### Run All E2E Tests

```bash
# Run all E2E tests
pytest tests/e2e/ -v

# Run with coverage
pytest tests/e2e/ --cov=mesh --cov=services -v

# Run with detailed output
pytest tests/e2e/ -vv -s
```

### Run Specific Test Categories

```bash
# Run only workflow tests
pytest tests/e2e/test_complete_workflows.py -v

# Run only security tests
pytest tests/e2e/test_security.py -v

# Run only resilience tests
pytest tests/e2e/test_resilience.py -v
```

### Run Specific Test Classes

```bash
# Run document workflow tests
pytest tests/e2e/test_complete_workflows.py::TestDocumentWorkflow -v

# Run authentication security tests
pytest tests/e2e/test_security.py::TestAuthenticationSecurity -v

# Run circuit breaker tests
pytest tests/e2e/test_resilience.py::TestCircuitBreaker -v
```

### Run with Custom Configuration

```bash
# Set custom mesh URL
MESH_URL=http://custom-host:8080 pytest tests/e2e/ -v

# Run with custom timeout
pytest tests/e2e/ --timeout=300 -v

# Run tests in parallel
pytest tests/e2e/ -n auto -v
```

## CI/CD Integration

E2E tests run automatically in the CI/CD pipeline:

### GitHub Actions Workflow

The tests run as part of the `ci.yml` workflow:

```yaml
jobs:
  e2e-tests:
    name: E2E Workflow Tests
    runs-on: ubuntu-latest
    steps:
      - name: Start services
        run: docker compose up -d

      - name: Run E2E tests
        run: pytest tests/e2e/ -v
```

### Workflow Triggers

- **Push** to `main`, `develop`, or `claude/**` branches
- **Pull Requests** targeting `main` or `develop`
- **Manual** workflow dispatch

### Test Reports

Test results are uploaded as artifacts:
- JUnit XML reports
- Coverage reports
- Service logs (on failure)

## Configuration

### Environment Variables

```bash
# Mesh service URL (default: http://localhost:8080)
MESH_URL=http://localhost:8080

# Test timeout in seconds (default: 120)
TEST_TIMEOUT=120

# Enable verbose logging
PYTEST_VERBOSE=1
```

### Fixtures

Common fixtures are defined in `conftest.py`:

- `mesh_url`: Mesh service URL
- `http_client`: Configured async HTTP client
- `wait_for_services`: Service readiness check
- `sample_*_request`: Pre-configured request payloads

## Test Patterns

### 1. Async Testing

All tests use `pytest-asyncio` for async operations:

```python
@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_example(http_client: httpx.AsyncClient):
    response = await http_client.post("/endpoint", json=data)
    assert response.status_code == 200
```

### 2. Service Health Checks

Tests automatically wait for services to be ready:

```python
@pytest.fixture(autouse=True)
async def ensure_services_ready(wait_for_services):
    """Auto-use fixture to ensure services are ready."""
    pass
```

### 3. Request Tracking

All requests include unique IDs for tracing:

```python
msg_id = str(uuid.uuid4())
request = {"id": msg_id, "agent": "osteon", ...}
```

### 4. Error Handling

Tests validate both success and failure scenarios:

```python
# Test successful case
assert response.status_code == 200

# Test error handling
assert response.status_code in [400, 422]
```

## Troubleshooting

### Services Not Ready

If tests fail with connection errors:

```bash
# Check service status
docker compose ps

# View service logs
docker compose logs mesh
docker compose logs postgres

# Restart services
docker compose restart
```

### Test Timeouts

Increase timeout for slow tests:

```bash
# Increase pytest timeout
pytest tests/e2e/ --timeout=300

# Or set in pytest.ini
[pytest]
timeout = 300
```

### Database Connection Issues

Verify PgBouncer is healthy:

```bash
# Check PgBouncer logs
docker compose logs pgbouncer

# Test database connection
docker compose exec pgbouncer psql -h localhost -U biowerk
```

### Port Conflicts

If ports are already in use:

```bash
# Stop conflicting services
docker compose down

# Check port usage
lsof -i :8080
lsof -i :5432

# Start with fresh state
docker compose down -v
docker compose up -d
```

## Best Practices

1. **Isolation**: Each test should be independent and not rely on state from other tests
2. **Cleanup**: Use fixtures to ensure proper cleanup after tests
3. **Timeouts**: Set appropriate timeouts for long-running tests
4. **Error Messages**: Provide clear assertion messages for debugging
5. **Parallel Execution**: Design tests to run in parallel when possible
6. **Idempotency**: Tests should produce same results when run multiple times

## Contributing

When adding new E2E tests:

1. Follow existing test patterns
2. Use descriptive test names
3. Add docstrings explaining test purpose
4. Include both positive and negative test cases
5. Set appropriate timeouts
6. Update this README with new test categories

## Performance Benchmarks

Typical test execution times:

| Test Suite | Duration | Tests |
|------------|----------|-------|
| Complete Workflows | ~2 min | 15 |
| Security Tests | ~3 min | 20 |
| Resilience Tests | ~4 min | 18 |
| **Total** | **~10 min** | **53** |

Times may vary based on system resources and network conditions.

## Further Reading

- [Security Documentation](../../docs/SECURITY.md)
- [Testing Strategy](../../docs/TESTING.md)
- [CI/CD Pipeline](../../.github/workflows/ci.yml)
- [OWASP ZAP Security Tests](../../.github/workflows/owasp-zap-security.yml)

---

**Last Updated**: 2025-11-16
**Maintained by**: BIOwerk Development Team
