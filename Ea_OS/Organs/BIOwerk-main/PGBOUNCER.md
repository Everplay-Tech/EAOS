# PgBouncer Connection Pooling

## Overview

BIOwerk uses **PgBouncer** for enterprise-grade PostgreSQL connection pooling. This provides:

- **Reduced PostgreSQL memory usage** - Fewer server-side connections
- **Better connection reuse** - Multiplexing across microservices
- **Protection against connection exhaustion** - Controlled connection limits
- **Improved performance** - Connection pooling optimizations
- **Production-ready** - Battle-tested in high-scale deployments

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Application Services                      │
│  ┌─────┐ ┌───────┐ ┌────────┐ ┌─────────┐ ┌────────┐       │
│  │Mesh │ │Osteon │ │Myocyte │ │ Synapse │ │  ...   │       │
│  └──┬──┘ └───┬───┘ └────┬───┘ └────┬────┘ └───┬────┘       │
│     │        │           │          │          │             │
│     └────────┴───────────┴──────────┴──────────┘             │
│              Small App Pools (5+5 each)                      │
└─────────────────────────┬───────────────────────────────────┘
                          │
                    Port 6432 (PgBouncer)
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                      PgBouncer                               │
│  ┌────────────────────────────────────────────────────┐     │
│  │ Connection Pool (25 default + 10 reserve)          │     │
│  │ - Transaction Mode                                 │     │
│  │ - Max 200 client connections                       │     │
│  │ - Max 50 server connections                        │     │
│  └────────────────────────────────────────────────────┘     │
└─────────────────────────┬───────────────────────────────────┘
                          │
                    Port 5432 (PostgreSQL)
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    PostgreSQL 16                             │
│  ┌────────────────────────────────────────────────────┐     │
│  │ Actual Backend Connections (25-50 active)          │     │
│  │ - Reduced from 100-300 without PgBouncer           │     │
│  │ - Lower memory footprint                           │     │
│  │ - Better cache efficiency                          │     │
│  └────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

## Configuration

### Environment Variables

All PgBouncer settings can be configured via environment variables in `.env`:

```bash
# PostgreSQL Connection (points to PgBouncer)
POSTGRES_HOST=pgbouncer
POSTGRES_PORT=6432

# PgBouncer Pool Mode
PGBOUNCER_POOL_MODE=transaction  # transaction | session | statement

# Connection Limits
PGBOUNCER_MAX_CLIENT_CONN=200        # Max connections from apps
PGBOUNCER_DEFAULT_POOL_SIZE=25       # Main pool size to PostgreSQL
PGBOUNCER_MIN_POOL_SIZE=10           # Minimum warm connections
PGBOUNCER_RESERVE_POOL_SIZE=10       # Emergency pool
PGBOUNCER_MAX_DB_CONNECTIONS=50      # Hard limit to PostgreSQL

# Timeouts (seconds)
PGBOUNCER_SERVER_IDLE_TIMEOUT=600    # Close idle server connections

# Logging
PGBOUNCER_LOG_CONNECTIONS=1          # Log connections
PGBOUNCER_LOG_DISCONNECTIONS=1       # Log disconnections
```

### Pool Modes

#### Transaction Mode (Recommended) ⭐

**How it works:**
- Connection is assigned to client only during a transaction
- Returned to pool immediately after `COMMIT` or `ROLLBACK`
- Best connection reuse and scalability

