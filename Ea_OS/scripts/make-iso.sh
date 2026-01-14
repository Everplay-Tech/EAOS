#!/bin/bash
# =============================================================================
# EAOS Bootable ISO Builder
# =============================================================================
# Creates a bootable UEFI ISO image containing:
#   1. referee.efi - The EAOS UEFI bootloader
#   2. sovereign_health.json - Organ manifest
#   3. startup.nsh - UEFI shell startup script
#
# Usage: ./make-iso.sh [output-dir]
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="${1:-$PROJECT_ROOT/dist}"
ISO_NAME="eaos-health-pod.iso"
ISO_PATH="$OUTPUT_DIR/$ISO_NAME"

# Source paths
MANIFEST="$PROJECT_ROOT/manifests/sovereign_health.json"
EFI_BINARY="$PROJECT_ROOT/target/x86_64-unknown-uefi/release/referee.efi"

# Temporary build directory
BUILD_DIR=$(mktemp -d)
trap "rm -rf $BUILD_DIR" EXIT

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { echo -e "${CYAN}[ISO]${NC} $1"; }
log_ok() { echo -e "${GREEN}[ISO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[ISO]${NC} $1"; }
log_err() { echo -e "${RED}[ISO]${NC} $1"; }

# =============================================================================
# Banner
# =============================================================================
echo ""
echo "========================================================================"
echo "             EAOS BOOTABLE ISO BUILDER"
echo "          Sovereign Health Pod - Braid Magic: 0xB8AD"
echo "========================================================================"
echo ""

# =============================================================================
# Pre-flight Checks
# =============================================================================
log "Checking prerequisites..."

mkdir -p "$OUTPUT_DIR"

# Check for required tools
MISSING_TOOLS=""
for cmd in xorriso mformat mcopy; do
    if ! command -v $cmd &> /dev/null; then
        MISSING_TOOLS="$MISSING_TOOLS $cmd"
    fi
done

if [ -n "$MISSING_TOOLS" ]; then
    log_err "Missing required tools:$MISSING_TOOLS"
    echo ""
    echo "Install with:"
    echo "  macOS:  brew install xorriso mtools"
    echo "  Debian: apt install xorriso mtools"
    echo "  Fedora: dnf install xorriso mtools"
    exit 1
fi
log_ok "All tools available"

# Check for manifest
if [ ! -f "$MANIFEST" ]; then
    log_err "Manifest not found: $MANIFEST"
    exit 1
fi
log_ok "Manifest found"

# Check for EFI binary
USE_STUB=0
if [ ! -f "$EFI_BINARY" ]; then
    log_warn "EFI binary not found at: $EFI_BINARY"
    log_warn "Building with stub EFI (for testing ISO structure)"
    USE_STUB=1
fi

# =============================================================================
# Create ISO Structure
# =============================================================================
log "Creating ISO directory structure..."

# Create directories - use 'boot' for efiboot.img to avoid macOS case insensitivity issues
mkdir -p "$BUILD_DIR/iso/EFI/BOOT"
mkdir -p "$BUILD_DIR/iso/boot"
mkdir -p "$BUILD_DIR/iso/EAOS/manifests"
mkdir -p "$BUILD_DIR/iso/EAOS/storage"

# =============================================================================
# Populate EFI Boot Files
# =============================================================================
log "Populating EFI boot files..."

if [ "$USE_STUB" = "0" ]; then
    cp "$EFI_BINARY" "$BUILD_DIR/iso/EFI/BOOT/BOOTX64.EFI"
    log_ok "Copied referee.efi as BOOTX64.EFI"
else
    # Create minimal stub EFI
    log_warn "Creating placeholder BOOTX64.EFI"
    dd if=/dev/zero of="$BUILD_DIR/iso/EFI/BOOT/BOOTX64.EFI" bs=512 count=1 2>/dev/null
fi

# Create startup.nsh for UEFI shell
cat > "$BUILD_DIR/iso/startup.nsh" << 'EOF'
@echo -off
cls
echo ""
echo "==========================================="
echo "  EAOS Sovereign Health Pod"
echo "  Version 1.0.0"
echo "==========================================="
echo ""
echo "  Braid Magic: 0xB8AD"
echo "  Compression: T9-Braid (7.9%)"
echo "  Governance:  Dr-Lex Healthcare Constitution"
echo ""
echo "Loading referee.efi..."
echo ""
\EFI\BOOT\BOOTX64.EFI
EOF
log_ok "Created startup.nsh"

# =============================================================================
# Populate EAOS Data
# =============================================================================
log "Populating EAOS data..."

# Copy manifest
cp "$MANIFEST" "$BUILD_DIR/iso/EAOS/manifests/sovereign_health.json"
log_ok "Installed sovereign_health.json"

