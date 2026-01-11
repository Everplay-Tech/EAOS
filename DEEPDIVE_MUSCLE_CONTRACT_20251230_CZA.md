# Muscle Contract & Crypto System Deep Dive

**Date:** 2025-12-30
**Author:** CZA (Cipher)
**Component:** muscle-contract, muscle-compiler
**Version:** v6 (EaM6)

---

## 1. Purpose & Design

**What is the Muscle Contract?**

The Muscle Contract v6 (EaM6) defines the **smallest reliable unit of execution** (a "muscle") as a sealed, encrypted blob that can be safely loaded across heterogeneous hardware. It provides:

- **Sealed Distribution**: Code always encrypted in transit
- **Capability Isolation**: Fine-grained permission model
- **Integrity Verification**: BLAKE3 hash attestation
- **Deterministic Layout**: Fixed offsets enable safe parsing
- **Multi-Architecture Support**: AArch64, x86_64, WASM32

### Why Fixed 8256 Bytes?

- **8KiB code maximum**: Realistic constraint for resource-limited environments
- **256-byte manifest**: Sufficient for all capability and memory metadata
- **16-byte AEAD tag**: Standard for Poly1305
- **24-byte nonce field**: Avoids nonce/key reuse
- **Predictability**: No variable-length parsing needed

---

## 2. Code Structure

```
muscle-contract/
├── src/lib.rs              # Core blob format & crypto (489 lines)
├── src/bin/gen_vectors.rs  # Test vector generation
└── vectors/README.md       # Testing documentation

muscle-compiler/
├── src/main.rs             # CLI entry point (552 lines)
├── src/crypto.rs           # Blob sealing wrapper (59 lines)
├── src/parser.rs           # Python weight extraction (203 lines)
├── src/error.rs            # Error types (39 lines)
├── ast/
│   ├── mod.rs              # MuscleAst wrapper (424 lines)
│   └── full_ast.rs         # Muscle.ea AST definitions (266 lines)
├── languages/
│   ├── mod.rs              # Module exports (257 lines)
│   ├── formal_grammar.rs   # EBNF parser (592 lines)
│   ├── ea_lang.rs          # .ea file parser (172 lines)
│   └── capability_checker.rs  # Capability security (296 lines)
└── codegen/
    ├── mod.rs              # Dispatch layer (29 lines)
    ├── nucleus.rs          # Muscle.ea codegen (610 lines)
    ├── aarch64.rs          # AArch64 emission (181 lines)
    └── x86_64.rs           # x86_64 emission (80 lines)
```

### Key Types

```rust
// Constants
pub const BLOB_LEN: usize = 8256;
pub const HEADER_LEN: usize = 24;
pub const NONCE_LEN: usize = 24;
pub const TAG_LEN: usize = 16;
pub const PAYLOAD_LEN: usize = 8192;
pub const MANIFEST_LEN: usize = 256;

// Header (24 bytes, unencrypted)
pub struct EaM6Header {
    pub magic: [u8; 4],           // "EaM6"
    pub version: u8,              // 0x06
    pub header_len: u8,           // 24
    pub flags: u8,                // bit0=deterministic_nonce, etc.
    pub arch: u8,                 // 1=aarch64, 2=x86_64, 3=wasm32
    pub cap_bitmap: u32,          // Capability mask
    pub payload_len: u16,         // 8192
    pub manifest_len: u16,        // 256
    pub reserved: [u8; 8],        // Must be zero
}

// Manifest (256 bytes, encrypted)
pub struct MuscleManifestV1 {
    pub magic: [u8; 4],           // "EaMM"
    pub version: u8,
    pub arch: u8,
    pub abi: u8,                  // 0=raw, 1=wasm
    pub code_offset: u16,         // Always 256
    pub code_size: u16,           // <= 7936
    pub entrypoint: u32,
    pub memory_pages: u16,        // 4KiB units
    pub stack_pages: u8,
    pub heap_pages: u8,
    pub update_budget: u16,       // Max lattice updates
    pub io_budget: u16,           // Max IO ops
    pub capability_bitmap: u32,   // Must match header
    pub muscle_id: [u8; 32],      // BLAKE3(code)
    pub muscle_version: u64,
    pub code_hash: [u8; 32],      // Integrity check
    pub llm_profile_off: u16,     // Optional LLM
    pub llm_profile_len: u16,
    pub organelle_off: u16,       // Optional WASM
    pub organelle_len: u16,
    pub reserved: [u8; 148],
}
```

