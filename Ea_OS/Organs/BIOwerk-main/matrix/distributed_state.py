"""Distributed state management using Redis.

This module provides abstractions for managing shared state across multiple
service instances, ensuring consistency and preventing race conditions.

Key Features:
- Atomic operations (increment, decrement, compare-and-swap)
- Hash-based state storage for complex objects
- List operations for queues and stacks
- Set operations for unique collections
- TTL support for automatic expiration
- Pub/Sub for state change notifications

Usage:
    # Simple key-value state
    state = DistributedState(redis, "counter")
    await state.set(0)
    await state.increment()  # Atomic increment
    value = await state.get()  # Returns 1

    # Hash-based state for complex objects
    state = DistributedHashState(redis, "user:123")
    await state.set_fields({
        "name": "John Doe",
        "email": "john@example.com",
        "status": "active"
    })
    user_data = await state.get_all()

    # List-based state for queues
    queue = DistributedListState(redis, "task_queue")
    await queue.push_right(task_id)  # Add to queue
    task_id = await queue.pop_left()  # Get from queue

    # Pub/Sub for state notifications
    pubsub = DistributedPubSub(redis, "cache_invalidation")
    await pubsub.publish({"action": "invalidate", "key": "user:123"})
"""

import json
from typing import Any, Optional, Dict, List, Set as SetType
from redis.asyncio import Redis
import structlog

logger = structlog.get_logger(__name__)


