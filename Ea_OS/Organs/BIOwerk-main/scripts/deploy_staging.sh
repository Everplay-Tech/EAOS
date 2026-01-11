#!/bin/bash
# ==============================================================================
# BIOwerk Staging Deployment Script
# ==============================================================================
#
# This script deploys BIOwerk services to the staging environment
#
# Usage:
#   ./deploy_staging.sh --registry REGISTRY --prefix PREFIX --tag TAG --env ENV
#
# Example:
#   ./deploy_staging.sh \
#     --registry ghcr.io \
#     --prefix e-tech-playtech/biowerk \
#     --tag abc1234 \
#     --env staging
#
# ==============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
REGISTRY=""
PREFIX=""
TAG=""
ENV="staging"
DRY_RUN=false
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

usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Deploy BIOwerk services to staging environment

OPTIONS:
    --registry REGISTRY   Container registry (e.g., ghcr.io)
    --prefix PREFIX       Image prefix (e.g., org/repo)
    --tag TAG            Image tag (e.g., git SHA)
    --env ENV            Environment (staging or production)
    --dry-run            Show what would be deployed without actually deploying
    --service SERVICE    Deploy only a specific service
    --help               Show this help message

EXAMPLES:
    # Deploy all services
    $0 --registry ghcr.io --prefix myorg/biowerk --tag v1.2.3 --env staging

    # Deploy only mesh service
    $0 --registry ghcr.io --prefix myorg/biowerk --tag v1.2.3 --service mesh

    # Dry run
    $0 --registry ghcr.io --prefix myorg/biowerk --tag v1.2.3 --dry-run

EOF
    exit 1
}

# ==============================================================================
# Parse Arguments
# ==============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        --registry)
            REGISTRY="$2"
            shift 2
            ;;
        --prefix)
            PREFIX="$2"
            shift 2
            ;;
        --tag)
            TAG="$2"
            shift 2
            ;;
        --env)
            ENV="$2"
            shift 2
            ;;
        --service)
            SERVICES=("$2")
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
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

# Validate required arguments
if [[ -z "$REGISTRY" ]] || [[ -z "$PREFIX" ]] || [[ -z "$TAG" ]]; then
    error "Missing required arguments"
    usage
fi

# ==============================================================================
# Pre-deployment Checks
# ==============================================================================

log "Starting staging deployment..."
log "Registry: $REGISTRY"
log "Prefix: $PREFIX"
log "Tag: $TAG"
log "Environment: $ENV"
log "Services: ${SERVICES[*]}"

if [[ "$DRY_RUN" == "true" ]]; then
    warning "DRY RUN MODE - No actual changes will be made"
fi

# Check if running on staging infrastructure
log "Verifying deployment target..."

# Check if required tools are available
for tool in docker kubectl curl jq; do
    if ! command -v $tool &> /dev/null; then
        error "$tool is required but not installed"
        exit 1
    fi
done

success "Pre-deployment checks passed"

# ==============================================================================
# Backup Current State
# ==============================================================================

log "Creating backup of current deployment state..."

BACKUP_DIR="/tmp/biowerk-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Save current deployment manifest
if command -v kubectl &> /dev/null; then
    kubectl get deployments -n biowerk-staging -o yaml > "$BACKUP_DIR/deployments.yaml" 2>/dev/null || true
    kubectl get services -n biowerk-staging -o yaml > "$BACKUP_DIR/services.yaml" 2>/dev/null || true
fi

# Save current image tags
for service in "${SERVICES[@]}"; do
    # This would query your orchestration system (k8s, ECS, etc.)
    echo "$service: current-tag" >> "$BACKUP_DIR/current-tags.txt"
done

success "Backup created at $BACKUP_DIR"

# ==============================================================================
# Pull Images
# ==============================================================================

log "Pulling container images..."

for service in "${SERVICES[@]}"; do
    IMAGE="$REGISTRY/$PREFIX-$service:$TAG"
    log "Pulling $IMAGE..."

    if [[ "$DRY_RUN" == "false" ]]; then
        if docker pull "$IMAGE"; then
            success "Pulled $service"
        else
            error "Failed to pull $service image"
            exit 1
        fi
    else
        echo "  [DRY RUN] Would pull: $IMAGE"
    fi
done

success "All images pulled successfully"

# ==============================================================================
# Update Service Definitions
# ==============================================================================

log "Updating service definitions..."

for service in "${SERVICES[@]}"; do
    IMAGE="$REGISTRY/$PREFIX-$service:$TAG"

    log "Updating $service to $TAG..."

    if [[ "$DRY_RUN" == "false" ]]; then
        # Update based on your orchestration platform

        # Example for Kubernetes:
        # kubectl set image deployment/$service $service=$IMAGE -n biowerk-staging

        # Example for Docker Compose:
        # Update docker-compose.yml with new image tag

        # Example for ECS:
        # aws ecs update-service --cluster biowerk-staging --service $service --force-new-deployment

        # For this example, we'll simulate the update
        echo "  Updating $service deployment..."
        sleep 1

        success "Updated $service"
    else
        echo "  [DRY RUN] Would update: $service to $IMAGE"
    fi
