#!/usr/bin/env bash
# EAOS Monorepo Split Automation Script
# This script splits the EAOS monorepo into multiple independent repositories
# while preserving full Git history for each component.

set -euo pipefail

# Configuration
GITHUB_ORG="E-TECH-PLAYTECH"
GITHUB_BASE_URL="https://github.com/${GITHUB_ORG}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRY_RUN="${DRY_RUN:-false}"
SKIP_GITHUB_CREATE="${SKIP_GITHUB_CREATE:-false}"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Component inventory
# Format: "component_name|source_directory|target_repo_name|description"
declare -a COMPONENTS=(
    "Hyperbolic Chamber|Ea_OS/muscles/hyperbolic-chamber|hyperbolic-chamber|Task planner and deployment engine"
    "Referee Kernel|Ea_OS/muscles/referee-kernel|referee-kernel|The core microkernel and brain of EAOS"
    "Ledger|Ea_OS/ledger|ledger|Distributed ledger and transaction system"
    "IHP|Ea_OS/IHP-main|ihp|Industrial-grade IHP capsule implementation"
    "Dr. Lex|Ea_OS/Intelligence/Dr-Lex|dr-lex|Governance engine and immune system"
    "Muscle Compiler|Ea_OS/muscle-compiler|muscle-compiler|Toolchain for compiling biological muscles"
    "Nucleus|Ea_OS/nucleus|nucleus|Core system runtime"
    "PermFS Bridge|Ea_OS/muscles/permfs-bridge|permfs-bridge|Bridge between kernel and PermFS"
    "Roulette|Ea_OS/muscles/roulette-kernel-rs-main|roulette|T9-Braid Compression engine"
    "Symbiote|Ea_OS/muscles/symbiote|symbiote|Interface for organ/muscle interaction"
    "Net Stack|Ea_OS/muscles/net-stack|net-stack|Networking stack implementation"
)

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

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if we're in a git repository
    if ! git -C "${REPO_ROOT}" rev-parse --git-dir > /dev/null 2>&1; then
        log_error "Not in a git repository"
        exit 1
    fi
    
    # Check for required commands
    local required_commands=("git" "gh")
    for cmd in "${required_commands[@]}"; do
        if ! command -v "$cmd" &> /dev/null; then
            log_error "Required command not found: $cmd"
            if [[ "$cmd" == "gh" ]]; then
                log_info "Install GitHub CLI from: https://cli.github.com/"
            fi
            exit 1
        fi
    done
    
    # Check GitHub authentication
    if [[ "${SKIP_GITHUB_CREATE}" != "true" ]]; then
        if ! gh auth status &> /dev/null; then
            log_error "Not authenticated with GitHub CLI"
            log_info "Run: gh auth login"
            exit 1
        fi
    fi
    
    log_success "Prerequisites check passed"
}

# Create a backup branch
create_backup() {
    log_info "Creating backup branch..."
    local backup_branch="backup/pre-split-$(date +%Y%m%d-%H%M%S)"
    
    if [[ "${DRY_RUN}" == "true" ]]; then
        log_info "[DRY RUN] Would create backup branch: ${backup_branch}"
    else
        git branch "${backup_branch}"
        log_success "Created backup branch: ${backup_branch}"
    fi
}

# Create GitHub repository
create_github_repo() {
    local repo_name="$1"
    local description="$2"
    
    if [[ "${SKIP_GITHUB_CREATE}" == "true" ]]; then
        log_warning "Skipping GitHub repository creation (SKIP_GITHUB_CREATE=true)"
        return 0
    fi
    
    log_info "Creating GitHub repository: ${GITHUB_ORG}/${repo_name}"
    
    if [[ "${DRY_RUN}" == "true" ]]; then
        log_info "[DRY RUN] Would create repository: ${GITHUB_ORG}/${repo_name}"
        return 0
    fi
    
    # Check if repository already exists
    if gh repo view "${GITHUB_ORG}/${repo_name}" &> /dev/null; then
        log_warning "Repository ${GITHUB_ORG}/${repo_name} already exists, skipping creation"
        return 0
    fi
    
    # Create repository
    gh repo create "${GITHUB_ORG}/${repo_name}" \
        --public \
        --description "${description}" \
        --enable-issues \
        --enable-wiki=false
    
    log_success "Created repository: ${GITHUB_ORG}/${repo_name}"
}

# Split git history for a component
split_component_history() {
    local component_name="$1"
    local source_dir="$2"
    local target_repo="$3"
    local split_branch="split/${target_repo}"
    
    log_info "Splitting history for ${component_name} (${source_dir})..."
    
    # Check if source directory exists
    if [[ ! -d "${REPO_ROOT}/${source_dir}" ]]; then
        log_error "Source directory does not exist: ${source_dir}"
        return 1
    fi
    
    if [[ "${DRY_RUN}" == "true" ]]; then
        log_info "[DRY RUN] Would split history for: ${source_dir}"
        return 0
    fi
    
    # Delete branch if it already exists
    if git show-ref --verify --quiet "refs/heads/${split_branch}"; then
        log_warning "Branch ${split_branch} already exists, deleting it"
        git branch -D "${split_branch}"
    fi
    
    # Split the history
    git subtree split --prefix="${source_dir}" -b "${split_branch}"
    
    log_success "Split history created in branch: ${split_branch}"
}

