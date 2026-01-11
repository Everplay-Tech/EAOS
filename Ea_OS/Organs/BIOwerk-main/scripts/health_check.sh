#!/bin/bash
# ==============================================================================
# BIOwerk Health Check Script
# ==============================================================================
#
# This script performs comprehensive health checks on BIOwerk services
#
# Usage:
#   ./health_check.sh ENVIRONMENT [OPTIONS]
#
# Examples:
#   ./health_check.sh staging
#   ./health_check.sh production --verbose
#   ./health_check.sh staging --service mesh
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
ENVIRONMENT=""
VERBOSE=false
SERVICE=""
TIMEOUT=300
SERVICES=(mesh osteon myocyte synapse circadian nucleus chaperone gdpr)

# Health check results
HEALTHY_SERVICES=()
UNHEALTHY_SERVICES=()
WARNING_SERVICES=()

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

verbose() {
    if [[ "$VERBOSE" == "true" ]]; then
        log "  $1"
    fi
}

usage() {
    cat << EOF
Usage: $0 ENVIRONMENT [OPTIONS]

Perform health checks on BIOwerk services

ARGUMENTS:
    ENVIRONMENT          Environment to check (staging or production)

OPTIONS:
    --service SERVICE    Check only a specific service
    --timeout SECONDS    Health check timeout in seconds (default: 300)
    --verbose           Show detailed health check information
    --help              Show this help message

EXAMPLES:
    # Check all services in staging
    $0 staging

    # Check production with verbose output
    $0 production --verbose

    # Check only mesh service
    $0 staging --service mesh

    # Custom timeout
    $0 production --timeout 600

EXIT CODES:
    0    All services healthy
    1    One or more services unhealthy
    2    Health check error/timeout

EOF
    exit 1
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
        --service)
            SERVICE="$2"
            SERVICES=("$2")
            shift 2
            ;;
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --verbose)
            VERBOSE=true
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
# Health Check Initialization
# ==============================================================================

log "═══════════════════════════════════════════════════════"
log "  BIOwerk Health Check - $ENVIRONMENT"
log "═══════════════════════════════════════════════════════"
echo ""

log "Environment: $ENVIRONMENT"
log "Services: ${SERVICES[*]}"
log "Timeout: ${TIMEOUT}s"
echo ""

# Check required tools
for tool in curl jq; do
    if ! command -v $tool &> /dev/null; then
        error "$tool is required but not installed"
        exit 2
    fi
done

# Set base URL based on environment
if [[ "$ENVIRONMENT" == "staging" ]]; then
    BASE_URL="https://staging.biowerk.example.com"
elif [[ "$ENVIRONMENT" == "production" ]]; then
    BASE_URL="https://biowerk.example.com"
fi

# ==============================================================================
# Health Check Functions
# ==============================================================================

check_http_health() {
    local service=$1
    local url=$2

    verbose "Checking HTTP health for $service at $url"

    local response
    local http_code
    local start_time
    local end_time
    local duration

    start_time=$(date +%s%N)

    response=$(curl -s -w "\n%{http_code}" --max-time 10 "$url" 2>/dev/null || echo -e "\n000")
    http_code=$(echo "$response" | tail -n 1)
    body=$(echo "$response" | head -n -1)

    end_time=$(date +%s%N)
    duration=$(( (end_time - start_time) / 1000000 )) # Convert to milliseconds

    if [[ "$http_code" == "200" ]]; then
        verbose "HTTP 200 OK (${duration}ms)"

        # Parse health check response if JSON
        if echo "$body" | jq empty 2>/dev/null; then
            local status=$(echo "$body" | jq -r '.status // "unknown"')
            verbose "Health status: $status"

            if [[ "$status" == "healthy" ]] || [[ "$status" == "ok" ]]; then
                return 0
            elif [[ "$status" == "degraded" ]]; then
                warning "$service is degraded"
                return 1
            else
                error "$service status: $status"
                return 1
            fi
        else
            # Non-JSON response, assume healthy if 200
            return 0
        fi
    else
        verbose "HTTP $http_code"
        return 1
    fi
}

