# Roulette Kernel - Bootable Image

This directory contains the Roulette Kernel, a verified braid-theoretic operating system that boots on bare metal x86_64 hardware.

## Features

- **Braid CPU**: 4-strand verified braid-theoretic CPU with mathematical guarantees
- **VGA Text Mode**: 80x25 color text display with scrolling support
- **Serial Output**: COM1 UART debugging interface
- **Bare Metal**: Runs directly on hardware without host OS
- **Zero Dependencies**: Pure Rust kernel with no external dependencies

## Prerequisites

### Required
- Rust nightly toolchain (already configured in project)
- `rust-src` component: `rustup component add rust-src`
- `llvm-tools-preview` component: `rustup component add llvm-tools-preview`
- `bootimage` tool: `cargo install bootimage`

### Optional (for testing)
- QEMU x86_64 emulator:
  - Ubuntu/Debian: `sudo apt install qemu-system-x86`
  - Fedora/RHEL: `sudo dnf install qemu-system-x86`
  - Arch Linux: `sudo pacman -S qemu-system-x86`
  - macOS: `brew install qemu`

## Building

### Build the kernel binary
```bash
cargo build
```

This compiles the kernel for the `x86_64-unknown-none` target with `core` and `compiler_builtins` built from source.

### Build the bootable disk image
```bash
cargo bootimage
```

This creates a bootable disk image at:
```
../target/x86_64-unknown-none/debug/bootimage-roulette-kernel.bin
```

The image includes:
- Bootloader stage 1 (BIOS boot sector)
- Bootloader stage 2 (kernel loader)
- Roulette kernel binary

## Running

### Run in QEMU (with GUI)
```bash
./run.sh
```

This will:
- Display VGA output in a GTK window
- Show serial output in your terminal
- Exit with Ctrl+C or by closing the window

### Run in QEMU (headless)
```bash
./run-headless.sh [timeout_seconds]
```

This will:
- Display only serial output (no GUI)
- Automatically exit after timeout (default: 10 seconds)
- Useful for CI/CD pipelines and automated testing

### Run on real hardware
1. Write the bootimage to a USB drive:
   ```bash
   sudo dd if=../target/x86_64-unknown-none/debug/bootimage-roulette-kernel.bin \
           of=/dev/sdX bs=1M status=progress
   ```
   **WARNING**: Replace `/dev/sdX` with your actual USB device. This will erase all data on the drive.

2. Boot from the USB drive:
   - Insert USB into target machine
   - Enter BIOS/UEFI settings (usually F2, F12, or Del during boot)
   - Set USB as first boot device
   - Save and reboot

## Expected Output

When the kernel boots, you should see:

### VGA Display (Color)
```
╔════════════════════════════════════════════════════════════════════════════╗
║                    ROULETTE KERNEL - Braid CPU OS                          ║
║                    Verified Braid-Theoretic Computing                      ║
╚════════════════════════════════════════════════════════════════════════════╝

Initializing Braid CPU (4 strands)...
Testing braid operations...
  Register 0 test: 42 (expected: 42)
  ✓ CPU test PASSED

Kernel initialized successfully.
Entering idle loop...
```

### Serial Output (COM1)
```
Roulette Kernel booting...
[BOOT] VGA text mode initialized
[BOOT] Serial port COM1 initialized
[BOOT] Braid CPU initialized with 4 strands
[TEST] Braid CPU register test: value=42
[TEST] CPU test PASSED
[BOOT] Kernel initialized, entering idle loop
```

## Architecture

### Memory Layout
- `0xb8000`: VGA text buffer (80x25 characters, 2 bytes each)
- `0x3F8`: COM1 serial port base address
- Kernel loaded at address specified by bootloader

### Initialization Sequence
1. Bootloader loads kernel into memory
2. Bootloader jumps to `_start` entry point
3. Kernel initializes VGA buffer and serial port
4. Kernel creates BraidCPUState with 4 strands
5. Kernel performs self-test (register write/read)
6. Kernel enters idle HLT loop

### Panic Handling
If a kernel panic occurs:
- Error message displayed on VGA screen
- Error details sent to serial port
- System halts (no reboot)

## Troubleshooting

### Build fails with "rust-src not found"
```bash
rustup component add rust-src
```

### Build fails with "llvm-tools not found"
```bash
rustup component add llvm-tools-preview
```

### cargo bootimage fails with "bootimage not found"
```bash
cargo install bootimage
```

### QEMU window doesn't appear
- Ensure QEMU is installed: `qemu-system-x86_64 --version`
- Try headless mode: `./run-headless.sh`
- Check if GTK display is available

### No serial output in QEMU
- Ensure you're using `./run.sh` or `./run-headless.sh`
- Check that `-serial stdio` flag is present
- Verify COM1 initialization in kernel logs

### Kernel panic on boot
- Check serial output for panic message
- Verify bootimage was built successfully
- Ensure target is `x86_64-unknown-none`
- Check `.cargo/config.toml` configuration

## Development

### Adding new features
1. Modify kernel source in `src/`
2. Rebuild: `cargo bootimage`
3. Test in QEMU: `./run.sh`

### Debugging
- Enable QEMU interrupt debugging: add `-d int` to run script
- Use serial output for debugging: `serial_println!("debug message")`
- VGA output for user-visible messages: `println!("message")`

### Testing
- Unit tests: Not applicable (no_std kernel)
- Integration tests: Use QEMU with `run-headless.sh`
- Hardware tests: Boot on real hardware

## Files

- `src/main.rs`: Kernel entry point and initialization
- `src/vga_buffer.rs`: VGA text mode driver
- `src/serial.rs`: Serial port (COM1) driver
- `Cargo.toml`: Kernel dependencies and configuration
- `run.sh`: QEMU boot script (GUI)
- `run-headless.sh`: QEMU boot script (headless)

## License

Copyright © 2025 Everplay-Tech. All rights reserved.
Proprietary and confidential. Not open source.
