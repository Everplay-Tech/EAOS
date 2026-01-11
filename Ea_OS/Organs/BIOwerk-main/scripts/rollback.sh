#!/bin/bash
# ==============================================================================
# BIOwerk Rollback Script
# ==============================================================================
#
# This script rolls back BIOwerk services to a previous version
#
# Usage:
#   ./rollback.sh ENVIRONMENT [OPTIONS]
#
# Examples:
#   ./rollback.sh staging
#   ./rollback.sh production --emergency
#   ./rollback.sh production --to-tag abc1234
#
# ==============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# Default values
ENVIRONMENT=""
EMERGENCY=false
TO_TAG=""
AUTO_APPROVE=false
SERVICES=(mesh osteon myocyte synapse circadian nucleus chaperone gdpr)

# ==============================================================================
# Helper Functions
# ==============================================================================

log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] ✓${NC} $1"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ✗${NC} $1"
}

warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] ⚠${NC} $1"
}

critical() {
    echo -e "${MAGENTA}[$(date +'%Y-%m-%d %H:%M:%S')] 🚨${NC} $1"
}

usage() {
    cat << EOF
Usage: $0 ENVIRONMENT [OPTIONS]

Rollback BIOwerk services to a previous version

ARGUMENTS:
    ENVIRONMENT          Environment to rollback (staging or production)

OPTIONS:
    --emergency          Emergency rollback (skip confirmations)
    --to-tag TAG         Rollback to specific tag (default: previous version)
    --service SERVICE    Rollback only a specific service
    --auto-approve       Skip manual approval prompts
    --help               Show this help message

EXAMPLES:
    # Rollback staging to previous version
    $0 staging

    # Emergency rollback production
    $0 production --emergency

    # Rollback to specific version
    $0 production --to-tag v1.2.2

    # Rollback only mesh service
    $0 production --service mesh

EOF
    exit 1
}

confirm() {
    if [[ "$AUTO_APPROVE" == "true" ]] || [[ "$EMERGENCY" == "true" ]]; then
        warning "Auto-approved: $1"
        return 0
    fi

    read -p "$(echo -e "${YELLOW}$1 [yes/no]:${NC} ")" -r
    if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        error "Rollback cancelled by user"
        exit 1
    fi
}

# ==============================================================================
# Parse Arguments
# ==============================================================================

if [[ $# -lt 1 ]]; then
    error "Missing environment argument"
    usage
fi

ENVIRONMENT="$1"
shift

while [[ $# -gt 0 ]]; do
    case $1 in
        --emergency)
            EMERGENCY=true
            shift
            ;;
        --to-tag)
            TO_TAG="$2"
            shift 2
            ;;
        --service)
            SERVICES=("$2")
            shift 2
            ;;
        --auto-approve)
            AUTO_APPROVE=true
            shift
            ;;
        --help)
            usage
            ;;
        *)
            error "Unknown option: $1"
            usage
            ;;
    esac
done

# Validate environment
if [[ "$ENVIRONMENT" != "staging" ]] && [[ "$ENVIRONMENT" != "production" ]]; then
    error "Invalid environment: $ENVIRONMENT (must be staging or production)"
    exit 1
fi

# ==============================================================================
# Rollback Initialization
# ==============================================================================

if [[ "$EMERGENCY" == "true" ]]; then
    critical "═══════════════════════════════════════════════════════"
    critical "  EMERGENCY ROLLBACK INITIATED"
    critical "═══════════════════════════════════════════════════════"
else
    warning "═══════════════════════════════════════════════════════"
    warning "  ROLLBACK INITIATED"
    warning "═══════════════════════════════════════════════════════"
fi

echo ""
log "Environment: $ENVIRONMENT"
log "Emergency mode: $EMERGENCY"
log "Services: ${SERVICES[*]}"
echo ""

# Check required tools
for tool in kubectl docker curl jq; do
    if ! command -v $tool &> /dev/null; then
        error "$tool is required but not installed"
        exit 1
    fi
done

# ==============================================================================
# Determine Rollback Target
# ==============================================================================

log "Determining rollback target..."

if [[ -n "$TO_TAG" ]]; then
    ROLLBACK_TAG="$TO_TAG"
    log "  Using specified tag: $ROLLBACK_TAG"
