#!/bin/bash
# =============================================================================
# EAOS Disk Image Builder
# =============================================================================
# Creates eaos-disk.img with:
#   1. GPT partition table
#   2. EFI System Partition (ESP) with referee.efi
#   3. EAOS Data Partition with sovereign_health.json manifest
#
# Usage: ./make-disk.sh [output-path]
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="${1:-$PROJECT_ROOT/dist}"
DISK_IMAGE="$OUTPUT_DIR/eaos-disk.img"
MANIFEST="$PROJECT_ROOT/manifests/sovereign_health.json"
EFI_BINARY="$PROJECT_ROOT/target/x86_64-unknown-uefi/release/referee.efi"

# Disk geometry
DISK_SIZE_MB=128
ESP_SIZE_MB=64
DATA_SIZE_MB=62

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { echo -e "${CYAN}[DISK]${NC} $1"; }
log_ok() { echo -e "${GREEN}[DISK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[DISK]${NC} $1"; }
log_err() { echo -e "${RED}[DISK]${NC} $1"; }

# =============================================================================
# Pre-flight Checks
# =============================================================================
log "EAOS Disk Image Builder"
log "======================"

mkdir -p "$OUTPUT_DIR"

# Check for required tools
for cmd in dd mkfs.fat parted; do
    if ! command -v $cmd &> /dev/null; then
        log_err "Required tool not found: $cmd"
        exit 1
    fi
done

# Check for manifest
if [ ! -f "$MANIFEST" ]; then
    log_err "Manifest not found: $MANIFEST"
    exit 1
fi
log_ok "Manifest found: $MANIFEST"

# Check for EFI binary (optional - can build without it)
if [ -f "$EFI_BINARY" ]; then
    log_ok "EFI binary found: $EFI_BINARY"
    HAS_EFI=1
else
    log_warn "EFI binary not found - building data-only image"
    log_warn "Build with: cargo build -p referee --release --target x86_64-unknown-uefi"
    HAS_EFI=0
fi

# =============================================================================
# Create Disk Image
# =============================================================================
log "Creating ${DISK_SIZE_MB}MB disk image..."

# Create empty disk image
dd if=/dev/zero of="$DISK_IMAGE" bs=1M count=$DISK_SIZE_MB status=progress 2>/dev/null

# Create GPT partition table
log "Creating GPT partition table..."
parted -s "$DISK_IMAGE" mklabel gpt

# Create EFI System Partition (ESP)
log "Creating EFI System Partition..."
parted -s "$DISK_IMAGE" mkpart "EFI System Partition" fat32 1MiB ${ESP_SIZE_MB}MiB
parted -s "$DISK_IMAGE" set 1 esp on

# Create EAOS Data Partition
log "Creating EAOS Data Partition..."
parted -s "$DISK_IMAGE" mkpart "EAOS Data" fat32 ${ESP_SIZE_MB}MiB 100%

log_ok "Partition table created"

# =============================================================================
# Mount and Populate Partitions (requires root or loop device support)
# =============================================================================

# Calculate partition offsets (in bytes)
ESP_START=$((1 * 1024 * 1024))  # 1MB offset
ESP_SIZE=$(((ESP_SIZE_MB - 1) * 1024 * 1024))
DATA_START=$((ESP_SIZE_MB * 1024 * 1024))

# Create temporary mount points
MOUNT_ESP=$(mktemp -d)
MOUNT_DATA=$(mktemp -d)

