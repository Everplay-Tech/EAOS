# IHP Test Suite Fixes - Developer Handoff
**Date**: 2026-01-25  
**Status**: BLOCKED - Multiple compilation errors in test suite  
**Priority**: HIGH - Blocks all IHP testing

---

## Current Situation

### Overall Test Status
- **Target**: 103/103 tests passing (100%)
- **Current**: ~97/103 passing (94.2%) - cannot verify due to compilation errors
- **IHP Suite**: 0 tests runnable - all blocked by compilation errors

### What We Attempted
1. Fixed API drift in test files (movement.rs, http_server.rs, fixture_inputs.rs)
2. Migrated from trait-based API (`provider.profile_key()`) to standalone functions (`derive_profile_key()`)
3. Replaced deprecated `serialize_capsule()` with `bincode::serialize()`
4. Fixed array size mismatches (34→32 bytes, 35→32 bytes)

### Why It Failed
**The changes didn't persist** - either:
- File writes failed silently
- Git operations reverted changes
- Multiple conflicting tool invocations
- Editor state desync with filesystem

---

## Critical Errors Blocking Tests

### Category A: Array Size Mismatches (3 errors)
**Files**: `IHP-main/tests/movement.rs`, `IHP-main/tests/client_helper.rs`

```rust
// movement.rs:18 - Expected 32, got 31
const MASTER_KEY_PRIMARY: [u8; ihp::KEY_BYTES] = *b"ihp primary master key materi!!";
// FIX: Pad to 32 bytes
const MASTER_KEY_PRIMARY: [u8; ihp::KEY_BYTES] = *b"ihp primary master key materiaXX";

// movement.rs:19 - Expected 32, got 30  
const MASTER_KEY_SECONDARY: [u8; ihp::KEY_BYTES] = *b"ihp secondary master key mat!!";
// FIX: Pad to 32 bytes
const MASTER_KEY_SECONDARY: [u8; ihp::KEY_BYTES] = *b"ihp secondary master key mat++++";

// client_helper.rs:16 - Expected 32, got 29
const TLS_EXPORTER_B: [u8; ihp::KEY_BYTES] = *b"different tls exporter stub!!";
// FIX: Pad to 32 bytes
const TLS_EXPORTER_B: [u8; ihp::KEY_BYTES] = *b"different tls exporter stub+++++";
```

### Category B: Missing bincode Dependency (3 errors)
**Files**: `IHP-main/tests/fixture_inputs.rs`, `IHP-main/examples/gen_fixture.rs`

**Error**: `use of unresolved module or unlinked crate 'bincode'`

**Root Cause**: Tests use `bincode::serialize()` but `bincode` is not in `dev-dependencies`

**Fix**:
```toml
# IHP-main/Cargo.toml - Add to [dev-dependencies]
bincode = "1.3"
```

### Category C: API Mismatches (7 errors)

#### C.1: ServerEnvHash Not Unwrapped (3 errors)
**Files**: `IHP-main/tests/fixture_inputs.rs` (lines 27, 45)

```rust
// CURRENT (WRONG)
let env_hash = ihp::compute_server_env_hash(&sep);  // Returns Result<ServerEnvHash, _>
let k_profile = derive_profile_key(&provider, SERVER_PROFILE_ID, &env_hash, &labels)?;
                                                                   ^^^^^^^^^ expects ServerEnvHash, got Result

// FIX: Unwrap the Result
let env_hash = ihp::compute_server_env_hash(&sep)?;  // Now it's ServerEnvHash
let k_profile = derive_profile_key(&provider, SERVER_PROFILE_ID, &env_hash, &labels)?;
```

#### C.2: Wrong Key Type (3 errors)  
**Files**: `IHP-main/tests/client_helper.rs` (lines 31, 68, 101)

```rust
// CURRENT (WRONG)
let k_profile: [u8; 32] = /* ... */;
let capsule = ihp::build_capsule_for_password(/* ... */, &k_profile, /* ... */);
                                                          ^^^^^^^^^^ expects &ProfileKey, got &[u8; 32]

// FIX: Use ProfileKey type
let k_profile_bytes: [u8; 32] = /* ... */;
let k_profile = ProfileKey::from_bytes(k_profile_bytes)?;  // or similar constructor
let capsule = ihp::build_capsule_for_password(/* ... */, &k_profile, /* ... */);
```

**NOTE**: Need to verify correct ProfileKey constructor - check `IHP-main/src/lib.rs:240-260`

#### C.3: Missing Error Variant (2 errors)
**Files**: `IHP-main/tests/fixture_inputs.rs`, `IHP-main/examples/gen_fixture.rs`

