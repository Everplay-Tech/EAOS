# Integration Tests

This directory contains integration tests that validate service-to-service communication and multi-service workflows in the BIOwerk platform.

## Overview

Integration tests verify that services work correctly together, focusing on:
- Service-to-service message contracts (Msg/Reply format)
- Multi-service workflows and orchestration
- Resilience patterns under integration (circuit breaker, retry, bulkhead)
- Error propagation between services
- Timeout handling across service boundaries
- Health-aware routing
- Database integration across services
- Authentication/authorization flows

## Test Structure

### test_document_workflow.py
Tests complete document generation workflows:
- User → Mesh → Osteon flow (direct routing)
- User → Mesh → Larry → Nucleus → Osteon (orchestrated flow)
- Msg/Reply format consistency across all services
- State hash validation and determinism
- GDPR data export workflow
- Token budget enforcement
- Error propagation
- Timeout handling
- Document creation end-to-end

**Test Count:** 11 tests

### test_mesh_routing.py
Tests mesh gateway routing functionality:
- URL-based routing to services
- API versioning (v1, v2, etc.)
- Health-aware routing (skip unhealthy services)
- Service discovery and dynamic routing
- Concurrent routing to multiple services
- Request ID preservation through routing
- Health check propagation
- Circuit breaker integration with routing
- Load balancing across service instances
- RBAC integration with routing

**Test Count:** 18 tests

### test_database_integration.py
Tests database interactions across services:
- Multi-service database access
- Data consistency across services
- Concurrent database writes
- Connection pooling behavior
- Transaction isolation
- Cache sharing between services
- Cache invalidation propagation
- Data persistence across service restarts
- Backup and restore workflows

**Test Count:** 10 tests

### test_auth_flow.py
Tests authentication and authorization flows:
- Unauthenticated request handling
- Authenticated request flow through mesh
- Token propagation from mesh to services
- API key authentication
- JWT token lifecycle (generation, validation, expiry)
- RBAC enforcement across services
- Service-to-service authentication
- Token validation and rejection
- Token refresh mechanism

**Test Count:** 15 tests

### test_resilience_patterns.py
Tests resilience patterns under integration:
- Circuit breaker opens after failures
- Circuit breaker recovery (half-open state)
- Circuit breaker isolation per service
- Retry on transient failures
- Exponential backoff behavior
- Retry limit enforcement
- No retry on client errors (4xx)
- Bulkhead limits concurrent requests
- Bulkhead queue behavior
- Bulkhead per-service isolation
- Health-aware routing to healthy services
- Skipping unhealthy services
- Health check updates to routing
- Request timeout propagation
- Service timeout handling
- Graceful degradation on partial failures
- Fallback behavior

**Test Count:** 17 tests

## Running Integration Tests

### Prerequisites

1. **Docker Compose**: All services must be running
   ```bash
   docker compose up -d
   ```

2. **Service Health**: Wait for services to be healthy
   ```bash
   # Wait for mesh to be ready
   until curl -f http://localhost:8080/health; do sleep 2; done
   ```

### Run All Integration Tests

```bash
# Run all integration tests
pytest tests/integration/ -v

# Run with integration marker
pytest -m integration -v

# Run with timeout (5 min max per test)
pytest tests/integration/ --timeout=300 -v
```

### Run Specific Test Files

```bash
# Document workflow tests
pytest tests/integration/test_document_workflow.py -v

# Mesh routing tests
pytest tests/integration/test_mesh_routing.py -v

# Database integration tests
pytest tests/integration/test_database_integration.py -v

# Auth flow tests
pytest tests/integration/test_auth_flow.py -v

# Resilience pattern tests
pytest tests/integration/test_resilience_patterns.py -v
```

### Run Specific Test Classes or Functions

```bash
# Run specific test class
pytest tests/integration/test_document_workflow.py::TestDocumentWorkflowIntegration -v

# Run specific test function
pytest tests/integration/test_resilience_patterns.py::TestCircuitBreakerIntegration::test_circuit_breaker_opens_after_failures -v
```

### Parallel Execution

```bash
# Run tests in parallel (4 workers)
pytest tests/integration/ -n 4 -v
```

## Configuration

Integration tests use the following environment variables:

- `MESH_URL`: Mesh gateway URL (default: http://localhost:8080)
- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`: Database config
- `MONGO_HOST`: MongoDB host
- `REDIS_HOST`: Redis host
- `REQUIRE_AUTH`: Whether authentication is required (default: false for tests)

## CI/CD Integration

Integration tests run automatically in the CI pipeline:

1. **Trigger**: On push to main/develop branches and pull requests
2. **Job**: `integration-tests` (runs after unit tests)
3. **Duration**: ~5-15 minutes
4. **Timeout**: 20 minutes max
5. **Requirements**: Full docker-compose stack

## Test Statistics

- **Total Integration Tests:** 68+
- **Test Files:** 5
- **Coverage Areas:**
  - ✅ Service-to-service communication
  - ✅ Multi-service workflows
  - ✅ Resilience patterns (circuit breaker, retry, bulkhead)
  - ✅ Mesh routing and load balancing
  - ✅ Database integration
  - ✅ Authentication/authorization
  - ✅ Health-aware routing
  - ✅ Error propagation
  - ✅ Timeout handling

## Fixtures

Integration tests use shared fixtures from `tests/integration/conftest.py`:

- `http_client`: Pre-configured async HTTP client
- `msg_factory`: Factory for creating Msg-formatted requests
- `reply_validator`: Validator for Reply message format
- `service_health_checker`: Utility to check service health
- `multi_service_request`: Make parallel requests to multiple services
- `resilience_test_helper`: Helper for testing resilience patterns
- `database_test_helper`: Helper for database integration tests
- `sample_integration_requests`: Sample request templates

## Best Practices

1. **Test Isolation**: Each test should be independent
2. **Cleanup**: Tests clean up any created resources
3. **Timeouts**: All tests have appropriate timeouts
4. **Resilience**: Tests handle service unavailability gracefully
5. **Assertions**: Use descriptive assertion messages
6. **Markers**: All tests are marked with `@pytest.mark.integration`

## Troubleshooting

### Services Not Ready
If tests fail with connection errors:
```bash
# Check service health
docker compose ps
curl http://localhost:8080/health

# Wait longer for services
sleep 30
```

### Port Conflicts
If services can't start:
```bash
# Check for port conflicts
lsof -i :8080
lsof -i :5432

# Stop conflicting services
docker compose down -v
```

### Test Timeouts
If tests timeout:
```bash
# Increase timeout
pytest tests/integration/ --timeout=600 -v

# Check service logs
docker compose logs mesh
docker compose logs osteon
```

### Debug Mode
Run with verbose output:
```bash
# Maximum verbosity
pytest tests/integration/ -vv --log-cli-level=DEBUG

# Show print statements
pytest tests/integration/ -v -s
```

## Contributing

When adding new integration tests:

1. Follow the existing test structure
2. Use the shared fixtures from `conftest.py`
3. Add descriptive docstrings
4. Mark tests with `@pytest.mark.integration`
5. Set appropriate timeouts
6. Handle service unavailability gracefully
7. Update this README with test counts

## Related Documentation

- [E2E Tests](../e2e/README.md) - End-to-end workflow tests
- [Unit Tests](../README.md) - Unit test documentation
- [CI/CD Pipeline](../../.github/workflows/ci.yml) - CI configuration
- [Service Architecture](../../docs/architecture.md) - System architecture
