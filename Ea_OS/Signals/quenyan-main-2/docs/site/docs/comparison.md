# Quenyan vs. Traditional Obfuscation

| Feature | Quenyan | Minifiers / Obfuscators |
| --- | --- | --- |
| Determinism | Yes – canonical AST encoding | Rare |
| Security | Authenticated encryption (ChaCha20-Poly1305) | Usually none |
| Compression | Multi-stage (morphemes + ANS) | gzip/brotli only |
| Extensibility | Versioned dictionary & presets | Language-specific hacks |

Further analysis can be found in `docs/compression_ratio_comparison.md`
and `docs/cryptographic_architecture.md`.