# Create version file
cat > "$BUILD_DIR/iso/EAOS/VERSION" << EOF
EAOS Sovereign Health Pod
Version: 1.0.0
Built: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Braid Magic: 0xB8AD
Target Compression: 7.9%
EOF
log_ok "Created VERSION file"

# Create README
cat > "$BUILD_DIR/iso/README.txt" << 'EOF'
EAOS Sovereign Health Pod
=========================

This ISO contains the EAOS healthcare operating system.

Contents:
  /EFI/BOOT/BOOTX64.EFI  - UEFI bootloader (referee.efi)
  /EAOS/manifests/       - Organ manifests
  /EAOS/storage/         - PermFS data storage
  /startup.nsh           - UEFI shell startup script

Boot Options:
  1. UEFI Direct Boot: Boot from BOOTX64.EFI
  2. UEFI Shell: Run startup.nsh

For QEMU testing:
  qemu-system-x86_64 \
    -m 512M \
    -bios /usr/local/share/qemu/edk2-x86_64-code.fd \
    -cdrom eaos-health-pod.iso \
    -serial stdio \
    -nographic
EOF

# =============================================================================
# Create EFI Boot Image (FAT)
# =============================================================================
log "Creating EFI boot image..."

EFI_IMG="$BUILD_DIR/efiboot.img"
EFI_IMG_SIZE=4096  # 4MB

# Create FAT image
dd if=/dev/zero of="$EFI_IMG" bs=1K count=$EFI_IMG_SIZE 2>/dev/null
mformat -i "$EFI_IMG" -F ::

# Create directory structure in FAT image
mmd -i "$EFI_IMG" ::/EFI
mmd -i "$EFI_IMG" ::/EFI/BOOT

# Copy boot files to FAT image
mcopy -i "$EFI_IMG" "$BUILD_DIR/iso/EFI/BOOT/BOOTX64.EFI" ::/EFI/BOOT/BOOTX64.EFI
mcopy -i "$EFI_IMG" "$BUILD_DIR/iso/startup.nsh" ::/startup.nsh

# Also add startup.nsh that references fs0: (ISO filesystem)
# Note: @echo -off removed so we can see what's happening
cat > "$BUILD_DIR/startup-fs.nsh" << 'EOFNSH'
echo "=== EAOS STARTUP ==="
echo "EAOS Sovereign Health Pod v1.0"
echo "Braid: 0xB8AD"
map -r
echo "Attempting to load BOOTX64.EFI..."
\EFI\BOOT\BOOTX64.EFI
EOFNSH
mcopy -oi "$EFI_IMG" "$BUILD_DIR/startup-fs.nsh" ::/startup.nsh

# Copy to ISO structure (in boot/ directory to avoid macOS case issues)
cp "$EFI_IMG" "$BUILD_DIR/iso/boot/efiboot.img"

log_ok "EFI boot image created"

# =============================================================================
# Create ISO Image
# =============================================================================
log "Creating bootable ISO..."

xorriso -as mkisofs \
    -o "$ISO_PATH" \
    -iso-level 3 \
    -full-iso9660-filenames \
    -volid "EAOS_HEALTH_POD" \
    -eltorito-alt-boot \
    -e "boot/efiboot.img" \
    -no-emul-boot \
    "$BUILD_DIR/iso"

log_ok "ISO created: $ISO_PATH"

# =============================================================================
# Summary
# =============================================================================
ISO_SIZE=$(du -h "$ISO_PATH" | cut -f1)

echo ""
echo "========================================================================"
echo "              BUILD COMPLETE"
echo "========================================================================"
echo "  Output:  $ISO_PATH"
echo "  Size:    $ISO_SIZE"
echo "  Type:    UEFI Bootable ISO"
echo "------------------------------------------------------------------------"

if [ "$USE_STUB" = "0" ]; then
    echo -e "  Status:  ${GREEN}READY FOR BOOT${NC}"
else
    echo -e "  Status:  ${YELLOW}STUB BUILD (no EFI binary)${NC}"
    echo "  Build referee.efi first:"
    echo "    cargo build -p referee --release --target x86_64-unknown-uefi"
fi

echo "========================================================================"
echo ""

# Print QEMU command for testing
echo "To test in QEMU:"
echo ""
echo "  # macOS with QEMU:"
echo "  qemu-system-x86_64 \\"
echo "    -m 512M \\"
echo "    -bios /opt/homebrew/share/qemu/edk2-x86_64-code.fd \\"
echo "    -cdrom $ISO_PATH \\"
echo "    -serial stdio \\"
echo "    -nographic"
echo ""
echo "  # Linux with OVMF:"
echo "  qemu-system-x86_64 \\"
echo "    -enable-kvm \\"
echo "    -m 512M \\"
echo "    -bios /usr/share/OVMF/OVMF_CODE.fd \\"
echo "    -cdrom $ISO_PATH \\"
echo "    -serial stdio"
echo ""

exit 0
