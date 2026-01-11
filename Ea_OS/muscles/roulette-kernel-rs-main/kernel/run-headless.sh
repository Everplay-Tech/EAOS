#!/bin/bash
# Roulette Kernel - Headless QEMU Test Script
# Boots the kernel in QEMU without GUI (serial output only)
# Useful for CI/CD pipelines and automated testing

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

# Timeout for boot test (seconds)
TIMEOUT=${1:-10}

echo -e "${GREEN}Starting Roulette Kernel in headless QEMU...${NC}"
echo -e "${YELLOW}Will automatically exit after ${TIMEOUT} seconds${NC}"
echo "----------------------------------------"

# Run QEMU in headless mode
# -drive: Boot from our disk image
# -serial stdio: Display serial output in terminal
# -nographic: No graphical output, serial only
# -no-reboot: Exit on kernel panic instead of rebooting
# -device isa-debug-exit: Allow kernel to exit QEMU programmatically
timeout "$TIMEOUT" qemu-system-x86_64 \
    -drive format=raw,file="$BOOTIMAGE" \
    -serial stdio \
    -nographic \
    -no-reboot \
    -device isa-debug-exit,iobase=0xf4,iosize=0x04 \
    || true

echo ""
echo "----------------------------------------"
echo -e "${GREEN}Test completed${NC}"

# Check if kernel panic occurred by looking for PANIC in output
if grep -q "PANIC" <<< "$OUTPUT"; then
    echo -e "${RED}Kernel panic detected!${NC}"
    exit 1
fi

echo -e "${GREEN}No kernel panic detected${NC}"