**When to use:**
- Microservices with short transactions (BIOwerk's architecture)
- Stateless applications
- RESTful APIs

**Limitations:**
- Cannot use session-level features:
  - Temporary tables
  - `PREPARE` statements (unless in same transaction)
  - `SET` variables between transactions
  - `LISTEN/NOTIFY` (use direct connection or Redis instead)

#### Session Mode

**How it works:**
- Connection assigned when client connects
- Held until client disconnects
- Traditional PostgreSQL behavior

**When to use:**
- Need temporary tables across transactions
- Using prepared statements
- Session-level state required

**Trade-offs:**
- Less efficient connection reuse
- Higher PostgreSQL memory usage

#### Statement Mode (Advanced)

**How it works:**
- Connection returned after **each statement**
- Most aggressive pooling

**When to use:**
- Very specific use cases
- Single-statement transactions only

**Limitations:**
- Breaks multi-statement transactions
- Rarely recommended

### Choosing Pool Mode

For **BIOwerk**, we use **transaction mode** because:

1. ✅ Microservices architecture with stateless APIs
2. ✅ Short-lived transactions (document generation, analysis, etc.)
3. ✅ Maximum connection multiplexing needed
4. ✅ No session-level state required (we use Redis for state)
5. ✅ SQLAlchemy handles transactions properly

## Tuning Guide

### Finding the Right Pool Size

#### 1. Monitor Connection Usage

```bash
# Using the monitoring script
./scripts/monitor-pgbouncer.sh --pools

# Watch mode (auto-refresh)
./scripts/monitor-pgbouncer.sh --watch
```

#### 2. Key Metrics to Watch

| Metric | What it means | Action |
|--------|--------------|--------|
| `cl_waiting` | Clients waiting for connections | **> 0**: Increase `default_pool_size` or `max_db_connections` |
| `maxwait` | Longest wait time | **> 5s**: Pool too small, increase size |
| `sv_idle` | Idle server connections | **> 15**: Pool too large, reduce `default_pool_size` |
| `sv_active` | Active server connections | Should track with actual query load |

#### 3. Tuning Formula

```
# Base pool size calculation:
default_pool_size = (expected_concurrent_queries / num_databases) + buffer

# For BIOwerk (10 services, ~30 concurrent queries typical):
default_pool_size = 30 / 1 + 5 = 35 (we use 25 conservatively)

# Reserve pool for spikes:
reserve_pool_size = default_pool_size * 0.3 to 0.5

# Max client connections:
max_client_conn = (num_services * connections_per_service) + overhead
                = (10 * 5) + 150 = 200

# Max database connections (must be < PostgreSQL max_connections):
max_db_connections = default_pool_size + reserve_pool_size
                   = 25 + 10 = 35 (we use 50 for headroom)
```

### Application Pool Sizes

When using PgBouncer, application connection pools should be **smaller**:

| Configuration | Without PgBouncer | With PgBouncer |
|--------------|-------------------|----------------|
| App pool size | 10 | 5 |
| App max overflow | 20 | 5 |
| Total app connections | 10 services × 30 = 300 | 10 services × 10 = 100 |
| PostgreSQL connections | 300 | 25-50 |

BIOwerk automatically detects PgBouncer and configures optimal pool sizes in `matrix/database.py`.

## Monitoring

### Built-in Monitoring Script

```bash
# Interactive menu
./scripts/monitor-pgbouncer.sh

# Show specific view
./scripts/monitor-pgbouncer.sh --summary
./scripts/monitor-pgbouncer.sh --pools
./scripts/monitor-pgbouncer.sh --stats

# Auto-refresh mode
./scripts/monitor-pgbouncer.sh --watch
```

### Using psql Directly

```bash
# Connect to PgBouncer admin console
psql -h pgbouncer -p 6432 -U biowerk pgbouncer

# Show pool status
SHOW POOLS;

# Show statistics
SHOW STATS;

# Show all clients
SHOW CLIENTS;

# Show server connections
SHOW SERVERS;

# Show configuration
SHOW CONFIG;
```

### Key Admin Commands

| Command | Description |
|---------|-------------|
| `SHOW POOLS;` | Pool status per database |
| `SHOW STATS;` | Database statistics |
| `SHOW CLIENTS;` | Active client connections |
| `SHOW SERVERS;` | PostgreSQL backend connections |
| `SHOW CONFIG;` | Current configuration |
| `SHOW DATABASES;` | Configured databases |
| `RELOAD;` | Reload configuration without restart |
| `PAUSE;` | Pause all traffic |
| `RESUME;` | Resume traffic |

## Health Checks

PgBouncer includes comprehensive health checks:

```bash
# Inside PgBouncer container
/usr/local/bin/health-check.sh

# From host
docker exec biowerk-pgbouncer /usr/local/bin/health-check.sh
```

The health check verifies:
1. ✅ PgBouncer process is running
2. ✅ Can connect to admin console
3. ✅ Can query database through PgBouncer

## Production Best Practices

### 1. PostgreSQL Configuration

Update `postgresql.conf` to work optimally with PgBouncer:

```ini
# Reduce max_connections since PgBouncer pools
max_connections = 100  # Down from 200+

# Increase shared_buffers with fewer connections
shared_buffers = 1GB  # Can increase with memory savings

# Connection limits per role (optional safety)
ALTER ROLE biowerk CONNECTION LIMIT 60;
```

### 2. Security

```bash
# Rotate passwords using environment variables
# Update .env and restart services
docker-compose restart pgbouncer

# Use secrets management in production
# - Kubernetes: Secrets
# - Docker Swarm: Docker Secrets
# - AWS: Secrets Manager / Parameter Store
```

### 3. Monitoring Alerts

Set up alerts for:

- `cl_waiting > 5` - Pool exhaustion
- `maxwait > 10s` - High latency
- `sv_idle > default_pool_size * 0.5` - Over-provisioned pool

### 4. Backup Connections

Always keep a way to connect directly to PostgreSQL:

```bash
# Direct PostgreSQL connection (bypassing PgBouncer)
psql -h postgres -p 5432 -U biowerk biowerk
```

Update firewall rules to allow admin access to port 5432 for emergencies.

### 5. Logging

PgBouncer logs are available via Docker:

```bash
# View logs
docker logs biowerk-pgbouncer

# Follow logs
docker logs -f biowerk-pgbouncer

# Last 100 lines
docker logs --tail 100 biowerk-pgbouncer
```

## Troubleshooting

### Issue: Clients Waiting for Connections

**Symptoms:**
```
cl_waiting > 0
maxwait increasing
```

**Solutions:**

1. **Increase pool size:**
   ```bash
   # In .env
   PGBOUNCER_DEFAULT_POOL_SIZE=40
   PGBOUNCER_MAX_DB_CONNECTIONS=60

   # Restart
   docker-compose restart pgbouncer
   ```

2. **Check for long-running queries:**
   ```sql
   -- In PostgreSQL
   SELECT pid, now() - query_start as duration, query
   FROM pg_stat_activity
   WHERE state = 'active'
   ORDER BY duration DESC;
   ```

3. **Optimize application code** - Reduce transaction duration

### Issue: Too Many Idle Connections

**Symptoms:**
```
sv_idle >> sv_active
High PostgreSQL memory usage
```

**Solutions:**

1. **Reduce pool size:**
   ```bash
   PGBOUNCER_DEFAULT_POOL_SIZE=15
   PGBOUNCER_MIN_POOL_SIZE=5
   ```

2. **Reduce idle timeout:**
   ```bash
   PGBOUNCER_SERVER_IDLE_TIMEOUT=300  # 5 minutes
   ```

### Issue: "Server Conn Crashed" Errors

**Causes:**
- PostgreSQL restarted
- Network issues
- PostgreSQL connection limits hit

**Solutions:**

1. **Check PostgreSQL health:**
   ```bash
   docker logs biowerk-postgres
   docker exec biowerk-postgres pg_isready
   ```

2. **Verify PostgreSQL max_connections:**
   ```sql
   SHOW max_connections;
   SELECT count(*) FROM pg_stat_activity;
   ```

3. **Ensure max_db_connections < PostgreSQL max_connections**

### Issue: Application Errors with Transaction Mode

**Symptoms:**
```
ERROR: prepared statement "..." does not exist
ERROR: temporary table "..." does not exist
```

**Cause:** Using session-level features in transaction mode

**Solutions:**

1. **Switch to session mode** (if needed):
   ```bash
   PGBOUNCER_POOL_MODE=session
   ```

2. **Refactor code** to avoid session state:
   - Use CTEs instead of temp tables
   - Execute prepared statements in same transaction
   - Move state to Redis/application layer

## Disabling PgBouncer (Development)

To connect directly to PostgreSQL (not recommended for production):

```bash
# In .env
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Restart services
docker-compose restart
```

## Performance Benchmarking

### Connection Setup Overhead

```bash
# Test connection pooling benefit
# Without PgBouncer: ~50-100ms per connection
# With PgBouncer: ~1-5ms per connection (cached)

# Benchmark
pgbench -c 50 -j 10 -T 60 -h pgbouncer -p 6432 -U biowerk biowerk
```

### Expected Improvements

| Metric | Without PgBouncer | With PgBouncer | Improvement |
|--------|-------------------|----------------|-------------|
| PostgreSQL connections | 100-300 | 25-50 | 70% reduction |
| PostgreSQL memory | ~500MB | ~200MB | 60% reduction |
| Connection setup time | 50-100ms | 1-5ms | 95% faster |
| Max throughput | ~1000 qps | ~3000 qps | 3x improvement |

*Results vary based on workload, query complexity, and hardware*

## References

- **PgBouncer Documentation**: https://www.pgbouncer.org/
- **PgBouncer GitHub**: https://github.com/pgbouncer/pgbouncer
- **PostgreSQL Connection Pooling**: https://wiki.postgresql.org/wiki/PgBouncer

## Support

For issues or questions:

1. Check PgBouncer logs: `docker logs biowerk-pgbouncer`
2. Monitor with: `./scripts/monitor-pgbouncer.sh`
3. Review this documentation
4. Check PostgreSQL logs: `docker logs biowerk-postgres`

## Next Steps

- ✅ PgBouncer is configured and ready
- 📊 Monitor performance with `./scripts/monitor-pgbouncer.sh`
- 🔧 Tune based on your workload
- 🚀 Deploy to production with confidence!
