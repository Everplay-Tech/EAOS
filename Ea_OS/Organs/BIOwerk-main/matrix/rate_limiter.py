"""
Enterprise-grade rate limiting with Redis backend.

This module provides:
- Multiple rate limiting strategies (fixed window, sliding window, token bucket)
- Redis-backed distributed rate limiting
- Per-IP and per-user rate limiting
- Configurable burst handling
- Rate limit headers (X-RateLimit-*)
- FastAPI middleware integration
"""
import time
import hashlib
from typing import Optional, Callable, Awaitable
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import redis.asyncio as aioredis
import logging

logger = logging.getLogger(__name__)


class RateLimitExceeded(HTTPException):
    """Exception raised when rate limit is exceeded."""

    def __init__(
        self,
        detail: str = "Rate limit exceeded",
        retry_after: int = 60,
        limit: int = 100,
        window: int = 60,
    ):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(time.time()) + retry_after),
            },
        )


class RateLimiter:
    """
    Enterprise rate limiter with multiple strategies.

    Supports:
    - Fixed window: Simple counter reset at fixed intervals
    - Sliding window: More accurate, considers request timestamps
    - Token bucket: Allows bursts, refills at constant rate
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        requests: int = 100,
        window: int = 60,
        strategy: str = "sliding_window",
        burst: int = 20,
        prefix: str = "ratelimit",
    ):
        """
        Initialize rate limiter.

        Args:
            redis_client: Async Redis client
            requests: Number of requests allowed per window
            window: Time window in seconds
            strategy: Rate limiting strategy ('fixed_window', 'sliding_window', 'token_bucket')
            burst: Burst size for token bucket strategy
            prefix: Redis key prefix
        """
        self.redis = redis_client
        self.requests = requests
        self.window = window
        self.strategy = strategy
        self.burst = burst
        self.prefix = prefix

        # Validate strategy
        valid_strategies = {"fixed_window", "sliding_window", "token_bucket"}
        if strategy not in valid_strategies:
            raise ValueError(
                f"Invalid strategy: {strategy}. Must be one of {valid_strategies}"
            )

        logger.info(
            f"Rate limiter initialized: {requests} requests per {window}s "
            f"using {strategy} strategy"
        )

    def _get_key(self, identifier: str) -> str:
        """Generate Redis key for rate limit tracking."""
        # Hash identifier for privacy and consistent key length
        hashed = hashlib.sha256(identifier.encode()).hexdigest()[:16]
        return f"{self.prefix}:{self.strategy}:{hashed}"

    async def check_rate_limit(self, identifier: str) -> dict:
        """
        Check rate limit for an identifier.

        Args:
            identifier: Unique identifier (IP address, user ID, etc.)

        Returns:
            Dictionary with rate limit status:
            - allowed: Whether request is allowed
            - remaining: Requests remaining in window
            - reset: Unix timestamp when limit resets
            - retry_after: Seconds to wait before retry (if blocked)

        Raises:
            RateLimitExceeded: If rate limit is exceeded
        """
        if self.strategy == "fixed_window":
            return await self._fixed_window(identifier)
        elif self.strategy == "sliding_window":
            return await self._sliding_window(identifier)
        elif self.strategy == "token_bucket":
            return await self._token_bucket(identifier)

    async def _fixed_window(self, identifier: str) -> dict:
        """
        Fixed window rate limiting.

        Simple counter that resets at fixed intervals.
        Pros: Simple, efficient
        Cons: Allows bursts at window boundaries
        """
        key = self._get_key(identifier)
        now = int(time.time())
        window_start = now - (now % self.window)
        window_end = window_start + self.window

        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expireat(key, window_end)
        results = await pipe.execute()

        count = results[0]
        remaining = max(0, self.requests - count)
        allowed = count <= self.requests

        if not allowed:
            retry_after = window_end - now
            raise RateLimitExceeded(
                detail=f"Rate limit exceeded: {self.requests} requests per {self.window}s",
                retry_after=retry_after,
                limit=self.requests,
                window=self.window,
            )

        return {
            "allowed": True,
            "remaining": remaining,
            "reset": window_end,
            "retry_after": 0,
        }

    async def _sliding_window(self, identifier: str) -> dict:
        """
        Sliding window rate limiting using Redis sorted sets.

        Tracks individual request timestamps for accurate rate limiting.
        Pros: Accurate, no boundary bursts
        Cons: More complex, higher memory usage
        """
        key = self._get_key(identifier)
        now = time.time()
        window_start = now - self.window

        pipe = self.redis.pipeline()

        # Remove requests older than window
        pipe.zremrangebyscore(key, 0, window_start)

        # Count requests in current window
        pipe.zcard(key)

        # Add current request timestamp
        pipe.zadd(key, {str(now): now})

        # Set expiration
        pipe.expire(key, self.window + 1)

        results = await pipe.execute()
        count = results[1]  # Count before adding current request

        remaining = max(0, self.requests - count - 1)
        allowed = count < self.requests

        if not allowed:
            # Calculate retry_after based on oldest request in window
            oldest_in_window = await self.redis.zrange(key, 0, 0, withscores=True)
            if oldest_in_window:
                oldest_timestamp = oldest_in_window[0][1]
                retry_after = int(oldest_timestamp + self.window - now) + 1
            else:
                retry_after = self.window

            # Remove the request we just added since it's not allowed
            await self.redis.zrem(key, str(now))

            raise RateLimitExceeded(
                detail=f"Rate limit exceeded: {self.requests} requests per {self.window}s",
                retry_after=retry_after,
                limit=self.requests,
                window=self.window,
            )

        reset_timestamp = int(now + self.window)

        return {
            "allowed": True,
            "remaining": remaining,
            "reset": reset_timestamp,
            "retry_after": 0,
        }

    async def _token_bucket(self, identifier: str) -> dict:
        """
        Token bucket rate limiting.

        Allows bursts up to bucket size, refills at constant rate.
        Pros: Handles bursts gracefully, smooth traffic shaping
        Cons: More complex state management

        Implementation:
        - Bucket capacity = requests (max tokens)
        - Refill rate = requests / window (tokens per second)
        - Burst = additional tokens for burst handling
        """
        key = self._get_key(identifier)
        now = time.time()

        # Lua script for atomic token bucket operation
        lua_script = """
        local key = KEYS[1]
        local capacity = tonumber(ARGV[1])
        local refill_rate = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])
        local window = tonumber(ARGV[4])
        local burst = tonumber(ARGV[5])

        -- Get current bucket state
        local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
        local tokens = tonumber(bucket[1])
        local last_refill = tonumber(bucket[2])

        -- Initialize if doesn't exist
        if not tokens then
            tokens = capacity + burst
            last_refill = now
        end

        -- Calculate tokens to add based on time elapsed
        local elapsed = now - last_refill
        local tokens_to_add = elapsed * refill_rate
        tokens = math.min(capacity + burst, tokens + tokens_to_add)

        -- Try to consume 1 token
        if tokens >= 1 then
            tokens = tokens - 1
            redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
            redis.call('EXPIRE', key, window * 2)
            return {1, math.floor(tokens)}  -- allowed=1, remaining=tokens
        else
            -- Calculate retry_after
            local tokens_needed = 1 - tokens
            local retry_after = math.ceil(tokens_needed / refill_rate)
            return {0, 0, retry_after}  -- allowed=0, remaining=0, retry_after
        end
        """

        refill_rate = self.requests / self.window  # tokens per second

        try:
            result = await self.redis.eval(
                lua_script,
                1,  # number of keys
                key,  # KEYS[1]
                self.requests,  # ARGV[1] - capacity
                refill_rate,  # ARGV[2] - refill rate
                now,  # ARGV[3] - current time
                self.window,  # ARGV[4] - window
                self.burst,  # ARGV[5] - burst size
            )

            allowed = bool(result[0])
            remaining = int(result[1])

            if not allowed:
                retry_after = int(result[2]) if len(result) > 2 else self.window
                raise RateLimitExceeded(
                    detail=f"Rate limit exceeded: {self.requests} requests per {self.window}s (burst: {self.burst})",
                    retry_after=retry_after,
                    limit=self.requests,
                    window=self.window,
                )

            reset_timestamp = int(now + self.window)

            return {
                "allowed": True,
                "remaining": remaining,
                "reset": reset_timestamp,
                "retry_after": 0,
            }

        except Exception as e:
            logger.error(f"Token bucket rate limit error: {e}")
            # Fail open on errors (allow request but log)
            return {
                "allowed": True,
                "remaining": self.requests,
                "reset": int(now + self.window),
                "retry_after": 0,
            }


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for automatic rate limiting.

    Features:
    - Per-IP rate limiting
    - Per-user rate limiting (for authenticated requests)
    - Configurable exclusion paths
    - Rate limit headers in responses
    """

    def __init__(
        self,
        app: ASGIApp,
        redis_client: aioredis.Redis,
        requests: int = 100,
        window: int = 60,
        strategy: str = "sliding_window",
        burst: int = 20,
        per_ip: bool = True,
        per_user: bool = True,
        exclude_paths: Optional[list] = None,
        get_user_id: Optional[Callable[[Request], Awaitable[Optional[str]]]] = None,
    ):
        """
        Initialize rate limit middleware.

        Args:
            app: ASGI application
            redis_client: Async Redis client
            requests: Requests allowed per window
            window: Time window in seconds
            strategy: Rate limiting strategy
            burst: Burst size for token bucket
            per_ip: Enable per-IP rate limiting
            per_user: Enable per-user rate limiting (requires get_user_id)
            exclude_paths: List of paths to exclude from rate limiting
            get_user_id: Async function to extract user ID from request
        """
        super().__init__(app)
        self.limiter = RateLimiter(
            redis_client=redis_client,
            requests=requests,
            window=window,
            strategy=strategy,
            burst=burst,
            prefix="ratelimit:api",
        )
        self.per_ip = per_ip
        self.per_user = per_user
        self.exclude_paths = exclude_paths or []
        self.get_user_id = get_user_id

        logger.info(
            f"Rate limit middleware initialized: "
            f"per_ip={per_ip}, per_user={per_user}, "
            f"exclude_paths={exclude_paths}"
        )

    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting."""
        # Skip rate limiting for excluded paths
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        identifiers = []

        # Per-IP rate limiting
        if self.per_ip:
            # Extract client IP (handles X-Forwarded-For for proxies)
            client_ip = request.client.host
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                client_ip = forwarded.split(",")[0].strip()

            identifiers.append(f"ip:{client_ip}")

        # Per-user rate limiting
        if self.per_user and self.get_user_id:
            try:
                user_id = await self.get_user_id(request)
                if user_id:
                    identifiers.append(f"user:{user_id}")
            except Exception as e:
                logger.warning(f"Failed to extract user ID for rate limiting: {e}")

        # Check rate limits for all identifiers
        for identifier in identifiers:
            try:
                rate_info = await self.limiter.check_rate_limit(identifier)

                # Add rate limit headers to request state for later use
                if not hasattr(request.state, "rate_limit_info"):
                    request.state.rate_limit_info = rate_info

            except RateLimitExceeded as e:
                logger.warning(
                    f"Rate limit exceeded for {identifier}: "
                    f"{request.method} {request.url.path}"
                )

                # Return rate limit error response
                return JSONResponse(
                    status_code=e.status_code,
                    content={"detail": e.detail},
                    headers=e.headers,
                )

        # Process request
        response = await call_next(request)

        # Add rate limit headers to response
        if hasattr(request.state, "rate_limit_info"):
            info = request.state.rate_limit_info
            response.headers["X-RateLimit-Limit"] = str(self.limiter.requests)
            response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
            response.headers["X-RateLimit-Reset"] = str(info["reset"])

        return response


# Utility function for extracting user ID from JWT token
async def get_user_id_from_jwt(request: Request) -> Optional[str]:
    """
    Extract user ID from JWT token in Authorization header.

    This is a helper function for RateLimitMiddleware.
    Customize based on your authentication implementation.

    Args:
        request: FastAPI request

    Returns:
        User ID if authenticated, None otherwise
    """
    try:
        from matrix.auth_dependencies import get_current_user

        # Try to get current user from JWT token
        user = await get_current_user(request)
        return str(user.id) if user else None
    except Exception:
        # Not authenticated or invalid token
        return None
