# Authentication & Authorization Guide

Complete guide for implementing authentication and authorization in BIOwerk.

## Overview

BIOwerk uses JWT tokens for user authentication and API keys for service-to-service communication, with role-based access control (RBAC).

**Authentication Methods:**
- **JWT Tokens** - User authentication (access + refresh tokens)
- **API Keys** - Service-to-service authentication
- **OAuth2** - Future support for third-party providers

## Quick Start

### 1. Start Auth Service

```bash
docker compose up -d auth
# Or standalone:
uvicorn auth_service:app --host 0.0.0.0 --port 8100
```

### 2. Register a User

```bash
curl -X POST http://localhost:8100/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "username": "johndoe",
    "password": "SecurePass123"
  }'
```

### 3. Login

```bash
curl -X POST http://localhost:8100/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=johndoe&password=SecurePass123"
```

Response:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "username": "johndoe"
  }
}
```

### 4. Use Protected Endpoints

```bash
curl http://localhost:8100/me \
  -H "Authorization: Bearer eyJ..."
```

## API Endpoints

### Public Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/register` | Register new user |
| POST | `/login` | Login (get tokens) |
| POST | `/refresh` | Refresh access token |
| GET | `/health` | Health check |

### Protected Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/me` | Get current user | JWT |
| GET | `/users` | List users | JWT (Admin) |
| POST | `/api-keys` | Create API key | JWT |
| GET | `/api-keys` | List API keys | JWT |
| DELETE | `/api-keys/{id}` | Revoke API key | JWT |

## Usage in Services

### Protect an Endpoint

```python
from fastapi import FastAPI, Depends
from matrix.db_models import User
from matrix.auth_dependencies import get_current_active_user

app = FastAPI()

@app.get("/protected")
async def protected_route(user: User = Depends(get_current_active_user)):
    return {"message": f"Hello, {user.username}!"}
```

### Require Admin

```python
from matrix.auth_dependencies import require_admin

@app.post("/admin/action")
async def admin_only(user: User = Depends(require_admin)):
    return {"message": "Admin access granted"}
```

### Optional Authentication

```python
from typing import Optional
from matrix.auth_dependencies import get_optional_user

@app.get("/public-or-private")
async def endpoint(user: Optional[User] = Depends(get_optional_user)):
    if user:
        return {"message": f"Welcome back, {user.username}!"}
    return {"message": "Hello, guest!"}
```

## API Key Authentication

### Create API Key

```bash
curl -X POST http://localhost:8100/api-keys \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Service Key",
    "scopes": ["read:artifacts", "write:artifacts"],
    "expires_in_days": 90
  }'
```

Response (key shown only once!):
```json
{
  "id": "key-uuid",
  "name": "My Service Key",
  "key": "abc123...",
  "scopes": ["read:artifacts", "write:artifacts"],
  "expires_at": "2025-04-15T10:00:00Z"
}
```

### Use API Key

```bash
curl http://localhost:8001/artifacts \
  -H "X-API-Key: abc123..."
```

## Security Best Practices

### Production Configuration

1. **Change JWT Secret**:
   ```bash
   # Generate secure key
   openssl rand -hex 32
   
   # Set in .env
   JWT_SECRET_KEY=your-generated-key-here
   ```

2. **Enable HTTPS**: Always use TLS in production

3. **Set REQUIRE_AUTH=true**: Enforce authentication globally

4. **Rotate API Keys**: Set expiration dates

5. **Use Strong Passwords**: Enforce password policies

### Password Requirements

- Minimum 8 characters
- Mix of letters, numbers, symbols (recommended)
- No common passwords

### Token Expiration

- **Access Token**: 30 minutes (default)
- **Refresh Token**: 7 days (default)
- Configure in `.env`:
  ```
  JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
  JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
  ```

## Configuration

See `.env.example` for all authentication settings:

- `JWT_SECRET_KEY` - Secret for signing tokens
- `JWT_ALGORITHM` - Algorithm (HS256 recommended)
- `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` - Access token TTL
- `JWT_REFRESH_TOKEN_EXPIRE_DAYS` - Refresh token TTL
- `API_KEY_HEADER` - Header name for API keys
- `REQUIRE_AUTH` - Global auth enforcement

## Troubleshooting

### "Not authenticated" Error

- Check token is valid and not expired
- Verify `Authorization: Bearer <token>` header
- Ensure user account is active

### "Invalid API key" Error

- Check API key is active (not revoked)
- Verify correct header name (`X-API-Key` by default)
- Check API key hasn't expired

### Token Expired

- Use refresh token to get new access token:
  ```bash
  curl -X POST http://localhost:8100/refresh \
    -H "Content-Type: application/json" \
    -d '{"refresh_token": "YOUR_REFRESH_TOKEN"}'
  ```

## Resources

- FastAPI Security: https://fastapi.tiangolo.com/tutorial/security/
- JWT.io: https://jwt.io/
- OWASP Auth Cheatsheet: https://cheatsheetseries.owasp.org/
