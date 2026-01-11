# PgBouncer Configuration Directory

This directory contains the production-ready PgBouncer configuration for BIOwerk.

## Files

- **`pgbouncer.ini`** - Main PgBouncer configuration file with enterprise-grade settings
- **`userlist.txt`** - Authentication file template (generated dynamically by entrypoint.sh)
- **`Dockerfile`** - PgBouncer Docker image with Alpine Linux
- **`entrypoint.sh`** - Startup script that generates credentials from environment variables

## Quick Start

PgBouncer is automatically started with `docker-compose up`:

```bash
# Start all services including PgBouncer
docker-compose up -d

# Check PgBouncer status
docker logs biowerk-pgbouncer

# Monitor PgBouncer
./scripts/monitor-pgbouncer.sh
```

## Configuration

All settings can be customized via environment variables in `.env`:

```bash
# Pool Mode
PGBOUNCER_POOL_MODE=transaction

# Connection Limits
PGBOUNCER_MAX_CLIENT_CONN=200
PGBOUNCER_DEFAULT_POOL_SIZE=25
PGBOUNCER_MIN_POOL_SIZE=10
PGBOUNCER_RESERVE_POOL_SIZE=10
PGBOUNCER_MAX_DB_CONNECTIONS=50

# Timeouts
PGBOUNCER_SERVER_IDLE_TIMEOUT=600
```

See `.env.example` for all available options.

## Security

**⚠️ IMPORTANT:** The `userlist.txt` file in this directory is a template only.

- The actual authentication file is generated at runtime by `entrypoint.sh`
- Credentials are read from environment variables (`POSTGRES_USER`, `POSTGRES_PASSWORD`)
- **Never commit actual passwords to version control**
- For production, use secrets management (Kubernetes Secrets, AWS Secrets Manager, etc.)

## Admin Console

Connect to PgBouncer admin console:

```bash
# Using psql
psql -h pgbouncer -p 6432 -U biowerk pgbouncer

# Show pool status
pgbouncer=# SHOW POOLS;

# Show statistics
pgbouncer=# SHOW STATS;

# Show configuration
pgbouncer=# SHOW CONFIG;
```

## Monitoring

Use the monitoring script for real-time metrics:

```bash
# Interactive dashboard
./scripts/monitor-pgbouncer.sh

# Watch mode (auto-refresh)
./scripts/monitor-pgbouncer.sh --watch

# Specific views
./scripts/monitor-pgbouncer.sh --pools
./scripts/monitor-pgbouncer.sh --stats
./scripts/monitor-pgbouncer.sh --summary
```

## Health Checks

PgBouncer includes built-in health checks:

```bash
# Manual health check
docker exec biowerk-pgbouncer /usr/local/bin/health-check.sh

# Docker healthcheck status
docker inspect biowerk-pgbouncer | grep -A 10 Health
```

## Customization

### Modifying Configuration

1. Edit `pgbouncer.ini` for static configuration
2. Use environment variables for dynamic configuration
3. Restart PgBouncer: `docker-compose restart pgbouncer`

### Adding Databases

Edit `pgbouncer.ini` under `[databases]` section:

```ini
[databases]
biowerk = host=postgres port=5432 dbname=biowerk
mydb = host=postgres port=5432 dbname=mydb
```

## Troubleshooting

### PgBouncer Won't Start

```bash
# Check logs
docker logs biowerk-pgbouncer

# Common issues:
# 1. PostgreSQL not ready - wait for postgres health check
# 2. Invalid configuration - check pgbouncer.ini syntax
# 3. Port conflict - ensure port 6432 is available
```

### Connection Errors

```bash
# Test PostgreSQL connectivity
docker exec biowerk-pgbouncer psql -h postgres -p 5432 -U biowerk biowerk

# Test PgBouncer connectivity
psql -h localhost -p 6432 -U biowerk biowerk
```

### Performance Issues

```bash
# Monitor pool status
./scripts/monitor-pgbouncer.sh --pools

# Look for:
# - cl_waiting > 0 (clients waiting - increase pool size)
# - maxwait > 5s (high latency - increase pool size)
# - sv_idle > 15 (too many idle - reduce pool size)
```

## Documentation

- **Full Documentation**: See `/PGBOUNCER.md` in project root
- **PgBouncer Official Docs**: https://www.pgbouncer.org/
- **Configuration Reference**: https://www.pgbouncer.org/config.html

## Production Deployment

For production environments:

1. ✅ Use secrets management for credentials
2. ✅ Set appropriate pool sizes based on load testing
3. ✅ Enable connection logging initially, disable after tuning
4. ✅ Set up monitoring and alerting
5. ✅ Configure PostgreSQL `max_connections` appropriately
6. ✅ Test failover and recovery procedures

See `PGBOUNCER.md` for detailed production best practices.