cleanup() {
    # Unmount and cleanup
    if mountpoint -q "$MOUNT_ESP" 2>/dev/null; then
        sudo umount "$MOUNT_ESP" || true
    fi
    if mountpoint -q "$MOUNT_DATA" 2>/dev/null; then
        sudo umount "$MOUNT_DATA" || true
    fi
    rm -rf "$MOUNT_ESP" "$MOUNT_DATA"

    # Detach loop devices
    if [ -n "$LOOP_ESP" ]; then
        sudo losetup -d "$LOOP_ESP" 2>/dev/null || true
    fi
    if [ -n "$LOOP_DATA" ]; then
        sudo losetup -d "$LOOP_DATA" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# Check if we can use loop devices (requires sudo)
if sudo -n true 2>/dev/null; then
    log "Setting up loop devices..."

    # Setup loop device for ESP
    LOOP_ESP=$(sudo losetup -f --show -o $ESP_START --sizelimit $ESP_SIZE "$DISK_IMAGE")
    log "ESP loop device: $LOOP_ESP"

    # Format ESP as FAT32
    sudo mkfs.fat -F 32 -n "EFI" "$LOOP_ESP"

    # Mount ESP
    sudo mount "$LOOP_ESP" "$MOUNT_ESP"

    # Create EFI directory structure
    sudo mkdir -p "$MOUNT_ESP/EFI/BOOT"

    # Copy EFI binary if available
    if [ "$HAS_EFI" = "1" ]; then
        sudo cp "$EFI_BINARY" "$MOUNT_ESP/EFI/BOOT/BOOTX64.EFI"
        log_ok "Installed referee.efi as BOOTX64.EFI"
    fi

    # Create startup.nsh for UEFI shell
    cat << 'EOF' | sudo tee "$MOUNT_ESP/startup.nsh" > /dev/null
@echo -off
echo "EAOS Sovereign Health Pod"
echo "========================="
echo "Loading referee.efi..."
\EFI\BOOT\BOOTX64.EFI
EOF
    log_ok "Created startup.nsh"

    sudo umount "$MOUNT_ESP"
    sudo losetup -d "$LOOP_ESP"
    LOOP_ESP=""

    # Setup loop device for Data partition
    LOOP_DATA=$(sudo losetup -f --show -o $DATA_START "$DISK_IMAGE")
    log "Data loop device: $LOOP_DATA"

    # Format Data partition as FAT32
    sudo mkfs.fat -F 32 -n "EAOS_DATA" "$LOOP_DATA"

    # Mount Data partition
    sudo mount "$LOOP_DATA" "$MOUNT_DATA"

    # Create EAOS directory structure
    sudo mkdir -p "$MOUNT_DATA/EAOS/manifests"
    sudo mkdir -p "$MOUNT_DATA/EAOS/storage"
    sudo mkdir -p "$MOUNT_DATA/EAOS/logs"

    # Copy manifest
    sudo cp "$MANIFEST" "$MOUNT_DATA/EAOS/manifests/sovereign_health.json"
    log_ok "Installed sovereign_health.json"

    # Create version marker
    echo "EAOS Sovereign Health Pod v1.0.0" | sudo tee "$MOUNT_DATA/EAOS/VERSION" > /dev/null
    echo "Built: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | sudo tee -a "$MOUNT_DATA/EAOS/VERSION" > /dev/null
    echo "Braid Magic: 0xB8AD" | sudo tee -a "$MOUNT_DATA/EAOS/VERSION" > /dev/null

    sudo umount "$MOUNT_DATA"
    sudo losetup -d "$LOOP_DATA"
    LOOP_DATA=""

    log_ok "Disk image populated successfully"
else
    log_warn "No sudo access - creating minimal image without filesystem population"
    log_warn "Run with sudo to fully populate the disk image"
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
log "========================================="
log "EAOS Disk Image Created Successfully"
log "========================================="
log "Output: $DISK_IMAGE"
log "Size: ${DISK_SIZE_MB}MB"
log "Partitions:"
log "  1. EFI System Partition (${ESP_SIZE_MB}MB)"
log "  2. EAOS Data Partition (${DATA_SIZE_MB}MB)"
echo ""

if [ "$HAS_EFI" = "1" ]; then
    log_ok "Ready for boot testing with QEMU"
else
    log_warn "No EFI binary - build referee-kernel first"
fi

exit 0
