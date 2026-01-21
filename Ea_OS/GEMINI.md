# EAOS (Eä OS) Project Context

## Project Overview
EAOS is a sovereign, biological, modular operating system written primarily in Rust. It utilizes a biological metaphor to organize its components into "Muscles" (Kernel/Drivers) and "Organs" (Userspace Agents), aiming for a secure, capability-based execution environment where data is "braided" and ethically governed.

**Current Version:** v1.0 "Sovereign Pod"
**Target Architecture:** x86_64 UEFI (Bare Metal) / QEMU

## Architecture & Anatomy
The system follows a strict biological hierarchy:

| Component | Biological Role | Path | Description |
|-----------|-----------------|------|-------------|
| **Referee** | Brain | `muscles/referee-kernel` | UEFI Bootloader & Micro-kernel. |
| **PermFS** | Skeleton | `permfs/` | Crash-proof distributed filesystem with 256-bit addressing. |
| **Bridge** | Nerves | `muscles/permfs-bridge` | Syscall interface & Braid integration. |
| **Roulette** | Reflexes | `muscles/roulette-rs` | T9-Braid Compression (High ratio). |
| **Dr-Lex** | Immune System | `intelligence/dr-lex` | Governance engine; blocks unethical writes. |
| **Organs** | Organs | `organs/` | Userspace agents (e.g., `biowerk-agent`, `cardio`). |
| **Muscle Compiler**| Growth | `muscle-compiler/` | Transforms NN definitions into isolated executables. |

### Core Principles
1.  **Sovereignty:** Users own their data and compute.
2.  **Biological Design:** Modular, resilient components that interact organically.
3.  **Governance:** Ethical rules embedded in the OS (e.g., "No unencrypted data on disk").
4.  **Security:** Capability-based isolation; minimal Trusted Computing Base (TCB).
5.  **Code Integrity:** NO placeholders. NO stubs. NO mock code. Always production-grade, real code. If innovation is required to solve a problem, consult the head innovators (Deep Thinkers).

## Build & Operations

### Prerequisites
- Rust Toolchain (Stable/Nightly)
- QEMU & OVMF (for UEFI emulation)
- `pkg-config`, `fuse` (for PermFS FUSE support)

### Key Commands
- **Build Entire OS:**
  ```bash
  ./scripts/build-all.sh
  ```
- **Run Emulator (QEMU):**
  ```bash
  ./run-eaos.sh
  ```
- **Generate ISO:**
  ```bash
  ./scripts/make-iso.sh
  ```
- **Run Tests:**
  ```bash
  cargo test --workspace
  ```
  *(Note: Check `STATUS_*.md` for known failing tests)*

## Development Conventions
- **Rust Edition:** 2021
- **Kernel Code:** Strict `no_std` for `referee` and core muscles.
- **Formatting:** `rustfmt` is mandatory.
- **Workspaces:** Managed via root `Cargo.toml`.
- **Governance:**
    - **Rule 1:** No unencrypted data touches the disk.
    - **Rule 2:** All writes must pass the `is_ethically_corrupt()` check.
- **Technical Precision:** Avoid biological metaphors in technical documentation. Use standard computer science terminology (e.g., "Kernel" instead of "Brain", "IPC" instead of "Synapse").

## Key Documentation Files
- **`EAOS_CONTEXT.md`**: High-level context, biological metaphors, and current goals.
- **`ARCHITECTURE.md`**: Technical architecture, cryptographic principles, and TCB details.
- **`permfs/GEMINI.md`**: Specific documentation for the PermFS subsystem.
- **`STATUS_*.md`**: Latest status reports and known issues (e.g., `STATUS_20251229_141039.md`).

## Current Focus (as of late 2025/early 2026)
- Transitioning `biowerk-agent` from a healthcare demo to a generic Sovereign Office Suite.
- Ensuring strict cryptographic binding (ChaCha20-Poly1305).
- stabilizing the `permfs` bridge and `referee` boot process.
