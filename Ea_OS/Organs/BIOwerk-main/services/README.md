# BIOwerk Services - Local Model Storage

Each service in this directory can have its own **standalone copy** of LLM models.

## Quick Start

Download models for all services:
```bash
./scripts/download-models.sh phi3-mini
```

## Directory Structure

```
services/
├── osteon/
│   └── models/
│       └── phi3-mini/      # 2.3GB standalone copy
│           ├── model.gguf
│           └── model.json
├── synapse/
│   └── models/
│       └── phi3-mini/      # 2.3GB standalone copy
│           ├── model.gguf
│           └── model.json
├── myocyte/
│   └── models/
│       └── phi3-mini/      # 2.3GB standalone copy
│           ├── model.gguf
│           └── model.json
└── ... (other services)
```

## Important Notes

- **NOT committed to git**: Model directories are in `.gitignore`
- **Each service has its own copy**: This enables true service isolation
- **Total storage**: 6+ services × 2.3GB = 13.8GB+ for phi3-mini
- **Download required**: Run `./scripts/download-models.sh` after cloning

## Documentation

See [MODELS_SETUP.md](../MODELS_SETUP.md) for complete documentation.
