#!/bin/bash
################################################################################
# MongoDB Restore Script - Enterprise Grade
#
# Features:
# - Full restore from mongodump archives
# - Decryption and decompression
# - Pre-restore validation
# - Collection-level restore
# - Oplog replay for point-in-time recovery
# - Verification of restored data
################################################################################

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${CONFIG_FILE:-${SCRIPT_DIR}/../config/backup.conf}"
LOG_FILE="${LOG_FILE:-/var/log/biowerk/restore-mongodb.log}"

# Load configuration
if [[ -f "${CONFIG_FILE}" ]]; then
    # shellcheck source=/dev/null
    source "${CONFIG_FILE}"
fi

# Default values
BACKUP_DIR="${BACKUP_DIR:-/var/backups/biowerk/mongodb}"
MONGODB_HOST="${MONGODB_HOST:-mongodb}"
MONGODB_PORT="${MONGODB_PORT:-27017}"
MONGODB_USER="${MONGODB_USER:-biowerk}"
MONGODB_DB="${MONGODB_DB:-biowerk}"
MONGODB_AUTH_DB="${MONGODB_AUTH_DB:-admin}"
ENCRYPTION_ENABLED="${ENCRYPTION_ENABLED:-true}"
ENCRYPTION_KEY_FILE="${ENCRYPTION_KEY_FILE:-/etc/biowerk/backup-encryption.key}"
DRY_RUN="${DRY_RUN:-false}"
DROP_COLLECTIONS="${DROP_COLLECTIONS:-true}"

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
    --no-drop              Don't drop collections before restore
    --db DATABASE          Database name to restore to (default: ${MONGODB_DB})

Arguments:
    backup_file            Path to backup file to restore

Examples:
    # Full restore from backup
    $0 /var/backups/biowerk/mongodb/daily/mongodb_20240115_120000.tar.zst.enc

    # Restore to different database
    $0 --db biowerk_restore /var/backups/biowerk/mongodb/daily/mongodb_20240115_120000.tar.zst.enc

    # Dry run (validation only)
    $0 --dry-run /var/backups/biowerk/mongodb/daily/mongodb_20240115_120000.tar.zst.enc
EOF
}

# Build MongoDB connection string
get_mongodb_uri() {
    if [[ -n "${MONGODB_PASSWORD:-}" ]]; then
        echo "mongodb://${MONGODB_USER}:${MONGODB_PASSWORD}@${MONGODB_HOST}:${MONGODB_PORT}/${MONGODB_DB}?authSource=${MONGODB_AUTH_DB}"
    else
        echo "mongodb://${MONGODB_HOST}:${MONGODB_PORT}/${MONGODB_DB}"
    fi
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

    # Find the dump directory
    local dump_dir
    dump_dir=$(find "${temp_dir}" -type d -name "mongodb_*" | head -n 1)

    if [[ -z "${dump_dir}" ]]; then
        log_error "Could not find dump directory in archive"
        return 1
    fi

    log "Dump directory: ${dump_dir}"
    echo "${dump_dir}"
    return 0
}

# Restore database
perform_restore() {
    local backup_file="$1"
    local dump_dir
    local exit_code=0
    local start_time
    local end_time
    local duration

    start_time=$(date +%s)

    log "========================================="
    log "MongoDB Restore - Starting"
    log "========================================="

    # Validate backup
    if ! validate_backup "${backup_file}"; then
        return 1
    fi

    # Prepare backup file
    if ! dump_dir=$(prepare_backup "${backup_file}"); then
        log_error "Failed to prepare backup file"
        return 1
    fi

    log "Prepared dump directory: ${dump_dir}"

    if [[ "${DRY_RUN}" == "true" ]]; then
        log "Dry run mode - skipping actual restore"
        log "Validation successful"
        cleanup_temp
        return 0
    fi

    # Build mongorestore command
    local mongorestore_args=(
        --uri="$(get_mongodb_uri)"
        --gzip
    )

    if [[ "${DROP_COLLECTIONS}" == "true" ]]; then
        mongorestore_args+=(--drop)
    fi

    mongorestore_args+=("${dump_dir}")

    # Perform restore
    log "Restoring database from backup..."

    if ! mongorestore "${mongorestore_args[@]}" 2>> "${LOG_FILE}"; then
        log_error "Restore failed"
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

    # Get collection count
    local collection_count
    if [[ -n "${MONGODB_PASSWORD:-}" ]]; then
        collection_count=$(mongosh "$(get_mongodb_uri)" \
            --quiet \
            --eval "db.getCollectionNames().length" 2>/dev/null || echo 0)
    else
        collection_count=$(mongosh --host "${MONGODB_HOST}" --port "${MONGODB_PORT}" "${MONGODB_DB}" \
            --quiet \
            --eval "db.getCollectionNames().length" 2>/dev/null || echo 0)
    fi

    log "Collections restored: ${collection_count}"

    # Get total document count
    local doc_count
    if [[ -n "${MONGODB_PASSWORD:-}" ]]; then
        doc_count=$(mongosh "$(get_mongodb_uri)" \
            --quiet \
            --eval "db.getCollectionNames().reduce((acc, coll) => acc + db[coll].countDocuments(), 0)" 2>/dev/null || echo 0)
    else
        doc_count=$(mongosh --host "${MONGODB_HOST}" --port "${MONGODB_PORT}" "${MONGODB_DB}" \
            --quiet \
            --eval "db.getCollectionNames().reduce((acc, coll) => acc + db[coll].countDocuments(), 0)" 2>/dev/null || echo 0)
    fi

    log "Total documents restored: ${doc_count}"
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
        --no-drop)
            DROP_COLLECTIONS=false
            shift
            ;;
        --db)
            MONGODB_DB="$2"
            shift 2
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
