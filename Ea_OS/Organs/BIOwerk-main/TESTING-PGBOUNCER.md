# PgBouncer Testing Guide

## Pre-Deployment Testing

Before deploying PgBouncer to production, follow this comprehensive testing checklist.

## 1. Build and Start Services

```bash
# Build PgBouncer image
docker-compose build pgbouncer

# Start PostgreSQL first
docker-compose up -d postgres

# Wait for PostgreSQL to be healthy
docker-compose ps postgres

# Start PgBouncer
docker-compose up -d pgbouncer

# Verify PgBouncer is healthy
docker-compose ps pgbouncer
```

## 2. Verify PgBouncer Connectivity

### Test 1: Direct Connection to PgBouncer

```bash
# Connect to PgBouncer admin console
psql -h localhost -p 6432 -U biowerk pgbouncer

# Expected output: pgbouncer=# prompt

# In the prompt, run:
SHOW VERSION;
SHOW CONFIG;
SHOW POOLS;
```

**Expected Results:**
- ✅ Can connect to PgBouncer admin console
- ✅ Version shows: `PgBouncer 1.x.x`
- ✅ Config shows expected settings
- ✅ Pools show `biowerk` database

### Test 2: Database Connection Through PgBouncer

```bash
# Connect to database through PgBouncer
psql -h localhost -p 6432 -U biowerk biowerk

# Run a test query
SELECT version();
SELECT current_database();
```

**Expected Results:**
- ✅ Can connect to database through PgBouncer
- ✅ Queries execute successfully
- ✅ PostgreSQL version displayed

### Test 3: Health Check Script

```bash
# Run health check
docker exec biowerk-pgbouncer /usr/local/bin/health-check.sh

# Expected output: "PgBouncer is healthy"
```

## 3. Start Application Services

```bash
# Start all services
docker-compose up -d

# Check all services are healthy
docker-compose ps

# Check logs for any errors
docker-compose logs --tail=50 mesh
docker-compose logs --tail=50 osteon
docker-compose logs --tail=50 pgbouncer
```

**Look For:**
- ✅ All services status: `Up (healthy)`
- ✅ No connection errors in logs
- ✅ Services log: "Using PgBouncer - configuring small application connection pool"

## 4. Connection Pool Testing

### Test 1: Monitor Initial Pool State

```bash
# Run monitoring script
./scripts/monitor-pgbouncer.sh --pools

# Or watch mode
./scripts/monitor-pgbouncer.sh --watch
```

**Expected Initial State:**
```
cl_active: 0-10    # Few active clients initially
cl_waiting: 0      # No clients waiting
sv_active: 0-5     # Few active servers
sv_idle: 10-15     # Min pool size maintained
maxwait: 0         # No wait time
```

### Test 2: Generate Load

```bash
# Simple load test using curl
for i in {1..100}; do
  curl -X GET http://localhost:8080/health &
done
wait

# Monitor during load
./scripts/monitor-pgbouncer.sh --pools
```

**Expected Under Load:**
```
cl_active: 10-50   # Active clients increase
cl_waiting: 0      # Should remain 0 (no queuing)
sv_active: 5-25    # Active servers increase
sv_idle: 5-10      # Some idle servers available
maxwait: 0-1       # Minimal wait time
```

**Red Flags:**
- ❌ `cl_waiting > 0` - Pool exhaustion
- ❌ `maxwait > 5` - High latency
- ❌ Connection errors in app logs

### Test 3: Verify Transaction Mode

```bash
# Connect to PgBouncer
psql -h localhost -p 6432 -U biowerk biowerk

# Start a transaction
BEGIN;
SELECT 1;
-- Keep transaction open

# In another terminal, check pools
docker exec biowerk-pgbouncer psql -h 127.0.0.1 -p 6432 -U biowerk pgbouncer -c "SHOW POOLS;"

# Should show connection in use

# Commit transaction
COMMIT;

# Check pools again
docker exec biowerk-pgbouncer psql -h 127.0.0.1 -p 6432 -U biowerk pgbouncer -c "SHOW POOLS;"

# Connection should be returned to pool
```

## 5. Application Integration Testing

### Test 1: API Endpoints

Test each service through the mesh gateway:

