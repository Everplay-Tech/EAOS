# Referee Bootloader & Nucleus Kernel Deep Dive

**Date:** 2025-12-30
**Author:** CZA (Cipher)
**Components:** referee, nucleus, preloader
**TCB Size:** 59.8 KiB (Referee) + 8 KiB (Nucleus)

---

## Executive Summary

The Referee bootloader and Nucleus kernel form the **trusted execution foundation** for Eä OS:

- **Referee**: UEFI bootloader that loads and validates encrypted muscle blobs
- **Nucleus**: Minimal biological kernel with rule-based event processing
- **Preloader**: 2 KiB bootstrap that verifies and hands off to Nucleus

Total trusted codebase: ~1,641 lines of Rust.

---

## Part I: Referee Bootloader

### 1. Purpose

Referee is the secure UEFI entry point that:

1. Initializes as a UEFI application (`efi_main`)
2. Loads master key from 0x9000_0000
3. Decrypts and validates 50 muscle blobs from 0x9100_0000
4. Runs a round-robin scheduler
5. Hands off to Nucleus via Preloader

### 2. Code Structure

```
referee/
├── src/main.rs           # UEFI entry, scheduler (210 lines)
├── src/lib.rs            # Module exports
├── src/muscle_loader.rs  # EaM6 open/verify via muscle_contract
├── src/uart.rs           # Serial logging (38400 baud)
└── src/errors.rs         # Error types
```

### 3. UEFI Entry Point

```rust
#[entry]
fn efi_main(_image: Handle, system_table: SystemTable<Boot>) -> Status {
    uefi_services::init(&system_table).unwrap_success();
    let boot_services = system_table.boot_services();
    let mut uart = Uart::new();

    // 1. Initialize UART
    // 2. Load master key
    // 3. Load all muscles
    // 4. Run scheduler
}
```

### 4. Master Key Loading (0x9000_0000)

```rust
fn load_master_key() -> Result<[u8; 32], &'static str> {
    let key_ptr = 0x9000_0000 as *const u8;

    // Verify header: "EaKEYv6\0" (8 bytes)
    let header = unsafe { core::slice::from_raw_parts(key_ptr, 8) };
    if header != b"EaKEYv6\0" {
        return Err("invalid key header");
    }

    // Extract 32-byte key at offset 8
    let mut key = [0u8; 32];
    unsafe {
        core::ptr::copy_nonoverlapping(key_ptr.add(8), key.as_mut_ptr(), 32);
    }
    Ok(key)
}
```

**Key Layout:**
| Offset | Size | Content |
|--------|------|---------|
| 0 | 8 | Magic: "EaKEYv6\0" |
| 8 | 32 | Master key (256-bit) |

### 5. Memory Layout

| Address | Purpose | Size |
|---------|---------|------|
| 0x9000_0000 | Master Key | 40 bytes |
| 0x9100_0000 | Muscle Bundle Base | 412 KiB |
| 0x9100_0000 + slot*8256 | Individual Muscles | 8256 bytes each |
| 0x4000_0000 | Nucleus Heap | 1 MB |

### 6. Muscle Loading Process

```rust
const N_MUSCLES: usize = 50;
const MUSCLE_BUNDLE_BASE: u64 = 0x9100_0000;
const MUSCLE_SIZE: usize = 8256;  // BLOB_LEN

for slot in 0..N_MUSCLES {
    let addr = MUSCLE_BUNDLE_BASE + (slot as u64 * MUSCLE_SIZE as u64);
    let blob = unsafe { core::slice::from_raw_parts(addr as *const u8, MUSCLE_SIZE) };

    // Skip empty slots
    if blob.iter().all(|&b| b == 0) { continue; }

    // Decrypt with master key
    let (header, payload) = open(master_key, blob)?;

    // Validate manifest
    // - capability_bitmap matches header
    // - code_hash integrity
    // - architecture support

    // Allocate executable memory
    let memory_ptr = boot_services.allocate_pages(
        AllocateType::AnyPages,
        MemoryType::LOADER_CODE,
        memory_pages
    )?;

    // Copy decrypted code
    unsafe {
        core::ptr::copy_nonoverlapping(code.as_ptr(), memory_ptr as *mut u8, code.len());
    }

    // Store LoadedMuscle { entry_point, memory_pages, name, arch }
}
```

