# ============================================================================
# PgBouncer Dockerfile for BIOwerk
# Production-ready connection pooling for PostgreSQL
# ============================================================================

FROM alpine:3.19

# Metadata
LABEL maintainer="BIOwerk Team"
LABEL description="PgBouncer connection pooler for BIOwerk PostgreSQL"
LABEL version="1.0.0"

# ============================================================================
# Install Dependencies
# ============================================================================

RUN apk add --no-cache \
    pgbouncer \
    postgresql-client \
    bash \
    && rm -rf /var/cache/apk/*

# ============================================================================
# Create Required Directories
# ============================================================================

RUN mkdir -p /etc/pgbouncer /var/log/pgbouncer /var/run/pgbouncer

# ============================================================================
# Copy Configuration Files
# ============================================================================

COPY pgbouncer.ini /etc/pgbouncer/pgbouncer.ini
COPY userlist.txt /etc/pgbouncer/userlist.txt
COPY entrypoint.sh /usr/local/bin/entrypoint.sh

# ============================================================================
# Set Permissions
# ============================================================================

RUN chmod +x /usr/local/bin/entrypoint.sh \
    && chmod 644 /etc/pgbouncer/pgbouncer.ini \
    && chmod 600 /etc/pgbouncer/userlist.txt \
    && chown -R pgbouncer:pgbouncer /etc/pgbouncer /var/log/pgbouncer /var/run/pgbouncer

# ============================================================================
# Expose Ports
# ============================================================================

# PgBouncer default port
EXPOSE 6432

# ============================================================================
# Health Check
# ============================================================================

# Health check: Verify PgBouncer can accept connections
# This will be replaced by a more comprehensive check in entrypoint.sh
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD /usr/local/bin/health-check.sh || exit 1

# ============================================================================
# Runtime Configuration
# ============================================================================

# Run as pgbouncer user
USER pgbouncer

# Set working directory
WORKDIR /etc/pgbouncer

# ============================================================================
# Start PgBouncer
# ============================================================================

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
