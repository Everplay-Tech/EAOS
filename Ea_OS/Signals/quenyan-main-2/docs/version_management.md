# Quenyan MCS Version Management

This document defines the forward-compatibility guarantees for the Morphemic Code Stream (MCS) format and the morpheme dictionary.

## Semantic versioning

MCS package files encode a semantic version in the wrapper header and the encrypted payload. Versions follow **major.minor.patch** semantics:

* **Major** – increments when the binary structure changes in a backward-incompatible way. Decoders only support packages whose major version matches their own.
* **Minor** – increments when optional sections or metadata are introduced. Minor upgrades must remain readable by the previous minor decoder within the same major series.
* **Patch** – represents bug fixes or clarifications that do not impact decoding.

As of this release the current format version is **1.2.0** and the minimum supported version is **1.0.0**. The `qyn1.versioning` module exposes helpers for negotiating compatible versions at runtime.

## Breaking-change policy

* Morpheme dictionary updates may introduce new entries in patch releases but removing or renaming entries requires a minor version increment.
* Optional metadata fields must be ignorable: new readers treat absent fields as default values, while old readers skip unknown fields.
* Dictionary migrations must ship with automated tooling (`quenyan migrate`) so older files can be upgraded without re-encoding source code.

## Deprecation timeline

* Versions remain supported for **three years** from their release date. Support includes regression coverage in the compatibility test suite and security updates.
* After three years, a version transitions into maintenance mode: the CLI issues warnings, but decoding continues to work for an additional year.
* Final removal is announced at least six months in advance and requires a major version bump.

## Version negotiation

The decoder inspects the wrapper header before decryption. If the version is:

* **Equal to the current version** – decoding proceeds normally.
* **Older minor version** – decoding loads the legacy branch and up-converts to the in-memory representation.
* **Newer major version** – decoding fails with a descriptive error, prompting users to upgrade their tooling.

`qyn1.versioning.compatibility_matrix` can be used by orchestration systems to plan multi-version deployments.

## Format evolution strategy

* New sections must be appended in JSON objects to avoid breaking canonical ordering.
* Optional chunks are added with sentinel keys; older decoders drop the fields while newer decoders use default fallbacks.
* Associated data always contains the canonical metadata representation to prevent downgrade or substitution attacks.

## Tooling guarantees

* `quenyan migrate` remaps dictionary indices, upgrades package wrappers, and writes `.bak` backups when performing in-place migrations.
* The compatibility archive (`tests/data/compatibility`) contains 100 sample packages covering every supported release and optional field permutation. Continuous integration executes decoding across the entire archive.
* Long-term support (LTS) releases are tagged every twelve months. Bug fixes are backported for two years, with critical security patches maintained for three.

Refer to `docs/stability_policy.md` for broader SLA commitments covering APIs and integrations.