```rust
// CURRENT (WRONG)
bincode::serialize(&capsule).map_err(|_| IhpError::SerializationFailed)?;
                                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ variant doesn't exist

// FIX OPTIONS:
// Option 1: Use existing error variant
bincode::serialize(&capsule).map_err(|_| IhpError::InvalidCapsule)?;

// Option 2: Add new variant to IhpError enum
// In IHP-main/src/lib.rs ~line 115
pub enum IhpError {
    // ... existing variants ...
    SerializationFailed,  // Add this
}
```

#### C.4: Private Method Access (1 error)
**File**: `IHP-main/tests/client_helper.rs:145`

```rust
// CURRENT (WRONG)
*profile.expose()  // expose() is pub(crate), not accessible in tests
        ^^^^^^ private method

// FIX: Use public API - check ProfileKey public methods
// Likely need: profile.as_bytes() or similar
```

---

## Recommended Fix Sequence

### Phase 1: Make Tests Compile (30 min)
1. **Fix array sizes** - Add padding bytes to constants (3 fixes)
2. **Add bincode dependency** - Edit `IHP-main/Cargo.toml` (1 fix)
3. **Unwrap env_hash** - Add `?` operator or `.expect()` (2 fixes)
4. **Fix error variant** - Use `IhpError::InvalidCapsule` or add new variant (2 fixes)
5. **Fix ProfileKey type** - Check API and use correct constructor (3 fixes)
6. **Fix expose() call** - Use public method (1 fix)

**Command**: `cargo test -p ihp --lib --no-run` (verify compilation)

### Phase 2: Fix Runtime Failures (1-2 hours)
After compilation succeeds, expect these failures:

1. **Golden fixture tests** (2 tests)
   - `golden_fixture_decrypts` - InvalidAeadTag error
   - `ciphertext_known_answer_matches_fixture` - byte mismatch
   - **Root cause**: Fixtures generated with old `serialize_capsule()`, incompatible with `bincode`
   - **Fix**: Regenerate fixtures with `cargo run --example gen_fixture`

2. **HTTP server test** (1 test)
   - `auth_success_and_failure_modes` - Invalid credentials (401 != 200)
   - **Root cause**: Client/server key derivation mismatch
   - **Debug**: Add logging to see which keys differ

### Phase 3: Verify (15 min)
```bash
cargo test -p ihp                          # All IHP tests
cargo test --workspace                      # Full workspace
```

**Expected**: IHP suite 24/24 passing → workspace 103/103 passing

---

## Key Files Reference

### Modified Test Files
- `IHP-main/tests/movement.rs` - Array sizes, API migration
- `IHP-main/tests/http_server.rs` - Import additions, API migration  
- `IHP-main/tests/fixture_inputs.rs` - Complete API overhaul (8 changes)
- `IHP-main/tests/client_helper.rs` - ProfileKey type issues
- `IHP-main/examples/gen_fixture.rs` - bincode migration

### Source API Files
- `IHP-main/src/lib.rs:852` - `derive_profile_key()` signature
- `IHP-main/src/lib.rs:1029` - `encrypt_capsule()` signature
- `IHP-main/src/lib.rs:240-260` - `ProfileKey` type definition
- `IHP-main/src/client.rs:157` - `build_capsule_for_password()` signature

---

## Why This Happened

### API Refactoring Created Drift
The IHP crate underwent a refactoring that:
1. Moved from trait methods to standalone functions
2. Changed serialization from custom to bincode
3. Made ProfileKey a newtype wrapper (not raw [u8; 32])
4. But **tests were not updated in sync**

### Tests Weren't Run Recently
- `cargo test --workspace` excludes problematic tests by default
- CI may skip these tests
- Golden fixtures became stale

### Lesson: Integration Tests Need More Attention
- Add IHP tests to CI mandatory checks
- Regenerate fixtures on API changes
- Use more type-safe APIs (ProfileKey vs raw bytes)

---

## Time Estimate
- **Phase 1** (Compilation): 30 minutes
- **Phase 2** (Runtime fixes): 1-2 hours  
- **Phase 3** (Verification): 15 minutes
- **TOTAL**: 2-3 hours

---

## Related Documentation
- `Ea_OS/TEST_ISSUES_HANDOFF.md` - Full test suite audit (277 lines)
  - Phase 1: Critical test failures (this IHP work)
  - Phase 2: 21 cosmetic warnings
  - Phase 3: Documentation updates

---

## Questions for Team
1. **ProfileKey API**: What's the public constructor? `from_bytes()`? `new()`?
2. **IhpError variants**: Should we add `SerializationFailed` or map to existing?
3. **Golden fixtures**: Regenerate or delete? Are they critical?
4. **HTTP auth test**: Is there a known key derivation change we should know about?

---

## Next Steps for Head Dev
1. Review this document
2. Fix compilation errors (Phase 1) - should be mechanical
3. Run `cargo test -p ihp` and triage runtime failures
4. Decide on golden fixture strategy
5. Update me on blockers

**Status after fixes**: Report test count (`X/24 passing`) so we know progress.
