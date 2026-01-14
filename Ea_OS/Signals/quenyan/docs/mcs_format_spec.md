# Morphemic Container Stream (MCS) Format v1.0 Specification

## 1. Overview

The Morphemic Container Stream (MCS) format encapsulates canonicalised Quenyan
encoder output together with compression models, metadata, and authenticated
cryptographic material.  All MCS artefacts are encoded as a **wrapper envelope**
and a **payload envelope**.  Each envelope is serialised as UTF-8 JSON for
transport convenience while the sections embedded inside the payload are
byte-precise binary structures described in this document.

```
+----------------------+------------------------------+
| Offset               | Contents                     |
+======================+==============================+
| 0                    | ASCII "QYN1" magic literal   |
| 4                    | u8 wrapper major version     |
| 5                    | u8 wrapper minor version     |
| 6                    | u16 wrapper patch version    |
| 8                    | u32 JSON byte length (Lw)    |
| 12                   | UTF-8 JSON wrapper (Lw bytes)|
+----------------------+------------------------------+
```

*   **Magic literal** guards against format confusion.
*   **Version fields** use semantic versioning.  All integers in the wrapper
    header are encoded big-endian.
*   **JSON wrapper** contains authenticated metadata, AEAD parameters, and the
    payload envelope serialised as base64.

The payload envelope repeats the version triplet and holds the binary sections
that implement the logical components of an encoded stream.

```
+----------------------+------------------------------------+
| Offset               | Contents                           |
+======================+====================================+
| 0                    | ASCII "MCS\0" payload magic        |
| 4                    | u8 payload major version           |
| 5                    | u8 payload minor version           |
| 6                    | u16 payload patch version          |
| 8                    | u32 payload byte length (Lp)       |
| 12                   | payload body (Lp bytes)            |
+----------------------+------------------------------------+
```

The payload body is itself a concatenation of typed sections.  Every section
uses the following canonical layout:

```
+----------------------+------------------------------------+
| Offset               | Contents                           |
+======================+====================================+
| 0                    | u16 section identifier (SID)       |
| 2                    | u16 feature flags                  |
| 4                    | u32 section length in bytes (Ls)   |
| 8                    | section payload (Ls bytes)         |
+----------------------+------------------------------------+
```

Sections **MUST** be stored in ascending `SID` order.  Unrecognised `SID`
values are ignored by compliant decoders, enabling forward-compatible
extensions.

## 2. Wrapper header fields

The JSON wrapper maps directly to the authenticated metadata exposed by the
AEAD layer.  The canonical structure is shown below (JSON Pointer references in
parentheses refer to the payload sections that the fields authenticate):

| Field             | Type   | Description |
|-------------------|--------|-------------|
| `version`         | string | Semantic version of wrapper (`#/version`). |
| `payload_version` | string | Mirror of the payload header version for redundancy. |
| `metadata`        | object | High-level package metadata (see §7). |
| `nonce`           | string | Base64-encoded 96-bit ChaCha20 nonce. |
| `salt`            | string | Base64-encoded 128-bit Argon2id salt. |
| `ciphertext`      | string | Base64 payload envelope (AEAD ciphertext). |
| `tag`             | string | Base64 Poly1305 authentication tag. |

The wrapper is authenticated using the canonicalised metadata object as
associated data.  Absent metadata falls back to the fixed literal
`QYN1-PACKAGE-v1`, permitting legacy compatibility.

## 3. Payload sections

The payload body for version 1.0 is composed of the following mandatory
sections.  Each section uses **little-endian** integers for compactness.

### 3.1 Section 0x0001 – Stream Header