```bash
# Test osteon (document service)
curl -X POST http://localhost:8080/api/v1/osteon/documents \
  -H "Content-Type: application/json" \
  -d '{"name": "test", "content": "test"}'

# Test myocyte (analysis service)
curl -X GET http://localhost:8080/api/v1/myocyte/analyses

# Test synapse (presentation service)
curl -X GET http://localhost:8080/api/v1/synapse/presentations

# Monitor connections during tests
./scripts/monitor-pgbouncer.sh --stats
```

**Expected:**
- ✅ All API calls succeed
- ✅ No connection errors
- ✅ Response times normal
- ✅ Connection counts increase/decrease appropriately

### Test 2: Database Migrations

```bash
# Run Alembic migrations through PgBouncer
docker-compose exec mesh alembic upgrade head

# Check migration succeeded
psql -h localhost -p 6432 -U biowerk biowerk -c "SELECT version_num FROM alembic_version;"
```

**Expected:**
- ✅ Migrations complete successfully
- ✅ No connection errors
- ✅ Schema updated correctly

### Test 3: Concurrent Transactions

Create a test script to simulate concurrent database operations:

```python
# test_concurrent.py
import asyncio
import asyncpg

async def test_transaction():
    conn = await asyncpg.connect(
        host='localhost',
        port=6432,
        user='biowerk',
        password='biowerk_dev_password',
        database='biowerk'
    )
    async with conn.transaction():
        result = await conn.fetchval('SELECT 1')
        await asyncio.sleep(0.1)
    await conn.close()

async def main():
    tasks = [test_transaction() for _ in range(50)]
    await asyncio.gather(*tasks)

asyncio.run(main())
```

```bash
# Run concurrent test
docker-compose exec mesh python test_concurrent.py

# Monitor during test
./scripts/monitor-pgbouncer.sh --pools
```

**Expected:**
- ✅ All transactions complete
- ✅ No deadlocks or errors
- ✅ Connections properly pooled

## 6. Failure Testing

### Test 1: PostgreSQL Restart

```bash
# Restart PostgreSQL
docker-compose restart postgres

# Monitor PgBouncer during restart
docker-compose logs -f pgbouncer

# Try to connect
psql -h localhost -p 6432 -U biowerk biowerk -c "SELECT 1"
```

**Expected:**
- ✅ PgBouncer handles reconnection automatically
- ✅ Brief connection errors during restart (expected)
- ✅ Connections resume after PostgreSQL is back
- ✅ No service crashes

### Test 2: PgBouncer Restart

```bash
# Restart PgBouncer
docker-compose restart pgbouncer

# Check application services
docker-compose logs --tail=50 mesh osteon myocyte

# Test API calls
curl http://localhost:8080/health
```

**Expected:**
- ✅ Brief connection errors during restart
- ✅ Services reconnect automatically
- ✅ Requests succeed after reconnection

### Test 3: Connection Limit Test

```bash
# Set low connection limit for testing
# Edit .env temporarily:
PGBOUNCER_MAX_DB_CONNECTIONS=5

# Restart PgBouncer
docker-compose restart pgbouncer

# Generate high load
for i in {1..100}; do
  curl http://localhost:8080/health &
done

# Monitor
./scripts/monitor-pgbouncer.sh --pools
```

**Expected:**
- ⚠️ `cl_waiting` increases (intentional)
- ⚠️ Some requests may be slow
- ✅ No crashes or permanent failures
- ✅ System recovers when load decreases

**Action:** Restore proper connection limits after test.

## 7. Performance Testing

### Test 1: Baseline Performance

```bash
# Test direct PostgreSQL connection (disable PgBouncer)
# Edit .env:
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Restart services
docker-compose restart

# Benchmark
ab -n 1000 -c 10 http://localhost:8080/health
```

### Test 2: PgBouncer Performance

```bash
# Enable PgBouncer
# Edit .env:
POSTGRES_HOST=pgbouncer
POSTGRES_PORT=6432

# Restart services
docker-compose restart

# Benchmark
ab -n 1000 -c 10 http://localhost:8080/health
```

**Compare:**
- Connection pooling efficiency
- Request latency (should be similar or better)
- PostgreSQL connection count (should be much lower)