class DistributedState:
    """Simple distributed key-value state with atomic operations.

    Suitable for: counters, flags, simple values that need atomic updates.
    """

    def __init__(self, redis: Redis, key: str, prefix: str = "state:"):
        """Initialize distributed state.

        Args:
            redis: Redis client instance
            key: State key
            prefix: Key prefix (default: "state:")
        """
        self.redis = redis
        self.key = f"{prefix}{key}"

    async def get(self, default: Any = None) -> Optional[Any]:
        """Get state value.

        Args:
            default: Default value if key doesn't exist

        Returns:
            State value or default
        """
        value = await self.redis.get(self.key)
        if value is None:
            return default

        # Try to decode as JSON, fall back to string
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value.decode() if isinstance(value, bytes) else value

    async def set(
        self,
        value: Any,
        ttl: Optional[int] = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """Set state value.

        Args:
            value: Value to set (will be JSON-encoded if not string/bytes)
            ttl: Optional TTL in seconds
            nx: Only set if key doesn't exist
            xx: Only set if key exists

        Returns:
            True if set, False if conditions not met (nx/xx)
        """
        # Encode value
        if isinstance(value, (str, bytes)):
            encoded_value = value
        else:
            encoded_value = json.dumps(value)

        result = await self.redis.set(
            self.key,
            encoded_value,
            ex=ttl,
            nx=nx,
            xx=xx,
        )

        return bool(result)

    async def delete(self) -> bool:
        """Delete state.

        Returns:
            True if deleted, False if didn't exist
        """
        result = await self.redis.delete(self.key)
        return result > 0

    async def exists(self) -> bool:
        """Check if state exists.

        Returns:
            True if exists, False otherwise
        """
        return await self.redis.exists(self.key) > 0

    async def increment(self, amount: int = 1) -> int:
        """Atomically increment integer value.

        Args:
            amount: Amount to increment (default: 1)

        Returns:
            New value after increment
        """
        return await self.redis.incrby(self.key, amount)

    async def decrement(self, amount: int = 1) -> int:
        """Atomically decrement integer value.

        Args:
            amount: Amount to decrement (default: 1)

        Returns:
            New value after decrement
        """
        return await self.redis.decrby(self.key, amount)

    async def increment_float(self, amount: float = 1.0) -> float:
        """Atomically increment float value.

        Args:
            amount: Amount to increment (default: 1.0)

        Returns:
            New value after increment
        """
        return await self.redis.incrbyfloat(self.key, amount)

    async def get_ttl(self) -> int:
        """Get remaining TTL in seconds.

        Returns:
            TTL in seconds, -1 if no TTL, -2 if key doesn't exist
        """
        return await self.redis.ttl(self.key)

    async def set_ttl(self, ttl: int) -> bool:
        """Set TTL on existing key.

        Args:
            ttl: TTL in seconds

        Returns:
            True if TTL set, False if key doesn't exist
        """
        return await self.redis.expire(self.key, ttl)

    async def compare_and_swap(
        self,
        expected: Any,
        new_value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """Atomically update value only if it matches expected value.

        Args:
            expected: Expected current value
            new_value: New value to set
            ttl: Optional TTL for new value

        Returns:
            True if updated, False if current value doesn't match expected
        """
        # Encode values
        if isinstance(expected, (str, bytes)):
            encoded_expected = expected
        else:
            encoded_expected = json.dumps(expected)

        if isinstance(new_value, (str, bytes)):
            encoded_new = new_value
        else:
            encoded_new = json.dumps(new_value)

        # Lua script for atomic compare-and-swap
        lua_script = """
        local current = redis.call("get", KEYS[1])
        if current == ARGV[1] then
            if ARGV[3] then
                redis.call("setex", KEYS[1], ARGV[3], ARGV[2])
            else
                redis.call("set", KEYS[1], ARGV[2])
            end
            return 1
        else
            return 0
        end
        """

        result = await self.redis.eval(
            lua_script,
            1,
            self.key,
            encoded_expected,
            encoded_new,
            str(ttl) if ttl else "",
        )

        return result == 1


class DistributedHashState:
    """Distributed hash-based state for complex objects.

    Suitable for: user sessions, service configurations, multi-field records.
    """

    def __init__(self, redis: Redis, key: str, prefix: str = "hash:"):
        """Initialize distributed hash state.

        Args:
            redis: Redis client instance
            key: State key
            prefix: Key prefix (default: "hash:")
        """
        self.redis = redis
        self.key = f"{prefix}{key}"

    async def get_field(self, field: str, default: Any = None) -> Optional[Any]:
        """Get single field value.

        Args:
            field: Field name
            default: Default value if field doesn't exist

        Returns:
            Field value or default
        """
        value = await self.redis.hget(self.key, field)
        if value is None:
            return default

        # Try to decode as JSON
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value.decode() if isinstance(value, bytes) else value

    async def get_fields(self, *fields: str) -> Dict[str, Any]:
        """Get multiple field values.

        Args:
            fields: Field names

        Returns:
            Dictionary of field:value pairs
        """
        if not fields:
            return {}

        values = await self.redis.hmget(self.key, *fields)
        result = {}

        for field, value in zip(fields, values):
            if value is not None:
                try:
                    result[field] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    result[field] = value.decode() if isinstance(value, bytes) else value

        return result

    async def get_all(self) -> Dict[str, Any]:
        """Get all fields and values.

        Returns:
            Dictionary of all field:value pairs
        """
        data = await self.redis.hgetall(self.key)
        result = {}

        for field, value in data.items():
            field_str = field.decode() if isinstance(field, bytes) else field
            try:
                result[field_str] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                result[field_str] = value.decode() if isinstance(value, bytes) else value

        return result

    async def set_field(
        self,
        field: str,
        value: Any,
        nx: bool = False,
    ) -> bool:
        """Set single field value.

        Args:
            field: Field name
            value: Field value (will be JSON-encoded if not string/bytes)
            nx: Only set if field doesn't exist

        Returns:
            True if set (or field created if nx=True), False if nx condition not met
        """
        # Encode value
        if isinstance(value, (str, bytes)):
            encoded_value = value
        else:
            encoded_value = json.dumps(value)

        if nx:
            result = await self.redis.hsetnx(self.key, field, encoded_value)
            return result == 1
        else:
            await self.redis.hset(self.key, field, encoded_value)
            return True

    async def set_fields(self, mapping: Dict[str, Any]) -> None:
        """Set multiple fields at once.

        Args:
            mapping: Dictionary of field:value pairs
        """
        if not mapping:
            return

        # Encode values
        encoded_mapping = {}
        for field, value in mapping.items():
            if isinstance(value, (str, bytes)):
                encoded_mapping[field] = value
            else:
                encoded_mapping[field] = json.dumps(value)

        await self.redis.hset(self.key, mapping=encoded_mapping)

    async def delete_field(self, *fields: str) -> int:
        """Delete one or more fields.

        Args:
            fields: Field names to delete

        Returns:
            Number of fields deleted
        """
        if not fields:
            return 0
        return await self.redis.hdel(self.key, *fields)

    async def field_exists(self, field: str) -> bool:
        """Check if field exists.

        Args:
            field: Field name

        Returns:
            True if exists, False otherwise
        """
        return await self.redis.hexists(self.key, field)

    async def increment_field(self, field: str, amount: int = 1) -> int:
        """Atomically increment integer field.

        Args:
            field: Field name
            amount: Amount to increment

        Returns:
            New value after increment
        """
        return await self.redis.hincrby(self.key, field, amount)

    async def increment_field_float(self, field: str, amount: float = 1.0) -> float:
        """Atomically increment float field.

        Args:
            field: Field name
            amount: Amount to increment

        Returns:
            New value after increment
        """
        return await self.redis.hincrbyfloat(self.key, field, amount)

    async def get_field_count(self) -> int:
        """Get number of fields in hash.

        Returns:
            Number of fields
        """
        return await self.redis.hlen(self.key)

    async def delete(self) -> bool:
        """Delete entire hash.

        Returns:
            True if deleted, False if didn't exist
        """
        result = await self.redis.delete(self.key)
        return result > 0


class DistributedListState:
    """Distributed list-based state for queues and stacks.

    Suitable for: task queues, event logs, ordered collections.
    """

    def __init__(self, redis: Redis, key: str, prefix: str = "list:"):
        """Initialize distributed list state.

        Args:
            redis: Redis client instance
            key: State key
            prefix: Key prefix (default: "list:")
        """
        self.redis = redis
        self.key = f"{prefix}{key}"

    async def push_left(self, *values: Any) -> int:
        """Push values to the left (head) of list.

        Args:
            values: Values to push

        Returns:
            New length of list
        """
        if not values:
            return await self.length()

        encoded_values = [
            json.dumps(v) if not isinstance(v, (str, bytes)) else v
            for v in values
        ]
        return await self.redis.lpush(self.key, *encoded_values)

    async def push_right(self, *values: Any) -> int:
        """Push values to the right (tail) of list.

        Args:
            values: Values to push

        Returns:
            New length of list
        """
        if not values:
            return await self.length()

        encoded_values = [
            json.dumps(v) if not isinstance(v, (str, bytes)) else v
            for v in values
        ]
        return await self.redis.rpush(self.key, *encoded_values)

    async def pop_left(self, timeout: Optional[float] = None) -> Optional[Any]:
        """Pop value from left (head) of list.

        Args:
            timeout: Optional blocking timeout in seconds

        Returns:
            Popped value or None if list empty (and no timeout)
        """
        if timeout:
            result = await self.redis.blpop(self.key, timeout=timeout)
            if result:
                _, value = result
            else:
                return None
        else:
            value = await self.redis.lpop(self.key)
            if value is None:
                return None

        # Decode value
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value.decode() if isinstance(value, bytes) else value

    async def pop_right(self, timeout: Optional[float] = None) -> Optional[Any]:
        """Pop value from right (tail) of list.

        Args:
            timeout: Optional blocking timeout in seconds

        Returns:
            Popped value or None if list empty (and no timeout)
        """
        if timeout:
            result = await self.redis.brpop(self.key, timeout=timeout)
            if result:
                _, value = result
            else:
                return None
        else:
            value = await self.redis.rpop(self.key)
            if value is None:
                return None

        # Decode value
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value.decode() if isinstance(value, bytes) else value

    async def get_range(self, start: int = 0, end: int = -1) -> List[Any]:
        """Get range of values from list.

        Args:
            start: Start index (0-based, inclusive)
            end: End index (-1 for end of list, inclusive)

        Returns:
            List of values
        """
        values = await self.redis.lrange(self.key, start, end)
        result = []

        for value in values:
            try:
                result.append(json.loads(value))
            except (json.JSONDecodeError, TypeError):
                result.append(value.decode() if isinstance(value, bytes) else value)

        return result

    async def length(self) -> int:
        """Get length of list.

        Returns:
            Number of elements
        """
        return await self.redis.llen(self.key)

    async def trim(self, start: int, end: int) -> None:
        """Trim list to specified range.

        Args:
            start: Start index (inclusive)
            end: End index (inclusive)
        """
        await self.redis.ltrim(self.key, start, end)

    async def delete(self) -> bool:
        """Delete entire list.

        Returns:
            True if deleted, False if didn't exist
        """
        result = await self.redis.delete(self.key)
        return result > 0


class DistributedSetState:
    """Distributed set-based state for unique collections.

    Suitable for: active user sets, unique tags, membership tracking.
    """

    def __init__(self, redis: Redis, key: str, prefix: str = "set:"):
        """Initialize distributed set state.

        Args:
            redis: Redis client instance
            key: State key
            prefix: Key prefix (default: "set:")
        """
        self.redis = redis
        self.key = f"{prefix}{key}"

    async def add(self, *members: Any) -> int:
        """Add members to set.

        Args:
            members: Members to add

        Returns:
            Number of members added (excludes duplicates)
        """
        if not members:
            return 0

        encoded_members = [
            json.dumps(m) if not isinstance(m, (str, bytes)) else m
            for m in members
        ]
        return await self.redis.sadd(self.key, *encoded_members)

    async def remove(self, *members: Any) -> int:
        """Remove members from set.

        Args:
            members: Members to remove

        Returns:
            Number of members removed
        """
        if not members:
            return 0

        encoded_members = [
            json.dumps(m) if not isinstance(m, (str, bytes)) else m
            for m in members
        ]
        return await self.redis.srem(self.key, *encoded_members)

    async def is_member(self, member: Any) -> bool:
        """Check if member is in set.

        Args:
            member: Member to check

        Returns:
            True if member in set, False otherwise
        """
        encoded_member = (
            json.dumps(member) if not isinstance(member, (str, bytes)) else member
        )
        return await self.redis.sismember(self.key, encoded_member)

    async def get_all(self) -> SetType[Any]:
        """Get all members of set.

        Returns:
            Set of all members
        """
        values = await self.redis.smembers(self.key)
        result = set()

        for value in values:
            try:
                result.add(json.loads(value))
            except (json.JSONDecodeError, TypeError):
                result.add(value.decode() if isinstance(value, bytes) else value)

        return result

    async def size(self) -> int:
        """Get number of members in set.

        Returns:
            Set size
        """
        return await self.redis.scard(self.key)

    async def delete(self) -> bool:
        """Delete entire set.

        Returns:
            True if deleted, False if didn't exist
        """
        result = await self.redis.delete(self.key)
        return result > 0


class DistributedPubSub:
    """Distributed pub/sub for state change notifications.

    Suitable for: cache invalidation, cluster-wide events, state synchronization.
    """

    def __init__(self, redis: Redis, channel: str):
        """Initialize distributed pub/sub.

        Args:
            redis: Redis client instance
            channel: Channel name
        """
        self.redis = redis
        self.channel = channel

    async def publish(self, message: Any) -> int:
        """Publish message to channel.

        Args:
            message: Message to publish (will be JSON-encoded)

        Returns:
            Number of subscribers that received the message
        """
        encoded_message = (
            json.dumps(message) if not isinstance(message, (str, bytes)) else message
        )
        return await self.redis.publish(self.channel, encoded_message)

    async def subscribe(self):
        """Subscribe to channel.

        Returns:
            PubSub object for receiving messages

        Usage:
            pubsub = await distributed_pubsub.subscribe()
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    # Handle message
        """
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(self.channel)
        return pubsub


class DistributedStateManager:
    """Manager for creating distributed state objects with shared Redis connection."""

    def __init__(self, redis: Redis):
        """Initialize state manager.

        Args:
            redis: Redis client instance
        """
        self.redis = redis

    def state(self, key: str, prefix: str = "state:") -> DistributedState:
        """Create simple key-value state.

        Args:
            key: State key
            prefix: Key prefix

        Returns:
            DistributedState instance
        """
        return DistributedState(self.redis, key, prefix)

    def hash_state(self, key: str, prefix: str = "hash:") -> DistributedHashState:
        """Create hash-based state.

        Args:
            key: State key
            prefix: Key prefix

        Returns:
            DistributedHashState instance
        """
        return DistributedHashState(self.redis, key, prefix)

    def list_state(self, key: str, prefix: str = "list:") -> DistributedListState:
        """Create list-based state.

        Args:
            key: State key
            prefix: Key prefix

        Returns:
            DistributedListState instance
        """
        return DistributedListState(self.redis, key, prefix)

    def set_state(self, key: str, prefix: str = "set:") -> DistributedSetState:
        """Create set-based state.

        Args:
            key: State key
            prefix: Key prefix

        Returns:
            DistributedSetState instance
        """
        return DistributedSetState(self.redis, key, prefix)

    def pubsub(self, channel: str) -> DistributedPubSub:
        """Create pub/sub for channel.

        Args:
            channel: Channel name

        Returns:
            DistributedPubSub instance
        """
        return DistributedPubSub(self.redis, channel)
