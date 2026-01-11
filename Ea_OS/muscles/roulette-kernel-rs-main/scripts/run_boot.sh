#!/bin/bash
# Copyright © 2025 Everplay-Tech
# Automates Roulette Kernel build → image → QEMU run while capturing logs.

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
LOG_DIR="$ROOT_DIR/logs"
TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
RUN_DIR="$LOG_DIR/$TIMESTAMP"
KERNEL_TARGET_DIR="$ROOT_DIR/target/x86_64-unknown-none/release"
KERNEL_BIN="$KERNEL_TARGET_DIR/roulette-kernel"
BOOT_BIN="$ROOT_DIR/bootloader/src/boot.bin"
IMG_PATH="$RUN_DIR/roulette-os.img"
SERIAL_LOG="$RUN_DIR/serial.log"
QEMU_LOG="$RUN_DIR/qemu.log"
META_JSON="$RUN_DIR/run.json"

mkdir -p "$RUN_DIR"
mkdir -p "$LOG_DIR"

echo "[boot] ⏱  Timestamp: $TIMESTAMP"

echo "[boot] 🧱 Building kernel (release, x86_64-unknown-none)..."
cargo build --package roulette-kernel --target x86_64-unknown-none --release

echo "[boot] 🪛 Assembling boot sector (nasm)..."
if ! command -v nasm >/dev/null 2>&1; then
  echo "[boot] ❌ nasm not found; install it before running this script." >&2
  exit 1
fi
nasm -f bin -o "$BOOT_BIN" "$ROOT_DIR/bootloader/src/boot.asm"

if [ ! -f "$KERNEL_BIN" ]; then
  echo "[boot] ❌ Kernel binary missing: $KERNEL_BIN" >&2
  exit 1
fi

if [ ! -f "$BOOT_BIN" ]; then
  echo "[boot] ❌ Boot sector missing: $BOOT_BIN" >&2
  exit 1
fi

echo "[boot] 💾 Creating fresh disk image..."
dd if=/dev/zero of="$IMG_PATH" bs=512 count=2880 status=none

echo "[boot] 🔗 Writing boot sector..."
dd if="$BOOT_BIN" of="$IMG_PATH" bs=512 count=1 conv=notrunc status=none

echo "[boot] 🧶 Writing kernel payload..."
dd if="$KERNEL_BIN" of="$IMG_PATH" bs=512 seek=1 conv=notrunc status=none

if ! command -v qemu-system-x86_64 >/dev/null 2>&1; then
  echo "[boot] ❌ qemu-system-x86_64 not found; install QEMU before running this script." >&2
  exit 1
fi

echo "[boot] 🚀 Launching QEMU (serial→$SERIAL_LOG, qemu log→$QEMU_LOG)..."
set +e
qemu-system-x86_64 \
  -drive file="$IMG_PATH",format=raw,if=floppy \
  -boot a \
  -serial "file:$SERIAL_LOG" \
  -d guest_errors,int,cpu_reset \
  -D "$QEMU_LOG" \
  -no-reboot -no-shutdown \
  -m 64 -smp 1 \
  -display none
QEMU_STATUS=$?
set -e

echo "[boot] 🧾 Recording metadata..."
cat >"$META_JSON" <<JSON
{
  "timestamp": "$TIMESTAMP",
  "kernel_binary": "$KERNEL_BIN",
  "boot_binary": "$BOOT_BIN",
  "image_path": "$IMG_PATH",
  "serial_log": "$SERIAL_LOG",
  "qemu_log": "$QEMU_LOG",
  "qemu_exit_code": $QEMU_STATUS
}
JSON

echo "[boot] ✅ Run complete (exit code: $QEMU_STATUS). Logs in $RUN_DIR"
