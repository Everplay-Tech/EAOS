"""FastAPI dependencies for authentication and authorization."""
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import logging

from .database import get_postgres_session
from .db_models import User, APIKey
from .auth import decode_token, verify_api_key
from .config import settings

logger = logging.getLogger(__name__)

# Security scheme for Swagger UI
security = HTTPBearer(auto_error=False)


# ============================================================================
# JWT Authentication
# ============================================================================

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_postgres_session)
) -> Optional[User]:
    """
    Get current user from JWT token.

    Usage:
        @app.get("/protected")
        async def protected_route(user: User = Depends(get_current_user)):
            return {"user_id": user.id}

    Args:
        credentials: HTTP Bearer token
        db: Database session

    Returns:
        User object if authenticated, None otherwise

    Raises:
        HTTPException: 401 if token is invalid or user not found
    """
    if not credentials:
        if settings.require_auth:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return None

    token = credentials.credentials
    payload = decode_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch user from database
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )

    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Get current active user (raises exception if user is None or inactive).

    Usage:
        @app.get("/protected")
        async def protected_route(user: User = Depends(get_current_active_user)):
            return {"user_id": user.id}
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    return current_user


# ============================================================================
# API Key Authentication
# ============================================================================

async def get_user_from_api_key(
    api_key: Optional[str] = Header(None, alias=None),  # Will be set dynamically
    db: AsyncSession = Depends(get_postgres_session)
) -> Optional[User]:
    """
    Get user from API key header.

    Args:
        api_key: API key from header
        db: Database session

    Returns:
        User object if API key is valid, None otherwise
    """
    if not api_key:
        return None

    # Find API key in database
    stmt = select(APIKey).where(APIKey.is_active == True)  # noqa: E712
    result = await db.execute(stmt)
    api_keys = result.scalars().all()

    for db_api_key in api_keys:
        if verify_api_key(api_key, db_api_key.key_hash):
            # Update last_used_at
            from datetime import datetime
            db_api_key.last_used_at = datetime.utcnow()
            await db.commit()

            # Fetch user
            stmt = select(User).where(User.id == db_api_key.user_id)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()

            if user and user.is_active:
                return user

    return None


async def get_current_user_or_api_key(
    user_from_jwt: Optional[User] = Depends(get_current_user),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_postgres_session)
) -> Optional[User]:
    """
    Get current user from either JWT token or API key.

    Tries JWT first, then API key.

    Usage:
        @app.get("/protected")
        async def protected_route(user: User = Depends(get_current_user_or_api_key)):
            if not user:
                raise HTTPException(401, "Not authenticated")
            return {"user_id": user.id}
    """
    if user_from_jwt:
        return user_from_jwt

    if x_api_key:
        user = await get_user_from_api_key(x_api_key, db)
        if user:
            return user

    return None


# ============================================================================
# Role-Based Access Control (RBAC)
# ============================================================================

async def get_user_roles(user_id: str, db: AsyncSession) -> list:
    """
    Get all active roles for a user.

    Args:
        user_id: User ID
        db: Database session

    Returns:
        List of role names
    """
    from .db_models import UserRole, Role
    from datetime import datetime

    stmt = select(Role).join(UserRole).where(
        UserRole.user_id == user_id,
        UserRole.is_active == True,  # noqa: E712
        Role.is_active == True,  # noqa: E712
        (UserRole.expires_at.is_(None) | (UserRole.expires_at > datetime.utcnow()))
    )
    result = await db.execute(stmt)
    roles = result.scalars().all()
    return [role.name for role in roles]


async def get_user_permissions(user_id: str, db: AsyncSession, resource_type: Optional[str] = None) -> list:
    """
    Get all active permissions for a user.

    Args:
        user_id: User ID
        db: Database session
        resource_type: Optional resource type filter

    Returns:
        List of (action, resource_type) tuples
    """
    from .db_models import UserRole, Role, RolePermission, Permission
    from datetime import datetime

    # Build query to get permissions through user roles
    stmt = select(Permission).join(RolePermission).join(Role).join(UserRole).where(
        UserRole.user_id == user_id,
        UserRole.is_active == True,  # noqa: E712
        Role.is_active == True,  # noqa: E712
        RolePermission.is_active == True,  # noqa: E712
        Permission.is_active == True,  # noqa: E712
        (UserRole.expires_at.is_(None) | (UserRole.expires_at > datetime.utcnow())),
        (RolePermission.expires_at.is_(None) | (RolePermission.expires_at > datetime.utcnow()))
    )

    if resource_type:
        stmt = stmt.where(Permission.resource_type == resource_type)

    result = await db.execute(stmt)
    permissions = result.scalars().all()
    return [(perm.action, perm.resource_type) for perm in permissions]


async def has_permission(
    user: User,
    action: str,
    resource_type: str,
    db: AsyncSession,
    resource_id: Optional[str] = None
) -> bool:
    """
    Check if user has specific permission.

    Args:
        user: User object
        action: Permission action (read, write, delete, admin)
        resource_type: Resource type (project, artifact, execution, etc.)
        db: Database session
        resource_id: Optional specific resource ID

    Returns:
        True if user has permission, False otherwise
    """
    # Admin users have all permissions
    if user.is_admin:
        return True

    # Check if user has the permission through their roles
    permissions = await get_user_permissions(user.id, db, resource_type)

    # Check for exact permission match
    if (action, resource_type) in permissions:
        return True

    # Check for admin permission on resource type (admin can do anything)
    if ("admin", resource_type) in permissions:
        return True

    # Check for global admin permission
    if ("admin", "global") in permissions:
        return True

    return False


