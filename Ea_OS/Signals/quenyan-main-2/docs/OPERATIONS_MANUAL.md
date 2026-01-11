# Quenyan (QYN-1) Operations Manual

**Version:** 1.0
**Last Updated:** 2025-11-19
**Target Audience:** System Operators, DevOps Engineers, Security Teams, Developers

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Installation & Setup](#2-installation--setup)
3. [Basic Operations](#3-basic-operations)
4. [Advanced Features](#4-advanced-features)
5. [Security & Key Management](#5-security--key-management)
6. [Integration](#6-integration)
7. [Performance & Optimization](#7-performance--optimization)
8. [Troubleshooting & Best Practices](#8-troubleshooting--best-practices)
9. [CLI Reference](#9-cli-reference)
10. [Appendices](#10-appendices)

---

## 1. Introduction

### 1.1 What is Quenyan?

Quenyan (QYN-1) is a reference implementation of the Quenya Morphemic Crypto-Language - a system that encodes, compresses, and securely encrypts source code using linguistically-inspired morphemes. The system provides:

- **Authenticated Encryption**: ChaCha20-Poly1305 AEAD for tamper-proof storage
- **Deterministic Canonicalization**: Eliminates formatting differences while preserving semantics
- **Semantic Compression**: High compression ratios through AST-level encoding
- **Reproducible Builds**: Identical outputs for semantically equivalent code
- **Secure Key Management**: Three-tier key hierarchy with HSM/KMS integration

### 1.2 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Source Code (.py)                         │
└───────────────────────────┬─────────────────────────────────┘
                            │
                    ┌───────▼────────┐
                    │  AST Parser    │
                    └───────┬────────┘
                            │
                    ┌───────▼────────┐
                    │ Morpheme       │ (230 Quenya-inspired tokens)
                    │ Encoder        │
                    └───────┬────────┘
                            │
                    ┌───────▼────────┐
                    │ rANS           │ (Range ANS compression)
                    │ Compressor     │
                    └───────┬────────┘
                            │
                    ┌───────▼────────┐
                    │ ChaCha20       │ (AEAD encryption)
                    │ Encryptor      │
                    └───────┬────────┘
                            │
                    ┌───────▼────────┐
                    │ MCS Package    │ (Binary format)
                    │ Format         │
                    └───────┬────────┘
                            │
                    ┌───────▼────────┐
                    │ Encrypted      │
                    │ .qyn1 File     │
                    └────────────────┘
```

### 1.3 Use Cases

- **Secure Code Distribution**: Distribute proprietary code with strong encryption
- **Compliance**: Meet regulatory requirements for code confidentiality
- **Supply Chain Security**: Verify code integrity with authenticated metadata
- **Code Archival**: Long-term storage with space-efficient compression
- **Continuous Integration**: Secure artifact storage in CI/CD pipelines

### 1.4 Key Concepts

- **Morpheme**: A linguistic-style token representing AST constructs (e.g., `construct:function`, `op:add`)
- **MCS Format**: Morphemic Crypto-Code Substrate - the binary container format
- **Stream**: Ordered sequence of morphemes representing encoded source code
- **Passphrase**: User-provided secret for key derivation (dev workflows)
- **Master Key**: Root cryptographic secret (production workflows)
- **Dictionary**: Versioned collection of 230 morpheme definitions

---

## 2. Installation & Setup

### 2.1 System Requirements

**Minimum Requirements:**
- Python 3.10 or later
- 512 MB RAM
- 100 MB disk space

**Recommended Requirements:**
- Python 3.11+
- 2 GB RAM (for large projects)
- 1 GB disk space (for caching)

**Supported Platforms:**
- Linux (Ubuntu 20.04+, RHEL 8+, Debian 11+)
- macOS (11.0+)
- Windows (10+, Windows Server 2019+)

### 2.2 Installation Methods

#### Method 1: pip install (Recommended)

```bash
# Install from source
cd /path/to/quenyan
python -m pip install .

# Install with development dependencies
python -m pip install .[dev]

# Editable install for development
python -m pip install -e .[dev]
```

#### Method 2: From Repository

```bash
# Clone repository
git clone https://github.com/E-TECH-PLAYTECH/quenyan.git
cd quenyan

# Install
python -m pip install .

# Verify installation
quenyan --help
```

#### Method 3: Docker (Coming Soon)

```bash
# Pull image
docker pull quenyan/qyn1:latest

# Run
docker run -v $(pwd):/workspace quenyan/qyn1 encode source.py --key /workspace/key.txt
```

### 2.3 Initial Configuration

#### Step 1: Initialize Project

```bash
# Initialize in current directory
quenyan init

# Initialize with key generation
quenyan init --generate-keys

# Initialize with custom compression mode
quenyan init --generate-keys --compression-mode=maximum

# Initialize in specific directory
quenyan init /path/to/project --generate-keys
```

This creates:
```
.quenyan/
├── config.json          # Default configuration
├── keys/
│   └── master.key       # Master encryption key (keep secure!)
└── cache/               # Incremental build cache (created on demand)
```

#### Step 2: Review Configuration

```bash
cat .quenyan/config.json
```

Example configuration:
```json
{
  "default_compression_mode": "balanced",
  "default_backend": "rans",
  "cache_dir": "/path/to/.quenyan/cache"
}
```

#### Step 3: Secure Your Keys

```bash
# Restrict key file permissions (Linux/macOS)
chmod 600 .quenyan/keys/master.key

# Add to .gitignore
echo ".quenyan/keys/" >> .gitignore
echo ".quenyan/cache/" >> .gitignore
```

### 2.4 Shell Completion Setup

```bash
# Bash
quenyan completion bash > ~/.local/share/bash-completion/completions/quenyan
source ~/.bashrc

# Zsh
quenyan completion zsh > ~/.zsh/completions/_quenyan
# Add to ~/.zshrc: fpath=(~/.zsh/completions $fpath)

# Fish
quenyan completion fish > ~/.config/fish/completions/quenyan.fish
```

### 2.5 Verification

```bash
# Check version
quenyan --version

# List available compression backends
quenyan compression-backends

# View manual
quenyan man
```

Expected output:
```
rans: available
chunked-rans: available
```

---

## 3. Basic Operations

### 3.1 Encoding Source Code

#### Simple Encoding

```bash
# Encode with passphrase from file
quenyan encode source.py --key .quenyan/keys/master.key -o build/source.qyn1

# Encode with inline passphrase (not recommended for production)
quenyan encode source.py --passphrase "my-secret-phrase" -o build/source.qyn1

# Encode with automatic output path (creates source.qyn1)
quenyan encode source.py --key .quenyan/keys/master.key
```

#### Encoding with Options

```bash
# Specify compression mode
quenyan encode source.py \
  --key .quenyan/keys/master.key \
  --compression-mode=maximum \
  -o build/source.qyn1

# Override compression backend
quenyan encode source.py \
  --key .quenyan/keys/master.key \
  --compression-backend=rans \
  -o build/source.qyn1

# Generate human-readable morpheme output
quenyan encode source.py \
  --key .quenyan/keys/master.key \
  --human-readable build/source.morphemes \
  -o build/source.qyn1

# Quiet mode (suppress progress output)
quenyan encode source.py \
  --key .quenyan/keys/master.key \
  --quiet \
  -o build/source.qyn1
```

**Output:**
```
Reading source.py: [########################################] 100%
Encoded source.py -> source.qyn1 in 0.23s; compression ratio 18.45%
```

### 3.2 Decoding Packages

#### Simple Decoding

```bash
# Decode to default output (source.py)
quenyan decode build/source.qyn1 --key .quenyan/keys/master.key

# Decode to specific output
quenyan decode build/source.qyn1 \
  --key .quenyan/keys/master.key \
  -o output/decoded.py

# Quiet mode
quenyan decode build/source.qyn1 \
  --key .quenyan/keys/master.key \
  -o output/decoded.py \
  --quiet
```

**Important:** Decoded source is emitted in canonical form using `ast.unparse()`, which:
- Removes comments
- Normalizes formatting
- Preserves semantic equivalence

**Output:**
```
Reading source.qyn1: [########################################] 100%
Decoded source.qyn1 -> decoded.py in 0.15s
```

### 3.3 Verifying Package Integrity

#### Wrapper-Only Verification

```bash
# Verify package format without decryption
quenyan verify build/source.qyn1

# JSON output
quenyan verify build/source.qyn1 --json
```

**Output:**
```
Package source.qyn1 (v1.0)
Status: wrapper-only
Wrapper metadata available; provide --key to verify contents
```

#### Full Verification with Decryption

```bash
# Verify with key
quenyan verify build/source.qyn1 --key .quenyan/keys/master.key

# Verify with signature check
quenyan verify build/source.qyn1 \
  --key .quenyan/keys/master.key \
  --check-signature

# JSON output
quenyan verify build/source.qyn1 \
  --key .quenyan/keys/master.key \
  --check-signature \
  --json
```

**Output:**
```
Package source.qyn1 (v1.0)
Status: ok
Dictionary v1 with 1523 symbols
Verified in 0.12s
Source hash matches authenticated metadata
```

### 3.4 Inspecting Package Metadata

```bash
# Basic inspection (no decryption)
quenyan inspect build/source.qyn1

# Show metadata fields
quenyan inspect build/source.qyn1 --show-metadata

# JSON output
quenyan inspect build/source.qyn1 --show-metadata --json

# YAML output
quenyan inspect build/source.qyn1 --show-metadata --yaml

# Validate audit trail
quenyan inspect build/source.qyn1 --validate-audit
```

**Output:**
```
Package: build/source.qyn1
Version: 1.0
Size: 45678 bytes
Integrity signature: OK
Provenance:
  created_at: 2025-11-19T10:30:00Z
  encoder_version: 1.0.0
Metadata hidden; pass --show-metadata to display fields
```

### 3.5 Comparing Packages

```bash
# Diff two packages at morpheme level
quenyan diff old.qyn1 new.qyn1 --key .quenyan/keys/master.key
```

**Output (JSON):**
```json
{
  "added_tokens": 42,
  "removed_tokens": 15,
  "changed_payloads": 3,
  "identical": false
}
```

### 3.6 Extracting Morpheme Streams

```bash
# View morphemes in terminal
quenyan morphemes build/source.qyn1 --key .quenyan/keys/master.key

# Save to file
quenyan morphemes build/source.qyn1 \
  --key .quenyan/keys/master.key \
  --output build/source.trace
```

**Output:**
```
construct:module
construct:function
name:calculate_total
construct:parameter
name:items
type:list
...
```

---

## 4. Advanced Features

### 4.1 Project Encoding

Encode multiple files in parallel with shared string tables for maximum compression.

#### Basic Project Encoding

```bash
# Encode multiple files
quenyan encode-project build/dist \
  src/main.py \
  src/utils.py \
  src/config.py \
  --key .quenyan/keys/master.key

# With JSON summary
quenyan encode-project build/dist \
  src/**/*.py \
  --key .quenyan/keys/master.key \
  --json > build/encode-report.json
```

#### Advanced Options

```bash
# Maximum compression with custom workers
quenyan encode-project build/dist \
  $(find src -name '*.py') \
  --key .quenyan/keys/master.key \
  --compression-mode=maximum \
  --workers=8

# Streaming for large files
quenyan encode-project build/dist \
  src/**/*.py \
  --key .quenyan/keys/master.key \
  --streaming-threshold=33554432 \    # 32 MB
  --streaming-backend=chunked-rans \
  --chunk-size=65536 \
  --max-buffered-tokens=65536
```

**Output:**
```
Encoded 15 files in 2.34s
Average throughput: 12.45 MB/s
- main.py: 0.23s, 2.50 MiB -> 0.45 MiB, backend=rans
- utils.py: 0.15s, 1.20 MiB -> 0.22 MiB, backend=rans
...
```

### 4.2 Incremental Builds

Build only what changed, with dependency-aware caching.

#### Setup Incremental Encoding

```bash
# First run (full build)
quenyan encode-incremental build/mcs \
  $(git ls-files '*.py') \
  --key .quenyan/keys/master.key \
  --cache-dir .qyn-cache \
  --json

# Subsequent runs (only changed files)
# Modify a file
echo "# Comment" >> src/main.py

# Rebuild (automatic cache reuse)
quenyan encode-incremental build/mcs \
  $(git ls-files '*.py') \
  --key .quenyan/keys/master.key \
  --cache-dir .qyn-cache \
  --json
```

#### With Dependency Tracking

```bash
# Create manifest describing dependencies
cat > manifest.json <<EOF
{
  "dependencies": {
    "src/main.py": ["src/utils.py", "src/config.py"],
    "src/utils.py": ["src/config.py"]
  }
}
EOF

# Incremental build with dependency awareness
quenyan encode-incremental build/mcs \
  $(git ls-files '*.py') \
  --key .quenyan/keys/master.key \
  --cache-dir .qyn-cache \
  --manifest manifest.json \
  --root $(pwd)
```

#### Distributed Encoding (CI Sharding)

```bash
# Shard 1 of 4
quenyan encode-incremental build/mcs \
  $(git ls-files '*.py') \
  --key .quenyan/keys/master.key \
  --cache-dir .qyn-cache \
  --shard-index=0 \
  --shard-count=4

# Shard 2 of 4
quenyan encode-incremental build/mcs \
  $(git ls-files '*.py') \
  --key .quenyan/keys/master.key \
  --cache-dir .qyn-cache \
  --shard-index=1 \
  --shard-count=4
```

**Output:**
```
Incremental encoding finished in 0.45s with hit rate 87.50%
Encoded: 3 files, reused: 12
Dependency-triggered rebuilds: 1
```

### 4.3 Repository Packaging

Package entire repositories with metadata and indexes.

#### Create Repository Package

```bash
# Create manifest
cat > repo-manifest.json <<EOF
{
  "root": ".",
  "compression_mode": "balanced",
  "backend": "rans",
  "entries": [
    {
      "source": "src/main.py",
      "package": "build/main.qyn1",
      "metadata": {
        "version": "1.0.0",
        "author": "dev-team"
      }
    },
    {
      "source": "src/utils.py",
      "package": "build/utils.qyn1",
      "metadata": {
        "version": "1.0.0",
        "author": "dev-team"
      }
    }
  ]
}
EOF

# Package repository
quenyan repo-pack repo-manifest.json build/repo \
  --archive build/repo.zip \
  --json
```

**Output:**
```
Repository created at build/repo with 2 entries (mode=balanced, backend=rans)
```

#### Compare Repository Versions

```bash
# Build new version
quenyan repo-pack repo-manifest-v2.json build/repo-v2

# Diff repositories
quenyan repo-diff build/repo-v2/index.json build/repo/index.json --json
```

**Output:**
```
Changes since previous repository index:
added: 1
  - src/new_module.py
removed: 0
changed: 1
  - src/main.py
```

### 4.4 Source Maps

Generate and extract source maps for debugging.

```bash
# Extract source map
quenyan source-map build/source.qyn1 \
  --key .quenyan/keys/master.key \
  --output build/source.map

# Summary in JSON
quenyan source-map build/source.qyn1 \
  --key .quenyan/keys/master.key \
  --json
```

**Output:**
```json
{
  "total_mappings": 1523,
  "source_lines": 245,
  "average_tokens_per_line": 6.2
}
```

### 4.5 Linting and Debugging

```bash
# Lint package for issues
quenyan lint build/source.qyn1 --key .quenyan/keys/master.key

# Decompile to canonical source
quenyan decompile build/source.qyn1 \
  --key .quenyan/keys/master.key \
  --output build/canonical.py
```

**Output:**
```
OK: no lint issues found
```

### 4.6 Package Migration

Migrate packages to new dictionary or format versions.

```bash
# Migrate to latest format
quenyan migrate old-package.qyn1 \
  --key .quenyan/keys/master.key \
  --output new-package.qyn1

# Migrate to specific dictionary version
quenyan migrate old-package.qyn1 \
  --key .quenyan/keys/master.key \
  --target-dictionary=v2 \
  --output new-package.qyn1

# In-place migration with backup
quenyan migrate package.qyn1 \
  --key .quenyan/keys/master.key

# In-place migration without backup
quenyan migrate package.qyn1 \
  --key .quenyan/keys/master.key \
  --no-backup
```

**Output:**
```
Migrated old-package.qyn1 -> new-package.qyn1 (dictionary v2, format v1.0)
Backup written to old-package.qyn1.bak
```

---

## 5. Security & Key Management

### 5.1 Key Hierarchy

Quenyan uses a three-tier key hierarchy:

```
┌─────────────────────────────────────────┐
│         Master Key (Root)                │
│  - High-entropy secret (256 bits)        │
│  - Stored in HSM/KMS/Vault               │
│  - Never leaves secure boundary          │
└──────────────────┬──────────────────────┘
                   │ HKDF-SHA256
                   │ info="qyn1:project:{id}:{dict_ver}"
                   │
      ┌────────────▼──────────────┐
      │      Project Key           │
      │  - Per-project scope       │
      │  - Quarterly rotation      │
      └────────────┬───────────────┘
                   │ HKDF-SHA256
                   │ info="qyn1:file:{hash}:{enc_ver}"
                   │
          ┌────────▼────────┐
          │    File Key     │
          │  - Per-package  │
          │  - Ephemeral    │
          └─────────────────┘
```

### 5.2 Key Generation

#### Development Keys (Passphrase-Based)

```bash
# Generate with init
quenyan init --generate-keys

# Manual generation
python -c "import secrets; print(secrets.token_urlsafe(32))" > .quenyan/keys/master.key
chmod 600 .quenyan/keys/master.key
```

**Security Level:** Suitable for development, testing, and local workflows.

#### Production Keys (HSM/KMS)

**Not recommended:**
- Environment variables
- Hardcoded passphrases
- Version-controlled keys

**Recommended:**
- AWS KMS
- Azure Key Vault
- Google Cloud KMS
- HashiCorp Vault
- Hardware Security Modules (HSMs)

### 5.3 Key Storage Options

#### Option 1: Local File (Development)

```bash
# Store in secure location
mkdir -p ~/.quenyan/keys
chmod 700 ~/.quenyan/keys

# Generate key
python -c "import secrets; print(secrets.token_urlsafe(32))" > ~/.quenyan/keys/master.key
chmod 600 ~/.quenyan/keys/master.key

# Use in commands
quenyan encode source.py --key ~/.quenyan/keys/master.key
```

#### Option 2: Environment Variable (CI/CD)

```bash
# Set in CI environment
export QYN1_PASSPHRASE="$(cat ~/.quenyan/keys/master.key)"

# Use in script
quenyan encode source.py --passphrase "$QYN1_PASSPHRASE"
```

#### Option 3: AWS KMS (Production)

```bash
# Create KMS key
aws kms create-key \
  --description "Quenyan master key" \
  --key-usage ENCRYPT_DECRYPT

# Create alias
aws kms create-alias \
  --alias-name alias/quenyan \
  --target-key-id <key-id>

# Retrieve data key
aws kms generate-data-key \
  --key-id alias/quenyan \
  --key-spec AES_256 \
  --query Plaintext \
  --output text | base64 -d > /tmp/master.key

# Use with Quenyan
quenyan encode source.py --key /tmp/master.key

# Cleanup
shred -u /tmp/master.key
```

#### Option 4: HashiCorp Vault

```bash
# Store key in Vault
vault kv put secret/quenyan master_key="$(cat .quenyan/keys/master.key)"

# Retrieve in pipeline
export QYN1_PASSPHRASE="$(vault kv get -field=master_key secret/quenyan)"

# Use in commands
quenyan encode source.py --passphrase "$QYN1_PASSPHRASE"
```

### 5.4 Key Rotation

#### Master Key Rotation

```bash
# Generate new master key
python -c "import secrets; print(secrets.token_urlsafe(32))" > .quenyan/keys/master-v2.key
chmod 600 .quenyan/keys/master-v2.key

# Backup old key
cp .quenyan/keys/master.key .quenyan/keys/master-v1.key

# Replace master key
mv .quenyan/keys/master-v2.key .quenyan/keys/master.key

# Re-encode packages with new key
for file in build/*.qyn1; do
  # Decode with old key
  quenyan decode "$file" \
    --key .quenyan/keys/master-v1.key \
    -o /tmp/temp.py

  # Encode with new key
  quenyan encode /tmp/temp.py \
    --key .quenyan/keys/master.key \
    -o "$file"
done

# Cleanup
shred -u /tmp/temp.py
```

**Rotation Schedule:**
- **Master Keys:** Annually or upon suspected compromise
- **Project Keys:** Quarterly or when team membership changes
- **File Keys:** Automatic (derived per-package)

### 5.5 Key Derivation Parameters

```python
# Master Key Derivation (from passphrase)
Argon2id(
    password=passphrase,
    salt=128-bit random,
    memory_cost=64 * 1024,  # 64 MiB
    time_cost=4,
    parallelism=4,
    hash_len=32
)
hkdf_salt = os.urandom(16)
envelope_key = HKDF-SHA256(
    ikm=argon2_output,
    salt=hkdf_salt,
    info="qyn1-envelope:v2",
    length=32
)

# Project Key Derivation
HKDF-SHA256(
    ikm=envelope_key,
    info=f"qyn1:project:{project_id}:{dictionary_version}",
    length=32
)

# File Key Derivation
HKDF-SHA256(
    ikm=project_key,
    info=f"qyn1:file:{source_hash}:{encoder_version}",
    length=32
)
```

### 5.6 Security Best Practices

#### ✅ DO:

- Store master keys in HSM/KMS for production
- Use unique passphrases (>20 characters, high entropy)
- Rotate master keys annually
- Restrict key file permissions (`chmod 600`)
- Use environment variables in CI/CD (with secrets manager)
- Prefer `QYN_PASSPHRASE`/`QUENYAN_PASSPHRASE` or OS keyrings over inline CLI flags
- Audit key access logs
- Implement least-privilege access
- Enable MFA for key retrieval
- Backup keys to encrypted offline storage

#### ❌ DON'T:

- Commit keys to version control
- Share keys via email/chat
- Reuse passphrases across environments
- Use weak passphrases (<15 characters)
- Store keys in container images
- Log passphrases or master keys
- Use `--passphrase` flag in CI (use `--key` instead)
- Leave keys in `/tmp` without shredding

### 5.7 Threat Mitigation

| Threat | Mitigation |
|--------|------------|
| **Stolen Packages** | ChaCha20-Poly1305 AEAD prevents unauthorized reading |
| **Nonce Reuse** | File keys derived from unique source hashes |
| **Insider Tampering** | Authenticated metadata detects malicious edits |
| **Supply Chain Compromise** | Key hierarchy limits blast radius to single project |
| **Side-Channel Leakage** | Libsodium-backed ChaCha20-Poly1305 with zeroized key buffers |
| **Key Compromise** | Regular rotation limits exposure window |
| **Brute Force** | Memory-hard Argon2id + HKDF envelope keys + high-entropy passphrases |

---

## 6. Integration

### 6.1 CI/CD Integration

#### GitHub Actions

```yaml
# .github/workflows/encode.yml
name: Encode with Quenyan

on: [push]

jobs:
  encode:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install Quenyan
        run: |
          pip install -e .

      - name: Encode sources
        env:
          QYN1_PASSPHRASE: ${{ secrets.QYN1_MASTER_KEY }}
        run: |
          quenyan encode-project build/dist \
            $(git ls-files '*.py') \
            --passphrase "$QYN1_PASSPHRASE" \
            --json > build/encode-report.json

      - name: Upload artifacts
        uses: actions/upload-artifact@v3
        with:
          name: encoded-packages
          path: build/dist/
```

#### GitLab CI

```yaml
# .gitlab-ci.yml
encode:
  stage: build
  image: python:3.11
  script:
    - pip install -e .
    - |
      quenyan encode-project build/dist \
        $(git ls-files '*.py') \
        --passphrase "$QYN1_MASTER_KEY" \
        --compression-mode=maximum \
        --json
  artifacts:
    paths:
      - build/dist/
    reports:
      dotenv: build/encode-report.json
  only:
    - main
```

#### Jenkins

```groovy
// Jenkinsfile
pipeline {
    agent any

    environment {
        QYN1_PASSPHRASE = credentials('quenyan-master-key')
    }

    stages {
        stage('Setup') {
            steps {
                sh 'pip install -e .'
            }
        }

        stage('Encode') {
            steps {
                sh '''
                    quenyan encode-incremental build/mcs \
                        $(git ls-files '*.py') \
                        --passphrase "$QYN1_PASSPHRASE" \
                        --cache-dir .qyn-cache \
                        --json > build/encode-report.json
                '''
            }
        }

        stage('Archive') {
            steps {
                archiveArtifacts artifacts: 'build/mcs/*.qyn1', fingerprint: true
            }
        }
    }
}
```

### 6.2 Package Manager Integration

#### npm Integration

```javascript
// package.json
{
  "name": "my-package",
  "scripts": {
    "prepublishOnly": "node integrations/npm/quenyan-publish.js"
  },
  "devDependencies": {
    "quenyan": "^1.0.0"
  }
}
```

```javascript
// integrations/npm/quenyan-publish.js (example)
const { execSync } = require('child_process');
const fs = require('fs');

// Encode sources before publish
const sources = fs.readdirSync('src')
  .filter(f => f.endsWith('.py'))
  .map(f => `src/${f}`);

execSync(`quenyan encode-project dist/encoded ${sources.join(' ')} --key .quenyan/keys/master.key`);
```

#### Python setuptools Integration

```python
# setup.py
from setuptools import setup
from integrations.python.quenyan_build import QuenyanBuildPy

setup(
    name='my-package',
    cmdclass={
        'build_py': QuenyanBuildPy,
    },
    # ... other setup args
)
```

```bash
# Build with encoding
python setup.py build_py

# Outputs .qyn1 files alongside .py files
```

### 6.3 IDE Integration

#### VS Code Extension

```bash
# Install extension (if published)
code --install-extension quenyan.vscode-quenyan

# Or install from source
cd ide/vscode
npm install
npm run compile
code --install-extension .
```

**Features:**
- Syntax highlighting for `.qyn1` files
- Encode/decode commands in context menu
- Integrated key management
- Source map debugging

**Usage:**
1. Right-click `.py` file → "Quenyan: Encode File"
2. Right-click `.qyn1` file → "Quenyan: Decode File"
3. View morphemes: "Quenyan: Show Morpheme Stream"

### 6.4 Docker Integration

```dockerfile
# Dockerfile
FROM python:3.11-slim

# Install Quenyan
COPY . /opt/quenyan
RUN pip install /opt/quenyan

# Set up keys
RUN mkdir -p /root/.quenyan/keys
COPY keys/master.key /root/.quenyan/keys/master.key
RUN chmod 600 /root/.quenyan/keys/master.key

# Working directory
WORKDIR /workspace

# Default command
ENTRYPOINT ["quenyan"]
CMD ["--help"]
```

```bash
# Build image
docker build -t quenyan:latest .

# Encode file
docker run -v $(pwd):/workspace quenyan:latest \
  encode source.py \
  --key /root/.quenyan/keys/master.key \
  -o /workspace/source.qyn1
```

### 6.5 Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: quenyan-encode
        name: Encode with Quenyan
        entry: quenyan encode
        language: system
        files: \.py$
        pass_filenames: true
        args: ['--key', '.quenyan/keys/master.key']
```

```bash
# Install pre-commit
pip install pre-commit
pre-commit install

# Run on all files
pre-commit run --all-files
```

---

## 7. Performance & Optimization

### 7.1 Compression Modes

Quenyan provides three preset compression modes:

#### Balanced (Default)

```bash
quenyan encode source.py \
  --key .quenyan/keys/master.key \
  --compression-mode=balanced
```

**Characteristics:**
- Adaptive rANS with per-stream optimization
- Moderate compression ratio (~15-25%)
- Fast encode/decode
- Suitable for: Most use cases, CI/CD pipelines

**Performance:**
- Encode: ~10-15 MB/s
- Decode: ~20-30 MB/s
- Memory: ~50 MB per file

#### Maximum

```bash
quenyan encode source.py \
  --key .quenyan/keys/master.key \
  --compression-mode=maximum
```

**Characteristics:**
- Project-wide string table sharing
- Highest compression ratio (~10-18%)
- Slower encoding
- Suitable for: Archival, bandwidth-constrained distribution

**Performance:**
- Encode: ~5-8 MB/s
- Decode: ~15-25 MB/s
- Memory: ~100 MB + (project size)

#### Security

```bash
quenyan encode source.py \
  --key .quenyan/keys/master.key \
  --compression-mode=security
```

**Characteristics:**
- Isolated per-file compression
- Lower compression ratio (~20-30%)
- Prevents cross-file information leakage
- Suitable for: High-security environments, multi-tenant systems

**Performance:**
- Encode: ~8-12 MB/s
- Decode: ~18-28 MB/s
- Memory: ~40 MB per file

### 7.2 Backend Selection

```bash
# List available backends
quenyan compression-backends
```

**Output:**
```
rans: available
chunked-rans: available
```

#### rANS (Default)

```bash
quenyan encode source.py \
  --key .quenyan/keys/master.key \
  --compression-backend=rans
```

**Best for:**
- Small to medium files (<10 MB)
- In-memory processing
- Standard compression ratios

#### Chunked rANS

```bash
quenyan encode source.py \
  --key .quenyan/keys/master.key \
  --compression-backend=chunked-rans
```

**Best for:**
- Large files (>32 MB)
- Memory-constrained environments
- Streaming workflows

### 7.3 Streaming Configuration

For large files, enable streaming to reduce memory usage:

```bash
quenyan encode-project build/dist \
  large-file.py \
  --key .quenyan/keys/master.key \
  --streaming-threshold=33554432 \      # 32 MB
  --streaming-backend=chunked-rans \
  --chunk-size=65536 \                  # 64k tokens per chunk
  --max-buffered-tokens=65536           # 64k token buffer
```

**Memory Usage:**
- Without streaming: ~5x file size
- With streaming: ~100 MB + (chunk size)

### 7.4 Parallel Encoding

```bash
# Use all CPU cores
quenyan encode-project build/dist \
  src/**/*.py \
  --key .quenyan/keys/master.key \
  --workers=$(nproc)

# Limit workers
quenyan encode-project build/dist \
  src/**/*.py \
  --key .quenyan/keys/master.key \
  --workers=4
```

**Scaling:**
- 1 worker: ~10 MB/s
- 4 workers: ~35 MB/s
- 8 workers: ~60 MB/s
- 16 workers: ~95 MB/s

### 7.5 Benchmarking

```bash
# Profile morpheme encoding
python scripts/profile_morphemes.py corpus/

# Benchmark compression backends
python scripts/benchmark_compression.py

# End-to-end performance
python scripts/benchmark_performance.py

# Full benchmark suite
python scripts/run_benchmark_suite.py
```

**Interpreting Results:**

```json
{
  "throughput_mb_s": 12.45,
  "compression_ratio": 0.1845,
  "memory_peak_mb": 67.3,
  "encode_time_s": 2.34,
  "decode_time_s": 1.12
}
```

### 7.6 Optimization Checklist

**For Speed:**
- ✅ Use `balanced` compression mode
- ✅ Use `rans` backend for small files
- ✅ Enable parallel encoding (`--workers`)
- ✅ Disable `--human-readable` output
- ✅ Use incremental builds (`encode-incremental`)

**For Compression:**
- ✅ Use `maximum` compression mode
- ✅ Encode related files together (`encode-project`)
- ✅ Pre-process to remove comments/docstrings
- ✅ Use consistent naming conventions

**For Memory:**
- ✅ Use streaming (`--streaming-threshold`)
- ✅ Use `chunked-rans` backend
- ✅ Reduce `--chunk-size` and `--max-buffered-tokens`
- ✅ Process files sequentially (`--workers=1`)

**For Security:**
- ✅ Use `security` compression mode
- ✅ Enable signature checking (`--check-signature`)
- ✅ Rotate keys regularly
- ✅ Audit access logs

---

## 8. Troubleshooting & Best Practices

### 8.1 Common Errors

#### Error: "Unable to read key file"

```
error: Unable to read key file '.quenyan/keys/master.key': No such file or directory
```

**Cause:** Key file doesn't exist or path is incorrect.

**Solution:**
```bash
# Initialize project with keys
quenyan init --generate-keys

# Or create key manually
python -c "import secrets; print(secrets.token_urlsafe(32))" > .quenyan/keys/master.key
chmod 600 .quenyan/keys/master.key
```

#### Error: "Failed to verify package"

```
error: Failed to verify package: Authentication tag mismatch
```

**Cause:** Wrong passphrase or package is corrupted.

**Solutions:**
1. Verify correct key file:
   ```bash
   # Try with different key
   quenyan decode package.qyn1 --key /path/to/correct/key
   ```

2. Check package integrity:
   ```bash
   # Inspect without decryption
   quenyan inspect package.qyn1

   # Verify file is not corrupted
   sha256sum package.qyn1
   ```

3. If package is corrupted, restore from backup

#### Error: "Compression backend unavailable"

```
error: Compression backend 'custom-backend' is unavailable: Backend not found
```

**Cause:** Specified backend doesn't exist.

**Solution:**
```bash
# List available backends
quenyan compression-backends

# Use available backend
quenyan encode source.py \
  --key .quenyan/keys/master.key \
  --compression-backend=rans
```

#### Error: "is not valid UTF-8"

```
error: source.py is not valid UTF-8 encoded text
```

**Cause:** Source file has invalid UTF-8 encoding.

**Solution:**
```bash
# Check file encoding
file source.py

# Convert to UTF-8
iconv -f WINDOWS-1252 -t UTF-8 source.py > source_utf8.py

# Encode converted file
quenyan encode source_utf8.py --key .quenyan/keys/master.key
```

#### Error: "Package does not include a source map"

```
Package does not include a source map
```

**Cause:** Package was encoded without source map generation.

**Solution:** Re-encode with source map enabled (future feature).

### 8.2 Performance Issues

#### Slow Encoding

**Symptoms:** Encoding takes >10s for 1MB file

**Diagnosis:**
```bash
# Profile pipeline
python scripts/profile_pipeline.py source.py > profile.json

# Check bottlenecks
cat profile.json | jq '.cumulative_time | to_entries | sort_by(.value) | reverse | .[0:5]'
```

**Solutions:**
1. Use faster compression mode:
   ```bash
   quenyan encode source.py --compression-mode=balanced
   ```

2. Disable human-readable output:
   ```bash
   quenyan encode source.py --key .quenyan/keys/master.key -o output.qyn1
   # (don't use --human-readable)
   ```

3. Upgrade Python version (3.11+ is faster)

#### High Memory Usage

**Symptoms:** Process uses >2GB RAM for small files

**Diagnosis:**
```bash
# Monitor memory
/usr/bin/time -v quenyan encode large-file.py --key .quenyan/keys/master.key
```

**Solutions:**
1. Enable streaming:
   ```bash
   quenyan encode-project build/dist large-file.py \
     --key .quenyan/keys/master.key \
     --streaming-threshold=10485760 \  # 10 MB
     --streaming-backend=chunked-rans
   ```

2. Reduce chunk size:
   ```bash
   quenyan encode-project build/dist large-file.py \
     --key .quenyan/keys/master.key \
     --chunk-size=32768
   ```

#### Slow Decoding

**Symptoms:** Decoding takes significantly longer than encoding

**Diagnosis:**
```bash
# Time decode operation
time quenyan decode package.qyn1 --key .quenyan/keys/master.key
```

**Solutions:**
1. Check disk I/O (slow disk may bottleneck)
2. Verify package isn't corrupted: `quenyan verify package.qyn1 --key .quenyan/keys/master.key`
3. Try different backend for re-encoding

### 8.3 Security Issues

#### Leaked Keys in Logs

**Prevention:**
```bash
# Never use --passphrase in scripts
# BAD:
quenyan encode source.py --passphrase "my-secret"

# GOOD:
echo "my-secret" > /tmp/key.txt
quenyan encode source.py --key /tmp/key.txt
shred -u /tmp/key.txt
```

**Remediation:**
1. Rotate compromised keys immediately
2. Re-encode all packages with new key
3. Audit access logs
4. Revoke leaked credentials

#### Weak Passphrases

**Detection:**
```bash
# Check passphrase entropy
python -c "
import math
passphrase = input('Enter passphrase: ')
entropy = math.log2(95 ** len(passphrase))  # 95 printable ASCII chars
print(f'Entropy: {entropy:.1f} bits')
"
```

**Recommendation:** Aim for >128 bits of entropy (≥20 random characters)

**Solution:**
```bash
# Generate strong passphrase
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 8.4 Best Practices

#### Development Workflow

```bash
# 1. Initialize project
quenyan init --generate-keys

# 2. Add to .gitignore
cat >> .gitignore <<EOF
.quenyan/keys/
.quenyan/cache/
*.qyn1
EOF

# 3. Encode during build
quenyan encode-project build/dist src/**/*.py \
  --key .quenyan/keys/master.key \
  --compression-mode=balanced

# 4. Verify encoded packages
for pkg in build/dist/*.qyn1; do
  quenyan verify "$pkg" --key .quenyan/keys/master.key --check-signature
done
```

#### Production Workflow

```bash
# 1. Use KMS for key management
export MASTER_KEY=$(aws kms generate-data-key --key-id alias/quenyan ...)

# 2. Incremental builds with caching
quenyan encode-incremental build/mcs \
  $(git ls-files '*.py') \
  --key <(echo "$MASTER_KEY") \
  --cache-dir .qyn-cache \
  --compression-mode=maximum

# 3. Sign packages with metadata
# (Add metadata during encoding)

# 4. Verify before deployment
quenyan verify build/mcs/app.qyn1 \
  --key <(echo "$MASTER_KEY") \
  --check-signature

# 5. Rotate keys quarterly
# (Follow key rotation procedure)
```

#### CI/CD Workflow

```bash
# 1. Store keys in secrets manager
# GitHub Secrets, GitLab CI/CD variables, etc.

# 2. Shard for parallel builds
quenyan encode-incremental build/mcs \
  $(git ls-files '*.py') \
  --passphrase "$QYN1_MASTER_KEY" \
  --cache-dir .qyn-cache \
  --shard-index=$CI_NODE_INDEX \
  --shard-count=$CI_NODE_TOTAL

# 3. Cache between builds
# - Cache .qyn-cache/ directory
# - Invalidate on dictionary version change

# 4. Publish artifacts
# - Upload .qyn1 files to artifact storage
# - Tag with commit SHA and build number
```

### 8.5 Debugging Techniques

#### Verbose Logging

```bash
# Enable Python warnings
PYTHONWARNINGS=all quenyan encode source.py --key .quenyan/keys/master.key

# Use Python debugger
python -m pdb -m qyn1.cli encode source.py --key .quenyan/keys/master.key
```

#### Inspect Intermediate Outputs

```bash
# Generate human-readable morphemes
quenyan encode source.py \
  --key .quenyan/keys/master.key \
  --human-readable debug.morphemes \
  -o debug.qyn1

# Examine morpheme stream
cat debug.morphemes

# Extract morphemes from existing package
quenyan morphemes debug.qyn1 \
  --key .quenyan/keys/master.key \
  --output debug-extracted.morphemes

# Compare
diff debug.morphemes debug-extracted.morphemes
```

#### Package Inspection

```bash
# Full inspection
quenyan inspect package.qyn1 --show-metadata --yaml

# Validate structure
quenyan inspect package.qyn1 --validate-audit

# Compare packages
quenyan diff old.qyn1 new.qyn1 --key .quenyan/keys/master.key
```

#### Test Roundtrip

```bash
# Encode
quenyan encode source.py --key .quenyan/keys/master.key -o test.qyn1

# Decode
quenyan decode test.qyn1 --key .quenyan/keys/master.key -o decoded.py

# Compare ASTs
python -c "
import ast
original = ast.parse(open('source.py').read())
decoded = ast.parse(open('decoded.py').read())
print('Match:', ast.dump(original) == ast.dump(decoded))
"
```

---

## 9. CLI Reference

### 9.1 Global Options

```
quenyan [command] [options]
```

**Common Options:**
- `--help` - Show help message
- `--version` - Show version number

### 9.2 Commands

#### `encode`

Encode Python source to QYN-1 package.

```bash
quenyan encode SOURCE [OPTIONS]
```

**Arguments:**
- `SOURCE` - Input Python source file

**Options:**
- `-o, --output PATH` - Output package path (default: `<source>.qyn1`)
- `--key PATH` - Passphrase file path
- `--passphrase TEXT` - Inline passphrase (not recommended)
- `--compression-mode {balanced,maximum,security}` - Compression preset (default: `balanced`)
- `--compression-backend {rans,chunked-rans}` - Backend override
- `--human-readable PATH` - Write human-readable morpheme stream
- `--quiet` - Suppress progress output

**Examples:**
```bash
quenyan encode app.py --key .quenyan/keys/master.key
quenyan encode app.py --key .quenyan/keys/master.key -o build/app.qyn1
quenyan encode app.py --key .quenyan/keys/master.key --compression-mode=maximum
```

#### `decode`

Decode QYN-1 package to canonical Python source.

```bash
quenyan decode PACKAGE [OPTIONS]
```

**Arguments:**
- `PACKAGE` - Input QYN-1 package

**Options:**
- `-o, --output PATH` - Output source file (default: `<package>.py`)
- `--key PATH` - Passphrase file path
- `--passphrase TEXT` - Inline passphrase
- `--quiet` - Suppress progress output

**Examples:**
```bash
quenyan decode build/app.qyn1 --key .quenyan/keys/master.key
quenyan decode build/app.qyn1 --key .quenyan/keys/master.key -o src/app.py
```

#### `verify`

Verify package integrity and signature.

```bash
quenyan verify PACKAGE [OPTIONS]
```

**Arguments:**
- `PACKAGE` - Input QYN-1 package

**Options:**
- `--key PATH` - Passphrase file path (optional for wrapper-only verification)
- `--passphrase TEXT` - Inline passphrase
- `--check-signature` - Validate source hash against metadata
- `--json` - Output JSON format

**Examples:**
```bash
quenyan verify build/app.qyn1
quenyan verify build/app.qyn1 --key .quenyan/keys/master.key --check-signature
```

#### `inspect`

Inspect package wrapper and metadata.

```bash
quenyan inspect PACKAGE [OPTIONS]
```

**Arguments:**
- `PACKAGE` - Input QYN-1 package

**Options:**
- `--show-metadata` - Display metadata fields
- `--validate-audit` - Validate audit trail
- `--json` - Output JSON format
- `--yaml` - Output YAML format

**Examples:**
```bash
quenyan inspect build/app.qyn1
quenyan inspect build/app.qyn1 --show-metadata --json
```

#### `encode-project`

Encode multiple files in parallel.

```bash
quenyan encode-project OUTPUT_DIR SOURCE... [OPTIONS]
```

**Arguments:**
- `OUTPUT_DIR` - Directory for output packages
- `SOURCE...` - One or more source files

**Options:**
- `--key PATH` - Passphrase file path
- `--passphrase TEXT` - Inline passphrase
- `--compression-mode {balanced,maximum,security}` - Compression preset
- `--compression-backend {rans,chunked-rans}` - Backend override
- `--streaming-backend {chunked-rans}` - Backend for large files
- `--streaming-threshold BYTES` - File size threshold for streaming (default: 32MB)
- `--chunk-size N` - Tokens per chunk (default: 65536)
- `--max-buffered-tokens N` - Max buffered tokens (default: 65536)
- `--workers N` - Number of parallel workers (default: CPU count)
- `--json` - Output JSON summary

**Examples:**
```bash
quenyan encode-project build/dist src/**/*.py --key .quenyan/keys/master.key
quenyan encode-project build/dist src/**/*.py --key .quenyan/keys/master.key --workers=8 --json
```

#### `encode-incremental`

Incrementally encode with caching and dependency tracking.

```bash
quenyan encode-incremental OUTPUT_DIR SOURCE... [OPTIONS]
```

**Arguments:**
- `OUTPUT_DIR` - Directory for output packages
- `SOURCE...` - One or more source files

**Options:**
- `--key PATH` - Passphrase file path
- `--passphrase TEXT` - Inline passphrase
- `--cache-dir PATH` - Cache directory (required)
- `--root PATH` - Project root (default: common ancestor)
- `--manifest PATH` - JSON dependency manifest
- `--compression-mode {balanced,maximum,security}` - Compression preset
- `--compression-backend {rans,chunked-rans}` - Backend override
- `--streaming-threshold BYTES` - Streaming threshold
- `--chunk-size N` - Tokens per chunk
- `--max-buffered-tokens N` - Max buffered tokens
- `--shard-index N` - CI shard index (default: 0)
- `--shard-count N` - Total CI shards (default: 1)
- `--json` - Output JSON summary

**Examples:**
```bash
quenyan encode-incremental build/mcs $(git ls-files '*.py') \
  --key .quenyan/keys/master.key \
  --cache-dir .qyn-cache

quenyan encode-incremental build/mcs $(git ls-files '*.py') \
  --key .quenyan/keys/master.key \
  --cache-dir .qyn-cache \
  --manifest deps.json \
  --shard-index=0 \
  --shard-count=4
```

#### `diff`

Compare two packages at morpheme level.

```bash
quenyan diff PACKAGE_A PACKAGE_B [OPTIONS]
```

**Arguments:**
- `PACKAGE_A` - First package
- `PACKAGE_B` - Second package

**Options:**
- `--key PATH` - Passphrase file path
- `--passphrase TEXT` - Inline passphrase

**Examples:**
```bash
quenyan diff old.qyn1 new.qyn1 --key .quenyan/keys/master.key
```

#### `source-map`

Extract or summarize embedded source map.

```bash
quenyan source-map PACKAGE [OPTIONS]
```

**Arguments:**
- `PACKAGE` - Input QYN-1 package

**Options:**
- `--key PATH` - Passphrase file path
- `--passphrase TEXT` - Inline passphrase
- `--output PATH` - Export source map to file
- `--json` - Output JSON summary

**Examples:**
```bash
quenyan source-map build/app.qyn1 --key .quenyan/keys/master.key --json
quenyan source-map build/app.qyn1 --key .quenyan/keys/master.key --output app.map
```

#### `morphemes`

Display human-readable morpheme stream.

```bash
quenyan morphemes PACKAGE [OPTIONS]
```

**Arguments:**
- `PACKAGE` - Input QYN-1 package

**Options:**
- `--key PATH` - Passphrase file path
- `--passphrase TEXT` - Inline passphrase
- `--output PATH` - Write to file instead of stdout

**Examples:**
```bash
quenyan morphemes build/app.qyn1 --key .quenyan/keys/master.key
quenyan morphemes build/app.qyn1 --key .quenyan/keys/master.key --output app.trace
```

#### `lint`

Run static analysis on package.

```bash
quenyan lint PACKAGE [OPTIONS]
```

**Arguments:**
- `PACKAGE` - Input QYN-1 package

**Options:**
- `--key PATH` - Passphrase file path
- `--passphrase TEXT` - Inline passphrase

**Examples:**
```bash
quenyan lint build/app.qyn1 --key .quenyan/keys/master.key
```

#### `decompile`

Emit canonical source without writing to file.

```bash
quenyan decompile PACKAGE [OPTIONS]
```

**Arguments:**
- `PACKAGE` - Input QYN-1 package

**Options:**
- `--key PATH` - Passphrase file path
- `--passphrase TEXT` - Inline passphrase
- `--output PATH` - Write to file (optional)

**Examples:**
```bash
quenyan decompile build/app.qyn1 --key .quenyan/keys/master.key
quenyan decompile build/app.qyn1 --key .quenyan/keys/master.key --output src/app.py
```

#### `migrate`

Migrate package to new dictionary or format version.

```bash
quenyan migrate PACKAGE [OPTIONS]
```

**Arguments:**
- `PACKAGE` - Input QYN-1 package

**Options:**
- `--output PATH` - Output package (default: overwrite input)
- `--target-dictionary VERSION` - Target dictionary version
- `--target-package VERSION` - Target package format version
- `--key PATH` - Passphrase file path
- `--passphrase TEXT` - Inline passphrase
- `--no-backup` - Skip creating .bak file
- `--quiet` - Suppress output

**Examples:**
```bash
quenyan migrate old.qyn1 --key .quenyan/keys/master.key --output new.qyn1
quenyan migrate package.qyn1 --key .quenyan/keys/master.key --target-dictionary=v2
```

#### `repo-pack`

Build repository archive from packages.

```bash
quenyan repo-pack MANIFEST OUTPUT [OPTIONS]
```

**Arguments:**
- `MANIFEST` - JSON manifest file
- `OUTPUT` - Output directory

**Options:**
- `--root PATH` - Override project root from manifest
- `--compression-mode MODE` - Compression mode label
- `--backend BACKEND` - Backend label
- `--archive PATH` - Create monolithic archive
- `--json` - Output JSON summary

**Examples:**
```bash
quenyan repo-pack manifest.json build/repo --archive build/repo.zip
```

#### `repo-diff`

Compare two repository indexes.

```bash
quenyan repo-diff CURRENT PREVIOUS [OPTIONS]
```

**Arguments:**
- `CURRENT` - Current index.json
- `PREVIOUS` - Previous index.json

**Options:**
- `--json` - Output JSON format

**Examples:**
```bash
quenyan repo-diff build/v2/index.json build/v1/index.json --json
```

#### `init`

Initialize project for Quenyan.

```bash
quenyan init [DIRECTORY] [OPTIONS]
```

**Arguments:**
- `DIRECTORY` - Project root (default: current directory)

**Options:**
- `--generate-keys` - Create master key
- `--compression-mode {balanced,maximum,security}` - Default compression mode
- `--compression-backend {rans,chunked-rans}` - Default backend
- `--force` - Overwrite existing keys
- `--quiet` - Suppress output

**Examples:**
```bash
quenyan init --generate-keys
quenyan init /path/to/project --generate-keys --compression-mode=maximum
```

#### `compression-backends`

List available compression backends.

```bash
quenyan compression-backends [OPTIONS]
```

**Options:**
- `--json` - Output JSON format

**Examples:**
```bash
quenyan compression-backends
quenyan compression-backends --json
```

#### `completion`

Generate shell completion script.

```bash
quenyan completion {bash,zsh,fish}
```

**Arguments:**
- `SHELL` - Shell type (bash, zsh, or fish)

**Examples:**
```bash
quenyan completion bash > ~/.local/share/bash-completion/completions/quenyan
quenyan completion zsh > ~/.zsh/completions/_quenyan
```

#### `man`

Display CLI manual page.

```bash
quenyan man
```

### 9.3 Exit Codes

- `0` - Success
- `1` - General error (CommandError)
- `2` - Invalid arguments
- `3` - File not found
- `4` - Permission denied
- `5` - Cryptographic error (wrong passphrase, corrupted package)

---

## 10. Appendices

### 10.1 Glossary

- **AEAD**: Authenticated Encryption with Associated Data - encryption that also verifies data integrity
- **ANS**: Asymmetric Numeral Systems - modern entropy coding algorithm
- **AST**: Abstract Syntax Tree - structured representation of source code
- **ChaCha20-Poly1305**: Modern authenticated encryption cipher suite
- **Dictionary**: Versioned collection of morpheme definitions
- **HKDF**: HMAC-based Key Derivation Function
- **HSM**: Hardware Security Module - tamper-resistant hardware for key storage
- **KMS**: Key Management Service - cloud-based key management
- **MCS**: Morphemic Crypto-Code Substrate - binary package format
- **Morpheme**: Linguistic-style token representing code constructs
- **PBKDF2**: Password-Based Key Derivation Function 2
- **rANS**: Range variant of Asymmetric Numeral Systems
- **Stream**: Ordered sequence of morphemes

### 10.2 FAQ

**Q: Can I encode languages other than Python?**

A: Currently, Quenyan supports Python. Multi-language support (JavaScript, Go, Rust, C++) is planned via the Universal AST schema.

**Q: Are comments and docstrings preserved?**

A: By default, no. The system encodes AST-level semantics only. Optional metadata preservation is planned.

**Q: Can I decrypt .qyn1 files without the original passphrase?**

A: No. Without the correct passphrase/key, decryption is cryptographically infeasible.

**Q: How do I migrate from v1 to v2 dictionary?**

A: Use the `migrate` command:
```bash
quenyan migrate old.qyn1 --key .quenyan/keys/master.key --target-dictionary=v2
```

**Q: What's the maximum file size supported?**

A: Theoretically unlimited with streaming mode. Tested up to 1GB files.

**Q: Can I use Quenyan in commercial projects?**

A: Check the LICENSE file. Generally, yes, with proper attribution.

**Q: How do I report security vulnerabilities?**

A: Email security@example.com or open a GitHub security advisory.

**Q: What's the compression ratio compared to gzip?**

A: Typically 10-30% better than gzip due to semantic-level compression. See `docs/compression_ratio_comparison.md`.

**Q: Is Quenyan suitable for real-time encoding?**

A: For small files (<1MB), yes. For larger files, consider batch processing or streaming mode.

**Q: Can I use custom morpheme dictionaries?**

A: Not currently supported. Future versions may allow plugin dictionaries.

### 10.3 Configuration File Reference

**Location:** `.quenyan/config.json`

```json
{
  "default_compression_mode": "balanced",
  "default_backend": "rans",
  "cache_dir": "/path/to/.quenyan/cache",
  "key_provider": "local",
  "kms_config": {
    "provider": "aws",
    "key_id": "alias/quenyan",
    "region": "us-east-1"
  }
}
```

**Fields:**
- `default_compression_mode` - Default preset (balanced, maximum, security)
- `default_backend` - Default compression backend
- `cache_dir` - Path to incremental build cache
- `key_provider` - Key storage provider (local, aws, azure, vault)
- `kms_config` - Provider-specific KMS configuration

### 10.4 Dependency Manifest Format

**Location:** User-defined (e.g., `manifest.json`)

```json
{
  "dependencies": {
    "src/main.py": ["src/utils.py", "src/config.py"],
    "src/utils.py": ["src/config.py"],
    "src/config.py": []
  }
}
```

**Purpose:** Declares file dependencies for incremental encoding. When a file changes, dependent files are automatically rebuilt.

### 10.5 Environment Variables

- `QYN1_PASSPHRASE` - Master passphrase (not recommended except in CI)
- `QUENYAN_CONFIG` - Override config file path
- `QUENYAN_CACHE_DIR` - Override cache directory
- `PYTHONWARNINGS` - Enable Python warnings for debugging

### 10.6 File Extensions

- `.qyn1` - Quenyan encrypted package
- `.map` - Source map file
- `.morphemes` / `.trace` - Human-readable morpheme stream
- `.key` - Passphrase file (plain text, keep secure!)

### 10.7 Related Documentation

- **Format Specification:** `docs/mcs_format_v1_specification.md`
- **Cryptographic Architecture:** `docs/cryptographic_architecture.md`
- **Morpheme Dictionary:** `docs/quenya_morpheme_dictionary_v1.md`
- **Threat Model:** `docs/threat_model.md`
- **CI Integration:** `docs/ci_integration.md`
- **Incremental Builds:** `docs/incremental_builds.md`
- **Performance Profiling:** `docs/performance_profiling.md`

### 10.8 Migration Guides

#### From v0.x to v1.0

```bash
# Migrate packages
for pkg in build/*.qyn1; do
  quenyan migrate "$pkg" --key .quenyan/keys/master.key
done

# Update config
quenyan init --force
```

**Breaking Changes:**
- New binary format (automatic migration)
- Dictionary v1 (backward compatible)
- Key derivation parameters changed

#### From Development to Production

1. **Replace file-based keys with KMS:**
   ```bash
   # Store key in KMS
   aws kms import-key-material --key-id alias/quenyan ...

   # Update config
   cat > .quenyan/config.json <<EOF
   {
     "key_provider": "aws",
     "kms_config": {
       "provider": "aws",
       "key_id": "alias/quenyan",
       "region": "us-east-1"
     }
   }
   EOF
   ```

2. **Enable audit logging**

3. **Implement key rotation schedule**

4. **Use incremental builds with caching**

### 10.9 Support & Resources

- **Documentation:** https://docs.quenyan.io (if available)
- **Issue Tracker:** https://github.com/E-TECH-PLAYTECH/quenyan/issues
- **Source Code:** https://github.com/E-TECH-PLAYTECH/quenyan
- **Community:** (Slack/Discord if available)

### 10.10 License & Attribution

This software is developed by E-TECH-PLAYTECH. See LICENSE file for details.

**Third-Party Dependencies:**
- ChaCha20-Poly1305 implementation: See `qyn1/crypto.py`
- rANS implementation: See `qyn1/compression.py`
- PyYAML: BSD License

---

**Document Version:** 1.0
**Last Updated:** 2025-11-19
**Feedback:** Please report issues or suggestions via GitHub Issues
