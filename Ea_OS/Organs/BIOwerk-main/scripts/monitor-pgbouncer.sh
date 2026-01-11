#!/bin/bash
# ============================================================================
# PgBouncer Monitoring Script for BIOwerk
# Displays real-time statistics and health metrics
# ============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
PGBOUNCER_HOST=${PGBOUNCER_HOST:-pgbouncer}
PGBOUNCER_PORT=${PGBOUNCER_PORT:-6432}
PGBOUNCER_USER=${POSTGRES_USER:-biowerk}
PGBOUNCER_PASSWORD=${POSTGRES_PASSWORD:-biowerk_dev_password}
REFRESH_INTERVAL=${REFRESH_INTERVAL:-5}

# ============================================================================
# Helper Functions
# ============================================================================

print_header() {
    echo -e "${CYAN}============================================================================${NC}"
    echo -e "${CYAN}$1${NC}"
    echo -e "${CYAN}============================================================================${NC}"
}

print_section() {
    echo -e "\n${BLUE}━━━ $1 ━━━${NC}"
}

run_query() {
    local query=$1
    PGPASSWORD=$PGBOUNCER_PASSWORD psql -h $PGBOUNCER_HOST -p $PGBOUNCER_PORT -U $PGBOUNCER_USER -d pgbouncer -t -A -c "$query" 2>/dev/null || echo "N/A"
}

# ============================================================================
# Monitoring Functions
# ============================================================================

show_version() {
    print_section "PgBouncer Version"
    run_query "SHOW VERSION;" | sed 's/|/ /g'
}

show_stats() {
    print_section "Database Statistics"
    echo -e "${YELLOW}Database statistics (queries, data transfer, averages):${NC}"
    run_query "SHOW STATS;" | column -t -s '|' | head -10
}

show_pools() {
    print_section "Connection Pools"
    echo -e "${YELLOW}Current pool status:${NC}"

    # Get pool statistics
    local pool_data=$(run_query "SHOW POOLS;")

    # Display header and data
    echo "$pool_data" | column -t -s '|' | head -10

    # Parse and show alerts
    echo ""
    local cl_waiting=$(echo "$pool_data" | grep biowerk | head -1 | cut -d'|' -f4)
    local sv_active=$(echo "$pool_data" | grep biowerk | head -1 | cut -d'|' -f6)
    local sv_idle=$(echo "$pool_data" | grep biowerk | head -1 | cut -d'|' -f7)
    local maxwait=$(echo "$pool_data" | grep biowerk | head -1 | cut -d'|' -f10)

    if [ ! -z "$cl_waiting" ] && [ "$cl_waiting" -gt 0 ]; then
        echo -e "${RED}⚠ WARNING: $cl_waiting clients waiting for connections!${NC}"
        echo -e "${YELLOW}  Consider increasing default_pool_size or max_db_connections${NC}"
    fi

    if [ ! -z "$maxwait" ] && [ "$maxwait" -gt 5 ]; then
        echo -e "${RED}⚠ WARNING: Max wait time is ${maxwait}s (high!)${NC}"
        echo -e "${YELLOW}  Pool may be undersized for current load${NC}"
    fi

    if [ ! -z "$sv_idle" ] && [ "$sv_idle" -gt 15 ]; then
        echo -e "${YELLOW}ℹ INFO: $sv_idle idle server connections${NC}"
        echo -e "${YELLOW}  Consider reducing default_pool_size to free resources${NC}"
    fi
}

show_clients() {
    print_section "Client Connections"
    echo -e "${YELLOW}Active client connections (limited to 20):${NC}"
    run_query "SHOW CLIENTS LIMIT 20;" | column -t -s '|' | head -21

    # Count total clients
    local total_clients=$(run_query "SHOW CLIENTS;" | wc -l)
    echo -e "\n${CYAN}Total clients: $total_clients${NC}"
}

show_servers() {
    print_section "Server Connections"
    echo -e "${YELLOW}PostgreSQL backend connections:${NC}"
    run_query "SHOW SERVERS;" | column -t -s '|' | head -15

    # Count by state
    local active=$(run_query "SHOW SERVERS;" | grep -c "active" || echo 0)
    local idle=$(run_query "SHOW SERVERS;" | grep -c "idle" || echo 0)
    echo -e "\n${GREEN}Active: $active${NC} | ${BLUE}Idle: $idle${NC}"
}

