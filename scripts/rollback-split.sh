#!/usr/bin/env bash
# EAOS Monorepo Split Rollback Script
# This script helps rollback a monorepo split if something goes wrong

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

# Find backup branches
find_backup_branches() {
    log_info "Searching for backup branches..."
    
    local branches=$(git branch --list 'backup/pre-split-*' | sed 's/^[* ] //')
    
    if [[ -z "$branches" ]]; then
        log_error "No backup branches found matching 'backup/pre-split-*'"
        log_info "Cannot proceed with rollback without a backup branch."
        exit 1
    fi
    
    echo "$branches"
}

# Display backup branches
display_backup_branches() {
    local branches=("$@")
    
    log_info "Available backup branches:"
    local i=1
    for branch in "${branches[@]}"; do
        echo "  ${i}. ${branch}"
        i=$((i + 1))
    done
    echo ""
}

# Rollback to a backup branch
rollback_to_backup() {
    local backup_branch="$1"
    local create_new_branch="${2:-true}"
    
    log_warning "This will discard ALL changes made since the backup was created."
    log_warning "Current branch: $(git branch --show-current)"
    log_warning "Rollback to: ${backup_branch}"
    echo ""
    
    if [[ "$create_new_branch" == "true" ]]; then
        read -p "Enter name for new rollback branch (default: rollback-$(date +%Y%m%d-%H%M%S)): " new_branch
        new_branch="${new_branch:-rollback-$(date +%Y%m%d-%H%M%S)}"
        
        log_info "Creating new branch '${new_branch}' from '${backup_branch}'..."
        git checkout -b "${new_branch}" "${backup_branch}"
        log_success "Created and switched to branch: ${new_branch}"
    else
        log_info "Checking out '${backup_branch}'..."
        git checkout "${backup_branch}"
        log_success "Switched to branch: ${backup_branch}"
    fi
    
    echo ""
    log_success "Rollback completed!"
    echo ""
    log_info "Next steps:"
    log_info "  1. Verify the state: git log --oneline -10"
    log_info "  2. Check files: ls -la"
    if [[ "$create_new_branch" == "true" ]]; then
        log_info "  3. Push if needed: git push origin ${new_branch}"
    fi
}

# Clean up after failed split
cleanup_failed_split() {
    log_info "Cleaning up after failed split..."
    
    # Remove split branches
    git branch --list 'split/*' | sed 's/^[* ] //' | while read -r branch; do
        log_info "  Deleting: ${branch}"
        git branch -D "${branch}"
    done
    
    # Remove temporary remotes (created by split-monorepo.sh)
    log_info "Checking for temporary remotes..."
    git remote | grep -E '^[a-z-]+-remote$' | while read -r remote; do
        log_info "  Removing: ${remote}"
        git remote remove "${remote}"
    done
    
    log_success "Cleanup completed"
}

# Interactive mode
interactive_rollback() {
    log_info "EAOS Monorepo Split Rollback"
    log_info "============================="
    echo ""
    
    # Find backup branches
    local backup_branches=($(find_backup_branches))
    
    # Display options
    display_backup_branches "${backup_branches[@]}"
    
    # Ask user to select
    read -p "Select backup branch number (or 'c' to cancel): " selection
    
    if [[ "$selection" == "c" ]] || [[ "$selection" == "C" ]]; then
        log_info "Rollback cancelled."
        exit 0
    fi
    
    # Validate selection
    if ! [[ "$selection" =~ ^[0-9]+$ ]] || [[ $selection -lt 1 ]] || [[ $selection -gt ${#backup_branches[@]} ]]; then
        log_error "Invalid selection: ${selection}"
        exit 1
    fi
    
    # Get selected branch
    local selected_branch="${backup_branches[$((selection - 1))]}"
    
    # Confirm
    echo ""
    read -p "Rollback to '${selected_branch}'? (yes/no): " confirm
    if [[ "$confirm" != "yes" ]]; then
        log_info "Rollback cancelled."
        exit 0
    fi
    
    echo ""
    
    # Perform rollback
    rollback_to_backup "${selected_branch}" "true"
    
    # Offer cleanup
    echo ""
    read -p "Clean up split branches and temporary remotes? (yes/no): " cleanup
    if [[ "$cleanup" == "yes" ]]; then
        cleanup_failed_split
    fi
}

# Main
main() {
    cd "${REPO_ROOT}"
    
    # Check if we're in a git repository
    if ! git rev-parse --git-dir > /dev/null 2>&1; then
        log_error "Not in a git repository"
        exit 1
    fi
    
    # Check for uncommitted changes
    if ! git diff-index --quiet HEAD --; then
        log_warning "You have uncommitted changes!"
        read -p "Continue anyway? (yes/no): " continue
        if [[ "$continue" != "yes" ]]; then
            log_info "Rollback cancelled. Commit or stash your changes first."
            exit 0
        fi
    fi
    
    echo ""
    interactive_rollback
}

# Parse command line arguments
if [[ $# -gt 0 ]]; then
    case $1 in
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Rollback a monorepo split by restoring from a backup branch."
            echo ""
            echo "Options:"
            echo "  --help, -h    Show this help message"
            echo ""
            echo "This script will:"
            echo "  1. List available backup branches"
            echo "  2. Select which backup to restore"
            echo "  3. Create a new branch from the backup"
            echo "  4. Optionally clean up split branches and remotes"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
fi

# Run main
main
