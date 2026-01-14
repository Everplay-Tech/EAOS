# QYN-1 Binary Package Framing

This document defines the canonical binary on-disk representation for `.mcs`
packages produced by the QYN-1 toolchain.  The goal of the framing layer is to
provide explicit self-describing envelopes that can be validated before
attempting decryption or higher-level decoding.

## Frame overview

Every envelope — both the outer wrapper and the encrypted payload — uses the
same fixed frame structure:

| Offset | Size | Field | Description |
| ------ | ---- | ----- | ----------- |
| 0      | 4    | Magic | ASCII tag identifying the frame kind.  The wrapper
magic is `QYNP`; the payload magic is `MCSP`. |
| 4      | 1    | Major | Semantic-version major component. |
| 5      | 1    | Minor | Semantic-version minor component. |
| 6      | 2    | Patch | Semantic-version patch component. |
| 8      | 4    | Feature bits | Bit-set advertising optional behaviours used by
this frame.  Feature assignments are listed in the section below. |
| 12     | 4    | Body length | Unsigned big-endian length of the frame body in
bytes. |
| 16     | *N*  | Body | Frame payload of arbitrary structure (UTF-8 JSON for
wrapper frames; a sequence of sections for payload frames). |
| 16+N   | 4    | CRC32 | Unsigned big-endian CRC32 of the body bytes, computed
with the IEEE polynomial. |

Receivers must verify both the magic value and the CRC before trusting any
content.  Frames may not contain trailing data; any remaining bytes after the
CRC are interpreted as the next envelope in the stream (QYN-1 writers only
emit a single frame per package).

## Feature registry

The feature bitset is shared by wrapper and payload frames.  Bits are allocated
as follows:

| Bit | Name | Meaning |
| --- | ---- | ------- |
| 0 | `compression:optimisation` | The payload includes token optimisation
metadata that must be respected when decoding. |
| 1 | `compression:extras` | Additional compression metadata is present in the
compression section. |
| 2 | `payload:source-map` | A source map section is present. |
| 3 | `compression:fse` | Tokens were compressed with the `fse` backend, which
requires the Finite State Entropy codec. |

Frames carrying unknown bits must be rejected unless the consumer explicitly
opted in to those capabilities.

## Payload section layout

Payload bodies are an ordered list of sections, each encoded as:

| Offset | Size | Field | Description |
| ------ | ---- | ----- | ----------- |
| 0      | 2    | Identifier | Section identifier. |
| 2      | 2    | Flags | Section-specific flags.  The stream-header section
sets bit `0x0001` when a source map accompanies the package. |
| 4      | 4    | Length | Unsigned little-endian payload length. |
| 8      | *L*  | Payload | Section payload bytes. |

Current identifiers:

| ID | Section |
| -- | ------- |
| 0x0001 | Stream header: dictionary and encoder metadata plus source hash. |
| 0x0002 | Compression model and optional extras. |
| 0x0003 | Length-prefixed compressed token buffer. |
| 0x0004 | Length-prefixed string table blob. |
| 0x0005 | JSON payload list, length-prefixed. |
| 0x0006 | Optional source-map blob (length-prefixed). |
| 0x0007 | Canonical metadata mirror. |

Unrecognised section identifiers must be ignored to preserve forward
compatibility.

## Version negotiation

Writers determine the payload format version by intersecting their supported
versions with the set advertised by the peer (if any).  The wrapper frame
records the chosen payload version and feature set in both the header and the
wrapper JSON body.  Readers must ensure:

* the wrapper and payload versions are within the supported compatibility
  window; and
* the payload feature set is a subset of the features the decoder is willing to
  process.

Unknown feature bits or mismatched feature declarations between wrapper and
payload are treated as hard errors.  If the outer wrapper does not use the
binary framing (historical packages), decoders fall back to the legacy JSON
transport format.
# Morpheme Container Stream (MCS) Binary Layout

This document defines the canonical binary framing used by Quenyan's Morpheme
Container Stream (MCS) archives. It supersedes the ad-hoc header structs used by
format v1.0 and introduces deterministic framing primitives that are reused by
both the wrapper envelope and the encrypted payload.

## Notation

* All multi-byte integers are encoded in **big-endian** order unless explicitly
  stated otherwise.