show_databases() {
    print_section "Configured Databases"
    run_query "SHOW DATABASES;" | column -t -s '|'
}

show_config() {
    print_section "Key Configuration Parameters"
    echo -e "${YELLOW}Important PgBouncer settings:${NC}"

    local pool_mode=$(run_query "SHOW pool_mode;" | tail -1)
    local max_client=$(run_query "SHOW max_client_conn;" | tail -1)
    local default_pool=$(run_query "SHOW default_pool_size;" | tail -1)
    local min_pool=$(run_query "SHOW min_pool_size;" | tail -1)
    local reserve_pool=$(run_query "SHOW reserve_pool_size;" | tail -1)
    local max_db=$(run_query "SHOW max_db_connections;" | tail -1)

    echo -e "Pool Mode:              ${GREEN}$pool_mode${NC}"
    echo -e "Max Client Connections: ${GREEN}$max_client${NC}"
    echo -e "Default Pool Size:      ${GREEN}$default_pool${NC}"
    echo -e "Min Pool Size:          ${GREEN}$min_pool${NC}"
    echo -e "Reserve Pool Size:      ${GREEN}$reserve_pool${NC}"
    echo -e "Max DB Connections:     ${GREEN}$max_db${NC}"
}

show_summary() {
    print_section "Health Summary"

    # Get key metrics
    local pool_data=$(run_query "SHOW POOLS;")
    local cl_active=$(echo "$pool_data" | grep biowerk | head -1 | cut -d'|' -f3 || echo 0)
    local cl_waiting=$(echo "$pool_data" | grep biowerk | head -1 | cut -d'|' -f4 || echo 0)
    local sv_active=$(echo "$pool_data" | grep biowerk | head -1 | cut -d'|' -f6 || echo 0)
    local sv_idle=$(echo "$pool_data" | grep biowerk | head -1 | cut -d'|' -f7 || echo 0)
    local maxwait=$(echo "$pool_data" | grep biowerk | head -1 | cut -d'|' -f10 || echo 0)

    # Calculate health score
    local health="HEALTHY"
    local color=$GREEN

    if [ "$cl_waiting" -gt 5 ] || [ "$maxwait" -gt 10 ]; then
        health="CRITICAL"
        color=$RED
    elif [ "$cl_waiting" -gt 0 ] || [ "$maxwait" -gt 5 ]; then
        health="WARNING"
        color=$YELLOW
    fi

    echo -e "Status:             ${color}${health}${NC}"
    echo -e "Active Clients:     ${GREEN}$cl_active${NC}"
    echo -e "Waiting Clients:    ${YELLOW}$cl_waiting${NC}"
    echo -e "Active Servers:     ${GREEN}$sv_active${NC}"
    echo -e "Idle Servers:       ${BLUE}$sv_idle${NC}"
    echo -e "Max Wait Time:      ${YELLOW}${maxwait}s${NC}"

    # Calculate connection efficiency
    local total_server=$((sv_active + sv_idle))
    if [ $total_server -gt 0 ]; then
        local efficiency=$((sv_active * 100 / total_server))
        echo -e "Pool Efficiency:    ${CYAN}${efficiency}%${NC} (active/total servers)"
    fi
}

show_dns() {
    print_section "DNS Cache"
    run_query "SHOW DNS_HOSTS;" | column -t -s '|' || echo "No DNS cache entries"
}

# ============================================================================
# Main Menu
# ============================================================================

show_menu() {
    clear
    print_header "BIOwerk PgBouncer Monitor - $(date '+%Y-%m-%d %H:%M:%S')"

    echo ""
    echo "Options:"
    echo "  1) Full Dashboard (default)"
    echo "  2) Summary Only"
    echo "  3) Pools Only"
    echo "  4) Clients Only"
    echo "  5) Servers Only"
    echo "  6) Stats Only"
    echo "  7) Configuration"
    echo "  w) Watch Mode (auto-refresh every ${REFRESH_INTERVAL}s)"
    echo "  q) Quit"
    echo ""
    echo -n "Select option [1-7/w/q]: "
}

full_dashboard() {
    clear
    print_header "BIOwerk PgBouncer Monitor - $(date '+%Y-%m-%d %H:%M:%S')"

    show_version
    show_summary
    show_pools
    show_stats
    show_config
}

