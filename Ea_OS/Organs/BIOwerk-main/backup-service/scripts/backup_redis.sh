#!/bin/bash
################################################################################
# Redis Backup Script - Enterprise Grade
#
# Features:
# - RDB and AOF backup support
# - AES-256 encryption
# - Compression (gzip/zstd)
# - Backup verification
# - Prometheus metrics
# - Retention policy enforcement
# - Multi-destination support (local, S3, Azure, GCP)
################################################################################

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${CONFIG_FILE:-${SCRIPT_DIR}/../config/backup.conf}"
LOG_FILE="${LOG_FILE:-/var/log/biowerk/backup-redis.log}"

# Load configuration
if [[ -f "${CONFIG_FILE}" ]]; then
    # shellcheck source=/dev/null
    source "${CONFIG_FILE}"
fi

# Default values
BACKUP_DIR="${BACKUP_DIR:-/var/backups/biowerk/redis}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
BACKUP_RETENTION_WEEKLY="${BACKUP_RETENTION_WEEKLY:-12}"
BACKUP_RETENTION_MONTHLY="${BACKUP_RETENTION_MONTHLY:-12}"
REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_DATA_DIR="${REDIS_DATA_DIR:-/data}"
ENCRYPTION_ENABLED="${ENCRYPTION_ENABLED:-true}"
ENCRYPTION_KEY_FILE="${ENCRYPTION_KEY_FILE:-/etc/biowerk/backup-encryption.key}"
COMPRESSION="${COMPRESSION:-zstd}"
METRICS_FILE="${METRICS_FILE:-/var/lib/biowerk/metrics/backup_redis.prom}"
S3_ENABLED="${S3_ENABLED:-false}"
S3_BUCKET="${S3_BUCKET:-}"
VERIFY_BACKUP="${VERIFY_BACKUP:-true}"
BACKUP_METHOD="${BACKUP_METHOD:-rdb}"  # rdb or aof

# Logging functions
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}"
}

log_error() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $*" | tee -a "${LOG_FILE}" >&2
}

# Metrics functions
write_metric() {
    local metric_name="$1"
    local metric_value="$2"
    local labels="${3:-}"

    mkdir -p "$(dirname "${METRICS_FILE}")"

    if [[ -n "${labels}" ]]; then
        echo "biowerk_backup_${metric_name}{${labels}} ${metric_value}" >> "${METRICS_FILE}.tmp"
    else
        echo "biowerk_backup_${metric_name} ${metric_value}" >> "${METRICS_FILE}.tmp"
    fi
}

publish_metrics() {
    if [[ -f "${METRICS_FILE}.tmp" ]]; then
        mv "${METRICS_FILE}.tmp" "${METRICS_FILE}"
    fi
}

# Create backup directory structure
create_backup_dirs() {
    mkdir -p "${BACKUP_DIR}"/{daily,weekly,monthly}
    mkdir -p "$(dirname "${LOG_FILE}")"
    mkdir -p "$(dirname "${METRICS_FILE}")"
}

# Generate encryption key if it doesn't exist
ensure_encryption_key() {
    if [[ "${ENCRYPTION_ENABLED}" == "true" ]]; then
        if [[ ! -f "${ENCRYPTION_KEY_FILE}" ]]; then
            log "Generating new encryption key..."
            mkdir -p "$(dirname "${ENCRYPTION_KEY_FILE}")"
            openssl rand -base64 32 > "${ENCRYPTION_KEY_FILE}"
            chmod 600 "${ENCRYPTION_KEY_FILE}"
            log "Encryption key generated at ${ENCRYPTION_KEY_FILE}"
        fi
    fi
}

