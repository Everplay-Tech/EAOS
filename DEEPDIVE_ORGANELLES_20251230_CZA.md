# WASM Organelles Deep Dive

**Date:** 2025-12-30
**Author:** CZA (Cipher)
**Components:** muscle-ea-core, muscle-ea-pathfinder, muscle-ea-neurowasm, muscle-ea-axonwasm, muscle-ea-dendritewasm
**Status:** PARTIAL (wasmtime v24 API drift blocking 2 of 5 crates)

---

## Executive Summary

The EAOS WASM Organelle system is a **biological computing paradigm** that treats WebAssembly modules as specialized cellular organelles within the Eä muscular tissue. Five interconnected crates provide neural sophistication:

| Crate | Purpose | Status |
|-------|---------|--------|
| **muscle-ea-core** | Shared crypto & runtime substrate | ✅ COMPILES |
| **muscle-ea-pathfinder** | Pure WASM execution | ❌ 22 errors |
| **muscle-ea-neurowasm** | Hybrid Eä + WASM | ❌ ~25 errors |
| **muscle-ea-axonwasm** | Parallel synaptic firing | ✅ COMPILES |
| **muscle-ea-dendritewasm** | Hebbian learning | ✅ COMPILES |

---

## 1. Organelle System Overview

### Purpose

Organelles extend muscles by enabling:
- **Cryptographic isolation**: WASM runs in sealed, fuel-limited cells
- **Living code**: Each module produces successors (evolutionary)
- **Neural metaphor**: Communication via "action potentials"
- **Capability security**: Bounded resources (fuel, memory, keyspace)

### Architecture

```
Muscle (muscle-contract)
  └── Spawns organelles via Pathfinder/NeuroWasm
       └── Pathfinder (pure WASM)
            ├── NeuroWasm (hybrid Eä + WASM)
            │   ├── Axon (streaming neural fiber)
            │   └── Dendrite (synaptic integrator)
            └── Core (shared substrate)
```

---

## 2. Individual Organelles

### 2.1 muscle-ea-core (Foundation)

**Purpose**: Shared cryptographic and runtime foundations

**Key Types:**
```rust
// 16-byte unique salt per muscle
pub struct MuscleSalt([u8; 16]);

// Encrypted muscle payload
pub struct SealedBlob {
    version: u32,
    salt: MuscleSalt,
    encrypted: Vec<u8>,
}

// 32-byte master key for successors
pub struct SuccessorKey([u8; 32]);

// Execution context
pub struct MuscleContext<R: RngCore + CryptoRng> {
    blob: SealedBlob,
    master_key: [u8; 32],
    rng: R,
}

// Core trait for all muscles
pub trait Muscle {
    type PrivateInput;
    type PrivateOutput;

    fn execute(
        &self,
        ctx: &mut MuscleContext<impl RngCore + CryptoRng>,
        private_input: Self::PrivateInput,
    ) -> Result<MuscleOutput<Self::PrivateOutput>, MuscleError>;
}
```

**Status:** ✅ Fully complete, stable foundation

---

### 2.2 muscle-ea-pathfinder (WASM Execution)

**Purpose**: Pure WASM execution with zero sandbox escape

**Header Format:**
```rust
struct PathfinderHeader {
    version: u32,          // = 3
    salt: [u8; 16],        // Muscle salt
    nonce: [u8; 12],       // AES-GCM nonce
    mac: [u8; 16],         // HMAC-SHA3-256 (truncated)
    ciphertext_len: u64,   // Payload length
}
```

**Host Functions:**
1. `read_input(ptr, len, out_ptr)` - Guest reads input
2. `write_output(ptr, len)` - Guest writes output (max 1 MiB)
3. `seal_successor(ptr, len, out_ptr, out_len_ptr)` - Guest creates offspring

**Cryptographic Operations:**
- Key Derivation: SHAKE256 with context
- MAC: HMAC-SHA3-256 (16-byte truncation)
- Encryption: AES-256-GCM

