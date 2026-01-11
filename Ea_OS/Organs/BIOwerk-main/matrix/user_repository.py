"""User repository for database operations."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import Optional, List
from datetime import datetime

from .db_models import User, APIKey
from .auth import hash_password, hash_api_key, generate_api_key


class UserRepository:
    """Repository for User CRUD operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_user(
        self,
        email: str,
        username: str,
        password: Optional[str] = None,
        auth_provider: str = "local",
        is_admin: bool = False
    ) -> User:
        """
        Create a new user.

        Args:
            email: User email
            username: Username
            password: Plain password (will be hashed)
            auth_provider: Auth provider (local, oauth2, etc.)
            is_admin: Admin flag

        Returns:
            Created user object
        """
        hashed_password = hash_password(password) if password else None

        user = User(
            email=email,
            username=username,
            hashed_password=hashed_password,
            auth_provider=auth_provider,
            is_admin=is_admin,
            is_active=True
        )

        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        return user

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        stmt = select(User).where(User.email == email)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        stmt = select(User).where(User.username == username)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_users(self, skip: int = 0, limit: int = 100) -> List[User]:
        """List all users with pagination."""
        stmt = select(User).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_user(self, user_id: str, **kwargs) -> Optional[User]:
        """Update user fields."""
        stmt = update(User).where(User.id == user_id).values(**kwargs).returning(User)
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.scalar_one_or_none()

    async def delete_user(self, user_id: str) -> bool:
        """Delete user (soft delete by setting is_active=False)."""
        stmt = update(User).where(User.id == user_id).values(is_active=False)
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount > 0

    async def activate_user(self, user_id: str) -> bool:
        """Activate a user."""
        stmt = update(User).where(User.id == user_id).values(is_active=True)
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount > 0

    async def deactivate_user(self, user_id: str) -> bool:
        """Deactivate a user."""
        stmt = update(User).where(User.id == user_id).values(is_active=False)
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount > 0


class APIKeyRepository:
    """Repository for API Key CRUD operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_api_key(
        self,
        user_id: str,
        name: str,
        scopes: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None
    ) -> tuple[APIKey, str]:
        """
        Create a new API key.

        Args:
            user_id: User ID
            name: Friendly name for the key
            scopes: List of allowed scopes
            expires_at: Expiration datetime

        Returns:
            Tuple of (APIKey object, plain API key string)
            Note: Plain key is only returned once and should be shown to user
        """
        plain_key = generate_api_key()
        hashed_key = hash_api_key(plain_key)

        api_key = APIKey(
            user_id=user_id,
            key_hash=hashed_key,
            name=name,
            scopes=scopes,
            expires_at=expires_at,
            is_active=True
        )

        self.db.add(api_key)
        await self.db.commit()
        await self.db.refresh(api_key)

        return api_key, plain_key

    async def get_api_key_by_id(self, key_id: str) -> Optional[APIKey]:
        """Get API key by ID."""
        stmt = select(APIKey).where(APIKey.id == key_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_user_api_keys(self, user_id: str) -> List[APIKey]:
        """List all API keys for a user."""
        stmt = select(APIKey).where(APIKey.user_id == user_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_active_user_api_keys(self, user_id: str) -> List[APIKey]:
        """List active API keys for a user."""
        stmt = select(APIKey).where(
            APIKey.user_id == user_id,
            APIKey.is_active == True  # noqa: E712
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def revoke_api_key(self, key_id: str) -> bool:
        """Revoke an API key."""
        stmt = update(APIKey).where(APIKey.id == key_id).values(is_active=False)
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount > 0

    async def delete_api_key(self, key_id: str) -> bool:
        """Delete an API key (hard delete)."""
        stmt = select(APIKey).where(APIKey.id == key_id)
        result = await self.db.execute(stmt)
        api_key = result.scalar_one_or_none()

        if api_key:
            await self.db.delete(api_key)
            await self.db.commit()
            return True

        return False

    async def update_last_used(self, key_id: str) -> bool:
        """Update last_used_at timestamp."""
        stmt = update(APIKey).where(APIKey.id == key_id).values(last_used_at=datetime.utcnow())
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount > 0
