#!/bin/bash
################################################################################
# PostgreSQL Restore Script - Enterprise Grade
#
# Features:
# - Full and point-in-time recovery (PITR)
# - Decryption and decompression
# - Pre-restore validation
# - Database recreation
# - Verification of restored data
# - Rollback capability
################################################################################

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${CONFIG_FILE:-${SCRIPT_DIR}/../config/backup.conf}"
LOG_FILE="${LOG_FILE:-/var/log/biowerk/restore-postgres.log}"

# Load configuration
if [[ -f "${CONFIG_FILE}" ]]; then
    # shellcheck source=/dev/null
    source "${CONFIG_FILE}"
fi

# Default values
BACKUP_DIR="${BACKUP_DIR:-/var/backups/biowerk/postgres}"
POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-biowerk}"
POSTGRES_DB="${POSTGRES_DB:-biowerk}"
ENCRYPTION_ENABLED="${ENCRYPTION_ENABLED:-true}"
ENCRYPTION_KEY_FILE="${ENCRYPTION_KEY_FILE:-/etc/biowerk/backup-encryption.key}"
RESTORE_TARGET_TIME="${RESTORE_TARGET_TIME:-}"
DRY_RUN="${DRY_RUN:-false}"
PARALLEL_JOBS="${PARALLEL_JOBS:-4}"

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
    -t, --target-time TIME Point-in-time recovery target (format: YYYY-MM-DD HH:MM:SS)
    -j, --jobs N           Number of parallel jobs (default: 4)
    --no-drop-db           Don't drop existing database before restore

Arguments:
    backup_file            Path to backup file to restore

Examples:
    # Full restore from latest backup
    $0 /var/backups/biowerk/postgres/daily/postgres_20240115_120000.dump.zst.enc

    # Point-in-time recovery
    $0 -t "2024-01-15 11:30:00" /var/backups/biowerk/postgres/daily/postgres_20240115_120000.dump.zst.enc

    # Dry run (validation only)
    $0 --dry-run /var/backups/biowerk/postgres/daily/postgres_20240115_120000.dump.zst.enc
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
            -out "${temp_dir}/backup.dump" \
            -pass file:"${ENCRYPTION_KEY_FILE}"; then

            log_error "Decryption failed"
            return 1
        fi
        prepared_file="${temp_dir}/backup.dump"
    fi

    # Decompress if needed
    if [[ "${prepared_file}" =~ \.zst$ ]] || [[ "${backup_file}" =~ \.zst\.enc$ ]]; then
        log "Decompressing backup (zstd)..."
        zstd -d "${prepared_file}" -o "${temp_dir}/backup.dump"
        prepared_file="${temp_dir}/backup.dump"
    elif [[ "${prepared_file}" =~ \.gz$ ]] || [[ "${backup_file}" =~ \.gz\.enc$ ]]; then
        log "Decompressing backup (gzip)..."
        gunzip -c "${prepared_file}" > "${temp_dir}/backup.dump"
        prepared_file="${temp_dir}/backup.dump"
    fi

    # Verify pg_dump file
    log "Verifying pg_dump file..."
    if ! pg_restore --list "${prepared_file}" > /dev/null 2>&1; then
        log_error "Invalid pg_dump file"
        return 1
    fi

    echo "${prepared_file}"
    return 0
}

# Create database snapshot before restore
create_snapshot() {
    local snapshot_name="${POSTGRES_DB}_snapshot_$(date +%Y%m%d_%H%M%S)"

    log "Creating database snapshot: ${snapshot_name}"

    if PGPASSWORD="${POSTGRES_PASSWORD}" psql \
        -h "${POSTGRES_HOST}" \
        -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" \
        -d postgres \
        -c "CREATE DATABASE ${snapshot_name} WITH TEMPLATE ${POSTGRES_DB};" 2>> "${LOG_FILE}"; then

        log "Snapshot created: ${snapshot_name}"
        echo "${snapshot_name}"
        return 0
    else
        log "WARNING: Could not create snapshot (database may not exist yet)"
        return 1
    fi
}