### Test 3: Memory Usage

```bash
# Check PostgreSQL memory without PgBouncer
docker stats biowerk-postgres --no-stream

# Check PostgreSQL memory with PgBouncer
docker stats biowerk-postgres --no-stream
```

**Expected:**
- ✅ 30-60% reduction in PostgreSQL memory usage
- ✅ Fewer backend processes in PostgreSQL

## 8. Monitoring Validation

### Test 1: Metrics Collection

```bash
# Run monitoring script
./scripts/monitor-pgbouncer.sh --stats

# Verify all metrics are collected:
# - total_xact_count
# - total_query_count
# - total_received
# - total_sent
# - avg_xact_time
# - avg_query_time
```

### Test 2: Alerting Thresholds

```bash
# Simulate pool exhaustion
PGBOUNCER_MAX_DB_CONNECTIONS=2
docker-compose restart pgbouncer

# Generate load
for i in {1..20}; do curl http://localhost:8080/health & done

# Check monitoring script shows alerts
./scripts/monitor-pgbouncer.sh --summary
```

**Expected:**
- ✅ Script shows warnings for high `cl_waiting`
- ✅ Script shows warnings for high `maxwait`

## 9. Security Testing

### Test 1: Authentication

```bash
# Try to connect with wrong password
PGPASSWORD=wrong psql -h localhost -p 6432 -U biowerk biowerk

# Expected: Authentication failure
```

### Test 2: User Isolation

```bash
# Verify only authorized user can connect
psql -h localhost -p 6432 -U nonexistent biowerk

# Expected: User not found
```

## 10. Production Readiness Checklist

Before deploying to production:

- [ ] All tests pass
- [ ] Documentation reviewed and updated
- [ ] Monitoring script works correctly
- [ ] Health checks pass
- [ ] Performance meets requirements
- [ ] Connection pools tuned for workload
- [ ] Failure scenarios tested
- [ ] PostgreSQL `max_connections` configured appropriately
- [ ] Secrets management configured (not using defaults)
- [ ] Logging configured appropriately
- [ ] Backup direct PostgreSQL access maintained
- [ ] Team trained on PgBouncer operations
- [ ] Rollback plan documented

## Common Issues and Solutions

### Issue: Cannot Build PgBouncer Image

```bash
# Check Dockerfile syntax
docker build --no-cache -t test ./pgbouncer

# Common fixes:
# 1. Ensure entrypoint.sh has LF line endings (not CRLF)
# 2. Verify all files exist in pgbouncer/
# 3. Check Docker daemon is running
```

### Issue: Health Check Fails

```bash
# Debug inside container
docker exec -it biowerk-pgbouncer /bin/bash

# Check pgbouncer process
ps aux | grep pgbouncer

# Check configuration
cat /etc/pgbouncer/pgbouncer.ini

# Try manual connection
psql -h 127.0.0.1 -p 6432 -U biowerk pgbouncer
```

### Issue: Applications Can't Connect

```bash
# Check environment variables
docker exec biowerk-mesh env | grep POSTGRES

# Should show:
# POSTGRES_HOST=pgbouncer
# POSTGRES_PORT=6432

# Check PgBouncer logs
docker logs biowerk-pgbouncer

# Check application logs
docker logs biowerk-mesh
```

## Reporting Results

Document test results:

```markdown
## Test Results

**Date:** YYYY-MM-DD
**Environment:** Development/Staging/Production
**Tested By:** Your Name

### Summary
- [x] All tests passed
- [ ] Some tests failed (see details below)

### Performance Metrics
- PostgreSQL connections: 300 → 35 (88% reduction)
- Memory usage: 500MB → 180MB (64% reduction)
- Request latency: 50ms → 45ms (10% improvement)
- Connection setup: 80ms → 2ms (97% faster)

### Issues Found
1. None / List issues

### Recommendations
1. List recommendations
```

## Next Steps

After successful testing:

1. ✅ Merge PgBouncer changes to main branch
2. ✅ Deploy to staging environment
3. ✅ Run extended load tests
4. ✅ Monitor for 24-48 hours
5. ✅ Deploy to production
6. ✅ Monitor and tune based on production load

---

**Good luck with your PgBouncer deployment! 🚀**
