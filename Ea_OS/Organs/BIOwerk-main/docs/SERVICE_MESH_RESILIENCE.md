# Service Mesh Resilience

## Overview

BIOwerk now includes enterprise-grade service mesh resilience patterns to handle failures gracefully and maintain high availability across all microservices. This implementation provides production-ready fault tolerance without requiring external service mesh infrastructure like Istio or Linkerd.

## Features

### 1. Circuit Breaker Pattern

Prevents cascading failures by "failing fast" when a service is experiencing issues.

**How it works:**
- **CLOSED State**: Normal operation, requests pass through
- **OPEN State**: Service is failing, requests are rejected immediately (fail fast)
- **HALF_OPEN State**: Testing recovery, allows limited requests to check if service recovered

**Configuration:**
```python
circuit_breaker_enabled = True
circuit_breaker_failure_threshold = 5           # Consecutive failures before opening
circuit_breaker_success_threshold = 2           # Successes in HALF_OPEN to close
circuit_breaker_timeout = 60                    # Seconds before OPEN → HALF_OPEN
circuit_breaker_failure_rate_threshold = 0.5    # 50% failure rate triggers open
circuit_breaker_window_size = 10                # Track last N calls
```

**Example:**
```
Attempt 1-4: Success → Circuit stays CLOSED
Attempt 5-9: Failure → Circuit opens after 5 consecutive failures
Attempt 10+: Rejected immediately (503 Service Unavailable)
After 60s: Circuit transitions to HALF_OPEN
Next success: Circuit closes, back to normal
```

### 2. Retry with Exponential Backoff

Automatically retries transient failures with increasing delays to avoid overwhelming failing services.

**How it works:**
- Attempt 1: Immediate
- Attempt 2: Wait 100ms
- Attempt 3: Wait 200ms
- Attempt 4: Wait 400ms
- And so on, up to max_delay

**Configuration:**
```python
retry_enabled = True
retry_max_attempts = 3          # Maximum retry attempts
retry_initial_delay = 0.1       # 100ms initial delay
retry_max_delay = 5.0           # 5s maximum delay
retry_exponential_base = 2.0    # Double delay each retry
retry_jitter = True             # Add randomness to prevent thundering herd
```

**Example:**
```
Request fails → Retry after 100ms
Retry fails → Retry after 200ms (with jitter: 100-300ms)
Retry fails → Retry after 400ms (with jitter: 200-600ms)
All retries exhausted → Return error
```

### 3. Bulkhead Pattern

Isolates resource pools to prevent one slow/failing service from exhausting all connections.

**How it works:**
- Limits concurrent requests per service
- Queues excess requests
- Rejects requests if queue is full or timeout exceeded

**Configuration:**
```python
bulkhead_enabled = True
bulkhead_max_concurrent = 10    # Max concurrent requests per service
bulkhead_queue_size = 5         # Queue up to 5 requests
bulkhead_timeout = 5.0          # 5s max wait for a slot
```

**Example:**
```
10 concurrent requests to Service A → All accepted
11th request → Queued (waits for slot)
16th request → Rejected (queue full, returns 429 Too Many Requests)
```

### 4. Health-Aware Routing

Routes requests based on real-time health status of services.

**How it works:**
- Tracks health status of each service
- Marks services unhealthy after consecutive failures
- Gradually restores health score on recovery
- Logs warnings when routing to unhealthy services

**Configuration:**
```python
health_check_enabled = True
health_check_interval = 10          # Check every 10 seconds
health_unhealthy_threshold = 3      # 3 failures → unhealthy
health_healthy_threshold = 2        # 2 successes → healthy
```

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      Mesh Gateway (8080)                     │
│  ┌────────────────────────────────────────────────────────┐ │
│  │           ResilientHttpClient (per agent)              │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │ │
│  │  │    Circuit   │  │    Retry     │  │   Bulkhead   │ │ │
│  │  │   Breaker    │→│   Logic      │→│   Pattern    │ │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘ │ │
│  └────────────────────────────────────────────────────────┘ │
│                            ↓                                 │
│                   Health-Aware Router                        │
└─────────────────────────────────────────────────────────────┘
                             ↓
        ┌────────────────────┼────────────────────┐
        ↓                    ↓                     ↓
  ┌──────────┐         ┌──────────┐         ┌──────────┐
  │ Osteon   │         │ Myocyte  │   ...   │ Synapse  │
  │  :8001   │         │  :8002   │         │  :8003   │
  └──────────┘         └──────────┘         └──────────┘
