# Example: Python Web App

This sample Flask application demonstrates Quenyan in a typical web
stack.

1. Add `quenyan encode-project build/mcs app/**/*.py --key .quenyan/keys/master.key` to the release pipeline.
2. Ship `.qyn1` artefacts instead of source and keep a metadata ledger
   using `quenyan repo-pack`.
3. Developers run `quenyan decode build/mcs/app.qyn1 --key .quenyan/keys/master.key -o app/restored.py` for debugging.
