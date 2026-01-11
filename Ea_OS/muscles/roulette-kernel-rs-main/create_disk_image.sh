#!/bin/bash

# Topos-Theoretic Disk Image Creator
# This implements the universal property of the bootable image functor
# F: (Bootloader × Kernel) → DiskImage

set -e

echo "🔧 Creating topos-theoretic bootable disk image..."

# Build the kernel
echo "📦 Building Roulette Kernel..."
cargo build --package roulette-kernel --target x86_64-unknown-none --release

# Get the kernel binary
KERNEL_BINARY="target/x86_64-unknown-none/release/roulette-kernel"
BOOT_SECTOR="bootloader/src/boot.bin"
DISK_IMAGE="roulette-os.img"

# Check if files exist
if [ ! -f "$KERNEL_BINARY" ]; then
    echo "❌ Kernel binary not found: $KERNEL_BINARY"
    exit 1
fi

if [ ! -f "$BOOT_SECTOR" ]; then
    echo "❌ Boot sector not found: $BOOT_SECTOR"
    exit 1
fi

# Create disk image (1.44MB floppy size for simplicity)
echo "💾 Creating disk image..."
dd if=/dev/zero of="$DISK_IMAGE" bs=512 count=2880

# Write boot sector to first sector
echo "🔗 Installing bootloader (geometric morphism)..."
dd if="$BOOT_SECTOR" of="$DISK_IMAGE" bs=512 count=1 conv=notrunc

# Write kernel to second sector onward
echo "🧶 Installing kernel (sheaf pullback)..."
dd if="$KERNEL_BINARY" of="$DISK_IMAGE" bs=512 seek=1 conv=notrunc

echo "✅ Topos-theoretic bootable disk image created: $DISK_IMAGE"
echo "📊 Image size: $(stat -f%z "$DISK_IMAGE") bytes"
echo ""
echo "🎯 Ready for execution in the braid-T9-Gödel topos!"
echo "💡 Run: qemu-system-x86_64 -drive format=raw,file=$DISK_IMAGE"