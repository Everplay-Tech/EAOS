# Entropy Bound Calculation Plan

## 2. Information-theoretic decomposition and entropy bounds

### 2.1 Decomposing the joint entropy

The zero-order (token-only) empirical entropy is already measured as roughly \(H_0(T) \approx 3.23\) bits per token. For the joint morpheme + payload channel we target the full joint entropy

\[
H(T, P) = H(T) + H(P \mid T).
\]

Because each payload class \(C\) is a deterministic function of the token \(T\), we can expand the conditional term as

\[
H(P \mid T) = \sum_{t \in \Sigma} p(t)\, H(P \mid T = t) = \sum_{t \in \Sigma} p(t)\, H(P \mid C = f(t), T = t).
\]

Grouping by payload type with \(\alpha_k = \Pr(C = k)\) for \(k \in \{\text{NONE}, \text{ID}, \text{STR}, \text{NUM}, \text{BOOL}, \text{OTHER}\}\) gives

\[
H(P \mid T) = \sum_k \alpha_k\, \mathbb{E}_{T \mid C = k}[H(P \mid T)].
\]

Key observations for the payload-bearing classes:

* Structural tokens (\(C = \text{NONE}\)) contribute nothing, so \(H(P \mid T) = 0\) for the majority of the stream.
* Identifier payloads draw from Zipfian index distributions scoped to a file or project string table.
* String literals behave similarly but point to longer contents stored elsewhere.
* Numeric payloads (counts and literals) are highly skewed toward very small integers.
* Boolean payloads are Bernoulli and often extremely biased.
* Rare “other” payloads can be grouped as a catch-all with a bounded contribution.

Combining the per-class contributions yields

\[
H(P \mid T) = \alpha_{\text{ID}} H(P_{\text{ID}} \mid T) + \alpha_{\text{STR}} H(P_{\text{STR}} \mid T) + \alpha_{\text{NUM}} H(P_{\text{NUM}} \mid T) + \alpha_{\text{BOOL}} H(P_{\text{BOOL}} \mid T) + \alpha_{\text{OTHER}} H(P_{\text{OTHER}} \mid T).
\]

Estimating each component empirically yields a tight, production-grade lower bound for any lossless scheme operating on the combined morpheme and payload channel.

### 2.2 Lower and upper bounds for each payload type

The following outlines what to measure and how to interpret the resulting bounds.

**Identifiers (ID).** The payload domain is \(Y_{\text{ID}} = \{0, \ldots, M_f - 1\}\) per file or per project, where \(M_f\) is the number of distinct identifiers. Identifier occurrences are highly Zipfian, and Quenyan already compresses the string table, achieving roughly 38% savings over naïve storage.

* **Conditional entropy.** \(H(P_{\text{ID}} \mid T = \texttt{structure:identifier}) = H(\text{ID index})\) under the position-specific index distribution.
* **Bounds.** The lower bound comes from the sample entropy of observed indices; the upper bound is the realised bits per ID from ANS/Huffman coding plus the amortised string-table representation cost.

**String literals (STR).** Similar to identifiers but with longer content stored in the STRINGS section.

* **Indices.** Measure entropy of string-table indices at use sites.
* **Content.** Measure character-level entropy per string (byte histograms or context models) to bound table size.

**Numeric payloads (NUM).** Includes structural counts and integer literals, typically following a geometric or logarithmic skew with small values dominating.

* **Bounds.** Fit parametric distributions (geometric/logarithmic or log-bucketed) to estimate the model entropy. Compare with the current integer encoding (fixed or variable length) to quantify headroom.

**Boolean payloads (BOOL).** Flags such as `has_value` or `async?` are often extremely biased.

* **Bounds.** The lower bound is \(H_2(p)\) for the empirical Bernoulli parameter; practical coding can use bit-packed side channels with ANS or arithmetic models tuned to the bias.

**Other (OTHER).** Rare or heterogeneous payloads (e.g., import specs or unknown tags).