```
SID: 0x0001 (Stream Header)
Flags: bit0 => presence of optional source map section

+---------+-------------------+------------------------------------------+
| Offset  | Field             | Description                              |
+=========+===================+==========================================+
| 0       | u16 dictionary id | ASCII digits of dictionary version (len) |
| 2       | bytes             | Dictionary version UTF-8 string          |
| 2+len   | u16 encoder id    | ASCII digits of encoder version (len)    |
| ...     | bytes             | Encoder version UTF-8 string             |
| ...     | u8 lang len       | Source language identifier length        |
| ...     | bytes             | UTF-8 language identifier                 |
| ...     | u8 lang ver len   | Source language version length           |
| ...     | bytes             | UTF-8 language version                    |
| ...     | u32 symbol count  | Token count prior to compression         |
| ...     | u8 hash type      | 0 = SHA-256                              |
| ...     | 32 bytes          | Source hash digest                       |
+---------+-------------------+------------------------------------------+
```

Strings are length-prefixed with a 16-bit or 8-bit unsigned integer as noted.
Any additional optional key/value metadata is encoded in Section 0x0007.

### 3.2 Section 0x0002 – Compression Model

```
SID: 0x0002 (Compression Model)
Flags: none (reserved)

+---------+-----------------------------+--------------------------------------+
| Offset  | Field                       | Description                          |
+=========+=============================+======================================+
| 0       | u16 backend len             | UTF-8 backend identifier length      |
| 2       | bytes                       | Backend identifier string            |
| ...     | u32 symbol count            | Token count used when encoding       |
| ...     | u32 model json length       | Length of canonical JSON model blob  |
| ...     | bytes                       | JSON model (`compression_model`)     |
| ...     | u32 extras json length      | Length of optional extras JSON       |
| ...     | bytes                       | JSON extras (mode/optimisation info) |
+---------+-----------------------------+--------------------------------------+
```

Both JSON documents are encoded canonically (sorted keys, no whitespace).  The
extras map carries fields such as `{"mode": "maximum", "optimisation": {...}}`.

### 3.3 Section 0x0003 – Compressed Token Stream

```
SID: 0x0003 (Compressed Tokens)
Flags: none

+---------+-------------------+------------------------------------------+
| Offset  | Field             | Description                              |
+=========+===================+==========================================+
| 0       | u32 byte length   | Length of compressed token payload       |
| 4       | bytes             | rANS-compressed token payload            |
+---------+-------------------+------------------------------------------+
```

The payload stores the ANS bit-stream produced by the codec indicated in
Section 0x0002.  The decoder reconstructs the original token sequence using the
model parameters from that section.

### 3.4 Section 0x0004 – String Table

The string table is identical to `StringTable.to_bytes()` and therefore uses a
varint-based prefix compression layout.  Refer to §6 for field-level detail.

### 3.5 Section 0x0005 – Payload Records

Payload records carry auxiliary data (numeric literals, identifiers, structural
metrics).  The section encodes a canonical JSON document of the shape
`{"payloads": [...]}`.  Each payload entry matches the JSON emitted by the
string table encoder (see §6) and therefore stores `{"type": <string>, "value":
...}` where string references are represented using the `__strref__` sentinel.

### 3.6 Section 0x0006 – Source Map (optional)

If the Stream Header flags bit0 is set, Section 0x0006 stores a compressed
source map.  The blob is identical to `SourceMap.to_bytes()` and therefore
begins with a u32 record count followed by varint-coded mappings.  Absent this
section, no source-map data is available.

### 3.7 Section 0x0007 – Extended Metadata (optional)

Optional metadata is encoded as canonical JSON (UTF-8) preceded by a u32 length
prefix.  Keys include `author`, `license`, and timestamp data.  Unknown keys are
ignored by decoders.

## 4. Morpheme dictionary representation

The morpheme dictionary is external to individual packages but the format needs
normative documentation for dictionary bundles.  Dictionary archives are stored
as canonical JSON files with the following top-level schema:

```json
{
  "version": "1.2.0",
  "entries": [
    { "key": "construct:function", "index": 17, "frequency": 12456 },
    { "key": "flow:return", "index": 44, "frequency": 6875 }
  ],
  "metadata": {
    "language": ["python", "javascript", "go", "rust", "cpp"],
    "created": "2024-02-15T00:00:00Z"
  }
}
```

Indices are unique integers spanning `[0, 2^31)`.  Packages embed only the
`version` identifier and rely on out-of-band distribution of the dictionary
catalogue.

## 5. Cryptographic envelope

