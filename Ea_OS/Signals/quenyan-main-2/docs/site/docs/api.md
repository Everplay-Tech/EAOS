# API Reference

The Python package exposes encoder, decoder, and repository helpers.
Import paths:

```python
from qyn1 import QYNEncoder, QYNDecoder, encode_package, decode_package
from qyn1.pipeline import encode_project
from qyn1.incremental import IncrementalEncoder
from qyn1.repository import RepositoryWriter
```

Refer to the docstrings in `qyn1/encoder.py`, `qyn1/decoder.py`, and
related modules for method signatures. The CLI mirrors these APIs and is
documented in `docs/man/quenyan.1.md`.
