# Compression vs. Security

Quenyan offers preset modes to balance compression and security:

- **Maximum**: Aggressive token remapping, project-level dictionaries,
  and prefix-compressed string tables. See
  `docs/compression_strategy.md` for model details.
- **Balanced**: Default preset optimising for determinism and good ratios
  without extra metadata.
- **Security**: Retains more metadata, disables aggressive remapping, and
  focuses on AEAD throughput.

`docs/performance_requirements.md` and `docs/performance_profiling.md`
outline throughput targets while `docs/pipeline_profile.json` captures
sample profiles from real codebases.
