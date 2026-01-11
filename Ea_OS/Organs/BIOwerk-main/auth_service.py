"""
Standalone authentication service for BIOwerk.

This service provides user registration, login, token management, and API key management.
It can be run as a standalone microservice or integrated into the mesh gateway.

Usage:
    uvicorn auth_service:app --host 0.0.0.0 --port 8100
"""
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from datetime import datetime, timedelta

from matrix.database import get_postgres_session, init_databases
from matrix.db_models import User, APIKey
from matrix.user_repository import UserRepository, APIKeyRepository
from matrix.auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    TokenResponse
)
from matrix.auth_dependencies import get_current_active_user, require_admin
from matrix.observability import setup_instrumentation
from matrix.logging_config import setup_logging

# Initialize app
app = FastAPI(title="BIOwerk Auth Service", version="1.0.0")
setup_instrumentation(app)
logger = setup_logging("auth_service")


# ============================================================================
# Request/Response Models
# ============================================================================

class UserRegister(BaseModel):
    """User registration request."""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)


class UserResponse(BaseModel):
    """User response (without sensitive data)."""
    id: str
    email: str
    username: str
    auth_provider: str
    is_active: bool
    is_admin: bool
    created_at: datetime

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    """Login response with tokens."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class RefreshTokenRequest(BaseModel):
    """Refresh token request."""
    refresh_token: str


class APIKeyCreate(BaseModel):
    """API key creation request."""
    name: str = Field(..., min_length=1, max_length=255)
    scopes: Optional[List[str]] = Field(default_factory=list)
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=365)


class APIKeyResponse(BaseModel):
    """API key response."""
    id: str
    name: str
    key: Optional[str] = None  # Only returned on creation
    scopes: Optional[List[str]]
    is_active: bool
    last_used_at: Optional[datetime]
    expires_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Startup/Shutdown Events
# ============================================================================

@app.on_event("startup")
async def startup():
    """Initialize database connections on startup."""
    await init_databases()
    logger.info("Auth service started")


# ============================================================================
# Public Endpoints (No Authentication Required)
# ============================================================================

@app.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserRegister,
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Register a new user.

    - **email**: Valid email address
    - **username**: Unique username (3-50 characters)
    - **password**: Strong password (min 8 characters)
    """
    repo = UserRepository(db)

    # Check if email already exists
    existing_user = await repo.get_user_by_email(user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Check if username already exists
    existing_user = await repo.get_user_by_username(user_data.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )

    # Create user
    user = await repo.create_user(
        email=user_data.email,
        username=user_data.username,
        password=user_data.password,
        auth_provider="local"
    )

    logger.info(f"New user registered: {user.email} (ID: {user.id})")

    return UserResponse.model_validate(user)


@app.post("/login", response_model=LoginResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Login with username/email and password.

    Returns access token and refresh token.

    - **username**: Username or email
    - **password**: User password
    """
    repo = UserRepository(db)

    # Try to find user by email or username
    user = await repo.get_user_by_email(form_data.username)
    if not user:
        user = await repo.get_user_by_username(form_data.username)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )

    # Verify password
    if not user.hashed_password or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    # Create tokens
    access_token = create_access_token(data={"sub": user.id})
    refresh_token = create_refresh_token(data={"sub": user.id})

    logger.info(f"User logged in: {user.email} (ID: {user.id})")

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user=UserResponse.model_validate(user)
    )


@app.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Refresh access token using refresh token.

    - **refresh_token**: Valid refresh token
    """
    payload = decode_token(request.refresh_token)

    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )

    # Verify user still exists and is active
    repo = UserRepository(db)
    user = await repo.get_user_by_id(user_id)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )

    # Create new access token
    access_token = create_access_token(data={"sub": user.id})

    logger.info(f"Token refreshed for user: {user.email}")

    return TokenResponse(access_token=access_token, token_type="bearer").dict()


# ============================================================================
# Protected Endpoints (Authentication Required)
# ============================================================================

@app.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """Get current user information."""
    return UserResponse.model_validate(current_user)


@app.get("/users", response_model=List[UserResponse])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    List all users (admin only).

    - **skip**: Number of records to skip
    - **limit**: Maximum number of records to return
    """
    repo = UserRepository(db)
    users = await repo.list_users(skip=skip, limit=limit)
    return [UserResponse.model_validate(user) for user in users]


# ============================================================================
# API Key Management
# ============================================================================

@app.post("/api-keys", response_model=APIKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    key_data: APIKeyCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Create a new API key for the current user.

    **Important**: The API key will only be shown once. Store it securely!

    - **name**: Friendly name for the key
    - **scopes**: List of allowed scopes (optional)
    - **expires_in_days**: Expiration in days (optional, max 365)
    """
    repo = APIKeyRepository(db)

    expires_at = None
    if key_data.expires_in_days:
        expires_at = datetime.utcnow() + timedelta(days=key_data.expires_in_days)

    api_key, plain_key = await repo.create_api_key(
        user_id=current_user.id,
        name=key_data.name,
        scopes=key_data.scopes,
        expires_at=expires_at
    )

    logger.info(f"API key created: {api_key.name} (ID: {api_key.id}) for user {current_user.email}")

    response = APIKeyResponse.model_validate(api_key)
    response.key = plain_key  # Only shown on creation
    return response


@app.get("/api-keys", response_model=List[APIKeyResponse])
async def list_api_keys(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """List all API keys for the current user."""
    repo = APIKeyRepository(db)
    api_keys = await repo.list_user_api_keys(current_user.id)
    return [APIKeyResponse.model_validate(key) for key in api_keys]


@app.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """Revoke an API key."""
    repo = APIKeyRepository(db)

    # Check if key belongs to current user
    api_key = await repo.get_api_key_by_id(key_id)
    if not api_key or api_key.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    await repo.revoke_api_key(key_id)
    logger.info(f"API key revoked: {key_id} by user {current_user.email}")


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "auth"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8100)