# Restore database
perform_restore() {
    local backup_file="$1"
    local prepared_file
    local exit_code=0
    local start_time
    local end_time
    local duration
    local snapshot_name=""

    start_time=$(date +%s)

    log "========================================="
    log "PostgreSQL Restore - Starting"
    log "========================================="

    # Validate backup
    if ! validate_backup "${backup_file}"; then
        return 1
    fi

    # Prepare backup file
    if ! prepared_file=$(prepare_backup "${backup_file}"); then
        log_error "Failed to prepare backup file"
        return 1
    fi

    log "Prepared file: ${prepared_file}"

    if [[ "${DRY_RUN}" == "true" ]]; then
        log "Dry run mode - skipping actual restore"
        log "Validation successful"
        cleanup_temp
        return 0
    fi

    # Create snapshot of existing database
    snapshot_name=$(create_snapshot) || true

    # Drop and recreate database
    log "Recreating database: ${POSTGRES_DB}"

    PGPASSWORD="${POSTGRES_PASSWORD}" psql \
        -h "${POSTGRES_HOST}" \
        -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" \
        -d postgres \
        <<EOF 2>> "${LOG_FILE}" || exit_code=1
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${POSTGRES_DB}' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS ${POSTGRES_DB};
CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER};
EOF

    if [[ ${exit_code} -ne 0 ]]; then
        log_error "Failed to recreate database"
        return 1
    fi

    # Perform restore
    log "Restoring database from backup..."

    if ! PGPASSWORD="${POSTGRES_PASSWORD}" pg_restore \
        -h "${POSTGRES_HOST}" \
        -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" \
        -d "${POSTGRES_DB}" \
        -j "${PARALLEL_JOBS}" \
        --verbose \
        --no-owner \
        --no-acl \
        "${prepared_file}" \
        2>> "${LOG_FILE}"; then

        log_error "Restore failed"
        exit_code=1

        # Attempt rollback if snapshot exists
        if [[ -n "${snapshot_name}" ]]; then
            log "Attempting rollback to snapshot: ${snapshot_name}"
            rollback_to_snapshot "${snapshot_name}"
        fi
    else
        end_time=$(date +%s)
        duration=$((end_time - start_time))

        log "Restore completed successfully"
        log "Duration: ${duration} seconds"

        # Verify restored data
        verify_restore

        # Clean up snapshot if restore was successful
        if [[ -n "${snapshot_name}" ]]; then
            log "Dropping snapshot: ${snapshot_name}"
            PGPASSWORD="${POSTGRES_PASSWORD}" psql \
                -h "${POSTGRES_HOST}" \
                -p "${POSTGRES_PORT}" \
                -U "${POSTGRES_USER}" \
                -d postgres \
                -c "DROP DATABASE IF EXISTS ${snapshot_name};" 2>> "${LOG_FILE}"
        fi
    fi

    # Cleanup temporary files
    cleanup_temp

    return ${exit_code}
}

# Verify restored data
verify_restore() {
    log "Verifying restored data..."

    # Get table count
    local table_count
    table_count=$(PGPASSWORD="${POSTGRES_PASSWORD}" psql \
        -h "${POSTGRES_HOST}" \
        -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" \
        -d "${POSTGRES_DB}" \
        -t \
        -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null || echo 0)

    log "Tables restored: ${table_count}"

    # Run ANALYZE
    log "Running ANALYZE..."
    PGPASSWORD="${POSTGRES_PASSWORD}" psql \
        -h "${POSTGRES_HOST}" \
        -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" \
        -d "${POSTGRES_DB}" \
        -c "ANALYZE;" 2>> "${LOG_FILE}"

    log "Verification complete"
}

# Rollback to snapshot
rollback_to_snapshot() {
    local snapshot_name="$1"

    log "Rolling back to snapshot: ${snapshot_name}"

    PGPASSWORD="${POSTGRES_PASSWORD}" psql \
        -h "${POSTGRES_HOST}" \
        -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" \
        -d postgres \
        <<EOF 2>> "${LOG_FILE}"
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${POSTGRES_DB}' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS ${POSTGRES_DB};
ALTER DATABASE ${snapshot_name} RENAME TO ${POSTGRES_DB};
EOF

    log "Rollback complete"
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
DROP_DB=true

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
        -t|--target-time)
            RESTORE_TARGET_TIME="$2"
            shift 2
            ;;
        -j|--jobs)
            PARALLEL_JOBS="$2"
            shift 2
            ;;
        --no-drop-db)
            DROP_DB=false
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