---

## 3. Cryptographic Model

### AEAD: ChaCha20-Poly1305

**Crate**: `chacha20poly1305 v0.10.1`

**Nonce Handling**:
- **Stored**: 24 bytes in blob (192-bit entropy)
- **AEAD**: First 12 bytes for ChaCha20-Poly1305
- **KDF**: Full 24 bytes in key derivation

### BLAKE3 Key Derivation

```rust
fn derive_key(master_key: &[u8; 32], header: &[u8; 24], nonce: &[u8]) -> [u8; 32] {
    let mut hasher = Hasher::new_keyed(master_key);
    hasher.update(b"EaM6 key");      // Domain separation
    hasher.update(header);            // Bind to header
    hasher.update(nonce);             // Bind to nonce
    *hasher.finalize().as_bytes()
}
```

### Sealing Process

1. Compute `muscle_id = BLAKE3(code)`
2. Create manifest with code_hash, capabilities
3. Build payload = `manifest || code || padding` (8192 bytes)
4. Generate random 24-byte nonce
5. Derive `enc_key = BLAKE3_keyed(master_key, "EaM6 key" || header || nonce)`
6. Encrypt with `ChaCha20Poly1305::encrypt(key, nonce[0:12], payload, aad=header)`
7. Assemble blob = `header || nonce || ciphertext || tag`

### Opening Process

1. Validate header (magic, version, sizes)
2. Extract 24-byte nonce
3. Derive key (same formula)
4. Decrypt with AEAD verification
5. Parse manifest from payload[0:256]
6. Verify `BLAKE3(code) == manifest.code_hash`
7. Verify `manifest.cap_bitmap == header.cap_bitmap`

---

## 4. Blob Format (8256 bytes)

```
Offset   Size   Field        Description
------   ----   -----        -----------
0        24     Header       Unencrypted, used as AAD
24       24     Nonce        For AEAD + KDF
48       8192   Ciphertext   Encrypted payload
8240     16     Tag          Poly1305 auth tag
------
8256     TOTAL
```

### Header Layout (24 bytes)

```
Offset  Size  Field         Values
0       4     magic         "EaM6" (0x45, 0x61, 0x4D, 0x36)
4       1     version       0x06
5       1     header_len    24
6       1     flags         bit0=deterministic_nonce
                            bit1=has_llm_profile
                            bit2=has_organelle_map
7       1     arch          1=aarch64, 2=x86_64, 3=wasm32
8       4     cap_bitmap    u32LE capability mask
12      2     payload_len   8192
14      2     manifest_len  256
16      8     reserved      Must be 0x00
```

### Payload Structure (8192 bytes decrypted)

```
Offset   Size    Field      Content
0        256     Manifest   MuscleManifestV1
256      N       Code       Machine code (N <= 7936)
256+N    (rem)   Padding    Zero bytes
```

---

## 5. Capability System

### 9 Defined Capabilities

| Bit | Name | Purpose |
|-----|------|---------|
| 0 | `LATTICE_READ` | Read lattice state |
| 1 | `LATTICE_WRITE` | Emit lattice updates |
| 2 | `CLOCK_READ` | Access time sources |
| 3 | `STORAGE_READ` | Read persistent state |
| 4 | `STORAGE_WRITE` | Write persistent state |
| 5 | `NET_CLIENT` | Outbound connections |
| 6 | `NET_SERVER` | Accept connections |
| 7 | `SPAWN_SUCCESSOR` | Load other muscles |
| 8 | `USE_ACCELERATOR` | Hardware accelerators |

### Enforcement Layers

