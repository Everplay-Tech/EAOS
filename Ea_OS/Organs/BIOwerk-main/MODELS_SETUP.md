# Local Model Installation Guide

## Overview

Each BIOwerk service can have its own **standalone copy** of LLM models. This approach provides:

- **Complete isolation** - Each service has its own model copy
- **No git bloat** - Models are NOT committed to the repository
- **Local control** - Download and manage models on your machine
- **Flexibility** - Different services can use different model versions

## Directory Structure

```
BIOwerk/
├── services/
│   ├── osteon/
│   │   └── models/
│   │       └── phi3-mini/         # 2.3GB standalone copy
│   │           ├── model.gguf
│   │           └── model.json
│   ├── synapse/
│   │   └── models/
│   │       └── phi3-mini/         # 2.3GB standalone copy
│   │           ├── model.gguf
│   │           └── model.json
│   ├── myocyte/
│   │   └── models/
│   │       └── phi3-mini/         # 2.3GB standalone copy
│   │           ├── model.gguf
│   │           └── model.json
│   └── ... (other services)
```

**Total storage**: 6+ services × 2.3GB = 13.8GB+ for phi3-mini

## Quick Start

### 1. Install Models for All Services

Download and install phi3-mini to all services:

```bash
./scripts/download-models.sh phi3-mini
```

### 2. Install for Specific Services Only

```bash
# Just osteon and synapse
./scripts/download-models.sh phi3-mini osteon synapse

# Just myocyte
./scripts/download-models.sh phi3-mini myocyte
```

### 3. Install Different Models

```bash
# Llama 3.2 (2GB per service)
./scripts/download-models.sh llama3.2

# Mistral 7B (4.1GB per service)
./scripts/download-models.sh mistral

# Qwen 2.5 (4.7GB per service)
./scripts/download-models.sh qwen2.5
```

## Available Models

| Model | Size/Service | Total (6 services) | Quality | Speed | Best For |
|-------|--------------|-------------------|---------|-------|----------|
| **phi3-mini** | 2.3GB | 13.8GB | ⭐⭐⭐⭐ | ⚡⚡⚡ | **Default - General use** |
| **llama3.2** | 2GB | 12GB | ⭐⭐⭐ | ⚡⚡⚡ | Conversation |
| **mistral** | 4.1GB | 24.6GB | ⭐⭐⭐⭐⭐ | ⚡⚡ | High quality |
| **qwen2.5** | 4.7GB | 28.2GB | ⭐⭐⭐⭐⭐ | ⚡⚡ | Structured data |

## Manual Installation

If you prefer to download models manually:

### Using HuggingFace CLI

```bash
# Install huggingface-hub
pip install huggingface_hub

# Download phi3-mini
huggingface-cli download microsoft/Phi-3-mini-4k-instruct-gguf \
  Phi-3-mini-4k-instruct-q4.gguf \
  --local-dir /tmp/phi3-mini

# Copy to each service
for service in osteon synapse myocyte nucleus chaperone circadian; do
  mkdir -p services/$service/models/phi3-mini
  cp /tmp/phi3-mini/Phi-3-mini-4k-instruct-q4.gguf \
     services/$service/models/phi3-mini/model.gguf
done
```

### Direct Download (Browser)

1. Visit HuggingFace model page
2. Download the GGUF file
3. Copy to each service directory:

```bash
# Example for phi3-mini
for service in osteon synapse myocyte nucleus chaperone circadian; do
  mkdir -p services/$service/models/phi3-mini
  cp ~/Downloads/Phi-3-mini-4k-instruct-q4.gguf \
     services/$service/models/phi3-mini/model.gguf
done
```

## Configuration

After installing models, update your `.env` file:

```bash
# Use local model files instead of Ollama
LLM_PROVIDER=local

# Specify model name
LOCAL_MODEL_NAME=phi3-mini
```

## Service-Specific Models

Each service can use a different model:

```bash
# Install different models
./scripts/download-models.sh phi3-mini osteon myocyte
./scripts/download-models.sh mistral synapse
./scripts/download-models.sh llama3.2 nucleus chaperone circadian

# Configure per service in docker-compose.yml
# osteon:
#   environment:
#     - LOCAL_MODEL_NAME=phi3-mini
# synapse:
#   environment:
#     - LOCAL_MODEL_NAME=mistral
```

## Verifying Installation

Check which models are installed:

```bash
# List all installed models
find services/*/models -name "*.gguf" -o -name "model.json"

# Check specific service
ls -lh services/osteon/models/*/
ls -lh services/synapse/models/*/
ls -lh services/myocyte/models/*/
```

Expected output:
```
services/osteon/models/phi3-mini/model.gguf    (2.3GB)
services/synapse/models/phi3-mini/model.gguf   (2.3GB)
services/myocyte/models/phi3-mini/model.gguf   (2.3GB)
...
```

## Storage Requirements

### Minimum (Single Model)
- **phi3-mini**: 13.8GB for all 6 services
- **llama3.2**: 12GB for all 6 services

### Recommended (Development)
- **phi3-mini** on all services: 13.8GB
- Leave 20-30GB free space for operations

### Production (High Quality)
- **mistral** on all services: 24.6GB
- Or mixed: phi3 on some, mistral on others

## Updating Models

To update to a newer version:

```bash
# Remove old model
rm -rf services/*/models/phi3-mini

# Download new version
./scripts/download-models.sh phi3-mini
```

## Cleaning Up

Remove models to free space:

```bash
# Remove from specific service
rm -rf services/osteon/models/phi3-mini

# Remove from all services
rm -rf services/*/models/phi3-mini

# Remove all models
rm -rf services/*/models/*
```

## Troubleshooting

### Download fails
```bash
# Check internet connection
ping huggingface.co

# Install/update huggingface-hub
pip install -U huggingface_hub

# Try manual download
```

### Not enough disk space
```bash
# Check available space
df -h

# Install to fewer services
./scripts/download-models.sh phi3-mini osteon synapse

# Use smaller model
./scripts/download-models.sh llama3.2  # 2GB vs 2.3GB
```

### Model not loading
```bash
# Verify file exists
ls -lh services/osteon/models/phi3-mini/

# Check file permissions
chmod 644 services/*/models/*/*.gguf

# Check model.json exists
cat services/osteon/models/phi3-mini/model.json
```

## Why Standalone Copies?

**Advantages:**
- ✅ True service isolation - no shared dependencies
- ✅ Easier deployment - each service is self-contained
- ✅ Testing - can test different model versions per service
- ✅ Resilience - one service's model issues don't affect others

**Trade-offs:**
- ❌ More disk space required (13.8GB vs 2.3GB for phi3-mini)
- ❌ Longer initial setup (download to each service)
- ❌ Updates must be applied to each service

For most production deployments, the isolation benefits outweigh the storage cost.

## Next Steps

1. ✅ Download models: `./scripts/download-models.sh phi3-mini`
2. ✅ Verify installation: `find services/*/models -name "*.gguf"`
3. ✅ Update configuration: Edit `.env` to use `LLM_PROVIDER=local`
4. ✅ Restart services: `docker compose restart`
5. ✅ Test: Make API calls to each service

## Support

- Script issues: Check `scripts/download-models.sh`
- Model registry: See `MODEL_REGISTRY` in download script
- Add custom models: Edit the registry or download manually
