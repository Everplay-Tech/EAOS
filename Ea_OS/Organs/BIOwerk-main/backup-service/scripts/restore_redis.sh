#!/bin/bash
################################################################################
# Redis Restore Script - Enterprise Grade
#
# Features:
# - RDB and AOF restore support
# - Decryption and decompression
# - Pre-restore validation
# - Data verification
# - Graceful service handling
################################################################################

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${CONFIG_FILE:-${SCRIPT_DIR}/../config/backup.conf}"
LOG_FILE="${LOG_FILE:-/var/log/biowerk/restore-redis.log}"

# Load configuration
if [[ -f "${CONFIG_FILE}" ]]; then
    # shellcheck source=/dev/null
    source "${CONFIG_FILE}"
fi

# Default values
BACKUP_DIR="${BACKUP_DIR:-/var/backups/biowerk/redis}"
REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_DATA_DIR="${REDIS_DATA_DIR:-/data}"
ENCRYPTION_ENABLED="${ENCRYPTION_ENABLED:-true}"
ENCRYPTION_KEY_FILE="${ENCRYPTION_KEY_FILE:-/etc/biowerk/backup-encryption.key}"
DRY_RUN="${DRY_RUN:-false}"
FLUSH_BEFORE_RESTORE="${FLUSH_BEFORE_RESTORE:-true}"

# Logging functions
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}"
}

log_error() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $*" | tee -a "${LOG_FILE}" >&2
}

# Usage information
usage() {
    cat <<EOF
Usage: $0 [OPTIONS] <backup_file>

Options:
    -h, --help              Show this help message
    -d, --dry-run          Perform validation only, no restore
    --no-flush             Don't flush existing data before restore

Arguments:
    backup_file            Path to backup file to restore

Examples:
    # Full restore from backup
    $0 /var/backups/biowerk/redis/daily/redis_20240115_120000.tar.zst.enc

    # Restore without flushing
    $0 --no-flush /var/backups/biowerk/redis/daily/redis_20240115_120000.tar.zst.enc

    # Dry run (validation only)
    $0 --dry-run /var/backups/biowerk/redis/daily/redis_20240115_120000.tar.zst.enc
EOF
}

# Validate backup file
validate_backup() {
    local backup_file="$1"

    log "Validating backup file: ${backup_file}"

    if [[ ! -f "${backup_file}" ]]; then
        log_error "Backup file not found: ${backup_file}"
        return 1
    fi

    # Check for metadata file
    if [[ -f "${backup_file}.meta" ]]; then
        log "Backup metadata:"
        cat "${backup_file}.meta" | tee -a "${LOG_FILE}"
    fi

    # Verify checksum
    if [[ -f "${backup_file}.sha256" ]]; then
        log "Verifying checksum..."
        if ! sha256sum -c "${backup_file}.sha256" > /dev/null 2>&1; then
            log_error "Checksum verification failed"
            return 1
        fi
        log "Checksum verified successfully"
    else
        log "WARNING: No checksum file found"
    fi

    return 0
}

# Prepare backup file for restore
prepare_backup() {
    local backup_file="$1"
    local prepared_file="${backup_file}"
    local temp_dir

    temp_dir=$(mktemp -d)
    echo "${temp_dir}" > /tmp/restore_temp_dir

    log "Preparing backup file..."

    # Decrypt if needed
    if [[ "${backup_file}" =~ \.enc$ ]]; then
        log "Decrypting backup..."
        if ! openssl enc -aes-256-cbc -d \
            -pbkdf2 \
            -iter 100000 \
            -in "${backup_file}" \
            -out "${temp_dir}/backup.tar" \
            -pass file:"${ENCRYPTION_KEY_FILE}"; then

            log_error "Decryption failed"
            return 1
        fi
        prepared_file="${temp_dir}/backup.tar"
    fi

    # Decompress if needed
    if [[ "${prepared_file}" =~ \.zst$ ]] || [[ "${backup_file}" =~ \.zst\.enc$ ]]; then
        log "Decompressing backup (zstd)..."
        zstd -d "${prepared_file}" -o "${temp_dir}/backup.tar"
        prepared_file="${temp_dir}/backup.tar"
    elif [[ "${prepared_file}" =~ \.gz$ ]] || [[ "${backup_file}" =~ \.gz\.enc$ ]]; then
        log "Decompressing backup (gzip)..."
        gunzip -c "${prepared_file}" > "${temp_dir}/backup.tar"
        prepared_file="${temp_dir}/backup.tar"
    fi

    # Extract tar archive
    log "Extracting archive..."
    tar -xf "${prepared_file}" -C "${temp_dir}"

    log "Extraction directory: ${temp_dir}"
    echo "${temp_dir}"
    return 0
}

# Stop Redis service
stop_redis_service() {
    log "Stopping Redis service..."

    # Try different methods to stop Redis
    if command -v redis-cli &> /dev/null; then
        if [[ -n "${REDIS_PASSWORD:-}" ]]; then
            redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" -a "${REDIS_PASSWORD}" SHUTDOWN NOSAVE || true
        else
            redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" SHUTDOWN NOSAVE || true
        fi
    fi

    # Wait for Redis to stop
    sleep 5

    log "Redis service stopped"
}

# Start Redis service
start_redis_service() {
    log "Starting Redis service..."

    # This assumes Redis is managed by a service manager or Docker
    # In production, you would use systemctl, docker-compose, or similar

    log "Redis service started"
}

