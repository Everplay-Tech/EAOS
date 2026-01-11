# Deterministic Encryption Security Analysis for QYN-1

Quenyan uses deterministic encryption to support content-addressable storage and
morpheme-level deduplication. This analysis outlines the resulting security
properties, limitations, and recommended deployment guidance.

## Background
- **Canonical Workflow:** Source code is canonicalised, morpheme-encoded, and
  compressed before AEAD encryption. Deterministic encryption derives the nonce
  from the plaintext hash and a secret salt, producing repeatable ciphertexts.
- **Security Goal:** Balance reproducible artefacts with confidentiality and
  integrity guarantees. ChaCha20-Poly1305 remains the AEAD primitive.

## Security Definitions
- Deterministic encryption cannot achieve IND-CPA because identical plaintexts
  always yield identical ciphertexts (Bellare, Boldyreva, O'Neill 2007).
- The achievable target is **priv** (privacy for deterministic encryption over
  high-min-entropy sources) or semantic security for block sources when
  plaintexts exhibit sufficient unpredictability.
- Our morpheme streams often have low entropy (e.g., boilerplate code), making
  the relaxed definitions difficult to satisfy without additional safeguards.

## Risk Assessment
1. **Ciphertext Equality Leakage**
   - **Impact:** Reveals when two encoded artefacts are identical, enabling code
     reuse inference or duplicate detection by adversaries.
   - **Likelihood:** High in shared storage environments.
   - **Mitigation:** Rotate per-tenant salts; optionally switch to random nonces
     for sensitive projects via "security-focused" preset.

2. **Dictionary Attacks / Guessing Plaintext**
   - **Impact:** Attackers pre-compute encodings of common files/snippets,
     comparing against observed ciphertexts to identify content.
   - **Likelihood:** Medium; morpheme canonicalisation makes known-plaintext
     attacks feasible for popular open-source packages.
   - **Mitigation:**
     - Encourage hybrid strategy: deterministic mode only for non-sensitive,
       widely published code.
     - Increase salt entropy and keep it secret; treat as part of project key
       hierarchy.
     - Consider applying format-preserving noise (dummy morphemes) before
       encryption.

3. **Chosen-Plaintext Attacks (CPA)**
   - **Impact:** Malicious service provider could request encodings of selected
     files and compare against stored artefacts to deduce contents.
   - **Likelihood:** Medium in hosted encoding scenarios.
   - **Mitigation:**
     - Restrict deterministic mode to self-hosted infrastructure.
     - Use access controls to prevent untrusted users from querying the encoder.

4. **Cross-Project Collisions**
   - **Impact:** Sharing salts across organisations leaks relationships between
     repositories and allows cross-project correlation.
   - **Likelihood:** Low if key hierarchy guidance is followed; otherwise
     medium.
   - **Mitigation:** Enforce unique master keys and salts per organisation.

## Comparison to Convergent Encryption
- Convergent encryption (used for storage deduplication) hashes plaintext to
  derive keys and nonces. Security is equivalent to ours only when plaintexts
  have high entropy.
- Literature (Douceur et al., 2002; Bellare et al., 2013) shows such schemes are
  vulnerable to confirmation-of-file attacks; mitigations include secret salts or
  access-controlled convergent encryption.
- QYN-1's approach mirrors "message-locked encryption with keyed hash" and is
  secure only under the "limited leakage" model when the salt remains secret and
  plaintext min-entropy is sufficient.

## Deployment Guidance
1. **Default Mode:** Continue shipping deterministic mode for public or
   open-source codebases where ciphertext equality leakage is acceptable and
   reproducibility is prioritised.
2. **Sensitive Mode:** Provide configuration toggles that switch to random nonce
   encryption, storing the nonce alongside ciphertext (already supported via
   metadata). Document trade-offs prominently.
3. **Salt Management:**
   - Derive per-project salts via HKDF(master key, project identifier).
   - Rotate salts when projects change confidentiality requirements.
4. **Monitoring:** Implement anomaly detection for repeated ciphertexts across
   projects and flag potential key reuse or salt misconfiguration.
5. **Future Work:**
   - Explore format-transforming encryption (FTE) or all-or-nothing transforms
     to add controlled randomness while maintaining partial determinism.
   - Evaluate domain separation (per-language/per-feature salts) to reduce
     cross-correlation.

## References
- Mihir Bellare, Alexandra Boldyreva, Adam O'Neill. "Deterministic and
  Efficiently Searchable Encryption." CRYPTO 2007.
- John R. Douceur et al. "Reclaiming Space from Duplicate Files in a Serverless
  Distributed File System." ICDCS 2002.
- Bellare, Keelveedhi, Ristenpart. "Message-Locked Encryption and Secure
  Deduplication." EUROCRYPT 2013.
