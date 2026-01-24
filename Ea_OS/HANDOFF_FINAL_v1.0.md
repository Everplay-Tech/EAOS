# EAOS v1.0: The Sovereign Pod - Final Handoff

**Date:** 2026-01-20
**Status:** GOLDEN MASTER (Feature Complete)
**Architect:** Gemini (Builder)

---

## 1. Executive Summary

EAOS (Eä Operating System) is a **biologically inspired, sovereign operating system**. It reimagines the computer not as a machine, but as a living organism.

-   **The Nucleus (Userspace):** The "Will" of the user. It is single-threaded, deterministic, and isolated.
-   **The Referee (Kernel):** The "Autonomic Nervous System." It manages hardware (network, disk, scheduling) but cannot disobey the Nucleus's signed intents.
-   **Muscles (Modules):** Specialized, hot-swappable functional units (Broca for language, Myocyte for logic).

This codebase represents a complete, compiling, and tested kernel/userspace split running on **UEFI/x86_64**, capable of logic execution, network transmission/reception, and encrypted storage.

---

## 2. Architectural Map

```text
                  [ THE HIVE MIND (Network) ]
                           ▲   ▼
                           │   │ (TCP Port 9000)
                           │   │
┌──────────────────────────┼───┼──────────────────────────────┐
│  THE REFEREE (Kernel)    │   │   (Ring 0)                   │
│                          │   │                              │
│  [ Arachnid (Vascular) ]─┘   └─[ Receptor (Server) ]        │
│           │                                                 │
│           ▼ (BioStream Ring Buffer)                         │
│                                                             │
│  [ Scheduler (Adrenaline) ] <───> [ Tasks (Muscles) ]       │
│           │                                                 │
│           │ Context Switch                                  │
│           ▼                                                 │
└───────────┼─────────────────────────────────────────────────┘
            │ Syscall Interface (Bridge)
┌───────────┼─────────────────────────────────────────────────┐
│  THE NUCLEUS (Userspace)     (Ring 3 / Logical)             │
│                                                             │
│  [ Thalamus (Senses) ] ────> [ Endocrine System ]           │
│                                      │ (Pheromones)         │
│                                      ▼                      │
│  [ Visual Cortex ] <─────── [ THE NUCLEUS DIRECTOR ]        │
│                                      │                      │
│                                      ▼                      │
│  [ Broca (Parser) ] <── [ Myocyte (Logic) ] ──> [ Osteon ]  │
│                                      │              │       │
│                                      ▼              ▼       │
│  [ Sentry (Crypto) ] ─────────> [ Symbiote ] ──> [ PermFS ] │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Component Encyclopedia

### Core Systems
*   **`muscles/referee-kernel`**: The UEFI bootloader and kernel.
    *   **Scheduler**: Cooperative/Preemptive weighted round-robin.
    *   **Arachnid**: TCP/IP stack (`smoltcp`) and "Acid Bath" sanitizer.
    *   **Syscall**: System call handlers (File I/O, Net I/O, Yield).
*   **`intelligence/nucleus-director`**: The main userspace event loop.
    *   **Endocrine**: Double-buffered event bus (Systole/Diastole).
    *   **Thalamus**: Input multiplexer (UART + Network).
*   **`muscles/symbiote`**: The ABI/IPC layer. Defines `Pheromone` and `SynapticVesicle`.

### Muscles (Functional Units)
*   **`ea-broca`**: Zero-alloc command parser.
*   **`ea-quenyan`**: Logic Engine. Compiler (Recursive Descent) + VM (Register-based).
*   **`ea-sentry`**: Cryptographic key custody (Ed25519).
*   **`ea-mirror`**: Pre-execution simulation (Safety).
*   **`ea-mitochondria`**: Resource governance (Cycle counting).
*   **`ea-antibody`**: Heuristic Intrusion Detection & Fuzzer.
*   **`ea-dreamer`**: Background integrity checker.

---

## 4. The Life Cycle (Metabolic Loop)

The Nucleus runs in a strict cycle (`boot_entry` in `lib.rs`):

1.  **Systole (Circulation):** The Endocrine System swaps the "Secretion" buffer to the "Circulation" buffer.
2.  **Diastole (Reaction):** Organs read circulating pheromones and react.
    *   *Visual Cortex* draws status updates.
    *   *Myocyte* executes logic.
    *   *Osteon* writes to disk.
3.  **Secretion (Input):**
    *   *Thalamus* checks UART and Network (`Symbiote::poll_network`).
    *   New inputs are pushed to the "Secretion" buffer for the *next* tick.
4.  **Governance:** *Mitochondria* checks energy budget.
5.  **Rest:** Syscall `Yield` returns control to the Referee Scheduler.

---

## 5. Developer Guide

### Building
The project is a Cargo Workspace.
```bash
# Build Host Tools & Userspace (Test Mode)
cargo build --workspace --exclude referee-kernel

# Run Unit Tests (Logic, VM, Parser)
cargo test --workspace
```

### Running (Simulation)
Requires QEMU and OVMF.
```bash
./run-eaos.sh
```

### Writing Logic (Quenyan)
The `Myocyte` accepts mathematical formulas:
```rust
// In Nucleus Shell:
> logic profit "revenue - cost * 0.2"
```
The **Quenyan Compiler** will:
1.  Tokenize the string.
2.  Parse into expression tree.
3.  Emit Register-Based Bytecode.
4.  Execute on the VM (Result: stored in `SovereignBlob`).

### Network Interaction
The **Hive Mind** is bidirectional:
1.  **Harvest (Client):** `IntentOp::Harvest` -> Signs Intent -> `Syscall::SubmitRequest` -> `Arachnid` sends TCP packet.
2.  **Receptor (Server):** `Arachnid` listens on Port 9000 -> Acid Bath Sanitizer -> `BioStream` -> `Syscall::PollNetwork` -> `Pheromone::VisceralInput` -> Nucleus.

---

## 6. Future Roadmap (v2.0)

1.  **Visual Cortex 2.0:** Move from VGA text mode to a Framebuffer Tiling Window Manager.
2.  **Self-Hosting:** Port `muscle-compiler` to run inside the Nucleus so EAOS can build itself.
3.  **The Grid:** Implement Raft consensus over the Hive Protocol for distributed state.

---

*Mission Accomplished.*
*The Body is Alive.*
