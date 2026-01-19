#!/bin/bash
#
# EAOS QEMU Launch Script
# Phase 4: Full network and IVSHMEM configuration
#
# Usage:
#   ./run_qemu.sh              # Normal mode
#   ./run_qemu.sh --debug      # With GDB stub
#   ./run_qemu.sh --no-gui     # Serial-only mode
#

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TARGET_DIR="${PROJECT_ROOT}/muscles/referee-kernel/target/x86_64-unknown-uefi/debug"
EFI_BINARY="${TARGET_DIR}/referee-kernel.efi"

# OVMF firmware paths (try common locations)
OVMF_CODE=""
for path in \
    "/opt/homebrew/share/qemu/edk2-x86_64-code.fd" \
    "/usr/share/OVMF/OVMF_CODE.fd" \
    "/usr/share/qemu/OVMF_CODE.fd" \
    "/usr/local/share/qemu/edk2-x86_64-code.fd"; do
    if [ -f "$path" ]; then
        OVMF_CODE="$path"
        break
    fi
done

if [ -z "$OVMF_CODE" ]; then
    echo "ERROR: OVMF firmware not found"
    echo "Install with: brew install qemu (macOS) or apt install ovmf (Linux)"
    exit 1
fi

# Check for EFI binary
if [ ! -f "$EFI_BINARY" ]; then
    echo "ERROR: EFI binary not found at $EFI_BINARY"
    echo "Run: cargo build first"
    exit 1
fi

# Create ESP structure
ESP_DIR="/tmp/eaos_esp"
mkdir -p "${ESP_DIR}/EFI/BOOT"
cp "$EFI_BINARY" "${ESP_DIR}/EFI/BOOT/BOOTX64.EFI"

# IVSHMEM shared memory setup
IVSHMEM_PATH="/dev/shm/eaos_biostream"
IVSHMEM_SIZE="64K"

# Create IVSHMEM file if it doesn't exist
if [ ! -f "$IVSHMEM_PATH" ]; then
    echo "Creating IVSHMEM file: $IVSHMEM_PATH"
    # Create a 64KB file filled with zeros
    dd if=/dev/zero of="$IVSHMEM_PATH" bs=1024 count=64 2>/dev/null
    chmod 666 "$IVSHMEM_PATH"
fi

# Parse arguments
DEBUG_OPTS=""
DISPLAY_OPTS="-display sdl"
EXTRA_OPTS=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --debug)
            DEBUG_OPTS="-s -S"
            echo "GDB stub enabled on localhost:1234"
            shift
            ;;
        --no-gui)
            DISPLAY_OPTS="-nographic"
            shift
            ;;
        --trace-net)
            EXTRA_OPTS="${EXTRA_OPTS} -object filter-dump,id=netdump,netdev=net0,file=/tmp/eaos_net.pcap"
            echo "Network trace: /tmp/eaos_net.pcap"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--debug] [--no-gui] [--trace-net]"
            exit 1
            ;;
    esac
done

echo "========================================"
echo "  EAOS QEMU Launch"
echo "========================================"
echo "  ESP:      ${ESP_DIR}"
echo "  OVMF:     ${OVMF_CODE}"
echo "  IVSHMEM:  ${IVSHMEM_PATH}"
echo "========================================"

# Launch QEMU
exec qemu-system-x86_64 \
    -machine q35 \
    -cpu qemu64 \
    -m 256M \
    \
    `# UEFI Firmware` \
    -drive if=pflash,format=raw,readonly=on,file="${OVMF_CODE}" \
    \
    `# EFI System Partition` \
    -drive format=raw,file=fat:rw:${ESP_DIR} \
    \
    `# ========================================` \
    `# VIRTIO NETWORK (SLIRP - User Mode)` \
    `# ========================================` \
    `# Guest IP: 10.0.2.15` \
    `# Gateway:  10.0.2.2` \
    `# DNS:      10.0.2.3` \
    `# ========================================` \
    -device virtio-net-pci,netdev=net0,mac=52:54:00:12:34:56 \
    -netdev user,id=net0,hostfwd=tcp::2222-:22 \
    \
    `# ========================================` \
    `# IVSHMEM (Inter-VM Shared Memory)` \
    `# ========================================` \
    `# Maps /dev/shm/eaos_biostream into guest` \
    `# bio-bridge tool reads this file directly` \
    `# ========================================` \
    -device ivshmem-plain,memdev=biostream \
    -object memory-backend-file,size=${IVSHMEM_SIZE},share=on,mem-path=${IVSHMEM_PATH},id=biostream \
    \
    `# Serial Console (UART)` \
    -serial stdio \
    \
    `# Display` \
    ${DISPLAY_OPTS} \
    \
    `# Optional: Debug and Extras` \
    ${DEBUG_OPTS} \
    ${EXTRA_OPTS}