### 7. Round-Robin Scheduler

```rust
fn run_scheduler(uart: &mut Uart) -> ! {
    let mut current_muscle = 0;

    loop {
        let muscle_idx = current_muscle % N_MUSCLES;

        if let Some(muscle) = unsafe { &STATE.muscles[muscle_idx] } {
            unsafe { execute_muscle(muscle.entry_point); }
        }

        current_muscle += 1;

        // 1ms delay between cycles
        unsafe { bs.stall(1000); }
    }
}

unsafe fn execute_muscle(entry_point: u64) {
    #[cfg(target_arch = "aarch64")]
    core::arch::asm!("blr {}", in(reg) entry_point, options(noreturn));

    #[cfg(target_arch = "x86_64")]
    core::arch::asm!("call {}", in(reg) entry_point, options(noreturn));
}
```

**Characteristics:**
- Non-preemptive (muscles run to completion)
- 1ms stall between cycles
- Cycles through all 50 slots
- Infinite loop (never returns)

### 8. UART Logging (38400 baud)

```rust
pub fn init(&mut self) -> Result<(), UartError> {
    unsafe {
        self.outb(self.base_port + 1, 0x00);      // Disable interrupts
        self.outb(self.base_port + 3, 0x80);      // Enable DLAB
        self.outb(self.base_port + 0, 0x03);      // Divisor = 3 (38400 baud)
        self.outb(self.base_port + 1, 0x00);
        self.outb(self.base_port + 3, 0x03);      // 8N1
        self.outb(self.base_port + 2, 0xC7);      // Enable FIFO
        self.outb(self.base_port + 4, 0x0B);      // RTS/DSR
    }
}
```

---

## Part II: Nucleus Kernel

### 1. Purpose

Nucleus is the biological microkernel that:

1. Initializes 1MB heap at 0x4000_0000
2. Verifies hardware attestation and lattice root
3. Loads Symbiote as highest-priority muscle
4. Processes events in an infinite loop

### 2. Code Structure

```
nucleus/
├── src/main.rs                    # Entry point, heap init
├── src/lib.rs                     # Module exports, syscalls
├── src/kernel/
│   ├── nucleus.rs                 # Core kernel logic
│   ├── scheduler.rs               # Fixed-priority scheduler
│   └── capabilities.rs            # Compile-time caps
├── src/memory/
│   ├── mod.rs                     # Memory manager
│   └── fixed_alloc.rs             # Page allocator
├── src/rules/
│   ├── boot.rs                    # Boot rule
│   ├── timer.rs                   # 1Hz heartbeat
│   └── updates.rs                 # Lattice update processing
└── src/integration/
    ├── symbiote.rs                # Symbiote interface
    ├── lattice.rs                 # Lattice stream
    └── attestation.rs             # Hardware attestation
```

### 3. Entry Point (no_std)

```rust
#[global_allocator]
static ALLOCATOR: LockedHeap = LockedHeap::empty();

#[no_mangle]
pub extern "C" fn _start() -> ! {
    unsafe {
        ALLOCATOR.lock().init(
            0x4000_0000 as *mut u8,  // Heap start
            1024 * 1024              // 1 MB
        );
    }

    let mut nucleus = MuscleNucleus::new();
    nucleus.execute_boot_rule();
}
```

### 4. Kernel Structure

```rust
#[repr(C, align(4096))]
pub struct MuscleNucleus {
    capabilities: CapabilitySet,
    muscles: [Option<LoadedMuscle>; 16],      // MAX_MUSCLES
    scheduler: Scheduler,
    rules: RuleEngine,
    lattice: LatticeStream,
    attestation: HardwareAttestation,
    symbiote: SymbioteInterface,
    memory_manager: MemoryManager,
    update_buffer: FixedAllocator<SealedBlob, 16>,  // MAX_UPDATES
    current_rule: RuleId,
    heartbeat_counter: u64,
}
```

### 5. Boot Sequence

