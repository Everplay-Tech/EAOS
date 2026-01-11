#!/bin/bash
# ============================================================================
# PgBouncer Entrypoint Script
# Generates userlist.txt from environment variables for security
# ============================================================================

set -e

echo "==> PgBouncer Entrypoint Starting..."

# ============================================================================
# Environment Variable Validation
# ============================================================================

if [ -z "$POSTGRES_USER" ]; then
    echo "ERROR: POSTGRES_USER environment variable is required"
    exit 1
fi

if [ -z "$POSTGRES_PASSWORD" ]; then
    echo "ERROR: POSTGRES_PASSWORD environment variable is required"
    exit 1
fi

# ============================================================================
# Generate Password Hash
# ============================================================================

echo "==> Generating authentication credentials..."

# MD5 hash format: md5<md5(password + username)>
# This matches PostgreSQL's MD5 authentication format
PASSWORD_HASH=$(echo -n "${POSTGRES_PASSWORD}${POSTGRES_USER}" | md5sum | cut -d ' ' -f 1)
MD5_PASSWORD="md5${PASSWORD_HASH}"

# Write userlist.txt with proper format
cat > /etc/pgbouncer/userlist.txt <<EOF
"${POSTGRES_USER}" "${MD5_PASSWORD}"
EOF

echo "==> Authentication file generated for user: ${POSTGRES_USER}"

# ============================================================================
# Dynamic Configuration Updates
# ============================================================================

# Update pgbouncer.ini with environment variables if provided
if [ -n "$PGBOUNCER_POOL_MODE" ]; then
    echo "==> Setting pool_mode = ${PGBOUNCER_POOL_MODE}"
    sed -i "s/^pool_mode = .*/pool_mode = ${PGBOUNCER_POOL_MODE}/" /etc/pgbouncer/pgbouncer.ini
fi

if [ -n "$PGBOUNCER_MAX_CLIENT_CONN" ]; then
    echo "==> Setting max_client_conn = ${PGBOUNCER_MAX_CLIENT_CONN}"
    sed -i "s/^max_client_conn = .*/max_client_conn = ${PGBOUNCER_MAX_CLIENT_CONN}/" /etc/pgbouncer/pgbouncer.ini
fi

if [ -n "$PGBOUNCER_DEFAULT_POOL_SIZE" ]; then
    echo "==> Setting default_pool_size = ${PGBOUNCER_DEFAULT_POOL_SIZE}"
    sed -i "s/^default_pool_size = .*/default_pool_size = ${PGBOUNCER_DEFAULT_POOL_SIZE}/" /etc/pgbouncer/pgbouncer.ini
fi

if [ -n "$PGBOUNCER_MIN_POOL_SIZE" ]; then
    echo "==> Setting min_pool_size = ${PGBOUNCER_MIN_POOL_SIZE}"
    sed -i "s/^min_pool_size = .*/min_pool_size = ${PGBOUNCER_MIN_POOL_SIZE}/" /etc/pgbouncer/pgbouncer.ini
fi

if [ -n "$PGBOUNCER_RESERVE_POOL_SIZE" ]; then
    echo "==> Setting reserve_pool_size = ${PGBOUNCER_RESERVE_POOL_SIZE}"
    sed -i "s/^reserve_pool_size = .*/reserve_pool_size = ${PGBOUNCER_RESERVE_POOL_SIZE}/" /etc/pgbouncer/pgbouncer.ini
fi

if [ -n "$PGBOUNCER_MAX_DB_CONNECTIONS" ]; then
    echo "==> Setting max_db_connections = ${PGBOUNCER_MAX_DB_CONNECTIONS}"
    sed -i "s/^max_db_connections = .*/max_db_connections = ${PGBOUNCER_MAX_DB_CONNECTIONS}/" /etc/pgbouncer/pgbouncer.ini
fi

if [ -n "$PGBOUNCER_SERVER_IDLE_TIMEOUT" ]; then
    echo "==> Setting server_idle_timeout = ${PGBOUNCER_SERVER_IDLE_TIMEOUT}"
    sed -i "s/^server_idle_timeout = .*/server_idle_timeout = ${PGBOUNCER_SERVER_IDLE_TIMEOUT}/" /etc/pgbouncer/pgbouncer.ini
fi

if [ -n "$PGBOUNCER_LOG_CONNECTIONS" ]; then
    echo "==> Setting log_connections = ${PGBOUNCER_LOG_CONNECTIONS}"
    sed -i "s/^log_connections = .*/log_connections = ${PGBOUNCER_LOG_CONNECTIONS}/" /etc/pgbouncer/pgbouncer.ini
fi

if [ -n "$PGBOUNCER_LOG_DISCONNECTIONS" ]; then
    echo "==> Setting log_disconnections = ${PGBOUNCER_LOG_DISCONNECTIONS}"
    sed -i "s/^log_disconnections = .*/log_disconnections = ${PGBOUNCER_LOG_DISCONNECTIONS}/" /etc/pgbouncer/pgbouncer.ini
fi

# ============================================================================
# Update Database Connection String
# ============================================================================

# Update the database connection string in pgbouncer.ini
POSTGRES_HOST=${POSTGRES_HOST:-postgres}
POSTGRES_PORT=${POSTGRES_PORT:-5432}
POSTGRES_DB=${POSTGRES_DB:-biowerk}

echo "==> Configuring database connection: ${POSTGRES_DB} -> ${POSTGRES_HOST}:${POSTGRES_PORT}"

sed -i "s/^biowerk = .*/biowerk = host=${POSTGRES_HOST} port=${POSTGRES_PORT} dbname=${POSTGRES_DB}/" /etc/pgbouncer/pgbouncer.ini

# ============================================================================
# File Permissions
# ============================================================================

chmod 600 /etc/pgbouncer/userlist.txt
chmod 644 /etc/pgbouncer/pgbouncer.ini

echo "==> Configuration complete!"
echo "==> PgBouncer Configuration Summary:"
echo "    Database: ${POSTGRES_DB}"
echo "    Backend: ${POSTGRES_HOST}:${POSTGRES_PORT}"
echo "    Listen Port: 6432"
echo "    User: ${POSTGRES_USER}"
echo ""

# ============================================================================
# Health Check Function
# ============================================================================

# Create a simple health check script
cat > /usr/local/bin/health-check.sh <<'HEALTHCHECK'
#!/bin/bash
# PgBouncer health check script
# Returns 0 if healthy, 1 if unhealthy

# Check if pgbouncer process is running
if ! pgrep -x pgbouncer > /dev/null; then
    echo "ERROR: PgBouncer process not running"
    exit 1
fi

# Check if we can connect to admin console
if ! echo "SHOW VERSION;" | psql -h 127.0.0.1 -p 6432 -U $POSTGRES_USER pgbouncer -t > /dev/null 2>&1; then
    echo "ERROR: Cannot connect to PgBouncer admin console"
    exit 1
fi

# Check if we can connect to the database through PgBouncer
if ! echo "SELECT 1;" | psql -h 127.0.0.1 -p 6432 -U $POSTGRES_USER $POSTGRES_DB -t > /dev/null 2>&1; then
    echo "ERROR: Cannot connect to database through PgBouncer"
    exit 1
fi

echo "PgBouncer is healthy"
exit 0
HEALTHCHECK

chmod +x /usr/local/bin/health-check.sh

# ============================================================================
# Start PgBouncer
# ============================================================================

echo "==> Starting PgBouncer..."
echo ""

# Start pgbouncer in foreground
exec pgbouncer -u pgbouncer /etc/pgbouncer/pgbouncer.ini
