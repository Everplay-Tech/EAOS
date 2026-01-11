FROM python:3.11-slim

LABEL maintainer="BIOwerk Team"
LABEL description="Enterprise-grade backup and disaster recovery service"

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client-15 \
    mongodb-clients \
    redis-tools \
    curl \
    openssl \
    zstd \
    gzip \
    tar \
    cron \
    awscli \
    && rm -rf /var/lib/apt/lists/*

# Create application directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY backup_orchestrator.py .
COPY scripts/ scripts/
COPY config/ config/

# Make scripts executable
RUN chmod +x scripts/*.sh

# Create necessary directories
RUN mkdir -p \
    /var/backups/biowerk/{postgres,mongodb,redis} \
    /var/log/biowerk \
    /var/lib/biowerk/metrics \
    /etc/biowerk

# Create non-root user
RUN useradd -m -u 1000 -s /bin/bash biowerk && \
    chown -R biowerk:biowerk /app /var/backups/biowerk /var/log/biowerk /var/lib/biowerk /etc/biowerk

# Switch to non-root user
USER biowerk

# Expose API port
EXPOSE 8090

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8090/health || exit 1

# Run the orchestrator
CMD ["python", "backup_orchestrator.py"]
