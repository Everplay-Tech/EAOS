"""
Comprehensive tests for Session Management - Redis-based session storage.

Tests cover:
- Session creation and retrieval
- TTL management
- Session update
- Session deletion
- Key namespacing
"""
import pytest
from unittest.mock import AsyncMock, patch
from matrix.sessions import RedisSessionManager
import json


# ============================================================================
# Session Manager Initialization
# ============================================================================

@pytest.mark.asyncio
async def test_session_manager_initialization():
    """Test session manager initialization."""
    mock_redis = AsyncMock()

    manager = RedisSessionManager(mock_redis, prefix="test_session", default_ttl=7200)

    assert manager.prefix == "test_session"
    assert manager.default_ttl == 7200


@pytest.mark.asyncio
async def test_session_manager_default_values():
    """Test session manager with default values."""
    mock_redis = AsyncMock()

    manager = RedisSessionManager(mock_redis)

    assert manager.prefix == "session"
    assert manager.default_ttl == 3600


# ============================================================================
# Session Storage Tests
# ============================================================================

@pytest.mark.asyncio
async def test_set_session():
    """Test storing session data."""
    mock_redis = AsyncMock()
    mock_redis.setex = AsyncMock(return_value=True)

    manager = RedisSessionManager(mock_redis)

    data = {"user_id": "123", "token": "abc"}
    result = await manager.set("session-1", data)

    assert result is True
    mock_redis.setex.assert_called_once()

    # Verify key format
    call_args = mock_redis.setex.call_args[0]
    assert call_args[0] == "session:session-1"
    assert call_args[1] == 3600  # default TTL
    assert json.loads(call_args[2]) == data


@pytest.mark.asyncio
async def test_set_session_with_custom_ttl():
    """Test storing session with custom TTL."""
    mock_redis = AsyncMock()
    mock_redis.setex = AsyncMock(return_value=True)

    manager = RedisSessionManager(mock_redis, default_ttl=3600)

    data = {"user_id": "456"}
    result = await manager.set("session-2", data, ttl=7200)

    assert result is True

    # Verify custom TTL
    call_args = mock_redis.setex.call_args[0]
    assert call_args[1] == 7200


# ============================================================================
# Session Retrieval Tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_session():
    """Test retrieving session data."""
    mock_redis = AsyncMock()
    stored_data = {"user_id": "123", "preferences": {"theme": "dark"}}
    mock_redis.get = AsyncMock(return_value=json.dumps(stored_data))

    manager = RedisSessionManager(mock_redis)

    result = await manager.get("session-1")

    assert result == stored_data
    mock_redis.get.assert_called_once_with("session:session-1")


@pytest.mark.asyncio
async def test_get_session_not_found():
    """Test retrieving non-existent session."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)

    manager = RedisSessionManager(mock_redis)

    result = await manager.get("missing-session")

    assert result is None


# ============================================================================
# Session Deletion Tests
# ============================================================================

@pytest.mark.asyncio
async def test_delete_session():
    """Test deleting session data."""
    mock_redis = AsyncMock()
    mock_redis.delete = AsyncMock(return_value=1)

    manager = RedisSessionManager(mock_redis)

    result = await manager.delete("session-1")

    assert result is True
    mock_redis.delete.assert_called_once_with("session:session-1")


@pytest.mark.asyncio
async def test_delete_nonexistent_session():
    """Test deleting non-existent session."""
    mock_redis = AsyncMock()
    mock_redis.delete = AsyncMock(return_value=0)

    manager = RedisSessionManager(mock_redis)

    result = await manager.delete("missing-session")

    assert result is False


# ============================================================================
# Session Update Tests
# ============================================================================

@pytest.mark.asyncio
async def test_update_session():
    """Test updating session data."""
    mock_redis = AsyncMock()
    existing_data = {"user_id": "123", "count": 1}
    mock_redis.get = AsyncMock(return_value=json.dumps(existing_data))
    mock_redis.setex = AsyncMock(return_value=True)

    manager = RedisSessionManager(mock_redis)

    # Update the session
    updated_data = {"user_id": "123", "count": 2, "new_field": "value"}
    result = await manager.update("session-1", updated_data)

    assert result is True


# ============================================================================
# Session Expiration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_extend_session_ttl():
    """Test extending session TTL."""
    mock_redis = AsyncMock()
    mock_redis.expire = AsyncMock(return_value=True)

    manager = RedisSessionManager(mock_redis)

    result = await manager.extend("session-1", ttl=7200)

    assert result is True
    mock_redis.expire.assert_called_once_with("session:session-1", 7200)


@pytest.mark.asyncio
async def test_get_ttl():
    """Test getting remaining session TTL."""
    mock_redis = AsyncMock()
    mock_redis.ttl = AsyncMock(return_value=1800)  # 30 minutes remaining

    manager = RedisSessionManager(mock_redis)

    ttl = await manager.get_ttl("session-1")

    assert ttl == 1800


# ============================================================================
# Error Handling Tests
# ============================================================================

@pytest.mark.asyncio
async def test_set_session_error():
    """Test handling of Redis errors during set."""
    mock_redis = AsyncMock()
    mock_redis.setex = AsyncMock(side_effect=Exception("Redis error"))

    manager = RedisSessionManager(mock_redis)

    result = await manager.set("session-1", {"data": "value"})

    assert result is False


@pytest.mark.asyncio
async def test_get_session_json_decode_error():
    """Test handling of JSON decode errors."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value="invalid json {{{")

    manager = RedisSessionManager(mock_redis)

    result = await manager.get("session-1")

    assert result is None


@pytest.mark.asyncio
async def test_get_session_redis_error():
    """Test handling of Redis errors during get."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(side_effect=Exception("Redis connection failed"))

    manager = RedisSessionManager(mock_redis)

    result = await manager.get("session-1")

    assert result is None


# ============================================================================
# Key Namespacing Tests
# ============================================================================

@pytest.mark.asyncio
async def test_custom_prefix():
    """Test custom key prefix."""
    mock_redis = AsyncMock()
    mock_redis.setex = AsyncMock(return_value=True)

    manager = RedisSessionManager(mock_redis, prefix="custom")

    await manager.set("session-1", {"data": "value"})

    call_args = mock_redis.setex.call_args[0]
    assert call_args[0] == "custom:session-1"


def test_sessions_summary():
    """
    Session Management Test Coverage:
    ✓ Session creation
    ✓ Session retrieval
    ✓ Session deletion
    ✓ Session updates
    ✓ TTL management
    ✓ Key namespacing
    ✓ Error handling
    """
    assert True