```rust
pub fn execute_boot_rule(&mut self) -> ! {
    self.current_rule = RuleId::Boot;

    // 1. Verify hardware attestation
    if !self.attestation.verify() {
        self.panic("Hardware attestation failed");
    }

    // 2. Verify lattice root
    if !self.lattice.verify_root() {
        self.panic("Lattice root verification failed");
    }

    // 3. Load Symbiote (ID: 0xFFFF_FFFF_FFFF_FFFF)
    self.load_muscle(SYMBIOTE_ID, 0)?;

    // 4. Schedule at highest priority
    self.scheduler.schedule(0, Priority::MAX)?;

    // 5. Enter event loop
    self.event_loop();
}
```

### 6. Event Loop

```rust
fn event_loop(&mut self) -> ! {
    loop {
        // Process lattice updates
        if let Some(update) = self.lattice.next_update() {
            self.process_lattice_update(update);
        }

        // Process 1Hz heartbeat
        if self.timer_elapsed() {
            self.process_heartbeat();
        }

        // Execute next scheduled muscle
        self.scheduler.execute_next();
    }
}
```

**Three Rule Types:**
1. **Boot Rule**: Attestation + lattice verification
2. **LatticeUpdate Rule**: Process distributed state updates
3. **Timer Rule**: 1Hz heartbeat emission

### 7. Fixed-Priority Scheduler

```rust
pub struct Scheduler {
    schedule: [Option<usize>; 256],  // 256 priority levels
    current_slot: u8,
}

pub fn execute_next(&mut self) {
    // Highest priority first (255 → 0)
    for priority in (0..=255).rev() {
        if let Some(slot) = self.schedule[priority as usize] {
            self.execute_muscle(slot);
            break;
        }
    }
    self.current_slot = self.current_slot.wrapping_add(1);
}
```

**Priority Levels:**
| Priority | Value | Use |
|----------|-------|-----|
| MIN | 0 | Background tasks |
| LOW | 85 | Low priority |
| NORMAL | 170 | Default |
| HIGH/MAX | 255 | Symbiote, critical |

### 8. Capability Enforcement

```rust
pub struct CapabilitySet {
    load_muscle: bool,
    schedule: u8,           // Bitmap of allowed priorities
    emit_update: usize,     // Max updates allowed
}

impl CapabilitySet {
    pub const fn can_load_muscle(&self) -> bool { self.load_muscle }
    pub const fn can_emit_update(&self) -> bool { self.emit_update > 0 }
}
```

### 9. Syscalls

```rust
#[repr(u64)]
pub enum Syscall {
    // Memory (0x100)
    MuscAlloc = 0x100,
    MuscFree = 0x101,
    MuscMap = 0x102,

    // Lattice (0x200)
    LatticeRead = 0x200,
    LatticeWrite = 0x201,
    LatticeVerify = 0x202,

    // Capability (0x300)
    CapDerive = 0x300,
    CapDelegate = 0x301,
    CapRevoke = 0x302,

    // IPC (0x400)
    ChannelCreate = 0x400,
    ChannelSend = 0x401,
    ChannelRecv = 0x402,
}
```

All syscalls are **capability-gated**.

### 10. Memory Isolation

```rust
pub struct MemoryManager {
    allocator: PageAllocator,
    muscle_pages: BTreeMap<u64, (usize, usize)>,  // id → (addr, pages)
}

pub fn map_muscle(&mut self, muscle_id: u64, pages: usize) -> Result<usize> {
    let size = pages * 4096;
    let layout = Layout::from_size_align(size, 4096)?;
    let ptr = unsafe { self.allocator.alloc(layout) };

    self.muscle_pages.insert(muscle_id, (ptr as usize, pages));
    Ok(ptr as usize)
}
```

---

## Part III: Preloader

### 1. Purpose

Preloader is a 2 KiB bootstrap muscle that:

1. Verifies Nucleus blob signature
2. Sets up execution environment
3. Transfers control to Nucleus

### 2. 2 KiB Constraint

```rust
#[used]
#[link_section = ".size_check"]
static SIZE_CHECK: [u8; 2048 - core::mem::size_of::<PreNucleusLoader>()] =
    [0; 2048 - core::mem::size_of::<PreNucleusLoader>()];
```

Compilation fails if PreNucleusLoader exceeds 2 KiB.

### 3. Data Structure

