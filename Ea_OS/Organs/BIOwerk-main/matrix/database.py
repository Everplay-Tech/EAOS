"""Database connection management for PostgreSQL, MongoDB, and Redis."""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from motor.motor_asyncio import AsyncIOMotorClient
from redis.asyncio import Redis
from typing import AsyncGenerator, Optional
import logging

from .config import settings

logger = logging.getLogger(__name__)

# SQLAlchemy Base for ORM models
Base = declarative_base()

# Global database connections
_pg_engine = None
_pg_session_maker = None
_mongo_client = None
_mongo_db = None
_redis_client = None


# ============================================================================
# PostgreSQL Connection Management
# ============================================================================

def get_postgres_engine():
    """
    Get or create PostgreSQL async engine.

    Connection pooling is optimized based on whether PgBouncer is in use:
    - With PgBouncer (port 6432): Small application pools (5 + 5 overflow)
      PgBouncer handles the actual connection pooling to PostgreSQL
    - Direct PostgreSQL (port 5432): Larger application pools (10 + 20 overflow)
      Each service manages its own connection pool

    Using smaller pools with PgBouncer prevents over-subscription and
    allows PgBouncer to efficiently multiplex connections.

    HORIZONTAL SCALING CONSIDERATIONS:

    When running multiple replicas of a service, each replica creates its own
    connection pool. Total connection usage calculation:

    Example with 3 mesh instances and PgBouncer:
    - Per instance pool: 5 + 5 overflow = 10 max connections
    - 3 instances × 10 connections = 30 total connections to PgBouncer
    - PgBouncer pool (default 100) handles these efficiently

    Example with 3 mesh instances without PgBouncer:
    - Per instance pool: 10 + 20 overflow = 30 max connections
    - 3 instances × 30 connections = 90 total connections to PostgreSQL
    - PostgreSQL max_connections should be configured accordingly (e.g., 200+)

    **IMPORTANT**: When scaling horizontally:
    1. Always use PgBouncer in production to prevent connection exhaustion
    2. Configure PgBouncer pool size based on: (replicas × pool_size) + buffer
    3. Monitor connection usage with pg_stat_activity
    4. Set appropriate pool_size based on workload characteristics

    For services that scale to 10+ replicas:
    - Reduce pool_size to 3 + 3 overflow (6 max per instance)
    - This gives 60 connections for 10 instances (well within PgBouncer limits)
    - PgBouncer efficiently multiplexes to PostgreSQL backend pool
    """
    global _pg_engine
    if _pg_engine is None:
        # Detect if using PgBouncer based on port
        is_using_pgbouncer = settings.postgres_port == 6432 or settings.postgres_host == "pgbouncer"

        if is_using_pgbouncer:
            # Smaller pools when using PgBouncer
            # PgBouncer handles connection pooling, so we don't need large app pools
            pool_size = 5
            max_overflow = 5
            logger.info("Using PgBouncer - configuring small application connection pool")
        else:
            # Larger pools for direct PostgreSQL connection
            pool_size = 10
            max_overflow = 20
            logger.info("Direct PostgreSQL connection - using standard connection pool")

        _pg_engine = create_async_engine(
            settings.postgres_url,
            echo=settings.log_level == "DEBUG",
            pool_pre_ping=True,
            pool_size=pool_size,
            max_overflow=max_overflow,
            # Pool recycle time - close connections after 1 hour
            # Prevents stale connections and works well with PgBouncer
            pool_recycle=3600,
            # Timeout for getting connection from pool
            pool_timeout=30,
        )
        logger.info(
            f"PostgreSQL engine created: {settings.postgres_host}:{settings.postgres_port} "
            f"(pool_size={pool_size}, max_overflow={max_overflow})"
        )
    return _pg_engine


def get_postgres_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get or create PostgreSQL session maker."""
    global _pg_session_maker
    if _pg_session_maker is None:
        engine = get_postgres_engine()
        _pg_session_maker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _pg_session_maker


async def get_postgres_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI to get PostgreSQL session.

    Usage:
        @app.post("/endpoint")
        async def endpoint(db: AsyncSession = Depends(get_postgres_session)):
            # Use db session here
    """
    session_maker = get_postgres_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_postgres():
    """Close PostgreSQL connections."""
    global _pg_engine, _pg_session_maker
    if _pg_engine:
        await _pg_engine.dispose()
        _pg_engine = None
        _pg_session_maker = None
        logger.info("PostgreSQL connections closed")


# ============================================================================
# MongoDB Connection Management
# ============================================================================

def get_mongo_client() -> AsyncIOMotorClient:
    """Get or create MongoDB client."""
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = AsyncIOMotorClient(
            settings.mongo_url,
            maxPoolSize=50,
            minPoolSize=10,
        )
        logger.info(f"MongoDB client created: {settings.mongo_host}:{settings.mongo_port}")
    return _mongo_client


def get_mongo_db():
    """Get MongoDB database instance."""
    global _mongo_db
    if _mongo_db is None:
        client = get_mongo_client()
        _mongo_db = client[settings.mongo_db]
    return _mongo_db


async def close_mongo():
    """Close MongoDB connections."""
    global _mongo_client, _mongo_db
    if _mongo_client:
        _mongo_client.close()
        _mongo_client = None
        _mongo_db = None
        logger.info("MongoDB connections closed")


# ============================================================================
# Redis Connection Management
# ============================================================================

def get_redis_client() -> Redis:
    """Get or create Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=50,
        )
        logger.info(f"Redis client created: {settings.redis_host}:{settings.redis_port}")
    return _redis_client


async def close_redis():
    """Close Redis connections."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
        logger.info("Redis connections closed")


# ============================================================================
# Session Management
# ============================================================================

def get_session_manager(session_type: str = "default"):
    """
    Get a configured session manager for storing session state in Redis.

    Args:
        session_type: Type of session ("short", "default", "long", "workflow")

    Returns:
        RedisSessionManager instance configured for the specified session type

    Usage:
        session_mgr = get_session_manager("workflow")
        await session_mgr.set("msg_123", {"outline": ["Intro", "Body", "Conclusion"]})
        data = await session_mgr.get("msg_123")
    """
    from .sessions import RedisSessionManager

    redis = get_redis_client()

    ttl_map = {
        "short": settings.session_ttl_short,
        "default": settings.session_ttl_default,
        "long": settings.session_ttl_long,
        "workflow": settings.session_ttl_workflow,
    }

    prefix_map = {
        "short": f"{settings.session_prefix}:short",
        "default": settings.session_prefix,
        "long": f"{settings.session_prefix}:long",
        "workflow": f"{settings.session_prefix}:workflow",
    }

    ttl = ttl_map.get(session_type, settings.session_ttl_default)
    prefix = prefix_map.get(session_type, settings.session_prefix)

    return RedisSessionManager(
        redis_client=redis,
        prefix=prefix,
        default_ttl=ttl
    )


# ============================================================================
# Application Lifecycle Management
# ============================================================================

async def init_databases():
    """Initialize all database connections."""
    logger.info("Initializing database connections...")
    get_postgres_engine()
    get_mongo_client()
    get_redis_client()
    logger.info("All database connections initialized")


async def close_databases():
    """Close all database connections."""
    logger.info("Closing database connections...")
    await close_postgres()
    await close_mongo()
    await close_redis()
    logger.info("All database connections closed")


async def create_tables():
    """Create all PostgreSQL tables."""
    engine = get_postgres_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("PostgreSQL tables created")
