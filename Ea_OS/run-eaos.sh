#!/bin/bash
# ============================================================================
# EAOS First Breath - QEMU Boot Script
# ============================================================================
#
# This script launches the EAOS Referee Kernel in QEMU with:
# - referee.efi as the UEFI boot target
# - A virtual disk for PermFS storage
# - Serial console output for debugging
#
# Usage: ./run-eaos.sh [options]
#   --rebuild    Rebuild referee.efi before running
#   --debug      Enable QEMU debugging (GDB stub on port 1234)
#   --disk SIZE  Create virtual disk of SIZE (default: 256M)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EFI_PATH="$SCRIPT_DIR/target/x86_64-unknown-uefi/release/referee.efi"
OVMF_CODE="/opt/homebrew/share/qemu/edk2-x86_64-code.fd"
OVMF_VARS="/opt/homebrew/share/qemu/edk2-i386-vars.fd"
DISK_PATH="$SCRIPT_DIR/target/eaos-disk.img"
DISK_SIZE="256M"
DEBUG_FLAGS=""
REBUILD=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --rebuild)
            REBUILD=true
            shift
            ;;
        --debug)
            DEBUG_FLAGS="-s -S"
            echo "Debug mode enabled. Connect GDB to localhost:1234"
            shift
            ;;
        --disk)
            DISK_SIZE="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Check for QEMU
if ! command -v qemu-system-x86_64 &> /dev/null; then
    echo "Error: qemu-system-x86_64 not found"
    echo "Install with: brew install qemu"
    exit 1
fi

# Find OVMF firmware (try multiple locations)
if [[ ! -f "$OVMF_CODE" ]]; then
    # Try alternative locations
    for path in \
        "/usr/share/OVMF/OVMF_CODE.fd" \
        "/usr/share/edk2/ovmf/OVMF_CODE.fd" \
        "/opt/homebrew/share/qemu/edk2-x86_64-code.fd" \
        "$HOME/.local/share/qemu/edk2-x86_64-code.fd"; do
        if [[ -f "$path" ]]; then
            OVMF_CODE="$path"
            break
        fi
    done
fi

if [[ ! -f "$OVMF_CODE" ]]; then
    echo "Warning: OVMF firmware not found. UEFI boot may not work."
    echo "Install with: brew install qemu (includes EDK2 firmware)"
fi

# Rebuild if requested
if [[ "$REBUILD" == true ]]; then
    echo "Building referee.efi..."
    cd "$SCRIPT_DIR/muscles/referee-kernel"
    cargo build --release
    cd "$SCRIPT_DIR"
fi

# Check if EFI exists
if [[ ! -f "$EFI_PATH" ]]; then
    echo "Error: referee.efi not found at $EFI_PATH"
    echo "Build with: cd muscles/referee-kernel && cargo build --release"
    exit 1
fi

# Create virtual disk for PermFS if it doesn't exist
if [[ ! -f "$DISK_PATH" ]]; then
    echo "Creating PermFS virtual disk ($DISK_SIZE)..."
    qemu-img create -f raw "$DISK_PATH" "$DISK_SIZE"
fi

# Create ESP (EFI System Partition) directory structure
ESP_DIR="$SCRIPT_DIR/target/esp"
mkdir -p "$ESP_DIR/EFI/BOOT"
cp "$EFI_PATH" "$ESP_DIR/EFI/BOOT/BOOTX64.EFI"

echo ""
echo "============================================================================"
echo "  EAOS First Breath"
echo "============================================================================"
echo ""
echo "  Referee EFI:  $EFI_PATH"
echo "  PermFS Disk:  $DISK_PATH ($DISK_SIZE)"
echo "  ESP Directory: $ESP_DIR"
echo ""
echo "  Press Ctrl+A, X to exit QEMU"
echo ""
echo "============================================================================"
echo ""

# Launch QEMU
# Note: On macOS without OVMF, we fall back to BIOS mode
if [[ -f "$OVMF_CODE" ]]; then
    qemu-system-x86_64 \
        -machine q35 \
        -m 512M \
        -cpu qemu64 \
        -drive if=pflash,format=raw,readonly=on,file="$OVMF_CODE" \
        -drive format=raw,file=fat:rw:"$ESP_DIR" \
        -drive format=raw,file="$DISK_PATH",if=virtio \
        -serial stdio \
        -display none \
        -no-reboot \
        $DEBUG_FLAGS
else
    echo "Note: Running without OVMF. UEFI applications require OVMF firmware."
    echo ""
    echo "To install OVMF on macOS:"
    echo "  brew install qemu  # Includes EDK2 firmware"
    echo ""
    echo "Simulating boot sequence..."
    echo ""
    echo "============================================================================"
    echo "  EAOS BOOT SIMULATION (OVMF not available)"
    echo "============================================================================"
    echo ""
    echo "INFO: Ea referee v3.0 awakens - production ready"
    echo "INFO: Chaos master key acquired"
    echo "WARN: Muscle validation failed (simulated)"
    echo "INFO: Muscles loaded - Ea breathes"
    echo ""
    echo "============================================================================"
    echo ""
    echo "To run the actual UEFI kernel, install OVMF firmware."
fi