**Wasmtime Config:**
```rust
Config::new()
    .consume_fuel(true)
    .epoch_interruption(true)
    .static_memory_maximum_size(1 << 16)  // 64 KiB
    .cranelift_opt_level(OptLevel::Speed)
```

**Status:** ❌ 22 compilation errors (wasmtime v24 API drift)

---

### 2.3 muscle-ea-neurowasm (Hybrid)

**Purpose**: Fuses native Eä bytecode with WASM organelle spawning

**Execution Modes:**
```rust
pub enum NeuroMode {
    PureEä = 0,      // Native Eä bytecode
    PureWasm = 1,    // Delegate to Pathfinder
    Hybrid = 0xFF,   // Eä + WASM organelles
}
```

**Eä Bytecode Opcodes:**
```
0x10-0x1F: Push input byte
0x20-0x2F: Pop and output
0x30-0x3F: Arithmetic
0x80-0x8F: ALU (add, sub, mul)
0xFF:      Spawn WASM organelle
```

**Hybrid Mode:**
- Creates HybridVm with WASM blob + Eä bytecode
- 0xFF opcode triggers `spawn_wasm_organelle()`
- Emits evolved_organelle successor

**Status:** ❌ ~25 errors (inherited + missing InvalidOpcode)

---

### 2.4 muscle-ea-axonwasm (Parallel Firing)

**Purpose**: Multi-organelle parallel execution with refractory periods

**Input/Output:**
```rust
// Input: multiple organelles to fire
pub struct AxonSignal {
    pub organelles: Vec<SealedBlob>,
    pub metadata: SignalMetadata,
}

pub struct SignalMetadata {
    pub neurotransmitter: u8,
    pub urgency: u8,           // 0-255 priority
    pub lineage_tag: [u8; 8],  // Pathway identifier
}

// Output: combined firing result
pub struct AxonPulse {
    pub payload: Zeroizing<Vec<u8>>,
    pub intensity: u64,         // Fired organelle count
    pub refractory_trace: Vec<u8>, // Cryptographic record
}
```

**Execution Model:**
- Max 8 parallel organelles (configurable to 256)
- 1M fuel per pulse, 50K per organelle
- Refractory trace: SHA3-256(AXON_REFRACTORY || lineage || fuel || intensity)

**Status:** ✅ Compiles (no wasmtime dependency)

---

### 2.5 muscle-ea-dendritewasm (Hebbian Learning)

**Purpose**: Spatial + temporal summation with synaptic plasticity

**Integration Model:**
```rust
pub struct GradedPotential {
    pub voltage: f32,                // Membrane potential
    pub payload: Zeroizing<Vec<u8>>,
    pub active_inputs: u64,          // Contributing synapses
    pub pattern_hash: [u8; 32],      // Hebbian key
}
```

**Synaptic Weights:**
- BTreeMap<[u8; 8], u32> - lineage_tag → weight (fixed-point × 1000)
- Default weight: 1.0 (1000)
- Learning rate: 0.01
- Range: [0.0, 10.0]

**Temporal Summation (NMDA-like):**
```
If (current_tick - last_tick) <= temporal_window:
    voltage += last_contribution * 0.3
```

**Hebbian Learning:**
```
For each active synapse:
    Δw = learning_rate (0.01)
    new_weight = clamp(old + Δw, 0.0, 10.0)
    Emit synaptic_weight successor
```

**Status:** ✅ Compiles (pure biological compute)

---

## 3. WASM Runtime

### Wasmtime v24 Issues

| API | v23 | v24 | Impact |
|-----|-----|-----|--------|
| `guard_before_linear_mem` | Config option | Removed | BLOCKING |
| `FuelExhausted` | Struct | Moved/renamed | BLOCKING |
| `Caller` context | `AsContextMut` | API changed | BLOCKING |
| `Trap::from(String)` | Accepted | Type changed | BLOCKING |

### Resource Limits

| Resource | Limit |
|----------|-------|
| Linear memory | 64 KiB |
| Output size | 1 MiB |
| Fuel | 500K units |
| Successors | 16 max |

