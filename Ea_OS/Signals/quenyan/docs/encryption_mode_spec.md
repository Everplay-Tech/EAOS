# QYN-1 Encryption Mode Specification

This document reconciles the requirement for deterministic packages (to enable
content-addressable storage and deduplication) with modern AEAD nonce
requirements.

## Background
ChaCha20-Poly1305 requires a unique nonce for every `(key, nonce)` pair to
preserve confidentiality. Deterministic encodings are desirable when packages
serve as build artefacts stored in deduplicated object stores.

We considered three approaches:

1. **Synthetic nonces derived from content hashes**
   - Nonce = `Truncate_96bits( H(source_hash || dictionary_version || salt) )`
   - Pros: Deterministic artefacts, compatible with content-addressable
     workflows.
   - Cons: Requires a secret salt to avoid chosen-plaintext attacks that abuse
     nonce predictability. Salt rotation invalidates the deterministic
     property.

2. **Random nonces stored alongside ciphertext**
   - Pros: Simplicity, proven security bounds, compatible with existing AEAD
     proofs.
   - Cons: Package bytes differ across invocations, reducing deduplication
     efficiency and complicating reproducibility checks.

3. **Hybrid model (default random, optional deterministic)**
   - Pros: Operators can enable deterministic packaging for public code or test
     fixtures while retaining strong guarantees for sensitive material.
   - Cons: Requires policy enforcement to avoid accidental deterministic usage
     with secret inputs.

## Selected Strategy
The reference implementation adopts the **hybrid model**:

- **Random mode (default):** Packages use 96-bit `os.urandom` nonces. The nonce
  is stored inside the wrapper and authenticated via AEAD. This mode is
  mandatory for any input that contains secrets or proprietary code.
- **Deterministic mode (opt-in):** Operators may provide a deterministic nonce
  derived from the canonical source hash and a project-wide secret salt managed
  via the key hierarchy. The salt never leaves the key management boundary and
  is rotated alongside project keys. Deterministic mode is exposed via the
  higher-level orchestration layer, not the CLI, to prevent casual misuse.

## Security Analysis
- Deterministic mode is only safe if (a) the salt remains secret, (b) the same
  `(key, salt)` pair is never reused after rotation, and (c) the canonical
  source hash is collision-resistant (SHA-256). Operators must ensure salts are
  generated with at least 128 bits of entropy and stored in HSM/KMS systems.
- Random mode inherits the security guarantees of ChaCha20-Poly1305 as long as
  nonces are never reused. The reference implementation enforces this by
  generating nonces with `os.urandom` and never accepting caller-provided
  nonce values.
- Switching between modes does not impact ciphertext authentication because the
  metadata (including the selected mode) is bound to the ciphertext as
  additional authenticated data (AAD). Tampering with the mode or nonce leads
  to tag verification failure.

## Operational Guidance
- Production pipelines MUST default to random mode. Deterministic mode requires
  an explicit policy exception and a security review.
- When deterministic mode is authorised, the salt should be versioned and the
  salt identifier included in the package metadata. Rotation invalidates the
  deterministic output; downstream caches must refresh accordingly.
- Metadata emitted by the encoder includes the canonical source hash, encoder
  version, dictionary version, and compression parameters. Clients must verify
  this metadata before deciding which decryption mode to apply.

## Future Work
- Implement streaming encryption support to avoid buffering large packages.
- Allow deterministic mode only when packages are marked "public" via metadata
  so that decryptors can reject deterministic packages that claim to contain
  secrets.
- Expand automated audits to flag nonce reuse or mode misconfiguration across
  a fleet of build agents.