* **Bounds.** Either measure entropy on their indices or bound their contribution by \(\alpha_{\text{OTHER}} \log_2 |Y_{\text{OTHER}}|\) when sparse.

### 2.3 Overall entropic bounds for the combined channel

With empirical estimates for \(H(T)\) and each \(H(P \mid T)\) component, report:

* **Per-token lower bound.** \(H_{\text{joint}} = H(T, P) = H(T) + H(P \mid T)\).
* **Per-source-byte lower bound.** For a source file \(s\) with \(N(s)\) tokens and \(|s|\) bytes,

  \[
  R_{\min}(s) \approx \frac{N(s)}{8\,|s|} H_{\text{joint}}(s) \quad \text{(bytes of compressed data per source byte).}
  \]

Comparing \(R_{\min}\) to realised Quenyan ratios (e.g., 0.387× for Maximum, 0.429× for Balanced) quantifies the distance from entropy and highlights whether payloads or morphemes dominate the remaining gap.

## 3.5 Phase 3 – Deriving explicit entropy bounds

Phase 3 converts the empirical measurements from the benchmarking corpus into actionable entropy budgets per channel and payload class.

### Global lower bounds
* Derive the global joint entropy lower bound, \(H_{\text{joint,global}}\), in both **bits/token** and **bytes per source byte** using the consolidated corpus statistics.
* Publish per-language lower bounds for Python, JavaScript/TypeScript, Go, Rust, and C++ using the same units to highlight skew between ecosystems.

### Upper bounds from the current design
For each compression mode (**Balanced**, **Maximum**, **Security**) and language:

1. Compute the expected token coding cost, \(\bar{R}_{\text{tokens}} = \mathbb{E}[\text{bits for TOKENS} / N]\).
2. Compute the expected payload coding cost, \(\bar{R}_{\text{payloads}} = \mathbb{E}[\text{bits for STRINGS & other payload sections} / N]\).
3. Report the **gap** between implementation and theory: \(\text{Gap} = (\bar{R}_{\text{tokens}} + \bar{R}_{\text{payloads}}) - H_{\text{joint}}\), where \(H_{\text{joint}}\) is the relevant lower bound from the corpus.

### Bounds by sub-channel
For each payload class \(k\) (identifiers, numeric literals, docstrings, comments, counts, etc.):

* **Lower bound:** \(H_k = \mathbb{E}[H(P_k \mid T, C = k)]\), the conditional entropy given token context and class membership.
* **Upper bound:** Measured bits per payload event for class \(k\) in the current implementation, aggregated per mode.

Summarise notable deltas to drive optimisation priorities, for example:

* *Identifiers:* contribute ~0.8 bits/token to \(H(P\mid T)\); current coder spends ~1.0 bits/token.
* *Numeric counts:* contribute ~0.1 bits/token yet consume ~0.4 bits/token, indicating headroom for a specialised coder.

### Reporting
* Present the bounds and gaps in a single dashboard table per language/mode, with sparkline deltas to track improvements over time.
* Call out any classes where the gap exceeds 0.2 bits/token and file follow-up tasks (e.g., switch counts to a Rice code or introduce per-language identifier models).
* Archive the raw calculations alongside the benchmark outputs so downstream teams can recompute the bounds when the corpus or encoder changes.

## 4. Turning analysis into practical compression targets

Once the joint entropy picture and per-class gaps are established, translate the analysis into concrete design objectives for the next Quenyan iteration.

### 4.1 Channel-factorization perspective

The analysis naturally suggests factorizing the joint source into semi-independent sub-sources, but doing so after measuring the true joint bounds keeps the design honest:

