#!/bin/bash
# Roulette Kernel - QEMU Boot Script
# Boots the kernel in QEMU and displays VGA + serial output

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if QEMU is installed
if ! command -v qemu-system-x86_64 &> /dev/null; then
    echo -e "${RED}Error: qemu-system-x86_64 not found${NC}"
    echo "Please install QEMU:"
    echo "  Ubuntu/Debian: sudo apt install qemu-system-x86"
    echo "  Fedora/RHEL:   sudo dnf install qemu-system-x86"
    echo "  Arch:          sudo pacman -S qemu-system-x86"
    exit 1
fi

# Path to bootimage
BOOTIMAGE="../target/x86_64-unknown-none/debug/bootimage-roulette-kernel.bin"

# Check if bootimage exists
if [ ! -f "$BOOTIMAGE" ]; then
    echo -e "${RED}Error: Bootimage not found at $BOOTIMAGE${NC}"
    echo "Please run 'cargo bootimage' first"
    exit 1
fi

echo -e "${GREEN}Starting Roulette Kernel in QEMU...${NC}"
echo -e "${YELLOW}Serial output will appear below${NC}"
echo -e "${YELLOW}VGA output will appear in QEMU window${NC}"
echo "----------------------------------------"

# Run QEMU with the bootimage
# -drive: Boot from our disk image
# -serial stdio: Display serial output in terminal
# -display gtk: Use GTK window for VGA display
# -no-reboot: Exit on kernel panic instead of rebooting
# -d int: Debug interrupts (uncomment for debugging)
qemu-system-x86_64 \
    -drive format=raw,file="$BOOTIMAGE" \
    -serial stdio \
    -display gtk \
    -no-reboot

echo "----------------------------------------"
echo -e "${GREEN}QEMU exited${NC}"
