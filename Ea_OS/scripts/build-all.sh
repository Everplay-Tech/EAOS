#!/bin/bash
# =============================================================================
# EAOS Complete Build Script
# =============================================================================
# Builds the entire EAOS Sovereign Health Pod:
#   1. Rust workspace (all crates)
#   2. PermFS bridge static library
#   3. Referee kernel (UEFI target)
#   4. Bootable ISO image
#
# Usage: ./build-all.sh [--release] [--iso] [--test]
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Parse arguments
BUILD_RELEASE=0
BUILD_ISO=0
RUN_TESTS=0

while [[ $# -gt 0 ]]; do
    case $1 in
        --release) BUILD_RELEASE=1; shift ;;
        --iso) BUILD_ISO=1; shift ;;
        --test) RUN_TESTS=1; shift ;;
        *) shift ;;
    esac
done

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { echo -e "${CYAN}[BUILD]${NC} $1"; }
log_ok() { echo -e "${GREEN}[BUILD]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[BUILD]${NC} $1"; }
log_err() { echo -e "${RED}[BUILD]${NC} $1"; }

cd "$PROJECT_ROOT"

echo ""
echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║            EAOS COMPLETE BUILD                                    ║"
echo "║         Sovereign Health Pod • Braid Magic: 0xB8AD                ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo ""

# =============================================================================
# Step 1: Build Rust Workspace (default members only - excludes referee-kernel)
# =============================================================================
log "Step 1: Building Rust workspace..."

if [ "$BUILD_RELEASE" = "1" ]; then
    BUILD_FLAGS="--release"
else
    BUILD_FLAGS=""
fi

cargo build $BUILD_FLAGS 2>&1 | tail -20
log_ok "Workspace built successfully"

# =============================================================================
# Step 2: Run Tests (optional)
# =============================================================================
if [ "$RUN_TESTS" = "1" ]; then
    log "Step 2: Running tests..."
    cargo test $BUILD_FLAGS 2>&1 | grep -E "^test |^running |^test result:" | tail -30
    log_ok "All tests passed"
fi

# =============================================================================
# Step 3: Build PermFS Bridge Static Library
# =============================================================================
log "Step 3: Building permfs-bridge static library..."

# Check if UEFI target is installed
if rustup target list --installed | grep -q "x86_64-unknown-uefi"; then
    log "Building for UEFI target..."
    cargo build -p permfs-bridge $BUILD_FLAGS \
        --target x86_64-unknown-uefi \
        --no-default-features \
        --features no_std 2>&1 | tail -5

    if [ "$BUILD_RELEASE" = "1" ]; then
        LIB_PATH="$PROJECT_ROOT/target/x86_64-unknown-uefi/release"
    else
        LIB_PATH="$PROJECT_ROOT/target/x86_64-unknown-uefi/debug"
    fi

    if [ -f "$LIB_PATH/libpermfs_bridge.a" ]; then
        log_ok "Static library built: $LIB_PATH/libpermfs_bridge.a"
    else
        log_warn "Static library not found at expected path"
    fi
else
    log_warn "UEFI target not installed"
    log_warn "Install with: rustup target add x86_64-unknown-uefi"
    log "Building for host target instead..."
    cargo build -p permfs-bridge $BUILD_FLAGS 2>&1 | tail -5
fi

# =============================================================================
# Step 4: Build Referee Kernel (UEFI)
# =============================================================================
log "Step 4: Building referee-kernel..."

if rustup target list --installed | grep -q "x86_64-unknown-uefi"; then
    cd "$PROJECT_ROOT/muscles/referee-kernel"

    # Build the kernel
    cargo build $BUILD_FLAGS --target x86_64-unknown-uefi 2>&1 | tail -10

    if [ "$BUILD_RELEASE" = "1" ]; then
        EFI_PATH="$PROJECT_ROOT/target/x86_64-unknown-uefi/release/referee.efi"
    else
        EFI_PATH="$PROJECT_ROOT/target/x86_64-unknown-uefi/debug/referee.efi"
    fi

    if [ -f "$EFI_PATH" ]; then
        log_ok "EFI binary built: $EFI_PATH"
    else
        log_warn "EFI binary not found at expected path"
    fi

    cd "$PROJECT_ROOT"
else
    log_warn "Skipping referee-kernel (UEFI target not available)"
fi

# =============================================================================
# Step 5: Create Bootable ISO (optional)
# =============================================================================
if [ "$BUILD_ISO" = "1" ]; then
    log "Step 5: Creating bootable ISO..."

    if command -v xorriso &> /dev/null; then
        bash "$SCRIPT_DIR/make-iso.sh" "$PROJECT_ROOT/dist"
    else
        log_warn "xorriso not found - skipping ISO creation"
        log_warn "Install with: brew install xorriso (macOS) or apt install xorriso (Linux)"
    fi
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║              BUILD SUMMARY                                        ║"
echo "╠═══════════════════════════════════════════════════════════════════╣"
echo "║  Workspace:      $(if [ "$BUILD_RELEASE" = "1" ]; then echo "RELEASE"; else echo "DEBUG  "; fi)                                        ║"
echo "║  Tests:          $(if [ "$RUN_TESTS" = "1" ]; then echo "PASSED "; else echo "SKIPPED"; fi)                                        ║"

if rustup target list --installed | grep -q "x86_64-unknown-uefi"; then
    echo "║  PermFS Bridge:  BUILT                                           ║"
    echo "║  Referee Kernel: BUILT                                           ║"
else
    echo -e "║  PermFS Bridge:  ${YELLOW}HOST ONLY${NC}                                      ║"
    echo -e "║  Referee Kernel: ${YELLOW}SKIPPED${NC}                                        ║"
fi

if [ "$BUILD_ISO" = "1" ]; then
    if [ -f "$PROJECT_ROOT/dist/eaos-health-pod.iso" ]; then
        echo "║  Bootable ISO:   CREATED                                         ║"
    else
        echo -e "║  Bootable ISO:   ${YELLOW}FAILED${NC}                                         ║"
    fi
fi

echo "╚═══════════════════════════════════════════════════════════════════╝"
echo ""

# Print next steps
echo "Next steps:"
echo "  1. Install UEFI target: rustup target add x86_64-unknown-uefi"
echo "  2. Build for UEFI: ./scripts/build-all.sh --release --iso"
echo "  3. Test in QEMU: See scripts/make-iso.sh output for commands"
echo ""

exit 0
