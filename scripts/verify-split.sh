#!/usr/bin/env bash
# EAOS Monorepo Split Verification Script
# This script verifies that the monorepo split completed successfully

set -euo pipefail

# Configuration
GITHUB_ORG="E-TECH-PLAYTECH"
GITHUB_BASE_URL="https://github.com/${GITHUB_ORG}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Component inventory (same as split-monorepo.sh)
declare -a COMPONENTS=(
    "Hyperbolic Chamber|Ea_OS/muscles/hyperbolic-chamber|hyperbolic-chamber"
    "Referee Kernel|Ea_OS/muscles/referee-kernel|referee-kernel"
    "Ledger|Ea_OS/ledger|ledger"
    "IHP|Ea_OS/IHP-main|ihp"
    "Dr. Lex|Ea_OS/Intelligence/Dr-Lex|dr-lex"
    "Muscle Compiler|Ea_OS/muscle-compiler|muscle-compiler"
    "Nucleus|Ea_OS/nucleus|nucleus"
    "PermFS Bridge|Ea_OS/muscles/permfs-bridge|permfs-bridge"
    "Roulette|Ea_OS/muscles/roulette-kernel-rs-main|roulette"
    "Symbiote|Ea_OS/muscles/symbiote|symbiote"
    "Net Stack|Ea_OS/muscles/net-stack|net-stack"
)

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}[⚠]${NC} $*"
}

log_error() {
    echo -e "${RED}[✗]${NC} $*"
}

# Track verification results
declare -i TOTAL_CHECKS=0
declare -i PASSED_CHECKS=0
declare -i FAILED_CHECKS=0

# Record check result
record_check() {
    local status="$1"
    local message="$2"
    
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    if [[ "$status" == "pass" ]]; then
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
        log_success "$message"
    else
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
        log_error "$message"
    fi
}

# Check if a path is a submodule
is_submodule() {
    local path="$1"
    git submodule status "${path}" &> /dev/null
}

# Check if remote repository exists
remote_repo_exists() {
    local repo_name="$1"
    
    if command -v gh &> /dev/null; then
        gh repo view "${GITHUB_ORG}/${repo_name}" &> /dev/null
    elif command -v curl &> /dev/null; then
        # Fallback to curl if gh is not available
        local http_code=$(curl -s -o /dev/null -w "%{http_code}" "https://github.com/${GITHUB_ORG}/${repo_name}")
        [[ "$http_code" == "200" ]]
    else
        log_warning "Neither 'gh' nor 'curl' available, skipping remote repo check"
        return 2  # Unknown status
    fi
}

# Verify a single component
verify_component() {
    local component_info="$1"
    
    # Parse component information
    IFS='|' read -r component_name source_dir target_repo <<< "${component_info}"
    
    log_info "Verifying: ${component_name}"
    
    # Check 1: Directory should be a submodule
    if is_submodule "${source_dir}"; then
        record_check "pass" "${source_dir} is configured as submodule"
    else
        record_check "fail" "${source_dir} is NOT a submodule"
    fi
    
    # Check 2: Remote repository should exist
    if remote_repo_exists "${target_repo}"; then
        record_check "pass" "Repository ${GITHUB_ORG}/${target_repo} exists"
    else
        local exit_code=$?
        if [[ $exit_code -eq 2 ]]; then
            log_warning "Repository check skipped (missing gh/curl)"
        else
            record_check "fail" "Repository ${GITHUB_ORG}/${target_repo} NOT found"
        fi
    fi
    
    # Check 3: Submodule should be initialized
    if [[ -d "${source_dir}/.git" ]] || [[ -f "${source_dir}/.git" ]]; then
        record_check "pass" "${source_dir} submodule is initialized"
    else
        record_check "fail" "${source_dir} submodule is NOT initialized (run: git submodule update --init)"
    fi
    
    # Check 4: Submodule URL should match expected
    local submodule_url=$(git config --file .gitmodules --get "submodule.${source_dir}.url" 2>/dev/null || echo "")
    local expected_url="${GITHUB_BASE_URL}/${target_repo}.git"
    if [[ "$submodule_url" == "$expected_url" ]]; then
        record_check "pass" "${source_dir} has correct URL"
    else
        if [[ -n "$submodule_url" ]]; then
            record_check "fail" "${source_dir} has incorrect URL: ${submodule_url} (expected: ${expected_url})"
        else
            record_check "fail" "${source_dir} URL not configured"
        fi
    fi
    
    echo ""
}

