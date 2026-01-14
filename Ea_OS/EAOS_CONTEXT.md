# EAOS: The Sovereign Operating System (Context & Architecture)

**Current Version:** v1.0 "Sovereign Pod"
**Target Architecture:** x86_64 UEFI (Bare Metal) / QEMU
**Core Philosophy:** A biological, modular OS where data is mathematically braided and ethically governed before storage.

---

## System Anatomy

The OS is organized into "Muscles" (Kernel/Drivers) and "Organs" (Userspace Agents).

| Component | Path | Function | Status |
|-----------|------|----------|--------|
| Brain | `muscles/referee-kernel` | UEFI Bootloader & Micro-kernel | :green_circle: Bootable (`referee.efi`) |
| Skeleton | `permfs` | Crash-proof FS with 256-bit addressing | :green_circle: Stable |
| Nerves | `muscles/permfs-bridge` | Syscall interface & Braid integration | :green_circle: Linked |
| Reflexes | `muscles/roulette-rs` | T9-Braid Compression (7.9% ratio) | :green_circle: Ported to Rust |
| Immune | `intelligence/dr-lex` | Governance engine. Blocks unethical writes | :green_circle: Active Hook |
| Organs | `organs/biowerk-agent` | Office Suite (formerly Healthcare) | :yellow_circle: Needs Expansion |
| Circulation | `IHP-main` | Secure Capsule Protocol | :yellow_circle: Needs Cleanup |

---

## Build & Deployment

**Build Entire OS:**
```bash
./scripts/build-all.sh
```

**Generate ISO:**
```bash
./scripts/make-iso.sh
# Output: dist/eaos-health-pod.iso
```

**Run Emulator:**
```bash
./run-eaos.sh
# Requires QEMU + OVMF
```

**QEMU Manual (Linux with KVM):**
```bash
qemu-system-x86_64 -enable-kvm -m 512M \
  -bios /usr/share/OVMF/OVMF_CODE.fd \
  -cdrom dist/eaos-health-pod.iso \
  -serial stdio
```

---

## The "Office Suite" Pivot

> **Constraint for AI:** The BIOwerk suite is NOT just for healthcare. It is a sovereign Office Suite (Docs, Sheets, Logic).

| Agent | Function |
|-------|----------|
| **Osteon** | Document handler (was Bones/Patient Records) |
| **Myocyte** | Logic/Compute handler |
| **Nucleus** | The Task Director (CLI/GUI entry point) |

---

## Data Flow Architecture

```
[Muscles] → syscall → [Referee Kernel] → [PermFS Bridge] → [PermFS Storage]
                             ↓
                      T9-Braid Transform
                      Magic: 0xB8AD
                      Compression: 7.9%
```

---

## Missing/Next Components

| Component | Status | Notes |
|-----------|--------|-------|
| **Symbiote** | Dormant | IPC middleware needs reactivation for Organ communication |
| **Quenyan** | Pending | OS language - Agents should speak QYN instead of raw binary |
| **Graphics** | Headless | Needs Framebuffer driver in referee-kernel |

---

## Governance Rules (Dr-Lex)

1. **Rule 1:** No unencrypted data touches the disk (PermFS)
2. **Rule 2:** All writes must pass the `is_ethically_corrupt()` check in permfs-bridge
3. **Rule 3:** System must survive a SIGKILL (Cataclysm) and replay from Journal

---

## Key Technical Details

### 256-bit Block Addressing (PermFS)
```rust
pub struct BlockAddr {
    pub high: u128,  // node_id (64) | volume_id (32) | shard_id (16)
    pub low: u128,   // block_offset (64) | reserved
}
```

### Braid Header Format
```
Offset  Size  Field
0       2     Magic (0xB8AD)
2       2     Compressed length
4       8     Gödel number (lower 64 bits)
12      N     Compressed data
```

### Bridge Result Codes
```rust
pub enum BridgeResult {
    Success = 0,
    InvalidAddress = -2,
    IoError = -3,
    PermissionDenied = -4,
    InvalidBuffer = -6,
    AuditBlocked = -10,  // Dr-Lex governance rejection
}
```

---

## How to Maintain Context Across Sessions

### 1. The ".cursorrules" File (For Editor AI)
Create `.cursorrules` in root and paste the System Anatomy table and Governance Rules.

### 2. The "Re-Injection" Prompt (For New Chats)
```
I am working on EAOS, a Rust-based Sovereign OS. We have completed Stage 7 (Manifestation).
The Kernel (referee.efi) boots, PermFS works, and Roulette-RS braids data at 7.9% compression.

Current Goal: Transform BIOwerk from a healthcare demo into a generic Sovereign Office Suite.

Reference: Please read the EAOS_CONTEXT.md file I am pasting below for architecture details.
```

### 3. CLI Session Context
```bash
tree -L 3 > file_structure.txt
# Feed this to the agent at session start
```

---

## Completed Stages

| Stage | Name | Deliverable |
|-------|------|-------------|
| 1 | Foundation | PermFS core, block device abstraction |
| 2 | Journaling | WAL + crash recovery |
| 3 | Directories | Hierarchical namespace |
| 4 | Permissions | Unix-style ACLs |
| 5 | Sparse Files | fallocate, hole detection |
| 6 | Governance | Dr-Lex integration, Sefirot chaos testing |
| 7 | Manifestation | BraidViewer dashboard, sovereign_health.json |
| 8 | Final Birthing | referee.efi boots, ISO created |

---

## Repository Structure

```
Ea_OS/
├── permfs/                 # Core filesystem
├── muscles/
│   ├── referee-kernel/     # UEFI bootloader
│   ├── permfs-bridge/      # Syscall bridge
│   └── roulette-rs/        # Braid compression
├── intelligence/
│   └── dr-lex/             # Governance engine
├── organs/
│   └── biowerk-agent/      # Office suite agents
├── manifests/
│   └── sovereign_health.json
├── scripts/
│   ├── build-all.sh
│   ├── make-iso.sh
│   └── make-disk.sh
└── dist/
    └── eaos-health-pod.iso
```

---

*Built by XZA (Magus) & CZA (Cipher). Wu-Tang style.*
