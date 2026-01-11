# npm / Node.js Integration

The Quenyan CLI can be invoked during npm publish or install hooks to
ensure encrypted source archives are distributed instead of raw source
files. The `quenyan-publish.js` helper wraps the CLI with sensible
defaults:

1. `npm install quenyan` or otherwise make the CLI available on `$PATH`.
2. Configure the list of source files to encode inside `package.json`:

   ```json
   {
     "name": "my-package",
     "version": "1.0.0",
     "scripts": {
       "prepublishOnly": "node integrations/npm/quenyan-publish.js"
     },
     "quenyan": {
       "sources": ["src/index.py", "src/runtime.py"],
       "output": "dist/mcs"
     }
   }
   ```

3. On `npm publish`, the helper ensures `.quenyan/config.json` exists,
   generates a master key when necessary, and runs `quenyan
   encode-project` to produce `.qyn1` artefacts under `dist/mcs`.
4. During `npm install`, add a `postinstall` script that calls
   `quenyan decode` to materialise plaintext source in local caches.

All CLI options can be customised by editing the helper script or
passing environment variables (`QUENYAN_PASSPHRASE`,
`QUENYAN_COMPRESSION_MODE`, etc.).
