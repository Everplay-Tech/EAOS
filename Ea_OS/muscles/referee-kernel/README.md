# Referee v3.0.0

Secure UEFI bootloader with capability-based isolation for muscle components.

## Features

- Secure UEFI boot process
- Cryptographic capability system using BLAKE3
- Memory isolation between components
- Audit logging and metrics
- Graceful error recovery

## Building

```bash
cargo build --target x86_64-unknown-uefi --release