watch_mode() {
    echo -e "${GREEN}Starting watch mode (refresh every ${REFRESH_INTERVAL}s, Ctrl+C to exit)...${NC}"
    sleep 2

    while true; do
        full_dashboard
        echo -e "\n${CYAN}Refreshing in ${REFRESH_INTERVAL}s... (Ctrl+C to exit)${NC}"
        sleep $REFRESH_INTERVAL
    done
}

# ============================================================================
# Main Script
# ============================================================================

# Check if psql is available
if ! command -v psql &> /dev/null; then
    echo -e "${RED}ERROR: psql command not found${NC}"
    echo "Install PostgreSQL client: apt-get install postgresql-client"
    exit 1
fi

# Check if we can connect
if ! PGPASSWORD=$PGBOUNCER_PASSWORD psql -h $PGBOUNCER_HOST -p $PGBOUNCER_PORT -U $PGBOUNCER_USER -d pgbouncer -c "SHOW VERSION;" &> /dev/null; then
    echo -e "${RED}ERROR: Cannot connect to PgBouncer at $PGBOUNCER_HOST:$PGBOUNCER_PORT${NC}"
    echo "Make sure PgBouncer is running and credentials are correct"
    echo ""
    echo "For Docker: docker exec -it biowerk-pgbouncer $0"
    echo "Or: docker run --rm --network biowerk_default -e PGBOUNCER_HOST=pgbouncer postgres:16-alpine /path/to/monitor-pgbouncer.sh"
    exit 1
fi

# Parse command line arguments
case "${1:-}" in
    --summary)
        show_summary
        ;;
    --pools)
        show_pools
        ;;
    --clients)
        show_clients
        ;;
    --servers)
        show_servers
        ;;
    --stats)
        show_stats
        ;;
    --config)
        show_config
        ;;
    --watch)
        watch_mode
        ;;
    --help|-h)
        echo "Usage: $0 [option]"
        echo ""
        echo "Options:"
        echo "  --summary    Show health summary"
        echo "  --pools      Show connection pools"
        echo "  --clients    Show client connections"
        echo "  --servers    Show server connections"
        echo "  --stats      Show statistics"
        echo "  --config     Show configuration"
        echo "  --watch      Auto-refresh mode"
        echo "  --help       Show this help"
        echo ""
        echo "Environment Variables:"
        echo "  PGBOUNCER_HOST      PgBouncer hostname (default: pgbouncer)"
        echo "  PGBOUNCER_PORT      PgBouncer port (default: 6432)"
        echo "  POSTGRES_USER       Database user (default: biowerk)"
        echo "  POSTGRES_PASSWORD   Database password"
        echo "  REFRESH_INTERVAL    Watch mode refresh interval in seconds (default: 5)"
        ;;
    "")
        # Interactive mode
        while true; do
            show_menu
            read -r choice

            case $choice in
                1)
                    full_dashboard
                    echo -e "\n${CYAN}Press Enter to continue...${NC}"
                    read
                    ;;
                2)
                    clear
                    show_summary
                    echo -e "\n${CYAN}Press Enter to continue...${NC}"
                    read
                    ;;
                3)
                    clear
                    show_pools
                    echo -e "\n${CYAN}Press Enter to continue...${NC}"
                    read
                    ;;
                4)
                    clear
                    show_clients
                    echo -e "\n${CYAN}Press Enter to continue...${NC}"
                    read
                    ;;
                5)
                    clear
                    show_servers
                    echo -e "\n${CYAN}Press Enter to continue...${NC}"
                    read
                    ;;
                6)
                    clear
                    show_stats
                    echo -e "\n${CYAN}Press Enter to continue...${NC}"
                    read
                    ;;
                7)
                    clear
                    show_config
                    echo -e "\n${CYAN}Press Enter to continue...${NC}"
                    read
                    ;;
                w|W)
                    watch_mode
                    ;;
                q|Q)
                    echo -e "${GREEN}Goodbye!${NC}"
                    exit 0
                    ;;
                *)
                    full_dashboard
                    echo -e "\n${CYAN}Press Enter to continue...${NC}"
                    read
                    ;;
            esac
        done
        ;;
    *)
        echo -e "${RED}Unknown option: $1${NC}"
        echo "Use --help for usage information"
        exit 1
        ;;
esac
