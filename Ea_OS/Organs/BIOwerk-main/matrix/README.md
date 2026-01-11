# Matrix - BIOwerk Shared Library

Matrix is the core shared library for all BIOwerk microservices, providing common utilities, models, authentication, database connections, and LLM integrations.

## Features

### Core Models
- `Msg` - Standard request message format for inter-service communication
- `Reply` - Standard response message format
- Database ORM models (User, Project, Artifact, Execution, APIKey)

### Database Support
- **PostgreSQL** - Async SQLAlchemy with connection pooling
- **MongoDB** - Motor async client with repository pattern
- **Redis** - Async Redis client for caching and pub/sub

### Authentication & Security
- JWT token generation and validation (access + refresh tokens)
- Password hashing with bcrypt
- API key generation and verification (BLAKE3 hashing)
- FastAPI dependency injection helpers for auth

### LLM Integration
Unified interface to multiple LLM providers:
- **OpenAI** (GPT-4, GPT-3.5)
- **Anthropic** (Claude)
- **DeepSeek** (DeepSeek Chat)
- **Ollama** (Local models)
- **Local GGUF** (llama-cpp-python)

The `llm_client` provides:
- `chat_completion()` - Chat-based completions
- `generate_json()` - Structured JSON responses
- Automatic provider selection via configuration
- Streaming support

### Utilities
- `state_hash()` - BLAKE3 hashing for state verification
- `canonical()` - Canonical JSON serialization
- Error handling with custom exception types
- Structured logging with request/response tracking
- Prometheus metrics integration

## Installation

Matrix is installed automatically in Docker containers via the service Dockerfiles.

For local development:

```bash
# From the project root
pip install -e .
```

## Usage

Import matrix utilities in your service:

```python
from matrix.models import Msg, Reply
from matrix.llm_client import llm_client
from matrix.logging_config import setup_logging
from matrix.errors import InvalidInputError
from matrix.cache import cache, cached
from matrix.auth import create_access_token, hash_password
```

### Example: Using LLM Client

```python
from matrix.llm_client import llm_client

# Chat completion
response = await llm_client.chat_completion(
    messages=[{"role": "user", "content": "Hello!"}],
    system_prompt="You are a helpful assistant."
)

# Structured JSON response
json_response = await llm_client.generate_json(
    prompt="List 3 colors",
    system_prompt="Return JSON with 'colors' array"
)
```

### Example: Database Access

```python
from matrix.database import get_db_session
from matrix.db_models import User

async with get_db_session() as db:
    user = await db.get(User, user_id)
```

### Example: Authentication

```python
from matrix.auth_dependencies import get_current_user
from fastapi import Depends

@app.get("/protected")
async def protected_route(user = Depends(get_current_user)):
    return {"user_id": user.id}
```

## Configuration

Matrix uses environment variables for configuration (see `config.py`):

### Database
- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
- `MONGO_HOST`, `MONGO_PORT`, `MONGO_USER`, `MONGO_PASSWORD`, `MONGO_DB`
- `REDIS_HOST`, `REDIS_PORT`

### Authentication
- `JWT_SECRET_KEY` - Secret for JWT signing
- `JWT_ALGORITHM` - Algorithm (default: HS256)
- `ACCESS_TOKEN_EXPIRE_MINUTES` - Access token TTL (default: 30)
- `REFRESH_TOKEN_EXPIRE_DAYS` - Refresh token TTL (default: 7)

### LLM Providers
- `LLM_PROVIDER` - Default provider: openai, anthropic, deepseek, ollama, local
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`
- `OLLAMA_BASE_URL` - Ollama server URL
- `LOCAL_MODEL_PATH`, `LOCAL_MODEL_NAME` - For GGUF models

## Architecture

Matrix follows these principles:

1. **Single Source of Truth** - One copy of shared code in `/matrix`
2. **Package-based Distribution** - Installed as Python package via setup.py
3. **No Code Duplication** - Services import from installed matrix package
4. **Environment-based Config** - All settings via environment variables
5. **Dependency Injection** - FastAPI dependencies for clean separation

## Development

When modifying matrix:

1. Make changes in `/matrix` directory
2. Rebuild affected Docker containers to pick up changes
3. Test across all services that use the modified functionality

```bash
# Rebuild specific service
docker-compose build osteon

# Rebuild all services
docker-compose build
```

## Services Using Matrix

- **osteon** - Document generation and editing
- **myocyte** - Data analysis and visualization
- **synapse** - Knowledge synthesis and connections
- **circadian** - Task scheduling and workflows
- **nucleus** - Project and execution orchestration
- **chaperone** - Quality assurance and validation
- **mesh** - API gateway and routing

## Version History

- **0.1.0** - Initial shared library refactoring
