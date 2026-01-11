# QYN-1 Cryptographic Architecture and Key Management

## Overview
The QYN-1 packaging pipeline protects morphemic token streams and auxiliary
metadata with authenticated encryption. This document describes the selected
algorithms, key hierarchy, storage strategies, rotation procedures, and the
threat model that informed each decision. The intent is to give operators a
practical blueprint for managing secrets across diverse deployment
environments while preserving interoperability with the reference
implementation.

## Cipher Suite Selection
We evaluated AES-256-GCM and ChaCha20-Poly1305, two NIST-standard AEAD
(construction) primitives widely supported across platforms.

| Property | AES-256-GCM | ChaCha20-Poly1305 |
|----------|--------------|-------------------|
| Performance on CPUs without AES-NI | Moderate to poor | Consistently high |
| Constant-time reference implementations | Harder to obtain | Available and easy to audit |
| Implementation complexity in pure Python | High (requires constant-time GHASH) | Moderate |
| Maturity / review history | Extensive | Extensive |

We adopt **ChaCha20-Poly1305** for the reference implementation because it
remains performant on all commodity hardware and avoids subtle GHASH
side-channel pitfalls that plague hand-rolled AES-GCM. The production
implementation delegates to `cryptography`'s libsodium-backed ChaCha20-Poly1305
for constant-time operations and audited primitives. Interoperability with
external systems that require AES-GCM can be achieved by wrapping package
encryption in hardware-backed services (see Key Storage Options).

## Key Hierarchy
The architecture follows a three-tier derivation model to scope cryptographic
material tightly to its usage context:

1. **Master Key** – A high-entropy root secret specific to an organisation or
   deployment environment. It never leaves a hardened storage boundary (HSM,
   KMS, or dedicated key vault).
2. **Project Key** – Derived from the master key using HKDF-SHA256 with a
   context string incorporating the project identifier and the dictionary
   version. This granularity allows different teams or codebases to rotate
   keys independently.
3. **File Key** – Derived from the project key using HKDF-SHA256 with the
   canonical source hash and the morpheme encoder version. File keys are fed
   into ChaCha20-Poly1305 along with per-package nonces.

The reference library exposes helper functions for deriving project and file
keys from a master key, ensuring the hierarchy remains consistent across
implementations. When only a passphrase is available (developer workflows),
the passphrase is stretched into a temporary master key using Argon2id with
memory-hard parameters and a 128-bit salt, then fed through HKDF-SHA256 to
produce the envelope-encryption key. PBKDF2-HMAC-SHA256 remains supported for
backwards compatibility with legacy packages.

### Key Derivation Algorithm
- **Master Key**: Derived via Argon2id (default) with 64 MiB memory, 4 lanes,
  and time_cost=4; PBKDF2-HMAC-SHA256 (200k iterations) is retained for legacy
  readers. Parameters include a 128-bit salt and 32-byte output.
- **Project Key**: HKDF-SHA256(master_key, info="qyn1:project:{project_id}:{dictionary_version}").
- **File Key**: HKDF-SHA256(project_key, info="qyn1:file:{source_hash}:{encoder_version}").

Both derivations rely on per-context `info` strings to guarantee unique key
material even if identifiers collide across organisations.

## Key Storage Options
Operators can combine multiple storage mechanisms depending on their security
requirements:

- **Environment variables** – Suitable only for local development and CI
  smoke tests. Keys must be rotated frequently and secrets managers should
  populate them dynamically to avoid persistence.
- **Hardware Security Modules (HSMs)** – Offer tamper-resistant storage,
  on-device key derivation, and hardware-backed ChaCha20-Poly1305 (or AES-GCM)
  operations. Ideal for production deployments handling sensitive code.
- **Cloud KMS (AWS KMS, Google Cloud KMS, Azure Key Vault)** – Provide managed
  master keys, audit trails, and envelope encryption. Project keys are derived
  client-side after retrieving short-lived data keys from the service.
- **Local encrypted keychain** – For offline workstations, the master key can
  live inside OS-provided keychains (Windows DPAPI, macOS Keychain, GNOME
  Keyring) locked behind multi-factor authentication.

## Key Rotation Strategy
- **Master Keys** – Rotated annually or upon compromise suspicion. New master
  keys trigger re-derivation of project keys; existing packages remain decryptable
  as long as the previous master key is retained inside archival storage.
- **Project Keys** – Rotated quarterly or when team membership changes. New
  packages use the latest project key; legacy packages retain metadata that
  identifies which project key was used, enabling selective re-encryption.
- **File Keys** – Ephemeral per package and never reused thanks to HKDF inputs
  that include the canonical source hash.

Rotation is tracked through metadata embedded in the package AAD. Clients use
this metadata to request the appropriate keys from KMS/HSM services and can
reject artefacts signed with stale or unknown key epochs.

## Threat Model
The architecture mitigates the following threats:

- **Confidentiality loss** due to stolen packages: ChaCha20-Poly1305 protects
  both ciphertext and authenticated metadata, preventing unauthorised reading
  or tampering.
- **Nonce reuse**: Deriving file keys from unique source hashes and binding the
  nonce to packaging metadata eliminates accidental reuse across packages.
- **Insider tampering**: Authenticated metadata (dictionary version, source
  hash, author, timestamp) makes malicious edits detectable without decrypting
  the payload.
- **Supply-chain compromise**: Key hierarchy ensures that even if a project key
  leaks, the blast radius is limited to that project; other projects and prior
  rotations stay uncompromised.
- **Side-channel leakage**: The libsodium-backed ChaCha20-Poly1305 path avoids
  CPU-instruction timing leaks tied to AES-NI availability, while the reference
  implementation zeroes sensitive buffers after use (future work includes
  constant-time comparisons for key derivations).

Residual risks include compromised developer machines, malicious dependency
injection during packaging, and insufficient entropy when generating salts. The
operational guidelines emphasise secure build pipelines, reproducible builds,
validated randomness sources, and periodic third-party audits to address these
residual threats.