* **Token channel \(\{T_i\}\):** Zero-order or context-driven models (e.g., improved n-grams or AST-conditional token models) for the token stream.
* **Payload channels conditioned on token class \(C_i\):**
  * **Identifier index stream \(\{P_i : C_i = \text{ID}\}\).**
  * **String-literal table content.**
  * **Count/integer streams \(\{P_i : C_i = \text{NUM}\}\)**, potentially partitioned by semantic role.
  * **Flag bitstreams.**
  * **Rare meta-payloads.**

By construction, the sum of entropies of these factored channels, plus small mutual-information corrections, equals the joint entropy \(H(T, P)\). Building practical coders that get within \(\varepsilon\) of each sub-entropy yields a combined scheme that is optimal up to \(\sum \varepsilon\).

### 4.2 Concrete follow-on steps based on the analysis

After Phase 3, focus on the sub-channels with the largest gaps and apply targeted coding strategies:

* **Identifier index stream:** Often strongly Zipfian—consider Golomb, Elias, or ANS coders with log-bucketed probability models.
* **Counts/integers:** Values are tiny and concentrated near 0–4—use a very small ANS distribution with hand-tuned probabilities.
* **Booleans:** Usually extremely biased—group into bitplanes and code as short ANS blocks.
* **String-table content:** Use a dedicated text compressor (e.g., a compact static model) for table payloads.

For each sub-channel:

1. Re-run entropy calculations on the isolated stream to confirm near-optimality.
2. Integrate the improved sub-codecs into the main encoder.
3. Recompute global \(H(T, P)\) versus realised bit costs to verify that you have closed the gaps.

### 4.3 Choosing between sub-channel refinement and contextual payload fusion

The entropy decomposition supports two complementary optimisation paths. Decide between them per payload family while keeping the
empirical joint-entropy baseline as the guardrail:

* **Refine individual sub-channels.** Maintain the current factorisation (e.g., separate ID, STR, NUM bitstreams) and upgrade each
  with tighter coders or richer priors. This is low-risk when the mutual information between channels is negligible. Example: keep the
  identifier index stream distinct but swap in an ANS table trained on the observed Zipfian slope for each file.
* **Fold payloads into richer context models.** When context materially changes the payload distribution, explicitly model the joint
  structure instead of treating payloads as independent. Example: model identifier indices conditioned on syntactic role (parameter
  name vs. attribute vs. loop iterator) so the coder exploits the tighter per-role distributions.

Whichever path you choose, enforce the measurement loop:

1. Recompute \(H(P \mid T)\) and \(H_{\text{joint}}\) after every modeling change to confirm the expected gain is real.
2. Compare realised bits/event against the corresponding lower bound for that channel or joint model.
3. Reject changes that regress the gap-to-entropy even if they simplify the implementation; the joint-entropy baseline is the source
   of truth for end-to-end efficiency.

### 1.4 Boolean sub-channel (BOOL)

#### Modeling idea

Boolean feature flags (e.g., "has return value", "async?", "exported?") are highly biased, so the Bernoulli probability \(p_F = \Pr(F = 1)\) should be estimated for each flag type. The entropy \(H_2(p_F)\) is typically well below 1 bit, and encoding should target that ceiling.

#### Implementation steps

* **Flag catalogues:** Enumerate every boolean payload type and log occurrences to compute \(p_F\) per flag.
* **Bitstreams:** Maintain a dedicated bitstream per flag (or tightly related flag family) and encode with ANS or arithmetic coding tuned to \(\text{Bernoulli}(p_F)\).
* **Packing:** Optionally pack bytes for transport, but keep per-flag segregation to preserve bias exploitation.
* **Baseline check:** Compare against the legacy representation (bytes or small ints) and target realised bits/flag of \(H_2(p_F) + \varepsilon\).

### 1.5 OTHER sub-channel

This channel is intentionally sparse and heterogeneous (e.g., import specifications or rare meta tags).

* Track it separately during measurement.
* If a subtype becomes dominant, split it into a dedicated channel and model it like STR/ID/NUM.
* If it remains <1% of total bit budget, prefer conservative coding to avoid unnecessary complexity.