* `CRC32` refers to the ISO HDLC polynomial (0xEDB88320) computed over the
  uncompressed payload bytes. The checksum field stores the unsigned 32-bit
  result.
* "Version" denotes the `(major, minor, patch)` triplet recorded in the header.

## Frame header

Every top-level envelope (the outer wrapper and the encrypted payload) begins
with a fixed-width 20 byte header:

| Offset | Size | Field    | Description                                                |
| ------ | ---- | -------- | ---------------------------------------------------------- |
| 0      | 4    | Magic    | ASCII literal identifying the frame (`QYN1` or `MCSF`).    |
| 4      | 1    | Major    | Major revision of the frame schema.                        |
| 5      | 1    | Minor    | Minor revision.                                            |
| 6      | 2    | Patch    | Patch revision (unsigned).                                 |
| 8      | 4    | Flags    | Bit field describing enabled features.                     |
| 12     | 4    | Length   | Length in bytes of the payload immediately following.      |
| 16     | 4    | Checksum | CRC32 of the payload (see above).                          |

The wrapper frame currently sets the following flags:

* `0x0001` — payload is encrypted (ChaCha20-Poly1305).
* `0x0002` — metadata covered by associated data (authenticated JSON).

The encrypted payload frame sets:

* `0x0001` — sections are emitted in canonical order with independent checksums.

Readers **must** validate the magic, version compatibility and CRC before
processing the payload body.

## Section header

The decrypted payload is an ordered list of sections. Each section begins with a
12 byte little-endian header followed by the raw payload:

| Offset | Size | Field    | Description                                 |
| ------ | ---- | -------- | ------------------------------------------- |
| 0      | 2    | ID       | Numeric section identifier.                  |
| 2      | 2    | Flags    | Section-specific feature bits.              |
| 4      | 4    | Length   | Length of the section payload in bytes.     |
| 8      | 4    | Checksum | CRC32 of the section payload.               |

Section identifiers are stable across revisions. Unknown sections should be
retained and skipped based on their length, allowing forward compatibility.

All section payloads that contain embedded variable-length data use an explicit
little-endian `u32` length prefix before the structured blob. The JSON payloads
(e.g. metadata, payload records) are serialised with the canonical
`json.dumps(..., sort_keys=True, separators=(",", ":"))` encoding.

## Wrapper body

After the frame header the wrapper stores a canonical JSON map with the
following fields:

* `version` — textual package version.
* `payload_version` — textual payload revision.
* `metadata` — canonical JSON dictionary mirrored in the metadata section.
* `nonce`, `salt`, `ciphertext`, `tag` — base64 encoded ChaCha20-Poly1305 values.

The ciphertext is the payload frame (including its header) encrypted with the
passphrase-derived key and authenticated with `metadata.to_associated_data()`.

## Section catalogue

The payload currently emits sections in the following order. Flags marked `*`
are optional and set when the feature is present.

| ID    | Meaning               | Flags          | Notes                                    |
| ----- | --------------------- | -------------- | ---------------------------------------- |
| 0x0001| Stream header         | `0x0001`*      | `0x0001` indicates a source map section. |
| 0x0002| Compression model     |                | Contains backend/model/extras metadata.  |
| 0x0003| Compressed token blob |                | Length-prefixed byte stream.             |
| 0x0004| String table          |                | Length-prefixed byte stream.             |
| 0x0005| Payload records       |                | Canonical JSON map `{"payloads": [...]}`. |
| 0x0006| Source map            |                | Optional length-prefixed blob.           |
| 0x0007| Metadata echo         |                | Canonical JSON copy of wrapper metadata. |

Any additional sections must use a distinct identifier and may define their own
flag semantics. Decoders that encounter an unknown section should retain the
bytes so that round-tripping does not discard data.

## Checksums and validation

* The wrapper and payload CRC32 fields protect against accidental corruption
  before MAC verification occurs.
* Each section payload is also checksummed, allowing readers to reject damaged
  subsections while still exposing other data for diagnostics.
* Writers must recompute all checksums when mutating any part of the structure.

## Compatibility

The framing introduced here is compatible with all 1.x releases. Readers should
attempt to parse the new headers first and fall back to the legacy 12-byte
headers when the CRC validation fails. The encoder continues to emit metadata
values compatible with earlier versions so that migration tooling can
re-serialise archives in older formats when necessary.