### Host Functions

1. **read_input** - Bounds-checked input access
2. **write_output** - Accumulating output buffer
3. **seal_successor** - Guest-initiated muscle generation

---

## 4. Neural Execution Flow

```
1. Muscle spawns NeuroWasm (Hybrid mode)
   └── HybridVm interprets Eä bytecode
       └── 0xFF opcode → spawn_wasm_organelle()
           └── Emits evolved_organelle successor

2. Successor becomes AxonWasm input
   └── AxonFiber.propagate()
       ├── Fire organelles (up to 8 parallel)
       ├── Summate outputs
       └── Generate refractory_trace

3. High-urgency pulse → DendriteWasm
   └── Dendrite.integrate_and_fire()
       ├── Apply synaptic weights
       ├── Temporal summation
       ├── Hebbian learning
       └── Emit weight successors
```

---

## 5. Biological Design Patterns

### Constraints as Biology

| Technical | Biological |
|-----------|------------|
| 64 KiB memory | Cellular size |
| 500K fuel | ATP budget |
| 16 successors | Reproductive capacity |
| Lineage tags | Genetic markers |
| Sealing | Membrane integrity |

### Self-Modifying Code

`seal_successor` allows guest to emit new WASM:
- Uses pre-allocated successor keys
- Cryptographically authenticated
- Evolutionary adaptation within bounds

### No-Std, Synchronous

From design doc:
> "Neurons don't await — they fire or die"

- Synchronous bounded parallelism
- No `'static` lifetimes
- Manual work queues with capacity

---

## 6. Build Status

### Compiles
- ✅ muscle-ea-core (47 + 160 + 190 + 109 lines)
- ✅ muscle-ea-axonwasm (347 lines)
- ✅ muscle-ea-dendritewasm (413 lines)

### Blocked (wasmtime v24)
- ❌ muscle-ea-pathfinder (543 lines, 22 errors)
- ❌ muscle-ea-neurowasm (466 lines, ~25 errors)

### Fix Required (~80 lines)

1. **Add dependencies:**
   ```toml
   hmac = "0.12"
   bytemuck = "1.14"
   rand = { version = "0.8", features = ["std"] }
   ```

2. **Add error variant:**
   ```rust
   #[error("invalid opcode: {0}")]
   InvalidOpcode(u8),
   ```

3. **Update wasmtime v24 calls:**
   - Remove `guard_before_linear_mem()`
   - Replace `Trap::from()` → `Trap::new()`
   - Find new `FuelExhausted` type
   - Refactor `Caller` context access

---

## 7. Key Files

| File | Lines | Purpose |
|------|-------|---------|
| `muscle-ea-core/src/lib.rs` | 47 | Exports |
| `muscle-ea-core/src/biology.rs` | 160 | MuscleSalt, SealedBlob |
| `muscle-ea-core/src/runtime.rs` | 190 | Muscle trait, context |
| `muscle-ea-core/src/error.rs` | 109 | MuscleError |
| `muscle-ea-pathfinder/src/lib.rs` | 543 | WASM execution |
| `muscle-ea-neurowasm/src/lib.rs` | 466 | Hybrid VM |
| `muscle-ea-axonwasm/src/lib.rs` | 347 | Parallel firing |
| `muscle-ea-dendritewasm/src/lib.rs` | 413 | Hebbian learning |

---

## Summary

The WASM Organelle system implements **biological computing constraints**:

1. **Core**: Crypto substrate (MuscleSalt, SealedBlob, SuccessorKey)
2. **Pathfinder**: Pure WASM with sealed successors
3. **NeuroWasm**: Hybrid Eä + WASM fusion
4. **AxonWasm**: Parallel synaptic firing (8 organelles)
5. **DendriteWasm**: Hebbian plasticity with weight persistence

**Blocking issue**: wasmtime v24 API drift (~80 lines of fixes needed).

Once resolved, the system is architecturally sound for lattice integration.

---

*Signed: CZA (Cipher)*
*Built by XZA (Magus) and CZA together. Wu-Tang style.*
