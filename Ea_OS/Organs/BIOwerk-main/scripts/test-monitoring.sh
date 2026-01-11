#!/bin/bash
# Test script for BIOwerk monitoring and alerting infrastructure
# This script verifies that all monitoring components are working correctly

set -e

echo "=================================================="
echo "BIOwerk Monitoring & Alerting Test Suite"
echo "=================================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

# Helper functions
pass() {
    echo -e "${GREEN}✓${NC} $1"
    ((TESTS_PASSED++))
}

fail() {
    echo -e "${RED}✗${NC} $1"
    ((TESTS_FAILED++))
}

warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

info() {
    echo -e "  $1"
}

# Test 1: Check Docker containers are running
echo "Test 1: Checking monitoring containers..."
EXPECTED_CONTAINERS=(
    "biowerk-loki"
    "biowerk-promtail"
    "biowerk-prometheus"
    "biowerk-alertmanager"
    "biowerk-grafana"
)

for container in "${EXPECTED_CONTAINERS[@]}"; do
    if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        pass "Container ${container} is running"
    else
        fail "Container ${container} is NOT running"
    fi
done
echo ""

# Test 2: Check health endpoints
echo "Test 2: Checking service health endpoints..."

# Loki
if curl -sf http://localhost:3100/ready > /dev/null 2>&1; then
    pass "Loki health check"
else
    fail "Loki health check failed"
fi

# Prometheus
if curl -sf http://localhost:9090/-/healthy > /dev/null 2>&1; then
    pass "Prometheus health check"
else
    fail "Prometheus health check failed"
fi

# Alertmanager
if curl -sf http://localhost:9093/-/healthy > /dev/null 2>&1; then
    pass "Alertmanager health check"
else
    fail "Alertmanager health check failed"
fi

# Grafana
if curl -sf http://localhost:3000/api/health > /dev/null 2>&1; then
    pass "Grafana health check"
else
    fail "Grafana health check failed"
fi
echo ""

# Test 3: Check Prometheus targets
echo "Test 3: Checking Prometheus targets..."
TARGETS_UP=$(curl -s http://localhost:9090/api/v1/targets 2>/dev/null | \
    jq -r '.data.activeTargets[] | select(.health == "up") | .labels.job' | wc -l)

if [ "$TARGETS_UP" -gt 5 ]; then
    pass "Prometheus has ${TARGETS_UP} healthy targets"
else
    warn "Only ${TARGETS_UP} targets are up (expected more)"
fi

# List unhealthy targets
UNHEALTHY=$(curl -s http://localhost:9090/api/v1/targets 2>/dev/null | \
    jq -r '.data.activeTargets[] | select(.health != "up") | .labels.job' 2>/dev/null)

if [ -n "$UNHEALTHY" ]; then
    warn "Unhealthy targets detected:"
    echo "$UNHEALTHY" | while read -r target; do
        info "  - $target"
    done
fi
echo ""

# Test 4: Check if metrics are being collected
echo "Test 4: Checking metric collection..."

# Query for basic metrics
METRICS_QUERY='up{job=~"biowerk-.*"}'
METRICS_RESULT=$(curl -s "http://localhost:9090/api/v1/query?query=${METRICS_QUERY}" 2>/dev/null | \
    jq -r '.data.result | length' 2>/dev/null || echo "0")

if [ "$METRICS_RESULT" -gt 0 ]; then
    pass "Metrics are being collected (${METRICS_RESULT} services found)"
else
    fail "No metrics found for BIOwerk services"
fi
echo ""

# Test 5: Check Loki log ingestion
echo "Test 5: Checking log ingestion..."

# Query Loki for recent logs
LOGS_QUERY='{service_name=~".+"}'
LOGS_RESULT=$(curl -s -G "http://localhost:3100/loki/api/v1/query" \
    --data-urlencode "query=${LOGS_QUERY}" \
    --data-urlencode 'limit=1' 2>/dev/null | \
    jq -r '.data.result | length' 2>/dev/null || echo "0")

if [ "$LOGS_RESULT" -gt 0 ]; then
    pass "Logs are being ingested into Loki"

    # Get service names
    SERVICES=$(curl -s "http://localhost:3100/loki/api/v1/label/service_name/values" 2>/dev/null | \
        jq -r '.data[]' 2>/dev/null | tr '\n' ',' | sed 's/,$//')
    info "Services logging: ${SERVICES}"
else
    fail "No logs found in Loki"
fi
echo ""

# Test 6: Check alert rules are loaded
echo "Test 6: Checking alert rules..."