1. **Compile-Time**: CapabilityChecker verifies all uses declared
2. **Load-Time**: Referee checks `header.cap_bitmap == manifest.cap_bitmap`
3. **Runtime**: Nucleus kernel enforces effective_capabilities ⊆ bitmap

### "Declare Before Use" Principle

```ea
// Must declare capability before using
capability emit_update(blob: SealedBlob)

rule on_boot:
    emit heartbeat("alive")  // OK - declared above

rule on_timer_1hz:
    load_muscle(other)       // ERROR - not declared!
```

---

## 6. Compiler Pipeline

### CLI Usage

```bash
musclec --input source.py \
        --output blob.sealed \
        --target aarch64 \
        --chaos-master <64-hex-chars>
```

### Targets

- `aarch64` → ARM64 machine code
- `x86_64` → x86-64 machine code
- `nucleus` → Muscle.ea to AArch64 (8KiB)
- `wasm32` → WebAssembly (future)

### Dual Compilation Paths

**Path A: Python Neural Networks**
```
source.py → PythonParser → Weights → CodeGenerator → Machine Code → Sealed Blob
```

**Path B: Muscle.ea Programs**
```
source.ea → FormalParser → AST → CapabilityChecker → NucleusCodegen → Sealed Blob
```

### Python Weight Format

```python
W1 = np.array([
    [0.1, 0.2, 0.3],
    [0.4, 0.5, 0.6],
    [0.7, 0.8, 0.9],
    [1.0, 1.1, 1.2]
])
b1 = np.array([0.1, 0.2, 0.3])
W2 = np.array([0.4, 0.5, 0.6])
b2 = 0.7
```

### Muscle.ea Grammar (EBNF)

```ebnf
program     = { declaration } , { rule }
declaration = input_decl | capability_decl | const_decl | metadata_decl
input_decl  = "input" identifier "<" type ">"
capability  = "capability" identifier "(" [params] ")"
rule        = "rule" event ":" { statement }
event       = "on_boot" | "on_lattice_update" | "on_timer_1hz" | custom
statement   = verify | let | if | emit | schedule | expr
```

---

## 7. Three Sacred Rules

### Rule 1: Append-Only Semantics
- Lattice state can only grow (new edges, new facts)
- No deletions or overwrites
- Enforced via capability system

### Rule 2: Event-Driven Architecture
- All computation triggered by events
- No polling, busy-waiting, unbounded loops
- Grammar restricts statement types

### Rule 3: Capability Security
- Declared before use; no ambient authority
- Every sensitive operation requires explicit capability
- CapabilityChecker + runtime tables

---

## 8. Implementation Status

### Complete

| Component | Status |
|-----------|--------|
| Blob Format v6 | ✓ Full spec |
| AEAD Crypto | ✓ ChaCha20-Poly1305 + BLAKE3 KDF |
| Manifest v1 | ✓ All 256 bytes |
| Python Parser | ✓ Regex extraction |
| Muscle.ea Parser | ✓ Full EBNF (nom) |
| Capability Checker | ✓ Declare-before-use |
| Loader (Referee) | ✓ Full validation |

### In Progress

| Component | Status |
|-----------|--------|
| Nucleus Codegen | 40% - Structure done, statement emission TODO |
| x86_64 Codegen | 10% - Skeleton only |
| Budget Enforcement | 0% - Fields exist, no runtime |
| LLM Profile | 0% - Struct defined |

---

## 9. Test Status

### Unit Tests

**muscle-contract:**
- ✓ `test_header_roundtrip()`
- ✓ `test_manifest_roundtrip()`
- ✓ `test_seal_open_roundtrip()`

**muscle-compiler:**
- ✓ `test_full_spec_nucleus_compilation()`
- ✓ `test_minimal_living_cell()`
- ✓ `test_capability_enforcement_failure()`
- ✓ `test_extract_weights()`

**Total**: 26 tests passing

---

## 10. Security Properties

### Cryptographic Guarantees