async def is_resource_owner(
    user: User,
    resource_type: str,
    resource_id: str,
    db: AsyncSession
) -> bool:
    """
    Check if user owns a specific resource.

    Args:
        user: User object
        resource_type: Resource type
        resource_id: Resource ID
        db: Database session

    Returns:
        True if user owns the resource, False otherwise
    """
    from .db_models import ResourceOwnership

    stmt = select(ResourceOwnership).where(
        ResourceOwnership.resource_type == resource_type,
        ResourceOwnership.resource_id == resource_id,
        ResourceOwnership.owner_id == user.id
    )
    result = await db.execute(stmt)
    ownership = result.scalar_one_or_none()
    return ownership is not None


def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """
    Require admin role for endpoint.

    Usage:
        @app.post("/admin/users")
        async def create_user(user: User = Depends(require_admin)):
            # Only admins can access this
            return {"message": "Admin only"}
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


def require_role(*required_roles: str):
    """
    Require specific role(s) for endpoint.

    Usage:
        @app.post("/projects")
        async def create_project(user: User = Depends(require_role("admin", "user"))):
            # Only users with admin or user role can access this
            return {"message": "Authorized"}

    Args:
        required_roles: One or more role names required

    Returns:
        Dependency function
    """
    async def _check_role(
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_postgres_session)
    ) -> User:
        # Admin always has access
        if current_user.is_admin:
            return current_user

        # Get user roles
        user_roles = await get_user_roles(current_user.id, db)

        # Check if user has any of the required roles
        if not any(role in user_roles for role in required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required role(s): {', '.join(required_roles)}"
            )

        return current_user

    return _check_role


def require_permission(action: str, resource_type: str):
    """
    Require specific permission for endpoint.

    Usage:
        @app.post("/projects")
        async def create_project(user: User = Depends(require_permission("write", "project"))):
            # Only users with write permission on projects can access this
            return {"message": "Authorized"}

    Args:
        action: Permission action (read, write, delete, admin)
        resource_type: Resource type (project, artifact, execution, etc.)

    Returns:
        Dependency function
    """
    async def _check_permission(
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_postgres_session)
    ) -> User:
        # Check if user has permission
        if not await has_permission(current_user, action, resource_type, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {action} on {resource_type}"
            )

        return current_user

    return _check_permission


def require_resource_permission(action: str, resource_type: str, allow_owner: bool = True):
    """
    Require permission for specific resource, with optional owner check.

    Usage:
        @app.delete("/projects/{project_id}")
        async def delete_project(
            project_id: str,
            user_and_resource: tuple = Depends(require_resource_permission("delete", "project"))
        ):
            user, resource_id = user_and_resource
            # User has delete permission or is the owner
            return {"message": "Deleted"}

    Args:
        action: Permission action (read, write, delete, admin)
        resource_type: Resource type (project, artifact, execution, etc.)
        allow_owner: If True, resource owner can perform action even without explicit permission

    Returns:
        Dependency function that returns (user, resource_id) tuple
    """
    async def _check_resource_permission(
        resource_id: str,
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_postgres_session)
    ) -> tuple:
        # Check if user has permission
        has_perm = await has_permission(current_user, action, resource_type, db, resource_id)

        # If user doesn't have permission, check if they're the owner (if allowed)
        if not has_perm and allow_owner:
            is_owner = await is_resource_owner(current_user, resource_type, resource_id, db)
            if not is_owner:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {action} on {resource_type}:{resource_id}"
                )
        elif not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {action} on {resource_type}:{resource_id}"
            )

        return (current_user, resource_id)

    return _check_resource_permission


async def check_resource_access(
    user: User,
    resource_type: str,
    resource_id: str,
    action: str,
    db: AsyncSession,
    allow_owner: bool = True
) -> bool:
    """
    Check if user can access a specific resource.

    Args:
        user: User object
        resource_type: Resource type
        resource_id: Resource ID
        action: Permission action
        db: Database session
        allow_owner: If True, resource owner has access

    Returns:
        True if user has access, False otherwise
    """
    # Check permission
    has_perm = await has_permission(user, action, resource_type, db, resource_id)
    if has_perm:
        return True

    # Check ownership if allowed
    if allow_owner:
        is_owner = await is_resource_owner(user, resource_type, resource_id, db)
        if is_owner:
            return True

    return False


def require_scopes(*required_scopes: str):
    """
    Require specific scopes from API key.

    Usage:
        @app.post("/sensitive")
        async def sensitive_route(user: User = Depends(require_scopes("read:sensitive", "write:sensitive"))):
            return {"message": "Authorized"}
    """
    async def _check_scopes(
        x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
        db: AsyncSession = Depends(get_postgres_session)
    ) -> User:
        if not x_api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key required"
            )

        # Find API key
        stmt = select(APIKey).where(APIKey.is_active == True)  # noqa: E712
        result = await db.execute(stmt)
        api_keys = result.scalars().all()

        for db_api_key in api_keys:
            if verify_api_key(x_api_key, db_api_key.key_hash):
                # Check scopes
                key_scopes = db_api_key.scopes or []
                if not all(scope in key_scopes for scope in required_scopes):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Missing required scopes: {required_scopes}"
                    )

                # Fetch user
                stmt = select(User).where(User.id == db_api_key.user_id)
                result = await db.execute(stmt)
                user = result.scalar_one_or_none()

                if user and user.is_active:
                    return user

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )

    return _check_scopes


# ============================================================================
# Optional Authentication
# ============================================================================

async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_postgres_session)
) -> Optional[User]:
    """
    Get current user if authenticated, None otherwise (no exception).

    Usage:
        @app.get("/public-or-private")
        async def endpoint(user: Optional[User] = Depends(get_optional_user)):
            if user:
                return {"message": "Hello, authenticated user!"}
            return {"message": "Hello, anonymous user!"}
    """
    if not credentials:
        return None

    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None