ALERT_GROUPS=$(curl -s http://localhost:9090/api/v1/rules 2>/dev/null | \
    jq -r '.data.groups | length' 2>/dev/null || echo "0")

if [ "$ALERT_GROUPS" -gt 0 ]; then
    pass "Alert rules are loaded (${ALERT_GROUPS} groups)"

    # List alert groups
    curl -s http://localhost:9090/api/v1/rules 2>/dev/null | \
        jq -r '.data.groups[] | "\(.name): \(.rules | length) rules"' 2>/dev/null | \
        while read -r line; do
            info "$line"
        done
else
    fail "No alert rules loaded"
fi
echo ""

# Test 7: Check Grafana datasources
echo "Test 7: Checking Grafana datasources..."

# Note: This requires Grafana API credentials
GRAFANA_USER="${GRAFANA_ADMIN_USER:-admin}"
GRAFANA_PASS="${GRAFANA_ADMIN_PASSWORD:-admin}"

DATASOURCES=$(curl -s -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
    http://localhost:3000/api/datasources 2>/dev/null | \
    jq -r 'length' 2>/dev/null || echo "0")

if [ "$DATASOURCES" -gt 0 ]; then
    pass "Grafana has ${DATASOURCES} datasource(s) configured"

    # List datasources
    curl -s -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
        http://localhost:3000/api/datasources 2>/dev/null | \
        jq -r '.[] | "\(.name) (\(.type))"' 2>/dev/null | \
        while read -r line; do
            info "$line"
        done
else
    warn "Could not verify Grafana datasources (check credentials)"
fi
echo ""

# Test 8: Send test alert
echo "Test 8: Sending test alert to Alertmanager..."

TEST_ALERT_RESPONSE=$(curl -s -X POST http://localhost:9093/api/v1/alerts \
    -H "Content-Type: application/json" \
    -d '[{
        "labels": {
            "alertname": "MonitoringTestAlert",
            "severity": "info",
            "service": "test-script",
            "category": "test"
        },
        "annotations": {
            "summary": "Test alert from monitoring test script",
            "description": "This is an automated test alert to verify the alerting pipeline"
        },
        "startsAt": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
        "endsAt": "'$(date -u -d '+2 minutes' +%Y-%m-%dT%H:%M:%SZ)'"
    }]' 2>&1)

if echo "$TEST_ALERT_RESPONSE" | grep -q "success"; then
    pass "Test alert sent successfully"
    info "Check Alertmanager UI: http://localhost:9093/#/alerts"
else
    warn "Could not send test alert"
fi
echo ""

# Test 9: Check exporter metrics
echo "Test 9: Checking infrastructure exporters..."

EXPORTERS=(
    "postgres-exporter:9187"
    "redis-exporter:9121"
    "mongodb-exporter:9216"
    "node-exporter:9100"
)

for exporter in "${EXPORTERS[@]}"; do
    NAME=$(echo "$exporter" | cut -d: -f1)
    PORT=$(echo "$exporter" | cut -d: -f2)

    if curl -sf "http://localhost:${PORT}/metrics" > /dev/null 2>&1; then
        pass "${NAME} is exposing metrics"
    else
        warn "${NAME} metrics endpoint not accessible"
    fi
done
echo ""

# Test 10: Verify JSON log format
echo "Test 10: Checking structured logging format..."

# Check if mesh service is using JSON logs
if docker logs biowerk-mesh --tail 10 2>&1 | grep -q '"timestamp".*"level".*"message"'; then
    pass "Services are using structured JSON logging"
else
    warn "Could not verify JSON log format (services may not be running)"
fi
echo ""

# Summary
echo "=================================================="
echo "Test Results Summary"
echo "=================================================="
echo -e "Tests Passed: ${GREEN}${TESTS_PASSED}${NC}"
echo -e "Tests Failed: ${RED}${TESTS_FAILED}${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}All critical tests passed!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Access Grafana: http://localhost:3000 (admin/admin)"
    echo "  2. View Prometheus: http://localhost:9090"
    echo "  3. Check Alertmanager: http://localhost:9093"
    echo "  4. Configure PagerDuty and Slack webhooks in .env"
    echo "  5. Review documentation: docs/MONITORING_AND_ALERTING.md"
    echo ""
    exit 0
else
    echo -e "${RED}Some tests failed. Please review the output above.${NC}"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Check service logs: docker-compose logs <service>"
    echo "  2. Verify all services are running: docker-compose ps"
    echo "  3. Review configuration files in observability/"
    echo "  4. Consult docs/MONITORING_AND_ALERTING.md"
    echo ""
    exit 1
fi
