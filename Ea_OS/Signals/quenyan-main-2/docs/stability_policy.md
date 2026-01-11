# Stability Guarantees and Service Levels

This policy formalises the commitments Quenyan makes to integrators and operators.

## API surface

* The public Python API exposed by `qyn1` follows semantic versioning. Symbols documented in the reference guide remain stable for **24 months**.
* Experimental modules are prefixed with `_experimental` and may change without notice. They are omitted from stability commitments.
* Command-line subcommands marked as **preview** may change in minor releases, but their flags are never silently repurposed.

## Feature classifications

| Classification | Description | Stability |
| -------------- | ----------- | --------- |
| Stable | Core encoding/decoding, migration, repository packaging | 24 months | 
| LTS | Annual long-term support release | 36 months security, 24 months bug fixes |
| Experimental | Research prototypes, preview integrations | No guarantees |

## Deprecation process

1. Deprecation notices appear in release notes, CLI warnings, and the documentation site at least **six months** before removal.
2. Deprecated APIs remain callable but emit warnings in minor releases.
3. Removals occur only in major releases, except for experimental features.

## Security response SLA

* Critical vulnerabilities: patch released within **7 days** with coordinated disclosure when possible.
* High severity issues: patch released within **30 days**.
* Medium/low: batched into the next scheduled maintenance release.

## Support cadence

* Quarterly feature releases (`1.x.0`) aligned with updated morpheme dictionaries and compression presets.
* Monthly maintenance releases (`1.x.y`) containing bug fixes and documentation updates.
* Compatibility tests (`tests/test_versioning.py`) gate all merges to ensure backward compatibility.

For commercial support agreements or custom SLAs, contact the Quenyan maintainers via the documentation portal.