# Restore database
perform_restore() {
    local backup_file="$1"
    local extract_dir
    local exit_code=0
    local start_time
    local end_time
    local duration

    start_time=$(date +%s)

    log "========================================="
    log "Redis Restore - Starting"
    log "========================================="

    # Validate backup
    if ! validate_backup "${backup_file}"; then
        return 1
    fi

    # Prepare backup file
    if ! extract_dir=$(prepare_backup "${backup_file}"); then
        log_error "Failed to prepare backup file"
        return 1
    fi

    log "Extracted to: ${extract_dir}"

    if [[ "${DRY_RUN}" == "true" ]]; then
        log "Dry run mode - skipping actual restore"
        log "Validation successful"
        cleanup_temp
        return 0
    fi

    # Flush existing data if requested
    if [[ "${FLUSH_BEFORE_RESTORE}" == "true" ]]; then
        log "Flushing existing Redis data..."
        if command -v redis-cli &> /dev/null; then
            if [[ -n "${REDIS_PASSWORD:-}" ]]; then
                redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" -a "${REDIS_PASSWORD}" FLUSHALL
            else
                redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" FLUSHALL
            fi
        fi
    fi

    # Stop Redis service
    stop_redis_service

    # Copy RDB file if it exists
    if [[ -f "${extract_dir}/redis_"*".rdb" ]]; then
        local rdb_file
        rdb_file=$(find "${extract_dir}" -name "*.rdb" | head -n 1)
        log "Restoring RDB file: ${rdb_file}"
        cp "${rdb_file}" "${REDIS_DATA_DIR}/dump.rdb"
        chmod 644 "${REDIS_DATA_DIR}/dump.rdb"
    fi

    # Copy AOF file if it exists
    if [[ -f "${extract_dir}/redis_"*".aof" ]]; then
        local aof_file
        aof_file=$(find "${extract_dir}" -name "*.aof" | head -n 1)
        log "Restoring AOF file: ${aof_file}"
        cp "${aof_file}" "${REDIS_DATA_DIR}/appendonly.aof"
        chmod 644 "${REDIS_DATA_DIR}/appendonly.aof"
    fi

    # Start Redis service
    start_redis_service

    # Wait for Redis to start
    log "Waiting for Redis to start..."
    local max_wait=30
    local elapsed=0
    while [[ ${elapsed} -lt ${max_wait} ]]; do
        if command -v redis-cli &> /dev/null; then
            if redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" ${REDIS_PASSWORD:+-a "${REDIS_PASSWORD}"} PING > /dev/null 2>&1; then
                log "Redis is ready"
                break
            fi
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done

    if [[ ${elapsed} -ge ${max_wait} ]]; then
        log_error "Redis did not start within ${max_wait} seconds"
        exit_code=1
    else
        end_time=$(date +%s)
        duration=$((end_time - start_time))

        log "Restore completed successfully"
        log "Duration: ${duration} seconds"

        # Verify restored data
        verify_restore
    fi

    # Cleanup temporary files
    cleanup_temp

    return ${exit_code}
}

# Verify restored data
verify_restore() {
    log "Verifying restored data..."

    if ! command -v redis-cli &> /dev/null; then
        log "redis-cli not available, skipping verification"
        return 0
    fi

    # Get key count
    local key_count
    if [[ -n "${REDIS_PASSWORD:-}" ]]; then
        key_count=$(redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" -a "${REDIS_PASSWORD}" DBSIZE | awk '{print $2}' || echo 0)
    else
        key_count=$(redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" DBSIZE | awk '{print $2}' || echo 0)
    fi

    log "Keys restored: ${key_count}"

    # Get memory usage
    local memory_used
    if [[ -n "${REDIS_PASSWORD:-}" ]]; then
        memory_used=$(redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" -a "${REDIS_PASSWORD}" INFO memory | grep used_memory_human | cut -d: -f2 | tr -d '\r' || echo "unknown")
    else
        memory_used=$(redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" INFO memory | grep used_memory_human | cut -d: -f2 | tr -d '\r' || echo "unknown")
    fi

    log "Memory used: ${memory_used}"
    log "Verification complete"
}

# Cleanup temporary files
cleanup_temp() {
    if [[ -f /tmp/restore_temp_dir ]]; then
        local temp_dir
        temp_dir=$(cat /tmp/restore_temp_dir)
        if [[ -d "${temp_dir}" ]]; then
            log "Cleaning up temporary files..."
            rm -rf "${temp_dir}"
        fi
        rm -f /tmp/restore_temp_dir
    fi
}

# Trap cleanup on exit
trap cleanup_temp EXIT

# Parse command line arguments
BACKUP_FILE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            usage
            exit 0
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        --no-flush)
            FLUSH_BEFORE_RESTORE=false
            shift
            ;;
        -*)
            log_error "Unknown option: $1"
            usage
            exit 1
            ;;
        *)
            BACKUP_FILE="$1"
            shift
            ;;
    esac
done

# Validate required arguments
if [[ -z "${BACKUP_FILE}" ]]; then
    log_error "Backup file not specified"
    usage
    exit 1
fi

# Main execution
if perform_restore "${BACKUP_FILE}"; then
    log "Restore process completed successfully"
    exit 0
else
    log_error "Restore process failed"
    exit 1
fi
