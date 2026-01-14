# MCS Format v1.0 Specification

## 1. Overview

The Quenyan Morpheme Container Stream (MCS) format stores canonicalised abstract
syntax trees, morpheme streams, compression metadata, and authenticated
cryptographic payloads in a single binary envelope. Files are composed of two
nested records:

1. **Wrapper** – an unauthenticated envelope that exposes the wrapper version and
   encrypted payload metadata required for decoding.
2. **Payload** – an AEAD-protected binary structure that contains sections for
   stream description, compression model, morpheme tokens, and optional
   artefacts such as source maps.

All multi-byte integers are encoded in big-endian order unless otherwise noted.
Fixed-width integers follow the size suffix conventions `u8`, `u16`, and `u32`.

Binary layout diagram:

```
+---------------------+-----------------------------------------------------+
| Offset (bytes)      | Field                                                |
+=====================+=====================================================+
| 0                   | Wrapper magic `0x51 0x59 0x4e 0x31` ("QYN1")        |
| 4                   | Wrapper version: major (u8)                          |
| 5                   | Wrapper version: minor (u8)                          |
| 6..7                | Wrapper version: patch (u16, big-endian)            |
| 8..11               | Wrapper JSON length (u32, big-endian)               |
| 12..(12+length-1)   | Canonical JSON wrapper document                     |
+---------------------+-----------------------------------------------------+
```

The canonical JSON document contains:

```json
{
  "version": "<wrapper version>",
  "payload_version": "<payload version>",
  "metadata": { ... canonical key ordering ... },
  "salt": "<base64>",
  "nonce": "<base64>",
  "ciphertext": "<base64>",
  "tag": "<base64>"
}
```

The ciphertext is the ChaCha20-Poly1305 encryption of the payload envelope
(described below) with associated data computed from the metadata section.

## 2. Payload Header

The decrypted payload begins with a fixed header:

```
+---------------------+-----------------------------------------------------+
| Offset (bytes)      | Field                                                |
+=====================+=====================================================+
| 0..3                | Payload magic `0x4d 0x43 0x53 0x00` ("MCS\0")       |
| 4                   | Payload version: major (u8)                         |
| 5                   | Payload version: minor (u8)                         |
| 6..7                | Payload version: patch (u16, big-endian)           |
| 8..11               | Payload body length (u32, big-endian)              |
| 12..                | Sequence of length-prefixed sections               |
+---------------------+-----------------------------------------------------+
```

The payload body length spans the concatenation of section records. Sections are
self-describing and can be skipped safely by decoders that do not recognise an
identifier.

## 3. Section Grammar

Each section record is encoded as:

```
struct SectionHeader {
  u16 section_id;       // little-endian
  u16 section_flags;    // little-endian, bitfield defined per-section
  u32 section_length;   // little-endian byte length of payload
  u8  payload[section_length];
}
```

The use of little-endian integers in the section header mirrors the
stream-oriented chunk layout used by PNG. Sections MAY appear in any order, but
writers MUST emit them in the canonical ordering shown below to ensure
bit-for-bit reproducibility.

### 3.1 Section Catalogue

| Section ID | Mnemonic      | Requirement | Description                                      |
|------------|---------------|-------------|--------------------------------------------------|
| `0x0001`   | `STREAM`      | Required    | Canonical stream metadata and morpheme summary.  |
| `0x0002`   | `COMPRESS`    | Required    | Compression backend and probability model.       |
| `0x0003`   | `TOKENS`      | Required    | Length-prefixed ANS-compressed morpheme stream.  |
| `0x0004`   | `STRINGS`     | Required    | Length-prefixed compressed string table bytes.   |
| `0x0005`   | `PAYLOADS`    | Required    | JSON array of auxiliary payload descriptors.     |
| `0x0006`   | `SMAP`        | Optional    | Compressed source map blob.                      |
| `0x0007`   | `METADATA`    | Required    | Canonical JSON metadata (authenticated).         |
| `0x7F00`   | `EXTENSION`   | Optional    | Generic extension container (see §8).            |

Writers MUST set the `STREAM` flag bit `0x0001` when a source map is present.
Flags in other sections are presently reserved and MUST be zero.

## 4. STREAM Section (`0x0001`)

Payload structure:

```
struct StreamSection {
  u16 dictionary_version_length;
  u8  dictionary_version[dictionary_version_length];
  u16 encoder_version_length;
  u8  encoder_version[encoder_version_length];
  u16 source_language_length;
  u8  source_language[source_language_length];
  u16 source_language_version_length;
  u8  source_language_version[source_language_version_length];
  u32 symbol_count;               // little-endian
  u8  hash_scheme;                // currently 0 == SHA-256
  u8  source_hash[32];
}
```

Strings are UTF-8 with `u16` little-endian length prefixes. Absent optional
strings are encoded as zero-length values. `source_hash` contains either the
32-byte SHA-256 digest of the canonicalised source or all zeros when the hash is
unknown. Additional hash schemes can be negotiated by incrementing the
`hash_scheme` field and advertising support via the extension mechanism.

## 5. COMPRESS Section (`0x0002`)