else
    # Find the most recent successful deployment before current
    BACKUP_DIR=$(ls -td /var/backups/biowerk/pre-deployment-* 2>/dev/null | head -n 2 | tail -n 1)

    if [[ -z "$BACKUP_DIR" ]]; then
        error "No backup found to rollback to"
        error "Please specify a tag with --to-tag"
        exit 1
    fi

    log "  Found backup: $BACKUP_DIR"

    # Read rollback tags from backup
    if [[ -f "$BACKUP_DIR/rollback-tags.txt" ]]; then
        log "  Previous versions:"
        cat "$BACKUP_DIR/rollback-tags.txt"
        echo ""

        # Extract tag from first service (assuming all services use same tag)
        ROLLBACK_TAG=$(head -n 1 "$BACKUP_DIR/rollback-tags.txt" | cut -d: -f2)
    else
        error "Backup directory missing rollback information"
        exit 1
    fi
fi

success "Rollback target determined: $ROLLBACK_TAG"

# ==============================================================================
# Rollback Approval
# ==============================================================================

if [[ "$ENVIRONMENT" == "production" ]] && [[ "$EMERGENCY" != "true" ]]; then
    echo ""
    critical "═══════════════════════════════════════════════════════"
    critical "  PRODUCTION ROLLBACK APPROVAL REQUIRED"
    critical "═══════════════════════════════════════════════════════"
    echo ""

    warning "You are about to rollback PRODUCTION"
    warning "Current version will be replaced with: $ROLLBACK_TAG"
    echo ""

    confirm "Do you want to proceed with production rollback?"
fi

# ==============================================================================
# Pre-Rollback Backup
# ==============================================================================

log "Creating pre-rollback backup..."

BACKUP_DIR="/var/backups/biowerk/pre-rollback-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Save current state before rollback
if command -v kubectl &> /dev/null; then
    kubectl get deployments -n "biowerk-$ENVIRONMENT" -o yaml > "$BACKUP_DIR/deployments.yaml" 2>/dev/null || true
    kubectl get services -n "biowerk-$ENVIRONMENT" -o yaml > "$BACKUP_DIR/services.yaml" 2>/dev/null || true
fi

# Record current versions
for service in "${SERVICES[@]}"; do
    CURRENT_TAG=$(kubectl get deployment "$service" -n "biowerk-$ENVIRONMENT" -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null | awk -F: '{print $2}' || echo "unknown")
    echo "$service:$CURRENT_TAG" >> "$BACKUP_DIR/current-tags.txt"
done

success "Pre-rollback backup created: $BACKUP_DIR"

# ==============================================================================
# Execute Rollback
# ==============================================================================

log "Executing rollback to $ROLLBACK_TAG..."

FAILED_SERVICES=()

for service in "${SERVICES[@]}"; do
    log "Rolling back $service..."

    # Determine image name
    if [[ -n "$TO_TAG" ]]; then
        # Use specified tag for all services
        TARGET_IMAGE="ghcr.io/e-tech-playtech/biowerk-$service:$ROLLBACK_TAG"
    else
        # Read service-specific tag from backup
        SERVICE_TAG=$(grep "^$service:" "$BACKUP_DIR/../rollback-tags.txt" 2>/dev/null | cut -d: -f2 || echo "$ROLLBACK_TAG")
        TARGET_IMAGE="ghcr.io/e-tech-playtech/biowerk-$service:$SERVICE_TAG"
    fi

    log "  Target image: $TARGET_IMAGE"

    # Execute rollback based on orchestration platform
    if command -v kubectl &> /dev/null; then
        # Kubernetes rollback
        if kubectl set image "deployment/$service" "$service=$TARGET_IMAGE" -n "biowerk-$ENVIRONMENT"; then
            success "  $service image updated"

            # Wait for rollout
            log "  Waiting for rollout to complete..."
            if kubectl rollout status "deployment/$service" -n "biowerk-$ENVIRONMENT" --timeout=300s; then
                success "  $service rolled back successfully"
            else
                error "  $service rollback failed"
                FAILED_SERVICES+=("$service")
            fi
        else
            error "  Failed to update $service image"
            FAILED_SERVICES+=("$service")
        fi
    else
        # Docker Compose rollback (for local/development)
        warning "  Using Docker Compose rollback (development only)"
        # docker service update --image "$TARGET_IMAGE" "biowerk_${service}"
    fi