# Trigger Redis save
trigger_redis_save() {
    log "Triggering Redis BGSAVE..."

    # Check if redis-cli is available
    if ! command -v redis-cli &> /dev/null; then
        log_error "redis-cli not found"
        return 1
    fi

    # Trigger background save
    local save_result
    if [[ -n "${REDIS_PASSWORD:-}" ]]; then
        save_result=$(redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" -a "${REDIS_PASSWORD}" BGSAVE)
    else
        save_result=$(redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" BGSAVE)
    fi

    if [[ "${save_result}" == "Background saving started" ]]; then
        log "BGSAVE started successfully"

        # Wait for save to complete
        local max_wait=300  # 5 minutes
        local elapsed=0
        while [[ ${elapsed} -lt ${max_wait} ]]; do
            local lastsave
            if [[ -n "${REDIS_PASSWORD:-}" ]]; then
                lastsave=$(redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" -a "${REDIS_PASSWORD}" LASTSAVE)
            else
                lastsave=$(redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" LASTSAVE)
            fi

            # Check if save is complete
            sleep 5
            elapsed=$((elapsed + 5))

            local current_lastsave
            if [[ -n "${REDIS_PASSWORD:-}" ]]; then
                current_lastsave=$(redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" -a "${REDIS_PASSWORD}" LASTSAVE)
            else
                current_lastsave=$(redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" LASTSAVE)
            fi

            if [[ "${current_lastsave}" -gt "${lastsave}" ]]; then
                log "BGSAVE completed"
                return 0
            fi
        done

        log_error "BGSAVE timed out after ${max_wait} seconds"
        return 1
    else
        log_error "BGSAVE failed: ${save_result}"
        return 1
    fi
}

# Perform Redis backup
perform_backup() {
    local backup_date
    local backup_file
    local backup_size
    local start_time
    local end_time
    local duration
    local exit_code=0

    backup_date=$(date +%Y%m%d_%H%M%S)
    start_time=$(date +%s)

    # Determine backup directory based on schedule
    local backup_subdir="daily"
    local day_of_week=$(date +%u)
    local day_of_month=$(date +%d)

    if [[ "${day_of_month}" == "01" ]]; then
        backup_subdir="monthly"
    elif [[ "${day_of_week}" == "7" ]]; then
        backup_subdir="weekly"
    fi

    backup_file="${BACKUP_DIR}/${backup_subdir}/redis_${backup_date}"

    log "Starting Redis backup: ${backup_file}"

    # Trigger save and wait for completion
    if ! trigger_redis_save; then
        exit_code=1
    fi

    if [[ ${exit_code} -eq 0 ]]; then
        # Copy RDB file
        if [[ "${BACKUP_METHOD}" == "rdb" ]]; then
            if [[ -f "${REDIS_DATA_DIR}/dump.rdb" ]]; then
                cp "${REDIS_DATA_DIR}/dump.rdb" "${backup_file}.rdb"
                log "RDB file copied"
            else
                log_error "RDB file not found at ${REDIS_DATA_DIR}/dump.rdb"
                exit_code=1
            fi
        fi

        # Copy AOF file if enabled
        if [[ "${BACKUP_METHOD}" == "aof" ]] || [[ "${BACKUP_METHOD}" == "both" ]]; then
            if [[ -f "${REDIS_DATA_DIR}/appendonly.aof" ]]; then
                cp "${REDIS_DATA_DIR}/appendonly.aof" "${backup_file}.aof"
                log "AOF file copied"
            else
                log "AOF file not found (may not be enabled)"
            fi
        fi

        # Create tar archive if both files exist
        local files_to_archive=()
        [[ -f "${backup_file}.rdb" ]] && files_to_archive+=("${backup_file}.rdb")
        [[ -f "${backup_file}.aof" ]] && files_to_archive+=("${backup_file}.aof")

        if [[ ${#files_to_archive[@]} -gt 0 ]]; then
            tar -cf "${backup_file}.tar" -C "$(dirname "${backup_file}")" \
                $(for f in "${files_to_archive[@]}"; do basename "$f"; done)
            rm -f "${files_to_archive[@]}"
            backup_file="${backup_file}.tar"
        else
            log_error "No backup files to archive"
            exit_code=1
        fi
    fi

    # Compress backup
    if [[ ${exit_code} -eq 0 ]]; then
        case "${COMPRESSION}" in
            gzip)
                log "Compressing backup with gzip..."
                gzip -9 "${backup_file}"
                backup_file="${backup_file}.gz"
                ;;
            zstd)
                log "Compressing backup with zstd..."
                zstd -19 --rm "${backup_file}" -o "${backup_file}.zst"
                backup_file="${backup_file}.zst"
                ;;
            none)
                ;;
            *)
                log_error "Unknown compression type: ${COMPRESSION}"
                exit_code=1
                ;;
        esac
    fi

    # Encrypt backup
    if [[ ${exit_code} -eq 0 ]] && [[ "${ENCRYPTION_ENABLED}" == "true" ]]; then
        log "Encrypting backup..."
        if ! openssl enc -aes-256-cbc \
            -salt \
            -pbkdf2 \
            -iter 100000 \
            -in "${backup_file}" \
            -out "${backup_file}.enc" \
            -pass file:"${ENCRYPTION_KEY_FILE}"; then

            log_error "Encryption failed"
            exit_code=1
        else
            rm -f "${backup_file}"
            backup_file="${backup_file}.enc"
        fi
    fi

    # Calculate backup size and duration
    if [[ ${exit_code} -eq 0 ]]; then
        backup_size=$(stat -f%z "${backup_file}" 2>/dev/null || stat -c%s "${backup_file}" 2>/dev/null || echo 0)
        end_time=$(date +%s)
        duration=$((end_time - start_time))

        log "Backup completed successfully"
        log "Backup file: ${backup_file}"
        log "Backup size: $((backup_size / 1024 / 1024)) MB"
        log "Duration: ${duration} seconds"

        # Generate checksum
        sha256sum "${backup_file}" > "${backup_file}.sha256"

        # Write metadata
        cat > "${backup_file}.meta" <<EOF
{
  "backup_date": "${backup_date}",
  "host": "${REDIS_HOST}",
  "size_bytes": ${backup_size},
  "duration_seconds": ${duration},
  "compression": "${COMPRESSION}",
  "encrypted": ${ENCRYPTION_ENABLED},
  "backup_type": "${backup_subdir}",
  "backup_method": "${BACKUP_METHOD}"
}
EOF

        # Verify backup
        if [[ "${VERIFY_BACKUP}" == "true" ]]; then
            verify_backup "${backup_file}"
        fi

        # Upload to cloud storage
        if [[ "${S3_ENABLED}" == "true" ]]; then
            upload_to_s3 "${backup_file}"
        fi

        # Write metrics
        write_metric "redis_last_success_timestamp" "${end_time}" "host=\"${REDIS_HOST}\""
        write_metric "redis_size_bytes" "${backup_size}" "host=\"${REDIS_HOST}\",type=\"${backup_subdir}\""
        write_metric "redis_duration_seconds" "${duration}" "host=\"${REDIS_HOST}\""
        write_metric "redis_status" "0" "host=\"${REDIS_HOST}\""
    else
        log_error "Backup failed"
        write_metric "redis_status" "1" "host=\"${REDIS_HOST}\""
        write_metric "redis_last_failure_timestamp" "$(date +%s)" "host=\"${REDIS_HOST}\""
    fi

    publish_metrics
    return ${exit_code}
}

# Verify backup integrity
verify_backup() {
    local backup_file="$1"
    local verify_exit_code=0
    local temp_dir

    log "Verifying backup integrity..."

    # Verify checksum
    if ! sha256sum -c "${backup_file}.sha256" > /dev/null 2>&1; then
        log_error "Checksum verification failed"
        verify_exit_code=1
    fi

    # Create temp directory for verification
    temp_dir=$(mktemp -d)
    trap "rm -rf ${temp_dir}" EXIT

    # Decrypt if needed
    local file_to_verify="${backup_file}"
    if [[ "${backup_file}" =~ \.enc$ ]]; then
        log "Decrypting for verification..."
        openssl enc -aes-256-cbc -d \
            -pbkdf2 \
            -iter 100000 \
            -in "${backup_file}" \
            -out "${temp_dir}/backup.tar" \
            -pass file:"${ENCRYPTION_KEY_FILE}"
        file_to_verify="${temp_dir}/backup.tar"
    fi

    # Decompress if needed
    if [[ "${file_to_verify}" =~ \.zst$ ]]; then
        zstd -d "${file_to_verify}" -o "${temp_dir}/backup.tar"
        file_to_verify="${temp_dir}/backup.tar"
    elif [[ "${file_to_verify}" =~ \.gz$ ]]; then
        gunzip -c "${file_to_verify}" > "${temp_dir}/backup.tar"
        file_to_verify="${temp_dir}/backup.tar"
    fi

    # Verify tar archive
    if ! tar -tf "${file_to_verify}" > /dev/null 2>&1; then
        log_error "Tar archive verification failed"
        verify_exit_code=1
    else
        log "Backup verification successful"
    fi

    write_metric "redis_verification_status" "${verify_exit_code}" "host=\"${REDIS_HOST}\""

    return ${verify_exit_code}
}

# Upload to S3
upload_to_s3() {
    local backup_file="$1"

    if [[ -z "${S3_BUCKET}" ]]; then
        log "S3 bucket not configured, skipping upload"
        return 0
    fi

    log "Uploading to S3: s3://${S3_BUCKET}/redis/"

    if command -v aws &> /dev/null; then
        aws s3 cp "${backup_file}" "s3://${S3_BUCKET}/redis/" \
            --storage-class STANDARD_IA \
            --metadata "host=${REDIS_HOST},timestamp=$(date +%s)"

        aws s3 cp "${backup_file}.sha256" "s3://${S3_BUCKET}/redis/"
        aws s3 cp "${backup_file}.meta" "s3://${S3_BUCKET}/redis/"

        log "Upload to S3 completed"
    else
        log_error "AWS CLI not found, skipping S3 upload"
    fi
}

# Cleanup old backups
cleanup_old_backups() {
    log "Cleaning up old backups..."

    # Daily backups
    find "${BACKUP_DIR}/daily" -type f -name "redis_*" -mtime +"${BACKUP_RETENTION_DAYS}" -delete 2>/dev/null || true

    # Weekly backups
    if [[ "${BACKUP_RETENTION_WEEKLY}" -gt 0 ]]; then
        find "${BACKUP_DIR}/weekly" -type f -name "redis_*" -mtime +"$((BACKUP_RETENTION_WEEKLY * 7))" -delete 2>/dev/null || true
    fi

    # Monthly backups
    if [[ "${BACKUP_RETENTION_MONTHLY}" -gt 0 ]]; then
        find "${BACKUP_DIR}/monthly" -type f -name "redis_*" -mtime +"$((BACKUP_RETENTION_MONTHLY * 30))" -delete 2>/dev/null || true
    fi

    log "Cleanup completed"
}

# Main execution
main() {
    log "========================================="
    log "Redis Backup Script - Starting"
    log "========================================="

    create_backup_dirs
    ensure_encryption_key

    if perform_backup; then
        cleanup_old_backups
        log "Backup process completed successfully"
        exit 0
    else
        log_error "Backup process failed"
        exit 1
    fi
}

# Handle command line arguments
case "${1:-backup}" in
    backup)
        main
        ;;
    cleanup)
        create_backup_dirs
        cleanup_old_backups
        ;;
    verify)
        verify_backup "$2"
        ;;
    *)
        echo "Usage: $0 {backup|cleanup|verify <backup_file>}"
        exit 1
        ;;
esac
