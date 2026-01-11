"""Distributed locking using Redis with Redlock algorithm.

This module provides distributed locks that work across multiple service instances,
preventing race conditions in concurrent operations like project creation, budget updates,
and audit writes.

The implementation follows the Redlock algorithm specification:
https://redis.io/docs/manual/patterns/distributed-locks/

Key Features:
- Automatic lock expiration (TTL)
- Deadlock prevention
- Safe lock release with unique tokens
- Lock extension/renewal support
- Context manager interface
- Retry logic with exponential backoff

Usage:
    # Basic usage with context manager
    async with DistributedLock(redis, "project:123:create"):
        # Critical section - only one instance executes this
        await create_project(project_id="123")

    # Manual lock management
    lock = DistributedLock(redis, "budget:456:update", ttl=30)
    if await lock.acquire():
        try:
            await update_budget(budget_id="456")
        finally:
            await lock.release()

    # Try-lock pattern (non-blocking)
    lock = DistributedLock(redis, "audit:789:write", blocking=False)
    if await lock.acquire():
        try:
            await write_audit_log()
        finally:
            await lock.release()
    else:
        # Lock already held, skip or queue for later
        await queue_for_retry()
"""

import asyncio
import uuid
import time
from typing import Optional
from redis.asyncio import Redis
import structlog

logger = structlog.get_logger(__name__)


class LockAcquisitionError(Exception):
    """Raised when lock cannot be acquired within timeout."""
    pass


class LockReleaseError(Exception):
    """Raised when lock release fails or lock doesn't exist."""
    pass