# Push split history to new repository
push_to_new_repo() {
    local target_repo="$1"
    local split_branch="split/${target_repo}"
    local remote_name="${target_repo}-remote"
    local remote_url="${GITHUB_BASE_URL}/${target_repo}.git"
    
    log_info "Pushing split history to ${GITHUB_ORG}/${target_repo}..."
    
    if [[ "${DRY_RUN}" == "true" ]]; then
        log_info "[DRY RUN] Would push ${split_branch} to ${remote_url}"
        return 0
    fi
    
    # Add remote if it doesn't exist
    if ! git remote get-url "${remote_name}" &> /dev/null; then
        git remote add "${remote_name}" "${remote_url}"
    else
        git remote set-url "${remote_name}" "${remote_url}"
    fi
    
    # Push the split branch to the new repository's main branch
    git push "${remote_name}" "${split_branch}:main" --force
    
    log_success "Pushed to ${GITHUB_ORG}/${target_repo}"
}

# Remove source directory and add as submodule
convert_to_submodule() {
    local source_dir="$1"
    local target_repo="$2"
    local submodule_url="${GITHUB_BASE_URL}/${target_repo}.git"
    
    log_info "Converting ${source_dir} to submodule..."
    
    if [[ "${DRY_RUN}" == "true" ]]; then
        log_info "[DRY RUN] Would convert ${source_dir} to submodule: ${submodule_url}"
        return 0
    fi
    
    # Remove the directory
    git rm -r "${source_dir}"
    
    # Add as submodule
    git submodule add "${submodule_url}" "${source_dir}"
    
    log_success "Converted ${source_dir} to submodule"
}

# Process a single component
process_component() {
    local component_info="$1"
    
    # Parse component information
    IFS='|' read -r component_name source_dir target_repo description <<< "${component_info}"
    
    log_info "=========================================="
    log_info "Processing: ${component_name}"
    log_info "  Source: ${source_dir}"
    log_info "  Target: ${target_repo}"
    log_info "  Description: ${description}"
    log_info "=========================================="
    
    # Step 1: Create GitHub repository
    create_github_repo "${target_repo}" "${description}"
    
    # Step 2: Split component history
    split_component_history "${component_name}" "${source_dir}" "${target_repo}"
    
    # Step 3: Push to new repository
    push_to_new_repo "${target_repo}"
    
    # Step 4: Convert to submodule
    convert_to_submodule "${source_dir}" "${target_repo}"
    
    # Commit the changes
    if [[ "${DRY_RUN}" != "true" ]]; then
        git commit -m "refactor: migrate ${component_name} to submodule

- Extracted ${source_dir} to ${GITHUB_ORG}/${target_repo}
- Converted to submodule at ${source_dir}
- Full Git history preserved in new repository"
    fi
    
    log_success "Completed processing: ${component_name}"
    echo ""
}

# Clean up split branches
cleanup_split_branches() {
    log_info "Cleaning up split branches..."
    
    if [[ "${DRY_RUN}" == "true" ]]; then
        log_info "[DRY RUN] Would clean up split branches"
        return 0
    fi
    
    # Find all split/* branches and delete them
    for branch in $(git branch --list 'split/*' | sed 's/^[* ] //'); do
        log_info "Deleting branch: ${branch}"
        git branch -D "${branch}"
    done
    
    log_success "Split branches cleaned up"
}

# Main execution
main() {
    log_info "EAOS Monorepo Split Automation"
    log_info "================================"
    echo ""
    
    if [[ "${DRY_RUN}" == "true" ]]; then
        log_warning "Running in DRY RUN mode - no changes will be made"
    fi
    
    # Change to repository root
    cd "${REPO_ROOT}"
    
    # Check prerequisites
    check_prerequisites
    
    # Create backup
    create_backup
    
    # Process each component
    for component in "${COMPONENTS[@]}"; do
        process_component "${component}"
    done
    
    # Clean up
    cleanup_split_branches
    
    log_success "=========================================="
    log_success "Monorepo split completed successfully!"
    log_success "=========================================="
    echo ""
    log_info "Next steps:"
    log_info "  1. Review the changes: git status"
    log_info "  2. Initialize submodules: git submodule update --init --recursive"
    log_info "  3. Push changes: git push origin <branch-name>"
    echo ""
    log_info "To rollback, use the backup branch created earlier"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --skip-github-create)
            SKIP_GITHUB_CREATE=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --dry-run              Run in dry-run mode (no changes made)"
            echo "  --skip-github-create   Skip GitHub repository creation"
            echo "  --help, -h             Show this help message"
            echo ""
            echo "Environment variables:"
            echo "  DRY_RUN                Same as --dry-run"
            echo "  SKIP_GITHUB_CREATE     Same as --skip-github-create"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Run main
main
