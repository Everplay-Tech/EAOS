# FUTURE IMPLEMENTATION PLAN: The Ossified Organism

**Objective:** Upgrade all system muscles from "Prototype/Mock" status to "Production/Real" implementations. Zero mocks. Zero stubs.

---

## 1. Adrenaline (The Endocrine Booster)
**Current Status:** Non-existent (Concept).
**Future Implementation:** **Priority-Based Scheduling**.
- **Mechanism:** Upgrade `TaskControlBlock` in `scheduler.rs` to include a `priority: u8` field (0=Idle, 255=Realtime).
- **Logic:** Refactor `schedule()` to use a Weighted Round-Robin or Priority Queue algorithm instead of simple iteration.
- **Muscle:** The `Adrenaline` muscle will simply be the userspace interface (via Pheromone) to request a priority boost (`Syscall::Nice`).

## 2. Antibody (The Immune System)
**Current Status:** Non-existent (Concept).
**Future Implementation:** **Active Heuristic Intrusion Detection**.
- **Mechanism:**
    1.  **Sentinel:** A background task that wakes up every N ticks.
    2.  **Telemetry Audit:** It reads the global `SYSCALL_STATS`. If `InvalidSyscall` or `PermissionDenied` counters increase faster than a threshold (e.g., >5 per sec), it triggers a `SystemLockdown`.
    3.  **Canary Check:** It iterates over the `TASKS` list (exposed via safe introspection) and verifies the "Stack Canary" (magic bytes at stack bottom) for every active task to detect overflows.
- **Action:** If a threat is detected, it secretes `Pheromone::Adrenaline(PANIC)`.

## 3. Synesthesia (The Voice)
**Current Status:** Non-existent (Concept).
**Future Implementation:** **PC Speaker Driver (Port 0x61)**.
- **Mechanism:** Direct hardware I/O to the Programmable Interval Timer (PIT) Channel 2 and Port 0x61.
- **Driver:** `muscles/referee-kernel/src/pc_speaker.rs`.
- **Capability:** `play_frequency(hz, duration)`.
- **Integration:** The Nucleus triggers sounds on events (e.g., Startup Beep, Error Buzz).

## 4. Pheromone (The Hive Protocol)
**Current Status:** Client-only (`Arachnid` fetches URLs).
**Future Implementation:** **TCP Server (The Receptor)**.
- **Mechanism:** Upgrade `Arachnid` to bind a `TcpSocket` to port 9000 (The Hive Port) and `listen()`.
- **Protocol:** Define a binary wire protocol (`HivePacket`) for inter-node identity exchange.
- **Logic:** When a connection is accepted, `Arachnid` secretes `Pheromone::VisceralInput` containing the remote peer's handshake.

---

## 5. Execution Order
1.  **Synesthesia:** Immediate feedback (Beeps). Proof of hardware control.
2.  **Adrenaline:** Scheduler core upgrade. Proof of control flow.
3.  **Antibody:** Security audit system. Proof of introspection.
4.  **Pheromone:** Server capability. Proof of connectivity.

**Constraint Checklist:**
- [ ] No `println!` debugging (Use UART/VGA).
- [ ] No `std::thread` (Use `Task` system).
- [ ] No `todo!()` macros.
- [ ] Real hardware ports / Memory addresses only.