```

### Request Flow

```
1. Request arrives at Mesh Gateway
   ↓
2. Health-Aware Router checks service health
   ↓
3. Bulkhead acquires slot (limits concurrency)
   ↓
4. Circuit Breaker checks state
   - OPEN → Reject immediately (503)
   - CLOSED/HALF_OPEN → Continue
   ↓
5. Retry Logic wraps HTTP call
   - Attempt request
   - On failure: Wait + Retry (exponential backoff)
   - On success: Return response
   ↓
6. Update health status
   ↓
7. Release bulkhead slot
   ↓
8. Return response to client
```

## Usage

### 1. In Application Code

The resilience patterns are automatically applied in the Mesh Gateway and Moe Orchestrator. No code changes needed!

### 2. Configuration

Set environment variables or update `.env`:

```bash
# Circuit Breaker
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_TIMEOUT=60

# Retry
RETRY_ENABLED=true
RETRY_MAX_ATTEMPTS=3
RETRY_INITIAL_DELAY=0.1

# Bulkhead
BULKHEAD_ENABLED=true
BULKHEAD_MAX_CONCURRENT=10

# Health Checks
HEALTH_CHECK_ENABLED=true
HEALTH_CHECK_INTERVAL=10
```

### 3. Using ResilientHttpClient Directly

For custom services that need resilience:

```python
from matrix.resilience import ResilientHttpClient

# Create resilient client
async with ResilientHttpClient(
    service_name="my_service",
    base_url="http://myservice:8000",
    circuit_breaker_kwargs={'failure_threshold': 5},
    retry_kwargs={'max_attempts': 3},
    bulkhead_kwargs={'max_concurrent': 10},
    enable_circuit_breaker=True,
    enable_retry=True,
    enable_bulkhead=True
) as client:
    # Make requests with automatic resilience
    response = await client.post("/endpoint", json={"data": "value"})
```

### 4. Using Individual Patterns

#### Circuit Breaker Only

```python
from matrix.resilience import CircuitBreaker

cb = CircuitBreaker(
    service_name="external_api",
    failure_threshold=5,
    timeout=60
)

async def call_external_api():
    async with httpx.AsyncClient() as http_client:
        return await http_client.get("http://api.example.com/data")

# Wrap calls with circuit breaker
try:
    result = await cb.call(call_external_api)
except CircuitBreakerError:
    # Circuit is open, fail fast
    return fallback_response()
```

#### Retry Only

```python
from matrix.resilience import retry_with_backoff

result = await retry_with_backoff(
    my_async_function,
    arg1,
    arg2,
    max_attempts=3,
    initial_delay=0.1,
    service_name="my_service"
)
```

#### Bulkhead Only

```python
from matrix.resilience import Bulkhead

bulkhead = Bulkhead(
    service_name="database",
    max_concurrent=5
)

async def query_database():
    async with bulkhead.acquire():
        # Only 5 concurrent queries allowed
        return await db.execute(query)
```

## Monitoring

### Prometheus Metrics

All resilience patterns expose Prometheus metrics:

#### Circuit Breaker Metrics

```
# Current state (0=CLOSED, 1=OPEN, 2=HALF_OPEN)
circuit_breaker_state{service="osteon"} 0

# State transitions
circuit_breaker_transitions_total{service="osteon",from_state="CLOSED",to_state="OPEN"} 3

# Failures and successes
circuit_breaker_failures_total{service="osteon"} 127
circuit_breaker_successes_total{service="osteon"} 5432

# Rejected requests
circuit_breaker_rejected_total{service="osteon"} 45
```

#### Retry Metrics

```
# Retry attempts per service
resilience_retry_attempts_total{service="osteon",attempt="1"} 1000
resilience_retry_attempts_total{service="osteon",attempt="2"} 50
resilience_retry_attempts_total{service="osteon",attempt="3"} 10

# Successful retries
resilience_retry_successes_total{service="osteon",attempt="2"} 40

# Exhausted retries
resilience_retry_exhausted_total{service="osteon"} 5
```

#### Bulkhead Metrics

```
# Capacity and current usage
bulkhead_capacity{service="osteon"} 10
bulkhead_current_usage{service="osteon"} 7

# Rejected requests
bulkhead_rejected_total{service="osteon"} 23

# Wait times
bulkhead_wait_seconds{service="osteon",quantile="0.5"} 0.05
bulkhead_wait_seconds{service="osteon",quantile="0.95"} 2.3
```

#### HTTP Request Metrics

```
# Request duration
resilience_http_request_duration_seconds{service="osteon",method="POST",status="200"} 0.234

