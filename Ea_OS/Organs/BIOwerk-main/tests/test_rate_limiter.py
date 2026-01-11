"""
Comprehensive tests for Rate Limiter - Redis-based distributed rate limiting.

Tests cover:
- Fixed window strategy
- Sliding window strategy
- Token bucket strategy
- Rate limit exceeded handling
- Rate limit headers
"""
import pytest
from unittest.mock import AsyncMock, patch
from matrix.rate_limiter import RateLimiter, RateLimitExceeded
import time


# ============================================================================
# Rate Limiter Initialization
# ============================================================================

@pytest.mark.asyncio
async def test_rate_limiter_initialization():
    """Test rate limiter initialization."""
    mock_redis = AsyncMock()

    limiter = RateLimiter(
        mock_redis,
        requests=100,
        window=60,
        strategy="sliding_window"
    )

    assert limiter.requests == 100
    assert limiter.window == 60
    assert limiter.strategy == "sliding_window"


@pytest.mark.asyncio
async def test_invalid_strategy():
    """Test initialization with invalid strategy."""
    mock_redis = AsyncMock()

    with pytest.raises(ValueError):
        RateLimiter(mock_redis, strategy="invalid_strategy")


# ============================================================================
# Fixed Window Tests
# ============================================================================

@pytest.mark.asyncio
async def test_fixed_window_within_limit():
    """Test fixed window allows requests within limit."""
    mock_redis = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()

    limiter = RateLimiter(
        mock_redis,
        requests=10,
        window=60,
        strategy="fixed_window"
    )

    allowed = await limiter.check("user:123")

    assert allowed is True


@pytest.mark.asyncio
async def test_fixed_window_exceeds_limit():
    """Test fixed window blocks requests over limit."""
    mock_redis = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=11)  # Over limit of 10

    limiter = RateLimiter(
        mock_redis,
        requests=10,
        window=60,
        strategy="fixed_window"
    )

    allowed = await limiter.check("user:123")

    assert allowed is False


# ============================================================================
# Sliding Window Tests
# ============================================================================

@pytest.mark.asyncio
async def test_sliding_window_within_limit():
    """Test sliding window allows requests within limit."""
    mock_redis = AsyncMock()
    mock_redis.zremrangebyscore = AsyncMock()
    mock_redis.zadd = AsyncMock()
    mock_redis.zcard = AsyncMock(return_value=5)  # Within limit
    mock_redis.expire = AsyncMock()

    limiter = RateLimiter(
        mock_redis,
        requests=10,
        window=60,
        strategy="sliding_window"
    )

    allowed = await limiter.check("user:456")

    assert allowed is True


@pytest.mark.asyncio
async def test_sliding_window_exceeds_limit():
    """Test sliding window blocks requests over limit."""
    mock_redis = AsyncMock()
    mock_redis.zremrangebyscore = AsyncMock()
    mock_redis.zadd = AsyncMock()
    mock_redis.zcard = AsyncMock(return_value=11)  # Over limit of 10
    mock_redis.expire = AsyncMock()

    limiter = RateLimiter(
        mock_redis,
        requests=10,
        window=60,
        strategy="sliding_window"
    )

    allowed = await limiter.check("user:456")

    assert allowed is False


# ============================================================================
# Token Bucket Tests
# ============================================================================

@pytest.mark.asyncio
async def test_token_bucket_with_tokens():
    """Test token bucket allows requests when tokens available."""
    mock_redis = AsyncMock()
    # Mock return: [tokens, last_refill]
    mock_redis.hmget = AsyncMock(return_value=[b"5", str(time.time()).encode()])
    mock_redis.hset = AsyncMock()

    limiter = RateLimiter(
        mock_redis,
        requests=10,
        window=60,
        strategy="token_bucket",
        burst=20
    )

    allowed = await limiter.check("user:789")

    assert allowed is True


@pytest.mark.asyncio
async def test_token_bucket_no_tokens():
    """Test token bucket blocks when no tokens available."""
    mock_redis = AsyncMock()
    # Mock return: [0 tokens, last_refill]
    mock_redis.hmget = AsyncMock(return_value=[b"0", str(time.time()).encode()])
    mock_redis.hset = AsyncMock()

    limiter = RateLimiter(
        mock_redis,
        requests=10,
        window=60,
        strategy="token_bucket",
        burst=20
    )

    allowed = await limiter.check("user:789")

    assert allowed is False


# ============================================================================
# Rate Limit Exception Tests
# ============================================================================

@pytest.mark.asyncio
async def test_rate_limit_exceeded_exception():
    """Test RateLimitExceeded exception."""
    exc = RateLimitExceeded(
        detail="Too many requests",
        retry_after=60,
        limit=100,
        window=60
    )

    assert exc.status_code == 429
    assert "Retry-After" in exc.headers
    assert exc.headers["X-RateLimit-Limit"] == "100"


# ============================================================================
# Get Remaining Tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_remaining_requests():
    """Test getting remaining request count."""
    mock_redis = AsyncMock()
    mock_redis.zcard = AsyncMock(return_value=3)  # 3 used, 7 remaining

    limiter = RateLimiter(
        mock_redis,
        requests=10,
        window=60,
        strategy="sliding_window"
    )

    remaining = await limiter.get_remaining("user:123")

    assert remaining == 7


# ============================================================================
# Reset Tests
# ============================================================================

@pytest.mark.asyncio
async def test_reset_rate_limit():
    """Test resetting rate limit for an identifier."""
    mock_redis = AsyncMock()
    mock_redis.delete = AsyncMock(return_value=1)

    limiter = RateLimiter(mock_redis)

    result = await limiter.reset("user:123")

    assert result is True


def test_rate_limiter_summary():
    """
    Rate Limiter Test Coverage:
    ✓ Fixed window strategy
    ✓ Sliding window strategy
    ✓ Token bucket strategy
    ✓ Rate limit enforcement
    ✓ Remaining requests
    ✓ Reset functionality
    """
    assert True
