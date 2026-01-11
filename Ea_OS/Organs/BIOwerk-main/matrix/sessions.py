"""Redis-based session management for BIOwerk services."""
import json
import logging
from typing import Any, Optional, Dict
from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class RedisSessionManager:
    """
    Redis-based session manager for storing session state across services.

    Features:
    - Automatic TTL management
    - JSON serialization for complex data structures
    - Namespaced keys for different session types
    - Async operations for FastAPI compatibility
    """

    def __init__(
        self,
        redis_client: Redis,
        prefix: str = "session",
        default_ttl: int = 3600
    ):
        """
        Initialize session manager.

        Args:
            redis_client: Async Redis client instance
            prefix: Key prefix for namespacing (default: "session")
            default_ttl: Default session TTL in seconds (default: 3600 = 1 hour)
        """
        self.redis = redis_client
        self.prefix = prefix
        self.default_ttl = default_ttl

    def _make_key(self, session_id: str) -> str:
        """Generate Redis key with namespace prefix."""
        return f"{self.prefix}:{session_id}"

    async def set(
        self,
        session_id: str,
        data: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Store session data in Redis.

        Args:
            session_id: Unique session identifier (e.g., message ID)
            data: Session data dictionary to store
            ttl: Time-to-live in seconds (uses default_ttl if None)

        Returns:
            True if successful, False otherwise
        """
        try:
            key = self._make_key(session_id)
            serialized = json.dumps(data)
            ttl_seconds = ttl or self.default_ttl

            await self.redis.setex(key, ttl_seconds, serialized)
            logger.debug(f"Session stored: {session_id} (TTL: {ttl_seconds}s)")
            return True

        except Exception as e:
            logger.error(f"Failed to store session {session_id}: {e}")
            return False

    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve session data from Redis.

        Args:
            session_id: Unique session identifier

        Returns:
            Session data dictionary if found, None otherwise
        """
        try:
            key = self._make_key(session_id)
            data = await self.redis.get(key)

            if data is None:
                logger.debug(f"Session not found: {session_id}")
                return None

            deserialized = json.loads(data)
            logger.debug(f"Session retrieved: {session_id}")
            return deserialized

        except json.JSONDecodeError as e:
            logger.error(f"Failed to deserialize session {session_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve session {session_id}: {e}")
            return None

    async def delete(self, session_id: str) -> bool:
        """
        Delete session data from Redis.

        Args:
            session_id: Unique session identifier

        Returns:
            True if session was deleted, False if not found or error
        """
        try:
            key = self._make_key(session_id)
            result = await self.redis.delete(key)

            if result > 0:
                logger.debug(f"Session deleted: {session_id}")
                return True
            else:
                logger.debug(f"Session not found for deletion: {session_id}")
                return False

        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False

    async def exists(self, session_id: str) -> bool:
        """
        Check if session exists in Redis.

        Args:
            session_id: Unique session identifier

        Returns:
            True if session exists, False otherwise
        """
        try:
            key = self._make_key(session_id)
            result = await self.redis.exists(key)
            return result > 0

        except Exception as e:
            logger.error(f"Failed to check session existence {session_id}: {e}")
            return False

    async def update(
        self,
        session_id: str,
        data: Dict[str, Any],
        extend_ttl: bool = True
    ) -> bool:
        """
        Update existing session data or create new session.

        Args:
            session_id: Unique session identifier
            data: New session data to merge with existing data
            extend_ttl: Whether to reset TTL (default: True)

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get existing data
            existing = await self.get(session_id)

            if existing is None:
                # Create new session
                return await self.set(session_id, data)

            # Merge data
            existing.update(data)

            # Store updated data
            return await self.set(session_id, existing)

        except Exception as e:
            logger.error(f"Failed to update session {session_id}: {e}")
            return False

    async def get_ttl(self, session_id: str) -> int:
        """
        Get remaining TTL for a session.

        Args:
            session_id: Unique session identifier

        Returns:
            Remaining TTL in seconds, -1 if no TTL, -2 if session doesn't exist
        """
        try:
            key = self._make_key(session_id)
            ttl = await self.redis.ttl(key)
            return ttl

        except Exception as e:
            logger.error(f"Failed to get TTL for session {session_id}: {e}")
            return -2

    async def extend_ttl(self, session_id: str, ttl: Optional[int] = None) -> bool:
        """
        Extend TTL for an existing session.

        Args:
            session_id: Unique session identifier
            ttl: New TTL in seconds (uses default_ttl if None)

        Returns:
            True if successful, False otherwise
        """
        try:
            key = self._make_key(session_id)
            ttl_seconds = ttl or self.default_ttl
            result = await self.redis.expire(key, ttl_seconds)

            if result:
                logger.debug(f"Session TTL extended: {session_id} (TTL: {ttl_seconds}s)")
                return True
            else:
                logger.debug(f"Session not found for TTL extension: {session_id}")
                return False

        except Exception as e:
            logger.error(f"Failed to extend TTL for session {session_id}: {e}")
            return False


# Factory function to create session managers with different configurations
def create_session_manager(
    redis_client: Redis,
    session_type: str = "default",
    ttl: Optional[int] = None
) -> RedisSessionManager:
    """
    Create a session manager with preset configurations.

    Args:
        redis_client: Async Redis client instance
        session_type: Type of session ("default", "short", "long", "workflow")
        ttl: Override TTL in seconds (optional)

    Returns:
        Configured RedisSessionManager instance
    """
    ttl_presets = {
        "short": 900,      # 15 minutes
        "default": 3600,   # 1 hour
        "long": 28800,     # 8 hours
        "workflow": 86400, # 24 hours
    }

    prefix_presets = {
        "short": "session:short",
        "default": "session",
        "long": "session:long",
        "workflow": "session:workflow",
    }

    session_ttl = ttl or ttl_presets.get(session_type, 3600)
    session_prefix = prefix_presets.get(session_type, "session")

    return RedisSessionManager(
        redis_client=redis_client,
        prefix=session_prefix,
        default_ttl=session_ttl
    )