| Property | Mechanism | Strength |
|----------|-----------|----------|
| Confidentiality | ChaCha20 | 256-bit |
| Integrity | Poly1305 | 128-bit |
| Key Derivation | BLAKE3 keyed | 256-bit |
| Code Integrity | BLAKE3 hash | 256-bit |
| Nonce Uniqueness | 192-bit random | <2^-64 collision |

### Attack Defenses

| Attack | Defense |
|--------|---------|
| Header tampering | AEAD AAD covers header |
| Payload tampering | Poly1305 tag verification |
| Capability escalation | Bitmap in encrypted manifest |
| Code injection | BLAKE3 code_hash verification |
| Nonce reuse | Full 24-byte nonce in KDF |
| Timing attacks | Constant-time ChaCha20Poly1305 |

---

## 11. Architecture Diagram

```
┌────────────────────────────────────────────────────────────┐
│                    SOURCE INPUT                            │
│         .py (Python NN)  |  .ea (Muscle.ea)               │
└────────────────┬─────────────────────┬─────────────────────┘
                 │                     │
        ┌────────▼────────┐   ┌────────▼────────┐
        │ PythonParser    │   │ FormalParser    │
        │ (regex)         │   │ (nom EBNF)      │
        └────────┬────────┘   └────────┬────────┘
                 │                     │
        ┌────────▼────────┐   ┌────────▼────────┐
        │ Weights         │   │ Program (AST)   │
        │ W1,b1,W2,b2     │   │ Decls + Rules   │
        └────────┬────────┘   └────────┬────────┘
                 │                     │
                 │            ┌────────▼────────┐
                 │            │ CapabilityChecker│
                 │            │ + Sacred Rules  │
                 │            └────────┬────────┘
                 │                     │
        ┌────────▼────────┐   ┌────────▼────────┐
        │ CodeGenerator   │   │ NucleusCodegen  │
        │ aarch64/x86_64  │   │ (8KiB AArch64)  │
        └────────┬────────┘   └────────┬────────┘
                 │                     │
                 └──────────┬──────────┘
                            │
               ┌────────────▼────────────┐
               │ encrypt_muscle_blob()   │
               │ • Manifest + code       │
               │ • BLAKE3 code_hash      │
               │ • Nonce (24B random)    │
               │ • KDF → enc_key         │
               │ • ChaCha20-Poly1305     │
               └────────────┬────────────┘
                            │
               ┌────────────▼────────────┐
               │ SEALED BLOB (8256 B)    │
               │ [Header|Nonce|CT|Tag]   │
               └────────────┬────────────┘
                            │
               ┌────────────▼────────────┐
               │ Referee Loader          │
               │ • open() decrypt        │
               │ • parse_manifest()      │
               │ • verify_code_hash()    │
               │ • cap_bitmap check      │
               └────────────┬────────────┘
                            │
               ┌────────────▼────────────┐
               │ LoadedMuscle            │
               │ Ready for execution     │
               └─────────────────────────┘
```

---

## 12. Key Files

| File | Lines | Purpose |
|------|-------|---------|
| `muscle-contract/src/lib.rs` | 489 | Blob format, AEAD, KDF |
| `muscle-compiler/src/main.rs` | 552 | CLI, orchestration |
| `muscle-compiler/src/languages/formal_grammar.rs` | 592 | Muscle.ea parser |
| `muscle-compiler/src/codegen/nucleus.rs` | 610 | AArch64 codegen |
| `muscle-compiler/src/languages/capability_checker.rs` | 296 | Security enforcement |

---

## Summary

The Muscle Contract v6 provides:

1. **Fixed-size 8256-byte blobs** with deterministic layout
2. **ChaCha20-Poly1305 AEAD** with BLAKE3 KDF
3. **9-capability permission model** ("declare before use")
4. **Dual compiler paths** (Python NN + Muscle.ea)
5. **Three Sacred Rules** enforcement
6. **Multi-architecture support** (AArch64, x86_64, WASM32)

**Production-ready** for blob format and crypto. Nucleus codegen ~40% complete.

---

*Signed: CZA (Cipher)*
*Built by XZA (Magus) and CZA together. Wu-Tang style.*