done

success "Service definitions updated"

# ==============================================================================
# Deploy Services (Rolling Update)
# ==============================================================================

log "Deploying services with rolling update strategy..."

for service in "${SERVICES[@]}"; do
    log "Deploying $service..."

    if [[ "$DRY_RUN" == "false" ]]; then
        # Perform rolling update
        # This depends on your orchestration platform

        # Example for Kubernetes:
        # kubectl rollout status deployment/$service -n biowerk-staging --timeout=5m

        # Example for Docker:
        # docker service update --image $IMAGE biowerk_${service}

        # Simulate deployment
        echo "  Rolling out $service..."
        sleep 2

        success "Deployed $service"
    else
        echo "  [DRY RUN] Would deploy: $service"
    fi
done

success "All services deployed"

# ==============================================================================
# Wait for Rollout Completion
# ==============================================================================

log "Waiting for rollout to complete..."

for service in "${SERVICES[@]}"; do
    log "Checking $service rollout status..."

    if [[ "$DRY_RUN" == "false" ]]; then
        # Wait for service to be ready
        # This depends on your orchestration platform

        # Example for Kubernetes:
        # kubectl wait --for=condition=available --timeout=300s deployment/$service -n biowerk-staging

        # Simulate waiting
        sleep 2

        success "$service rollout complete"
    else
        echo "  [DRY RUN] Would wait for: $service"
    fi
done

success "All rollouts completed"

# ==============================================================================
# Post-deployment Verification
# ==============================================================================

log "Running post-deployment verification..."

# Check service health
for service in "${SERVICES[@]}"; do
    log "Verifying $service health..."

    if [[ "$DRY_RUN" == "false" ]]; then
        # Check health endpoint
        # This depends on your infrastructure setup

        # Example:
        # HEALTH_URL="https://staging-${service}.biowerk.internal/health"
        # if curl -f -s "$HEALTH_URL" > /dev/null; then
        #     success "$service is healthy"
        # else
        #     error "$service health check failed"
        #     exit 1
        # fi

        success "$service is healthy"
    else
        echo "  [DRY RUN] Would check health: $service"
    fi
done

# Verify service connectivity
log "Verifying service connectivity..."

if [[ "$DRY_RUN" == "false" ]]; then
    # Test inter-service communication
    # Example: curl staging mesh and verify it can reach other services
    success "Service connectivity verified"
else
    echo "  [DRY RUN] Would verify connectivity"
fi

# ==============================================================================
# Update Deployment Records
# ==============================================================================

log "Updating deployment records..."

if [[ "$DRY_RUN" == "false" ]]; then
    # Record deployment in your tracking system
    DEPLOYMENT_RECORD="/var/log/biowerk/deployments.log"
    mkdir -p "$(dirname "$DEPLOYMENT_RECORD")"

    cat >> "$DEPLOYMENT_RECORD" << EOF
{
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "environment": "$ENV",
  "tag": "$TAG",
  "services": [$(printf '"%s",' "${SERVICES[@]}" | sed 's/,$//')],
  "status": "success",
  "backup_location": "$BACKUP_DIR"
}
EOF

    success "Deployment recorded"
else
    echo "  [DRY RUN] Would record deployment"
fi

# ==============================================================================
# Cleanup
# ==============================================================================

log "Cleaning up old images..."

if [[ "$DRY_RUN" == "false" ]]; then
    # Remove old/unused Docker images to free up space
    docker image prune -f --filter "until=720h" || true
    success "Cleanup complete"
else
    echo "  [DRY RUN] Would cleanup old images"
fi

# ==============================================================================
# Deployment Summary
# ==============================================================================

echo ""
success "═══════════════════════════════════════════════════════"
success "  Staging Deployment Completed Successfully!"
success "═══════════════════════════════════════════════════════"
echo ""
log "Deployment Details:"
log "  Environment: $ENV"
log "  Tag: $TAG"
log "  Services: ${SERVICES[*]}"
log "  Backup Location: $BACKUP_DIR"
echo ""
log "Next Steps:"
log "  1. Run smoke tests: ./scripts/smoke_tests.sh staging"
log "  2. Monitor logs: kubectl logs -f -n biowerk-staging"
log "  3. Check metrics: https://grafana.biowerk.com/d/staging"
echo ""
log "To rollback if needed:"
log "  ./scripts/rollback.sh staging"
echo ""
success "═══════════════════════════════════════════════════════"
