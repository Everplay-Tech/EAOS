# Example: JavaScript React App

Use the npm integration under `integrations/npm` to encode React source
before publishing:

```json
{
  "scripts": {
    "prepublishOnly": "node integrations/npm/quenyan-publish.js",
    "postinstall": "quenyan decode dist/mcs/app.qyn1 --key $QUENYAN_KEY -o src/App.decoded.tsx"
  },
  "quenyan": {
    "sources": ["src/**/*.tsx"],
    "output": "dist/mcs"
  }
}
```

CI caches the decoded output for faster local rebuilds.
