# CI/CD Integration

The Quenyan toolchain supports incremental builds, distributed encoding, and
repository packaging. This document ties the pieces together for common CI/CD
systems.

## GitHub Actions

Use the bundled composite action under `ci/github-action`:

```yaml
jobs:
  encode:
    strategy:
      matrix:
        shard: [0, 1, 2, 3]
      fail-fast: false
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: ./ci/github-action
        with:
          passphrase: ${{ secrets.QYN1_PASSPHRASE }}
          sources: |
            $(git ls-files '*.py')
          shard-index: ${{ matrix.shard }}
          shard-count: ${{ strategy.job-total }}
```

## GitLab CI

```
encode:
  image: python:3.11
  script:
    - pip install .
    - python -m qyn1.cli encode-incremental build/mcs $(git ls-files '*.py') \
        --passphrase "$QYN1_PASSPHRASE" \
        --cache-dir .qyn-cache \
        --json > build/report.json
  artifacts:
    paths:
      - build/mcs
      - build/report.json
```

## Jenkins Pipeline Snippet

```groovy
stage('encode') {
  steps {
    sh 'pip install .'
    sh '''python -m qyn1.cli encode-incremental build/mcs $(git ls-files '*.py') \
      --passphrase "$QYN1_PASSPHRASE" \
      --cache-dir .qyn-cache \
      --json > build/report.json'''
  }
}
```

## Cache Hit Rate Monitoring

The incremental encoder reports `cache_hit_rate`. Persist the JSON summary and
feed it into observability tooling or upload it as a CI artifact for regression
analysis.
