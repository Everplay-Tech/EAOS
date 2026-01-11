#!/bin/bash

set -e

echo "🧬 Building Eä Nucleus System"

# Configuration
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MUSCLES_DIR="$ROOT_DIR/muscles"
COMPILER_DIR="$ROOT_DIR/muscle-compiler"
BUNDLES_DIR="$ROOT_DIR/bundles"
TARGET_DIR="$ROOT_DIR/target"
TARGET="aarch64"
PRELOADER_TARGETS=("aarch64-unknown-uefi" "x86_64-unknown-uefi")
SYSROOT="$(rustc --print sysroot)"
HOST_TRIPLE="$(rustc -vV | awk '/host:/ {print $2}')"
LLVM_BIN="$SYSROOT/lib/rustlib/$HOST_TRIPLE/bin"
LLVM_AR="$LLVM_BIN/llvm-ar"
LLVM_OBJCOPY="$LLVM_BIN/llvm-objcopy"
RUST_LLD="$LLVM_BIN/rust-lld"

# Create bundles directory
mkdir -p "$BUNDLES_DIR"

echo "🔨 Step 1: Building enhanced muscle compiler..."
cd "$COMPILER_DIR"
cargo build --release
cd "$ROOT_DIR"

if [ ! -x "$LLVM_AR" ] || [ ! -x "$LLVM_OBJCOPY" ] || [ ! -x "$RUST_LLD" ]; then
    echo "❌ Missing LLVM tools in $LLVM_BIN"
    echo "   Install with: rustup component add llvm-tools-preview"
    exit 1
fi

echo "🔨 Step 2: Compiling nucleus.ea to sealed blob..."
MUSCLEC_BIN="$TARGET_DIR/release/musclec"
if [ ! -x "$MUSCLEC_BIN" ]; then
    echo "❌ musclec not found at $MUSCLEC_BIN"
    exit 1
fi
 "$MUSCLEC_BIN" \
    --input "$MUSCLES_DIR/nucleus.ea" \
    --target "$TARGET" \
    --output "$BUNDLES_DIR/nucleus.blob" \
    --chaos-master $(openssl rand -hex 32)

# Verify nucleus blob size
NUCLEUS_SIZE=$(stat -f%z "$BUNDLES_DIR/nucleus.blob" 2>/dev/null || stat -c%s "$BUNDLES_DIR/nucleus.blob")
if [ "$NUCLEUS_SIZE" -ne 8256 ]; then
    echo "❌ Nucleus blob size incorrect: $NUCLEUS_SIZE bytes (expected 8256)"
    exit 1
fi
echo "✅ Nucleus blob: $NUCLEUS_SIZE bytes"

echo "🔐 Step 2b: Pinning nucleus blob hash..."
NUCLEUS_HASH_HEX=$(cargo run --offline -q -p muscle-contract --bin hash-blob -- "$BUNDLES_DIR/nucleus.blob")
echo "✅ Nucleus hash: $NUCLEUS_HASH_HEX"

echo "🔨 Step 3: Building pre-nucleus loader (static blob)..."
cd "$MUSCLES_DIR/preloader"
for PRELOADER_TARGET in "${PRELOADER_TARGETS[@]}"; do
    echo "   - target: $PRELOADER_TARGET"
    EXPECTED_NUCLEUS_HASH_HEX=$NUCLEUS_HASH_HEX cargo build --offline --target "$PRELOADER_TARGET" --release
    PRELOADER_ARCHIVE="$TARGET_DIR/$PRELOADER_TARGET/release/libpreloader.a"
    if [ ! -f "$PRELOADER_ARCHIVE" ]; then
        echo "❌ Pre-loader archive missing: $PRELOADER_ARCHIVE"
        exit 1
    fi
    ARCH_TAG="${PRELOADER_TARGET%%-*}"
    cp "$PRELOADER_ARCHIVE" "$BUNDLES_DIR/preloader.${ARCH_TAG}.a"

    PRELOADER_TMP="$(mktemp -d)"
    (
        cd "$PRELOADER_TMP"
        "$LLVM_AR" x "$PRELOADER_ARCHIVE"
        OBJ_FILES=(*.o)
        if [ "${#OBJ_FILES[@]}" -eq 0 ]; then
            echo "❌ No object files extracted from $PRELOADER_ARCHIVE"
            exit 1
        fi
        PRELOADER_EFI="$PRELOADER_TMP/preloader.${ARCH_TAG}.efi"
        "$RUST_LLD" -flavor link /NOLOGO /NODEFAULTLIB /SUBSYSTEM:EFI_APPLICATION /ENTRY:entry_point /BASE:0 /OUT:"$PRELOADER_EFI" "${OBJ_FILES[@]}"
        PRELOADER_BIN="$BUNDLES_DIR/preloader.${ARCH_TAG}.bin"
        "$LLVM_OBJCOPY" -O binary --strip-all --remove-section=.eh_fram --remove-section=.reloc "$PRELOADER_EFI" "$PRELOADER_BIN"
        PRELOADER_BIN_SIZE=$(stat -f%z "$PRELOADER_BIN" 2>/dev/null || stat -c%s "$PRELOADER_BIN")
        if [ "$PRELOADER_BIN_SIZE" -gt 2048 ]; then
            echo "❌ Pre-loader blob exceeds 2KiB: $PRELOADER_BIN_SIZE bytes"
            exit 1
        fi
        echo "✅ Pre-loader blob: preloader.${ARCH_TAG}.bin ($PRELOADER_BIN_SIZE bytes)"
    )
    rm -rf "$PRELOADER_TMP"
done
cd "$ROOT_DIR"

echo "🔨 Step 4: Creating boot bundle..."

echo "🎉 Nucleus build complete!"
echo "📦 Boot bundle created in $BUNDLES_DIR/:"
echo "   - preloader.a (static archive, per-arch)"
echo "     - preloader.aarch64.a"
echo "     - preloader.x86_64.a"
echo "   - preloader.bin (raw loader blob, per-arch)"
echo "     - preloader.aarch64.bin"
echo "     - preloader.x86_64.bin"
echo "   - nucleus.blob (8.06KiB sealed muscle blob)"