done

# ==============================================================================
# Post-Rollback Verification
# ==============================================================================

log "Verifying rollback..."

ALL_HEALTHY=true

for service in "${SERVICES[@]}"; do
    log "Checking $service health..."

    # Skip if rollback failed for this service
    if [[ " ${FAILED_SERVICES[*]} " =~ " ${service} " ]]; then
        error "  $service rollback failed - skipping health check"
        ALL_HEALTHY=false
        continue
    fi

    # Check pod status
    RETRIES=30
    for i in $(seq 1 $RETRIES); do
        READY=$(kubectl get deployment "$service" -n "biowerk-$ENVIRONMENT" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
        DESIRED=$(kubectl get deployment "$service" -n "biowerk-$ENVIRONMENT" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "1")

        if [[ "$READY" == "$DESIRED" ]] && [[ "$READY" != "0" ]]; then
            success "  $service is healthy ($READY/$DESIRED replicas)"
            break
        fi

        if [[ $i -eq $RETRIES ]]; then
            error "  $service health check timeout"
            ALL_HEALTHY=false
        fi

        sleep 10
    done
done

# ==============================================================================
# Rollback Results
# ==============================================================================

echo ""

if [[ "$ALL_HEALTHY" == "true" ]] && [[ ${#FAILED_SERVICES[@]} -eq 0 ]]; then
    success "═══════════════════════════════════════════════════════"
    success "  ROLLBACK COMPLETED SUCCESSFULLY"
    success "═══════════════════════════════════════════════════════"
    echo ""
    log "Rollback Details:"
    log "  Environment: $ENVIRONMENT"
    log "  Rolled back to: $ROLLBACK_TAG"
    log "  Services: ${SERVICES[*]}"
    log "  Backup: $BACKUP_DIR"
    echo ""
    log "Next Steps:"
    log "  1. Monitor application: https://grafana.biowerk.com"
    log "  2. Check logs: kubectl logs -n biowerk-$ENVIRONMENT"
    log "  3. Investigate root cause of issues"
    log "  4. Review deployment process"
    echo ""
    success "═══════════════════════════════════════════════════════"

    # Send success notification
    if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
        curl -X POST "$SLACK_WEBHOOK_URL" \
            -H 'Content-Type: application/json' \
            -d "{
                \"text\": \"✅ Rollback Successful - $ENVIRONMENT\",
                \"blocks\": [{
                    \"type\": \"section\",
                    \"text\": {
                        \"type\": \"mrkdwn\",
                        \"text\": \"*Rollback Successful* ✅\n\n*Environment:* $ENVIRONMENT\n*Rolled back to:* \`$ROLLBACK_TAG\`\n*Services:* ${SERVICES[*]}\"
                    }
                }]
            }" || true
    fi

    exit 0
else
    error "═══════════════════════════════════════════════════════"
    error "  ROLLBACK COMPLETED WITH ERRORS"
    error "═══════════════════════════════════════════════════════"
    echo ""
    error "Failed services: ${FAILED_SERVICES[*]}"
    echo ""
    error "IMMEDIATE ACTION REQUIRED:"
    error "  1. Check service logs: kubectl logs -n biowerk-$ENVIRONMENT"
    error "  2. Review events: kubectl get events -n biowerk-$ENVIRONMENT"
    error "  3. Contact on-call engineer"
    error "  4. Consider manual intervention"
    echo ""
    error "Backup location: $BACKUP_DIR"
    echo ""
    error "═══════════════════════════════════════════════════════"

    # Send failure notification
    if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
        curl -X POST "$SLACK_WEBHOOK_URL" \
            -H 'Content-Type: application/json' \
            -d "{
                \"text\": \"❌ Rollback Failed - $ENVIRONMENT - IMMEDIATE ACTION REQUIRED\",
                \"blocks\": [{
                    \"type\": \"section\",
                    \"text\": {
                        \"type\": \"mrkdwn\",
                        \"text\": \"*Rollback Failed* ❌\n\n*Environment:* $ENVIRONMENT\n*Failed services:* ${FAILED_SERVICES[*]}\n*Immediate action required*\"
                    }
                }]
            }" || true
    fi

    exit 1
fi