```
struct CompressSection {
  u16 backend_name_length;
  u8  backend_name[backend_name_length];
  u32 symbol_count;               // little-endian
  u32 model_blob_length;          // little-endian
  u8  model_blob[model_blob_length];  // Canonical JSON document
  u32 extras_blob_length;         // little-endian
  u8  extras_blob[extras_blob_length]; // Optional canonical JSON (may be empty)
}
```

`model_blob` encodes the static probability distribution for ANS or other
compression algorithms. The JSON document MUST use sorted keys and omit
insignificant whitespace. `extras_blob` provides backend-specific hints and MAY
be empty.

## 6. TOKENS Section (`0x0003`)

The payload is a length-prefixed byte sequence representing the morpheme stream
compressed by the configured backend. Writers MUST use a 32-bit little-endian
length prefix followed by raw bytes emitted by the compression engine.

## 7. STRINGS Section (`0x0004`)

The string table section mirrors the tokens section: a 32-bit little-endian
length prefix followed by compressed table data. String table encoding is
implementation-defined but MUST be lossless and deterministic.

## 8. PAYLOADS Section (`0x0005`)

Encodes auxiliary payload records as canonical JSON. The binary layout is a
32-bit little-endian length prefix followed by UTF-8 JSON text representing an
object with a single key `"payloads"` whose value is an array. The array entries
mirror the `payloads` exported by the primary encoder (e.g., code spans, macro
expansions).

## 9. Source Map Section (`0x0006`)

When present, the source map section contains a 32-bit length prefix followed by
compressed source map bytes (typically CBOR-deflated). Readers that do not
understand the compression scheme MAY ignore the section after authenticating
the payload.

## 10. Metadata Section (`0x0007`)

The metadata section binds contextual information (language, timestamps,
licensing) to the encrypted payload. It uses the same length-prefixed canonical
JSON format as the `PAYLOADS` section. The metadata document is included in the
AEAD associated data using the expression:

```
AAD = "QYN1-METADATA-v1:" || canonical_json(metadata)
```

Readers MUST verify the AEAD tag before consuming any metadata contents.

## 11. Morpheme Dictionary Encoding

Dictionary versions are tracked by semantic version strings within the `STREAM`
section. The actual morpheme dictionary is not stored inline; instead, the
version string is resolved by the decoder to the appropriate dictionary artefact
(e.g., `morpheme_dictionary_v1.json`). If a dictionary delta is required, it is
carried as a dedicated `EXTENSION` record.

## 12. Compression Format

The morpheme stream is compressed using rANS or a compatible backend indicated
in the `COMPRESS` section. Backends MUST produce deterministic output for the
same input token sequence and model. The probability table stored in
`model_blob` allows offline training and on-device decoding without recomputing
statistics.

## 13. Encryption Format

Quenyan packages use ChaCha20-Poly1305 AEAD with 96-bit nonces and 256-bit keys.
Keys are derived via PBKDF2-HMAC-SHA256 with 200,000 iterations using the
provided salt. The wrapper stores the salt, nonce, ciphertext, and tag as Base64
strings. Implementations MUST reject ciphertext when tag verification fails.

## 14. String Table Format

String table payloads are encoder-defined byte streams that MUST round-trip via
the `qyn1.string_table` module. Implementations SHALL treat the byte payload as
opaque and rely on the canonical encoder to manage compression features such as
prefix tables or delta chains. Future revisions MAY specify a normative string
encoding.

## 15. Optional Metadata Blocks

Optional metadata (comments, docstrings, provenance) is captured via additional
objects inside the `payloads` array or via dedicated `EXTENSION` sections.
Encoders SHOULD reference the metadata preservation ledger to describe the
structure used for a given project.

## 16. Integrity and Signatures

Every package includes an AEAD authentication tag that covers the entire payload
and metadata. Optionally, projects may add an `EXTENSION` section with a digital
signature over the wrapper header and payload using project-specific keys. The
reserved section IDs `0x7F01`–`0x7FFF` are allocated for signature schemes and
revocation manifests.

## 17. Extension Mechanisms

The format reserves high-bit section identifiers (`0x7F00`–`0x7FFF`) for
extensions. Readers MUST ignore unrecognised extension IDs while retaining the
associated bytes for authenticated verification. Writers introducing new
features MUST document the section ID and set capability flags in the metadata
under `metadata.capabilities`.

Within existing sections, reserved bytes and zero-length placeholders permit
non-breaking augmentation. For example, additional hash algorithms can be
negotiated via a new `hash_scheme` value paired with a feature flag.

## 18. Versioning

Wrapper and payload semantic versions are encoded separately. Readers MUST
compare the major version before attempting decoding. If the major version is
unsupported, decoding MUST fail with an informative diagnostic. Minor versions
MAY introduce new optional sections or fields guarded by feature flags.

## 19. Conformance Test Vectors

Reference encoders and decoders located in `reference/python`, `reference/js`,
`reference/rust`, and `reference/go` produce canonical byte streams that serve
as normative examples. The `tests/test_reference_impls.py` test case asserts
bit-for-bit identity between implementations. Additional cross-version corpora
are maintained under `tests/data/compatibility`.

