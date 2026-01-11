# Ea Muscle Blob Contract v6

Status: Draft
Scope: Sealed muscle blob format, cryptographic sealing/opening, manifest layout, and limits.

This contract defines the smallest reliable unit of execution (a "muscle") and the
cryptographic envelope used to load it. It is designed for fixed-size, capability-limited
execution on AArch64 first, with clear paths to custom hardware.

## Goals

- Fixed-size blobs for predictability and safety.
- Minimal trusted parsing surface (header + AEAD only).
- Explicit capability and budget limits in a fixed manifest.
- Portability across AArch64 hardware (QEMU virt today, custom boards later).
- Deterministic test mode without weakening production crypto.

## Blob Size and Layout

Total size is fixed at 8256 bytes.

```
| Offset | Size | Field        | Notes                                  |
|--------|------|--------------|----------------------------------------|
| 0      | 24   | Header       | Unencrypted, authenticated as AAD      |
| 24     | 24   | Nonce        | 24-byte nonce field (see crypto)       |
| 48     | 8192 | Ciphertext   | Encrypted payload                      |
| 8240   | 16   | Tag          | ChaCha20-Poly1305 tag                  |
```

## Header (24 bytes)

All integers are little-endian.

```
struct EaM6Header {
  magic[4]      = "EaM6";
  version       = 0x06;       // format version
  header_len    = 24;         // must be 24
  flags         = u8;         // see flags below
  arch          = u8;         // 1=aarch64, 2=x86_64, 3=wasm32
  cap_bitmap    = u32;        // coarse capabilities, see table
  payload_len   = u16;        // must be 8192
  manifest_len  = u16;        // must be 256
  reserved[8];                // zero for now
}
```

Flags:
- bit 0: deterministic_nonce (tests only; MUST be 0 in production)
- bit 1: has_llm_profile
- bit 2: has_organelle_map
- bits 3-7: reserved, must be 0

## Cryptography

AEAD: ChaCha20-Poly1305

Key derivation (BLAKE3 keyed mode):

```
enc_key = blake3_keyed_hash(master_key, "EaM6 key" || header || nonce)
```

- `master_key` is 32 bytes.
- `header` is the exact 24 bytes in the blob.
- `nonce` is the 24-byte nonce field in the blob.

AAD: the 24-byte header.

Nonce:
- 24 bytes stored in the blob.
- The first 12 bytes are used as the ChaCha20-Poly1305 nonce.
- The full 24 bytes are included in key derivation to avoid nonce/key reuse.
- MUST be random and unique per blob in production.
- MAY be deterministic only for test vectors.

## Payload (8192 bytes, encrypted)

The first 256 bytes are the manifest. The remainder is muscle code + data.

```
| Offset | Size | Field            | Notes                      |
|--------|------|------------------|----------------------------|
| 0      | 256  | Manifest         | fixed-size, see below      |
| 256    | N    | Code + Data      | code_size <= 7936          |
```

### Manifest (256 bytes)

```
struct MuscleManifestV1 {
  magic[4]          = "EaMM";
  version           = 0x01;
  flags             = u8;       // reserved for future
  arch              = u8;       // must match header.arch
  abi               = u8;       // 0=raw, 1=wasm
  code_offset       = u16;      // must be 256
  code_size         = u16;      // <= 7936
  entrypoint        = u32;      // offset from code start
  memory_pages      = u16;      // 4KiB pages
  stack_pages       = u8;
  heap_pages        = u8;
  update_budget     = u16;      // max lattice updates
  io_budget         = u16;      // max IO ops per run
  capability_bitmap = u32;      // must match header.cap_bitmap
  muscle_id[32];                // 32-byte identifier
  muscle_version    = u64;      // monotonic version
  code_hash[32];                // BLAKE3(code region)
  llm_profile_off   = u16;      // 0 if none
  llm_profile_len   = u16;
  organelle_off     = u16;      // 0 if none
  organelle_len     = u16;
  reserved[148];                // zero for now
}
```

### Capability Bitmap (coarse)

- bit 0: lattice_read
- bit 1: lattice_write
- bit 2: clock_read
- bit 3: storage_read
- bit 4: storage_write
- bit 5: net_client
- bit 6: net_server
- bit 7: spawn_successor
- bit 8: use_accelerator
- bits 9-31: reserved

Kernel MUST enforce that the effective capabilities are no greater than this bitmap.

## LLM Profile (optional)

Placed inside the payload at `llm_profile_off` with length `llm_profile_len`.

```
struct LlmProfileV1 {
  magic[4]        = "EaLM";
  version         = 0x01;
  quantization    = u8;     // 0=f16,1=q8_0,2=q4_0,...
  tensor_format   = u8;     // 0=ggml,1=gguf,2=custom
  reserved0       = u8;
  max_context     = u16;
  max_tokens      = u16;
  vocab_size      = u32;
  weights_root[32];         // lattice root for weight pages
  rope_base       = u32;
  rope_scale      = u32;
  reserved[12];
}
```

## Organelle Map (optional)

Placed inside the payload at `organelle_off` with length `organelle_len`.
It defines offsets for WASM or native organelles used by the muscle.

## Sealing Procedure (Compiler)

1. Build manifest (including code_hash).
2. Assemble payload: manifest + code/data padded to 8192 bytes.
3. Construct header with fixed sizes and capability bitmap.
4. Generate 24-byte nonce (random in production).
5. Derive enc_key with BLAKE3 keyed hash.
6. Encrypt payload with ChaCha20-Poly1305 using AAD=header and nonce[0..12].
7. Emit header + nonce + ciphertext + tag.

## Opening Procedure (Referee / Loader)

1. Parse header, validate magic/version/lengths.
2. Derive enc_key using header + nonce.
3. AEAD decrypt with AAD=header; reject on failure.
4. Parse manifest; validate magic/version/arch match.
5. Validate code_hash and code_size bounds.
6. Enforce capability bitmap, memory pages, update/IO budgets.

## Test Vectors

Deterministic vectors MUST be provided by the compatibility harness.
Production builds MUST set flags bit0=0 and use random nonces.

## Invariants

- Total blob size is exactly 8256 bytes.
- payload_len is 8192, manifest_len is 256.
- capability bitmap in header MUST match manifest.
- Nonce uniqueness is required per master_key.
