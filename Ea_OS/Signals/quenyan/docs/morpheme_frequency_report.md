# Morpheme Frequency Profiling

The `scripts/profile_morphemes.py` utility builds language-specific histograms by scanning
canonical morpheme streams. Each dataset entry uses the QYN-1 encoder (for Python) or
pre-encoded morpheme traces (for other languages) to ensure determinism. The script emits
per-language summaries that include token entropy, the most common morphemes, and frequent
3-gram patterns that help guide ANS model design.【F:scripts/profile_morphemes.py†L1-L218】

The bundled `data/morpheme_frequency_profile.json` file captures a reference run over the
development test corpus. Although compact, it highlights several trends that recur in
larger codebases:

* Identifiers (`structure:identifier`) dominate token frequency, confirming the need for
  the dedicated string table and short morphemes for symbols that appear in every
  statement.【F:data/morpheme_frequency_profile.json†L1-L27】
* Operator tokens (`op:call`, `op:assign`) form tight clusters with surrounding
  structural markers, producing predictable trigrams the ANS backend can exploit via
  context modelling.【F:data/morpheme_frequency_profile.json†L1-L27】
* The measured zero-order entropy (\~3.30 bits per symbol on the sample) provides a
  conservative bound for naive modelling, while the trigram conditional entropy drops the
  per-token uncertainty to \~1.47 bits, giving a much tighter empirical lower bound for
  ANS context models.【F:data/morpheme_frequency_profile.json†L1-L23】

To profile a new corpus, provide one or more `--input` arguments with `language=path`
values, where the path is either a directory containing source files (Python) or exported
morpheme JSON traces. The script writes a consolidated JSON report suitable for training
static models or validating adaptive strategies:

```bash
python scripts/profile_morphemes.py \
  --input python=/path/to/python/projects \
  --input javascript=/path/to/js/token-streams \
  --output morpheme_profile.json
```