# Check for leftover split branches
check_split_branches() {
    log_info "Checking for leftover split branches..."
    
    local split_branches
    split_branches=$(git branch --list 'split/*' | wc -l | tr -d ' ')
    
    if [[ $split_branches -eq 0 ]]; then
        record_check "pass" "No leftover split branches"
    else
        record_check "fail" "Found ${split_branches} split/* branches (should be cleaned up)"
    fi
    
    echo ""
}

# Check for backup branches
check_backup_branches() {
    log_info "Checking for backup branches..."
    
    local backup_branches
    backup_branches=$(git branch --list 'backup/pre-split-*' | wc -l | tr -d ' ')
    
    if [[ $backup_branches -gt 0 ]]; then
        log_success "Found ${backup_branches} backup branch(es) for rollback"
        git branch --list 'backup/pre-split-*' | sed 's/^/    /'
    else
        log_warning "No backup branches found"
    fi
    
    echo ""
}

# Check .gitmodules file
check_gitmodules() {
    log_info "Checking .gitmodules file..."
    
    if [[ -f ".gitmodules" ]]; then
        record_check "pass" ".gitmodules file exists"
        
        local submodule_count=$(grep -c '^\[submodule' .gitmodules)
        log_info "Total submodules configured: ${submodule_count}"
    else
        record_check "fail" ".gitmodules file NOT found"
    fi
    
    echo ""
}

# Check working directory cleanliness
check_working_directory() {
    log_info "Checking working directory..."
    
    if git diff-index --quiet HEAD --; then
        record_check "pass" "Working directory is clean"
    else
        record_check "fail" "Working directory has uncommitted changes"
        log_info "Run 'git status' to see changes"
    fi
    
    echo ""
}

# Main verification
main() {
    log_info "EAOS Monorepo Split Verification"
    log_info "================================="
    echo ""
    
    # Change to repository root
    cd "${REPO_ROOT}"
    
    # Verify each component
    for component in "${COMPONENTS[@]}"; do
        verify_component "${component}"
    done
    
    # Additional checks
    check_split_branches
    check_backup_branches
    check_gitmodules
    check_working_directory
    
    # Summary
    log_info "=========================================="
    log_info "Verification Summary"
    log_info "=========================================="
    echo -e "Total checks:  ${TOTAL_CHECKS}"
    echo -e "${GREEN}Passed:        ${PASSED_CHECKS}${NC}"
    if [[ $FAILED_CHECKS -gt 0 ]]; then
        echo -e "${RED}Failed:        ${FAILED_CHECKS}${NC}"
    else
        echo -e "Failed:        ${FAILED_CHECKS}"
    fi
    echo ""
    
    if [[ $FAILED_CHECKS -eq 0 ]]; then
        log_success "All checks passed! ✓"
        echo ""
        log_info "Next steps:"
        log_info "  1. Test build/functionality"
        log_info "  2. Push changes: git push origin <branch-name>"
        log_info "  3. Update CI/CD configurations"
        exit 0
    else
        log_error "Some checks failed. Please review and fix issues."
        echo ""
        log_info "Common fixes:"
        log_info "  - Initialize submodules: git submodule update --init --recursive"
        log_info "  - Clean up split branches: git branch -D split/*"
        log_info "  - Commit changes: git add . && git commit"
        exit 1
    fi
}

# Run main
main