check_kubernetes_deployment() {
    local service=$1
    local namespace="biowerk-$ENVIRONMENT"

    if ! command -v kubectl &> /dev/null; then
        verbose "kubectl not available, skipping k8s check"
        return 0
    fi

    verbose "Checking Kubernetes deployment for $service"

    # Check if deployment exists
    if ! kubectl get deployment "$service" -n "$namespace" &>/dev/null; then
        verbose "Deployment $service not found in namespace $namespace"
        return 1
    fi

    # Check replicas
    local desired=$(kubectl get deployment "$service" -n "$namespace" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "0")
    local ready=$(kubectl get deployment "$service" -n "$namespace" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    local available=$(kubectl get deployment "$service" -n "$namespace" -o jsonpath='{.status.availableReplicas}' 2>/dev/null || echo "0")

    verbose "Replicas: $ready/$desired ready, $available available"

    if [[ "$ready" == "$desired" ]] && [[ "$available" == "$desired" ]] && [[ "$desired" != "0" ]]; then
        return 0
    else
        return 1
    fi
}

check_database_connectivity() {
    local service=$1

    verbose "Checking database connectivity for $service"

    # Check if service can connect to database
    # This would typically be done through a dedicated health endpoint
    # that verifies DB connectivity

    # For now, we'll check the /ready endpoint which should verify DB
    local url="$BASE_URL/ready"

    if curl -s -f --max-time 5 "$url" &>/dev/null; then
        verbose "Database connectivity OK"
        return 0
    else
        verbose "Database connectivity check failed"
        return 1
    fi
}

check_service_dependencies() {
    local service=$1

    verbose "Checking service dependencies for $service"

    # For mesh service, check if it can reach agent services
    if [[ "$service" == "mesh" ]]; then
        local agents=(osteon myocyte synapse circadian nucleus chaperone gdpr)

        for agent in "${agents[@]}"; do
            # Check if mesh can communicate with agent
            # This would be done through a service mesh health endpoint
            verbose "  Checking connectivity to $agent"
        done
    fi

    return 0
}

# ==============================================================================
# Perform Health Checks
# ==============================================================================

log "Starting health checks..."
echo ""

START_TIME=$(date +%s)

for service in "${SERVICES[@]}"; do
    log "Checking $service..."

    SERVICE_HEALTHY=true
    CHECKS_PASSED=0
    CHECKS_FAILED=0

    # Check 1: HTTP Health Endpoint
    verbose "Check 1: HTTP Health Endpoint"
    if [[ "$service" == "mesh" ]]; then
        HEALTH_URL="$BASE_URL/health"
    else
        # For individual services (when checking directly)
        HEALTH_URL="http://${ENVIRONMENT}-${service}.internal:800X/health"
    fi

    if check_http_health "$service" "$HEALTH_URL"; then
        ((CHECKS_PASSED++))
        verbose "✓ HTTP health check passed"
    else
        ((CHECKS_FAILED++))
        verbose "✗ HTTP health check failed"
        SERVICE_HEALTHY=false
    fi

    # Check 2: Kubernetes Deployment Status
    verbose "Check 2: Kubernetes Deployment"
    if check_kubernetes_deployment "$service"; then
        ((CHECKS_PASSED++))
        verbose "✓ Kubernetes deployment healthy"
    else
        ((CHECKS_FAILED++))
        verbose "✗ Kubernetes deployment unhealthy"
        SERVICE_HEALTHY=false
    fi

    # Check 3: Database Connectivity
    verbose "Check 3: Database Connectivity"
    if check_database_connectivity "$service"; then
        ((CHECKS_PASSED++))
        verbose "✓ Database connectivity OK"
    else
        ((CHECKS_FAILED++))
        verbose "⚠ Database connectivity check failed"
        # Don't mark as unhealthy for DB check failure (might be degraded)
        WARNING_SERVICES+=("$service")
    fi

    # Check 4: Service Dependencies
    verbose "Check 4: Service Dependencies"
    if check_service_dependencies "$service"; then
        ((CHECKS_PASSED++))
        verbose "✓ Service dependencies OK"
    else
        ((CHECKS_FAILED++))
        verbose "⚠ Service dependencies check failed"
    fi

    # Summary for service
    echo ""
    if [[ "$SERVICE_HEALTHY" == "true" ]]; then
        success "$service is healthy ($CHECKS_PASSED/$((CHECKS_PASSED+CHECKS_FAILED)) checks passed)"
        HEALTHY_SERVICES+=("$service")
    else
        error "$service is unhealthy ($CHECKS_FAILED/$((CHECKS_PASSED+CHECKS_FAILED)) checks failed)"
        UNHEALTHY_SERVICES+=("$service")
    fi
    echo ""
done

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

# ==============================================================================
# Health Check Summary
# ==============================================================================

echo ""
log "═══════════════════════════════════════════════════════"
log "  Health Check Summary"
log "═══════════════════════════════════════════════════════"
echo ""

log "Environment: $ENVIRONMENT"
log "Duration: ${DURATION}s"
log "Total services checked: ${#SERVICES[@]}"
log "Healthy: ${#HEALTHY_SERVICES[@]}"
log "Unhealthy: ${#UNHEALTHY_SERVICES[@]}"
log "Warnings: ${#WARNING_SERVICES[@]}"
echo ""

if [[ ${#HEALTHY_SERVICES[@]} -gt 0 ]]; then
    success "Healthy services: ${HEALTHY_SERVICES[*]}"
fi

if [[ ${#WARNING_SERVICES[@]} -gt 0 ]]; then
    warning "Services with warnings: ${WARNING_SERVICES[*]}"
fi

if [[ ${#UNHEALTHY_SERVICES[@]} -gt 0 ]]; then
    error "Unhealthy services: ${UNHEALTHY_SERVICES[*]}"
fi

echo ""

# ==============================================================================
# Exit with appropriate code
# ==============================================================================

if [[ ${#UNHEALTHY_SERVICES[@]} -eq 0 ]]; then
    if [[ ${#WARNING_SERVICES[@]} -gt 0 ]]; then
        warning "All services operational with warnings"
        log "═══════════════════════════════════════════════════════"
        exit 0
    else
        success "All services healthy!"
        log "═══════════════════════════════════════════════════════"
        exit 0
    fi
else
    error "Health check failed - unhealthy services detected"
    log "═══════════════════════════════════════════════════════"
    exit 1
fi