# Total requests
resilience_http_requests_total{service="osteon",method="POST",status="200"} 5000
resilience_http_requests_total{service="osteon",method="POST",status="error"} 50
```

### Viewing Metrics

```bash
# Access Prometheus metrics endpoint
curl http://localhost:8080/metrics

# Or use Prometheus/Grafana dashboards
```

### Logging

All resilience events are logged with structured logging:

```
INFO  - CircuitBreaker initialized for osteon: failure_threshold=5, timeout=60s
WARN  - CircuitBreaker osteon OPENED: failure_count=5, failure_rate=60.0%
INFO  - CircuitBreaker osteon transitioned to HALF_OPEN (testing recovery)
INFO  - CircuitBreaker osteon CLOSED (service recovered)

INFO  - Attempt 1/3 failed for myocyte: HTTPError. Retrying in 0.123s...
WARN  - All 3 retry attempts exhausted for myocyte. Last error: Connection refused

INFO  - Bulkhead initialized for synapse: max_concurrent=10, queue_size=5
WARN  - Bulkhead timeout for synapse after 5.0s. Current requests: 10/10
```

## Error Handling

### HTTP Status Codes

The resilience system returns appropriate HTTP status codes:

| Status | Reason | Description |
|--------|--------|-------------|
| 503 | Circuit Breaker Open | Service is temporarily unavailable, circuit breaker is open |
| 503 | Retry Exhausted | All retry attempts failed, service may be down |
| 429 | Bulkhead Full | Too many concurrent requests, rate limited |
| 502 | Network Error | Connection/network error communicating with service |

### Error Response Format

Circuit breaker open:
```json
{
  "error": "Service Unavailable",
  "message": "Circuit breaker is OPEN for osteon. Service is temporarily unavailable.",
  "agent": "osteon",
  "retry_after": 60
}
```

Retry exhausted:
```json
{
  "error": "Service Unavailable",
  "message": "All retry attempts exhausted for myocyte. Service may be down.",
  "agent": "myocyte",
  "max_attempts": 3
}
```

Bulkhead full:
```json
{
  "error": "Too Many Requests",
  "message": "Too many concurrent requests to synapse. Please try again later.",
  "agent": "synapse",
  "max_concurrent": 10,
  "retry_after": 1
}
```

## Testing

### Running Tests

```bash
# Run resilience tests
pytest tests/test_resilience.py -v

# Run with coverage
pytest tests/test_resilience.py --cov=matrix.resilience --cov-report=html
```

### Test Coverage

The test suite covers:
- Circuit breaker state transitions (CLOSED → OPEN → HALF_OPEN → CLOSED)
- Failure threshold and failure rate triggering
- Retry logic with exponential backoff
- Retry exhaustion scenarios
- Bulkhead concurrency limiting
- Bulkhead timeout and rejection
- ResilientHttpClient integration
- Health-aware routing and health scores
- All patterns working together

### Manual Testing

#### Test Circuit Breaker

```bash
# Simulate service failure (stop a service)
docker stop biowerk-osteon-1

# Make requests to trigger circuit breaker
for i in {1..10}; do
  curl -X POST http://localhost:8080/osteon/outline \
    -H "Content-Type: application/json" \
    -d '{"id":"test","user_id":"user1","agent":"osteon","data":{}}'
done

# After 5 failures, circuit opens
# Subsequent requests fail immediately with 503

# Wait 60 seconds, circuit transitions to HALF_OPEN

# Restart service
docker start biowerk-osteon-1

# Next request tests recovery and closes circuit
```

#### Test Retry Logic

```bash
# Enable verbose logging
export LOG_LEVEL=DEBUG

# Make a request to a flaky endpoint
# Watch logs for retry attempts
```

#### Test Bulkhead

```bash
# Send many concurrent requests
for i in {1..20}; do
  curl -X POST http://localhost:8080/osteon/outline \
    -H "Content-Type: application/json" \
    -d '{"id":"test-'$i'","user_id":"user1","agent":"osteon","data":{}}' &
done

