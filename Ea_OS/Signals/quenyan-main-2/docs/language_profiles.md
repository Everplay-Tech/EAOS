# Language profile discovery and extension

QYN ships with a set of production-ready language profiles for Python, Rust, Go,
JavaScript, and TypeScript. These profiles live in
`qyn1/data/language_profiles/` as JSON manifests that describe morpheme keys,
operator mappings, literal encodings, and canonicalisation hints.

## Selecting profiles

The encoder and CLI resolve profiles from several signals:

- Explicit selectors such as `--language rust`, `--language ./custom.json`, or
  programmatic calls to `resolve_profile_spec`.
- File extensions and MIME types via `profile_for_path`, which first respects
  explicit hints and then falls back to extension/MIME lookups.
- Built-in defaults when no stronger signal is available.

`qyn1.language_detection.detect_language` composes these helpers so callers can
mix hints, extension detection, and user overrides without duplicating logic.

## Adding new languages without core changes

New languages can be added at runtime without touching the core package:

1. **Ship a manifest** that matches the schema used by the bundled files. Load
   it via `resolve_profile_spec(path)` or pass the path to CLI commands through
   `--language`. The registry will register the manifest and re-use it for the
   rest of the process.
2. **Publish a plugin module** that exposes either a
   `register_language_profiles(registry)` hook or a
   `language_profiles`/`LANGUAGE_PROFILES` iterable of `LanguageProfile`
   instances. Call `register_language_module("your.module")` during
   initialisation to register all provided profiles.

This extension surface keeps the encoder portable while making it trivial to
introduce bespoke languages for domain-specific workflows or downstream
integrations.
