# Quenyan Incremental Encoder GitHub Action

This composite action installs the Quenyan toolchain and executes the
incremental encoder as part of a GitHub Actions workflow. It exposes cache hit
rates so that pipelines can track the effectiveness of content-based
rebuilds.

## Usage

```yaml
jobs:
  quenyan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Gather sources
        run: |
          git ls-files '*.py' > sources.txt
      - uses: ./ci/github-action
        with:
          passphrase: ${{ secrets.QYN1_PASSPHRASE }}
          sources: |
            $(cat sources.txt)
          output-dir: build/mcs
          cache-dir: .qyn-cache
          manifest: config/dependencies.json
          shard-index: ${{ strategy.job-index }}
          shard-count: ${{ strategy.job-total }}
```

The `sources` input expects a newline separated list. Pairing the action with a
matrix strategy allows horizontal scaling across CI runners. The outputs
`hit-rate`, `encoded-count`, and `reused-count` can be surfaced as workflow job
summaries or used to trigger alerts when cache effectiveness drops.