class DistributedLock:
    """Distributed lock implementation using Redis with Redlock algorithm.

    This lock is safe for use across multiple service instances and prevents
    race conditions in concurrent operations.

    Attributes:
        redis: Redis client instance
        key: Lock key (will be prefixed with "lock:")
        ttl: Lock time-to-live in seconds (default: 10)
        blocking: Whether to block until lock is acquired (default: True)
        timeout: Maximum time to wait for lock acquisition in seconds (default: 30)
        retry_delay: Initial delay between lock acquisition attempts in seconds
        retry_backoff: Multiplier for exponential backoff (default: 1.5)
        max_retry_delay: Maximum delay between retries in seconds (default: 1.0)
    """

    LOCK_PREFIX = "lock:"

    def __init__(
        self,
        redis: Redis,
        key: str,
        ttl: int = 10,
        blocking: bool = True,
        timeout: float = 30.0,
        retry_delay: float = 0.1,
        retry_backoff: float = 1.5,
        max_retry_delay: float = 1.0,
    ):
        """Initialize distributed lock.

        Args:
            redis: Redis client instance
            key: Lock key (e.g., "project:123:create")
            ttl: Lock TTL in seconds (auto-release after expiry)
            blocking: Block until lock acquired (True) or return immediately (False)
            timeout: Maximum time to wait for lock acquisition (only with blocking=True)
            retry_delay: Initial delay between retry attempts
            retry_backoff: Exponential backoff multiplier
            max_retry_delay: Maximum delay between retries
        """
        self.redis = redis
        self.key = f"{self.LOCK_PREFIX}{key}"
        self.ttl = ttl
        self.blocking = blocking
        self.timeout = timeout
        self.retry_delay = retry_delay
        self.retry_backoff = retry_backoff
        self.max_retry_delay = max_retry_delay

        # Unique token for this lock instance (for safe release)
        self.token: Optional[str] = None
        self._acquired = False

    async def acquire(self) -> bool:
        """Acquire the distributed lock.

        Returns:
            True if lock acquired, False if not (only with blocking=False)

        Raises:
            LockAcquisitionError: If lock cannot be acquired within timeout (with blocking=True)
        """
        # Generate unique token for this lock acquisition
        self.token = str(uuid.uuid4())

        if not self.blocking:
            # Non-blocking: try once and return
            return await self._try_acquire()

        # Blocking: retry until acquired or timeout
        start_time = time.monotonic()
        current_delay = self.retry_delay
        attempt = 0

        while True:
            attempt += 1

            if await self._try_acquire():
                logger.info(
                    "distributed_lock_acquired",
                    key=self.key,
                    ttl=self.ttl,
                    attempt=attempt,
                    elapsed=time.monotonic() - start_time,
                )
                return True

            # Check timeout
            elapsed = time.monotonic() - start_time
            if elapsed >= self.timeout:
                logger.warning(
                    "distributed_lock_acquisition_timeout",
                    key=self.key,
                    timeout=self.timeout,
                    attempts=attempt,
                )
                raise LockAcquisitionError(
                    f"Could not acquire lock '{self.key}' within {self.timeout}s "
                    f"({attempt} attempts)"
                )

            # Wait before retry with exponential backoff
            await asyncio.sleep(min(current_delay, self.max_retry_delay))
            current_delay *= self.retry_backoff

    async def _try_acquire(self) -> bool:
        """Try to acquire lock once using Redis SET NX EX.

        Returns:
            True if acquired, False otherwise
        """
        # SET key value NX EX seconds
        # NX: Only set if key doesn't exist
        # EX: Set expiry in seconds
        result = await self.redis.set(
            self.key,
            self.token,
            nx=True,  # Only set if not exists
            ex=self.ttl,  # Expiry time
        )

        if result:
            self._acquired = True
            return True

        return False

    async def release(self) -> bool:
        """Release the distributed lock safely.

        Only releases if this instance holds the lock (token matches).
        Uses Lua script for atomic check-and-delete operation.

        Returns:
            True if lock released, False if lock not held by this instance

        Raises:
            LockReleaseError: If lock was never acquired
        """
        if not self._acquired or self.token is None:
            raise LockReleaseError(f"Lock '{self.key}' was never acquired")

        # Lua script for atomic check-and-delete
        # Only delete if token matches (ensures we don't delete someone else's lock)
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """

        result = await self.redis.eval(lua_script, 1, self.key, self.token)

        if result == 1:
            self._acquired = False
            logger.info("distributed_lock_released", key=self.key)
            return True
        else:
            # Lock was already released or taken by someone else
            logger.warning(
                "distributed_lock_release_failed",
                key=self.key,
                reason="lock_not_held_or_expired",
            )
            self._acquired = False
            return False

    async def extend(self, additional_ttl: int) -> bool:
        """Extend lock TTL (keep-alive).

        Useful for long-running operations that need to maintain the lock.

        Args:
            additional_ttl: Additional seconds to add to lock TTL

        Returns:
            True if extended, False if lock not held or expired
        """
        if not self._acquired or self.token is None:
            return False

        # Lua script for atomic check-and-extend
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("expire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """

        result = await self.redis.eval(
            lua_script,
            1,
            self.key,
            self.token,
            str(additional_ttl),
        )

        if result == 1:
            logger.debug("distributed_lock_extended", key=self.key, ttl=additional_ttl)
            return True
        else:
            logger.warning("distributed_lock_extend_failed", key=self.key)
            self._acquired = False
            return False

    async def is_locked(self) -> bool:
        """Check if lock is currently held (by any instance).

        Returns:
            True if locked, False otherwise
        """
        return await self.redis.exists(self.key) > 0

    async def get_ttl(self) -> int:
        """Get remaining TTL of lock in seconds.

        Returns:
            Remaining TTL in seconds, -1 if lock doesn't exist, -2 if no TTL set
        """
        return await self.redis.ttl(self.key)

    # Context manager support
    async def __aenter__(self):
        """Acquire lock when entering context."""
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Release lock when exiting context."""
        if self._acquired:
            try:
                await self.release()
            except Exception as e:
                logger.error(
                    "distributed_lock_release_error_in_context",
                    key=self.key,
                    error=str(e),
                )
        return False  # Don't suppress exceptions


class DistributedLockManager:
    """Manager for creating distributed locks with shared Redis connection.

    Provides a convenient interface for creating locks without passing
    Redis connection each time.

    Usage:
        lock_manager = DistributedLockManager(redis)

        async with lock_manager.lock("project:123:create"):
            await create_project()
    """

    def __init__(self, redis: Redis):
        """Initialize lock manager.

        Args:
            redis: Redis client instance
        """
        self.redis = redis

    def lock(
        self,
        key: str,
        ttl: int = 10,
        blocking: bool = True,
        timeout: float = 30.0,
    ) -> DistributedLock:
        """Create a distributed lock.

        Args:
            key: Lock key
            ttl: Lock TTL in seconds
            blocking: Block until acquired
            timeout: Acquisition timeout

        Returns:
            DistributedLock instance
        """
        return DistributedLock(
            redis=self.redis,
            key=key,
            ttl=ttl,
            blocking=blocking,
            timeout=timeout,
        )

    async def is_locked(self, key: str) -> bool:
        """Check if a key is locked.

        Args:
            key: Lock key

        Returns:
            True if locked, False otherwise
        """
        full_key = f"{DistributedLock.LOCK_PREFIX}{key}"
        return await self.redis.exists(full_key) > 0

    async def force_release(self, key: str) -> bool:
        """Force release a lock (admin operation).

        WARNING: Only use for emergency cleanup. This bypasses token validation.

        Args:
            key: Lock key

        Returns:
            True if lock deleted, False if lock didn't exist
        """
        full_key = f"{DistributedLock.LOCK_PREFIX}{key}"
        result = await self.redis.delete(full_key)

        if result > 0:
            logger.warning("distributed_lock_force_released", key=full_key)
            return True
        return False


# Convenience functions for common lock patterns

async def with_lock(
    redis: Redis,
    key: str,
    ttl: int = 10,
    timeout: float = 30.0,
):
    """Decorator for protecting functions with distributed locks.

    Usage:
        @with_lock(redis, "project:create", ttl=30)
        async def create_project(project_id: str):
            # Critical section
            pass
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            lock = DistributedLock(redis, key, ttl=ttl, timeout=timeout)
            async with lock:
                return await func(*args, **kwargs)
        return wrapper
    return decorator