# Requests 11-15 will be queued
# Requests 16+ will be rejected with 429
```

## Best Practices

### 1. Tuning Circuit Breaker

**Conservative (High Availability):**
```python
failure_threshold = 10      # More tolerant of failures
timeout = 30                # Shorter recovery test interval
failure_rate_threshold = 0.7  # Only open at 70% failure rate
```

**Aggressive (Fail Fast):**
```python
failure_threshold = 3       # Quick to open
timeout = 120               # Longer recovery time
failure_rate_threshold = 0.3  # Open at 30% failure rate
```

### 2. Tuning Retry Logic

**For Transient Errors:**
```python
max_attempts = 5
initial_delay = 0.05        # Fast retries
exponential_base = 1.5      # Slower growth
```

**For Slow Services:**
```python
max_attempts = 3
initial_delay = 0.5         # Slower retries
exponential_base = 2.0      # Standard growth
max_delay = 10.0           # Allow longer delays
```

### 3. Tuning Bulkhead

**For High-Throughput Services:**
```python
max_concurrent = 50
queue_size = 20
timeout = 10.0
```

**For Resource-Constrained Services:**
```python
max_concurrent = 5
queue_size = 2
timeout = 2.0
```

### 4. Combining Patterns

**Critical Services (Maximum Resilience):**
```python
enable_circuit_breaker = True
enable_retry = True
enable_bulkhead = True
```

**Non-Critical Services (Minimal Overhead):**
```python
enable_circuit_breaker = True   # Fail fast only
enable_retry = False
enable_bulkhead = False
```

**High-Volume Services (Prevent Overload):**
```python
enable_circuit_breaker = False
enable_retry = False
enable_bulkhead = True          # Rate limit only
```

## Troubleshooting

### Circuit Breaker Stuck Open

**Symptom:** Circuit breaker stays open even though service recovered

**Solutions:**
1. Check circuit breaker timeout (may need to wait longer)
2. Verify service is actually healthy (`curl http://service:port/health`)
3. Check logs for HALF_OPEN transition failures
4. Restart the mesh gateway to reset circuit breaker state

### Too Many Retries

**Symptom:** Requests taking too long due to excessive retries

**Solutions:**
1. Reduce `retry_max_attempts`
2. Decrease `retry_max_delay`
3. Enable circuit breaker to fail fast instead of retrying
4. Check if underlying service issue needs fixing

### Bulkhead Rejections

**Symptom:** Many 429 errors, requests being rejected

**Solutions:**
1. Increase `bulkhead_max_concurrent`
2. Increase `bulkhead_queue_size`
3. Optimize slow endpoints to reduce request duration
4. Scale out the service to handle more load

### High Latency

**Symptom:** Requests slower after adding resilience

**Solutions:**
1. Check if retries are adding latency (failed requests being retried)
2. Reduce bulkhead timeout if requests are waiting too long
3. Disable patterns for low-latency requirements
4. Check Prometheus metrics to identify bottleneck

## Performance Impact

### Overhead

| Pattern | Latency Overhead | Memory Overhead | CPU Overhead |
|---------|------------------|-----------------|--------------|
| Circuit Breaker | ~0.1ms | ~1KB per service | Negligible |
| Retry | Variable (depends on failures) | Negligible | Low |
| Bulkhead | ~0.1ms (if slot available) | ~2KB per service | Negligible |
| All Combined | ~0.2-0.5ms | ~5KB per service | Low |

### Recommendations

- **Development:** Enable all patterns with verbose logging
- **Staging:** Enable all patterns, tune thresholds based on testing
- **Production:** Enable based on service criticality and requirements

## Future Enhancements

Potential improvements for future versions:

1. **Adaptive Circuit Breakers:** Automatically adjust thresholds based on historical data
2. **Rate Limiting:** Token bucket or leaky bucket rate limiting
3. **Fallback Handlers:** Automatic fallback responses when circuits are open
4. **Service Discovery Integration:** Dynamic service endpoint discovery
5. **Distributed Tracing:** OpenTelemetry integration for request tracing
6. **Advanced Health Checks:** Custom health check logic per service
7. **Dashboard:** Real-time visualization of circuit breaker states
8. **Alerting:** Automatic alerts when circuits open or retries exhaust

## References

- [Martin Fowler - Circuit Breaker](https://martinfowler.com/bliki/CircuitBreaker.html)
- [Microsoft - Retry Pattern](https://docs.microsoft.com/en-us/azure/architecture/patterns/retry)
- [Microsoft - Bulkhead Pattern](https://docs.microsoft.com/en-us/azure/architecture/patterns/bulkhead)
- [AWS - Exponential Backoff and Jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/)

## Support

For issues or questions:
- GitHub Issues: https://github.com/E-TECH-PLAYTECH/BIOwerk/issues
- Documentation: `docs/SERVICE_MESH_RESILIENCE.md` (this file)
- Code: `matrix/resilience.py`
- Tests: `tests/test_resilience.py`