MCS employs ChaCha20-Poly1305 with Argon2id key derivation.  The KDF parameters
are stored alongside the salt in the metadata ledger (§7).  Key derivation uses
32-byte output with parameters `(t=3, m=1<<18, p=4)` by default; alternative
values are permitted via the extension mechanism.

The AEAD ciphertext in the wrapper envelops the entire payload envelope (magic,
versions, section table, and section bytes).  The authentication tag verifies
both the encrypted payload and the metadata used as AAD.

## 6. String table layout

The binary format emitted by `StringTable.to_bytes()` is specified as follows:

```
+---------+-----------------------------+------------------------------+
| Offset  | Field                       | Description                  |
+=========+=============================+==============================+
| 0       | varint entry_count          | Number of table entries      |
| ...     | varint prefix_len[i]        | Prefix length with previous  |
| ...     | varint suffix_len[i]        | UTF-8 suffix byte length     |
| ...     | bytes suffix[i]             | UTF-8 suffix bytes           |
| ...     | varint frequency[i]         | Occurrence count             |
+---------+-----------------------------+------------------------------+
```

`varint` is the standard unsigned 7-bit continuation encoding (little-endian
base-128).  The first entry uses `prefix_len = 0`.

## 7. Metadata schema

Metadata objects follow the canonical JSON schema below.  Fields marked
"optional" may be omitted without impacting authentication.

| Field                   | Type   | Description |
|-------------------------|--------|-------------|
| `package_version`       | string | Version of the wrapper/payload format. |
| `dictionary_version`    | string | Morpheme dictionary identifier. |
| `encoder_version`       | string | Semantic version of the encoder. |
| `source_language`       | string | ISO-like language identifier. |
| `source_language_version` | string | Toolchain or language runtime version. |
| `source_hash`           | string | Hex-encoded SHA-256 of canonical source. |
| `compression_backend`   | string | Name of ANS backend used. |
| `compression_model_digest` | string | SHA-256 digest of compression model. |
| `symbol_count`          | integer| Number of morpheme tokens. |
| `timestamp`             | string | Optional RFC 3339 timestamp. |
| `author`                | string | Optional author attribution. |
| `license`               | string | Optional SPDX license identifier. |

The canonical form is produced using `json.dumps(..., sort_keys=True,
separators=(",", ":"))`.

## 8. Integrity, signatures, and checksums

All MCS artefacts rely on AEAD authentication for integrity.  In addition,
Section 0x0007 may include digital signatures or Merkle proofs.  When present,
these follow the detached signature profile:

```
{
  "signatures": [
    {
      "algorithm": "ed25519",
      "public_key": "base64(ed25519 pk)",
      "signature": "base64(signature over payload envelope)",
      "timestamp": "2024-03-12T00:00:00Z"
    }
  ]
}
```

The signature always covers the raw payload envelope (`MCS\0 ...`) prior to
compression or encryption, ensuring deterministic verification.

## 9. Extension points

*   **Section identifiers:** values `>= 0x8000` are reserved for vendor-specific
    extensions.  Decoders ignore unknown sections while retaining ordering.
*   **Feature flags:** each section reserves higher 8 bits of the flag field for
    experimental use; conforming readers mask only the lower 8 bits.
*   **Metadata keys:** unknown keys are ignored but preserved during re-encode
    operations.
*   **Wrapper header:** additional top-level fields beginning with `x-` are
    preserved and ignored by baseline decoders.

## 10. Deterministic serialisation rules

1. Sections **must** appear in strictly increasing `SID` order.
2. Strings use UTF-8 without BOM.
3. Integers are little-endian unless explicitly noted.
4. Optional sections are omitted entirely when no data is present.
5. Canonical JSON serialisation is mandatory for metadata and optional sections.
6. CBOR payloads use canonical ordering per RFC 8949 §4.2.

## 11. Versioning

Version numbers follow semantic versioning.  Payload readers **must** accept any
minor or patch version at or below their supported major version.  Reserved
fields enable future expansion without breaking older decoders as long as the
ordering and section semantics remain consistent.