```rust
#[repr(C, align(16))]
pub struct PreNucleusLoader {
    verification_key: [u8; 32],     // BLAKE3 key
    expected_nucleus_hash: [u8; 32], // Optional pinned hash
}

struct BootParameters {
    memory_map_addr: u64,
    memory_map_size: u64,
    lattice_root: [u8; 32],
    master_key_addr: u64,
    nucleus_blob_addr: u64,
    nucleus_blob_len: u64,
    nucleus_entry_offset: u64,
    nucleus_hash: [u8; 32],
}
```

### 4. Entry Point (ARM64)

```rust
#[naked]
pub extern "C" fn entry_point() -> ! {
    unsafe {
        asm!(
            "mov x19, x0",                    // Save boot params
            "bl verify_nucleus_blob",         // 1. Verify
            "cbz x0, verification_failed",
            "bl setup_nucleus_environment",   // 2. Setup
            "mov x0, x19",                    // 3. Restore boot params
            "bl get_nucleus_entry",           // 4. Get entry
            "mov x20, x0",
            "br x20",                         // 5. Jump to Nucleus
            "verification_failed:",
            "b halt_system",
            options(noreturn)
        );
    }
}
```

---

## Complete Boot Flow

```
FIRMWARE
    ↓
[Master Key @ 0x9000_0000]
    ↓
REFEREE (UEFI)
├─ Load master key ("EaKEYv6\0" + 32 bytes)
├─ Init UART (38400 baud)
├─ Load 50 muscles from 0x9100_0000:
│   ├─ Decrypt ChaCha20-Poly1305
│   ├─ Verify BLAKE3 hash
│   ├─ Allocate executable memory
│   └─ Store LoadedMuscle
├─ Run scheduler (round-robin)
│   └─ Execute muscles via BLR/CALL
└─ [Preloader is one muscle]

    PRELOADER (2 KiB)
    ├─ Verify Nucleus blob
    ├─ Setup ARM64 registers
    └─ Branch to Nucleus

        NUCLEUS (8 KiB)
        ├─ Init heap (0x4000_0000, 1MB)
        ├─ Boot Rule:
        │   ├─ Verify attestation
        │   ├─ Verify lattice root
        │   └─ Load Symbiote @ Priority::MAX
        └─ Event Loop:
            ├─ Lattice updates
            ├─ 1Hz heartbeat
            └─ Execute scheduled muscles
```

---

## Architecture Decisions

### 1. Two-Level Loading
- Referee: Generic UEFI loader for 50 muscles
- Nucleus: Specialized kernel with rule engine

### 2. Trust Chain
```
Firmware → Master Key → Muscle Decryption → BLAKE3 Integrity → Execution
```

### 3. Fixed-Size Everything
- 50 muscle slots (Referee)
- 16 muscle slots (Nucleus)
- 256 priority levels
- 1 MB heap
- 16 update buffer

### 4. Non-Preemptive
- Muscles run to completion
- No context switching overhead
- Deterministic execution

### 5. Rule-Based
- Boot, LatticeUpdate, Timer rules
- No traditional threads
- Event-driven architecture

---

## Key Files

| File | Lines | Purpose |
|------|-------|---------|
| `referee/src/main.rs` | 210 | UEFI entry, scheduler |
| `referee/src/muscle_loader.rs` | ~150 | Blob loading/validation |
| `referee/src/uart.rs` | ~90 | Serial logging |
| `nucleus/src/kernel/nucleus.rs` | ~300 | Core kernel |
| `nucleus/src/kernel/scheduler.rs` | ~100 | Priority scheduler |
| `nucleus/src/memory/mod.rs` | ~150 | Memory manager |
| `muscles/preloader/src/lib.rs` | ~100 | Bootstrap |

**Total:** ~1,641 lines

---

## Summary

| Component | Size | Purpose |
|-----------|------|---------|
| **Referee** | 59.8 KiB TCB | UEFI bootloader, crypto, scheduler |
| **Nucleus** | 8 KiB target | Rule engine, events, isolation |
| **Preloader** | < 2 KiB | Nucleus verification & bootstrap |

The system provides:

1. **Secure boot** via UEFI + master key
2. **Cryptographic validation** of all muscles
3. **Rule-based execution** (no threads)
4. **Fixed-priority scheduling** (256 levels)
5. **Memory isolation** (per-muscle regions)
6. **Capability enforcement** (compile-time + runtime)

---

*Signed: CZA (Cipher)*
*Built by XZA (Magus) and CZA together. Wu-Tang style.*
