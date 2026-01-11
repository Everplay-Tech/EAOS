# Database Integration Guide

This document describes the database integration for BIOwerk, including PostgreSQL, MongoDB, and Redis.

## Overview

BIOwerk uses a multi-database architecture:

- **PostgreSQL**: Relational data (users, projects, metadata, audit logs)
- **MongoDB**: Document storage (artifacts: .osteon, .myotab, .synslide files)
- **Redis**: Caching and session management

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      BIOwerk Services                        │
│  (Mesh, Osteon, Myocyte, Synapse, Circadian, Nucleus, etc)  │
└─────────────────────────────────────────────────────────────┘
                         │
           ┌─────────────┼─────────────┐
           │             │             │
           ▼             ▼             ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐
    │PostgreSQL│  │ MongoDB  │  │  Redis   │
    │          │  │          │  │          │
    │ Metadata │  │Artifacts │  │  Cache   │
    └──────────┘  └──────────┘  └──────────┘
```

## Database Schema

### PostgreSQL Tables

#### 1. **users**
Stores user account information.

| Column          | Type      | Description                    |
|-----------------|-----------|--------------------------------|
| id              | UUID      | Primary key                    |
| email           | String    | User email (unique)            |
| username        | String    | Username (unique)              |
| hashed_password | String    | Bcrypt hashed password         |
| auth_provider   | String    | Auth provider (local, oauth2)  |
| is_active       | Boolean   | Account active status          |
| is_admin        | Boolean   | Admin privileges flag          |
| created_at      | Timestamp | Account creation time          |
| updated_at      | Timestamp | Last update time               |

#### 2. **projects**
Organizes artifacts into projects.

| Column       | Type      | Description              |
|--------------|-----------|--------------------------|
| id           | UUID      | Primary key              |
| user_id      | UUID      | Foreign key to users     |
| name         | String    | Project name             |
| description  | Text      | Project description      |
| is_archived  | Boolean   | Archive status           |
| created_at   | Timestamp | Creation time            |
| updated_at   | Timestamp | Last update time         |

#### 3. **artifacts**
Metadata for generated artifacts.

| Column      | Type      | Description                       |
|-------------|-----------|-----------------------------------|
| id          | UUID      | Primary key                       |
| project_id  | UUID      | Foreign key to projects           |
| kind        | String    | Artifact type (osteon/myotab/synslide) |
| title       | String    | Artifact title                    |
| version     | Integer   | Version number                    |
| state_hash  | String    | BLAKE3 hash of content            |
| mongo_id    | String    | MongoDB document ID               |
| metadata    | JSON      | Additional metadata               |
| created_at  | Timestamp | Creation time                     |
| updated_at  | Timestamp | Last update time                  |

#### 4. **executions**
Audit log of all agent requests/responses.

| Column        | Type      | Description                   |
|---------------|-----------|-------------------------------|
| id            | UUID      | Primary key (matches msg.id)  |
| user_id       | UUID      | Foreign key to users          |
| agent         | String    | Agent name                    |
| endpoint      | String    | Endpoint name                 |
| origin        | String    | Request origin                |
| target        | String    | Target agent                  |
| request_data  | JSON      | Full Msg object               |
| response_data | JSON      | Full Reply object             |
| ok            | Boolean   | Success flag                  |
| state_hash    | String    | Response state hash           |
| duration_ms   | Float     | Processing duration           |
| error_message | Text      | Error details (if failed)     |
| created_at    | Timestamp | Execution time                |

#### 5. **api_keys**
API keys for service-to-service authentication.

| Column       | Type      | Description                    |
|--------------|-----------|--------------------------------|
| id           | UUID      | Primary key                    |
| user_id      | UUID      | Foreign key to users           |
| key_hash     | String    | Hashed API key                 |
| name         | String    | Friendly name                  |
| scopes       | JSON      | Allowed scopes/permissions     |
| is_active    | Boolean   | Active status                  |
| last_used_at | Timestamp | Last usage time                |
| expires_at   | Timestamp | Expiration time                |
| created_at   | Timestamp | Creation time                  |

### MongoDB Collections

#### 1. **artifacts**
Full artifact content storage.

```json
{
  "_id": ObjectId("..."),
  "kind": "osteon",
  "meta": {
    "title": "Document Title",
    "version": "1.0",
    "created": "2025-01-15T10:30:00Z"
  },
  "body": {
    "sections": [
      {"id": "s1", "title": "Introduction", "text": "..."}
    ],
    "toc": ["Introduction", "..."],
    "citations": []
  },
  "_created_at": ISODate("2025-01-15T10:30:00Z"),
  "_updated_at": ISODate("2025-01-15T10:30:00Z")
}
```

#### 2. **execution_logs** (optional)
Detailed execution logs for large payloads.

```json
{
  "_id": ObjectId("..."),
  "execution_id": "uuid-from-postgres",
  "agent": "osteon",
  "full_request": {...},
  "full_response": {...},
  "_created_at": ISODate("2025-01-15T10:30:00Z")
}
```

### Redis Keys

Redis is used for caching with the following patterns:

| Pattern               | Description                  | TTL     |
|-----------------------|------------------------------|---------|
| `user:<id>`           | User data cache              | 5 min   |
| `artifact:<id>`       | Artifact metadata cache      | 5 min   |
| `project:<id>`        | Project data cache           | 5 min   |
| `execution:<id>`      | Execution result cache       | 1 hour  |
| `rate_limit:<key>`    | Rate limiting counters       | 1 min   |

## Getting Started

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and update with your configuration:

```bash
cp .env.example .env
```

### 3. Start Database Services

```bash
docker compose up -d postgres mongodb redis
```

Wait for services to be healthy:

```bash
docker compose ps
```

### 4. Run Database Migrations

Initialize the PostgreSQL schema:

```bash
# Create initial migration (already done)
# alembic revision --autogenerate -m "Initial schema"

# Apply migrations
alembic upgrade head
```

### 5. Start Application Services

```bash
docker compose up --build
```

## Usage Examples

### PostgreSQL with SQLAlchemy

```python
from matrix.database import get_postgres_session
from matrix.db_models import User, Project, Artifact
from sqlalchemy import select

# In FastAPI endpoint
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

@app.post("/users")
async def create_user(
    email: str,
    username: str,
    db: AsyncSession = Depends(get_postgres_session)
):
    # Create user
    user = User(
        email=email,
        username=username,
        auth_provider="local"
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return {"id": user.id, "email": user.email}

@app.get("/users/{user_id}")
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_postgres_session)
):
    # Query user
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404)

    return {"id": user.id, "email": user.email}
```

### MongoDB with Motor

```python
from matrix.mongo_repository import ArtifactRepository

# Create repository instance
artifact_repo = ArtifactRepository()

# Save artifact
artifact_data = {
    "kind": "osteon",
    "meta": {"title": "My Document"},
    "body": {"sections": [...]}
}
mongo_id = await artifact_repo.create_artifact(artifact_data)

# Retrieve artifact
artifact = await artifact_repo.get_artifact(mongo_id)

# Search artifacts
artifacts = await artifact_repo.list_artifacts_by_kind("osteon", limit=10)
```

### Redis Caching

```python
from matrix.cache import cache, cached

# Manual caching
await cache.set("my_key", {"data": "value"}, ttl=300)
value = await cache.get("my_key")

# Decorator-based caching
@cached("user", ttl=600)
async def get_user_expensive(user_id: str):
    # This result will be cached for 10 minutes
    return await fetch_user_from_db(user_id)

# Use it
user = await get_user_expensive("user-123")  # First call: hits DB
user = await get_user_expensive("user-123")  # Second call: from cache
```

## Database Migrations with Alembic

### Create a New Migration

```bash
alembic revision --autogenerate -m "Add new column to users table"
```

### Apply Migrations

```bash
# Upgrade to latest
alembic upgrade head

# Upgrade to specific revision
alembic upgrade <revision_id>

# Downgrade one revision
alembic downgrade -1

# Show current revision
alembic current

# Show migration history
alembic history
```

### Manual Migration Example

```bash
# Create empty migration
alembic revision -m "Add custom index"
```

Edit the generated file in `alembic/versions/`:

```python
def upgrade():
    op.create_index('idx_custom', 'table_name', ['column1', 'column2'])

def downgrade():
    op.drop_index('idx_custom', 'table_name')
```

## Configuration

### PostgreSQL

**Connection String:**
```
postgresql+asyncpg://user:password@host:port/database
```

**Pool Settings:**
- `pool_size`: 10
- `max_overflow`: 20
- `pool_pre_ping`: True (validates connections)

### MongoDB

**Connection String:**
```
mongodb://user:password@host:port/database?authSource=admin
```

**Pool Settings:**
- `maxPoolSize`: 50
- `minPoolSize`: 10

### Redis

**Connection String:**
```
redis://host:port/db
redis://:password@host:port/db  # With password
```

**Pool Settings:**
- `max_connections`: 50
- `decode_responses`: True

## Best Practices

### 1. Always Use Async Sessions

```python
# Good
async with get_postgres_session() as session:
    user = await session.execute(select(User))

# Bad (blocking)
session = Session()  # Don't use sync sessions
```

### 2. Use Transactions

```python
async with db.begin():
    # Multiple operations in a transaction
    db.add(user)
    db.add(project)
    # Auto-commits if no exception
```

### 3. Handle Exceptions

```python
try:
    await db.commit()
except IntegrityError:
    await db.rollback()
    raise HTTPException(status_code=400, detail="Duplicate entry")
```

### 4. Use Indexes

```python
# Define indexes in models
class User(Base):
    __table_args__ = (
        Index('idx_email', 'email'),
        Index('idx_created', 'created_at'),
    )
```

### 5. Cache Expensive Queries

```python
@cached("expensive_query", ttl=3600)
async def get_dashboard_stats():
    # Expensive aggregation query
    return stats
```

## Monitoring

### Database Health Checks

```bash
# PostgreSQL
docker exec biowerk-postgres pg_isready -U biowerk

# MongoDB
docker exec biowerk-mongodb mongosh --eval "db.adminCommand('ping')"

# Redis
docker exec biowerk-redis redis-cli ping
```

### Check Connections

```python
# In your service
from matrix.database import get_postgres_engine, get_mongo_client, get_redis_client

# PostgreSQL
engine = get_postgres_engine()
async with engine.connect() as conn:
    result = await conn.execute("SELECT 1")

# MongoDB
client = get_mongo_client()
await client.admin.command('ping')

# Redis
redis = get_redis_client()
await redis.ping()
```

### View Logs

```bash
# PostgreSQL logs
docker logs biowerk-postgres

# MongoDB logs
docker logs biowerk-mongodb

# Redis logs
docker logs biowerk-redis
```

## Backup and Recovery

### PostgreSQL Backup

```bash
# Backup
docker exec biowerk-postgres pg_dump -U biowerk biowerk > backup.sql

# Restore
docker exec -i biowerk-postgres psql -U biowerk biowerk < backup.sql
```

### MongoDB Backup

```bash
# Backup
docker exec biowerk-mongodb mongodump --db biowerk --out /tmp/backup

# Restore
docker exec biowerk-mongodb mongorestore --db biowerk /tmp/backup/biowerk
```

### Redis Backup

```bash
# Trigger save
docker exec biowerk-redis redis-cli BGSAVE

# Copy RDB file
docker cp biowerk-redis:/data/dump.rdb ./backup/
```

## Troubleshooting

### Connection Refused

**Problem:** Services can't connect to databases

**Solution:**
1. Check if databases are running: `docker compose ps`
2. Check if health checks pass: `docker compose ps`
3. Verify environment variables in docker-compose.yml
4. Check network connectivity: `docker network inspect biowerk_default`

### Migration Errors

**Problem:** Alembic migrations fail

**Solution:**
1. Check current revision: `alembic current`
2. View migration history: `alembic history`
3. Check database connection: verify POSTGRES_HOST and credentials
4. Manual fix if needed: Connect to PostgreSQL and fix schema manually

### Performance Issues

**Problem:** Slow queries

**Solution:**
1. Enable query logging: Set `LOG_LEVEL=DEBUG`
2. Add database indexes for frequently queried columns
3. Use Redis caching for expensive queries
4. Optimize N+1 queries with `selectinload()` or `joinedload()`

### Cache Not Working

**Problem:** Redis cache misses

**Solution:**
1. Check if Redis is running: `docker exec biowerk-redis redis-cli ping`
2. Verify `CACHE_ENABLED=true` in environment
3. Check cache keys: `docker exec biowerk-redis redis-cli KEYS "*"`
4. Monitor cache hits: `docker exec biowerk-redis redis-cli INFO stats`

## Production Considerations

### Security

- [ ] Use strong passwords (not dev_password)
- [ ] Enable SSL/TLS for all connections
- [ ] Restrict network access with firewalls
- [ ] Regular security updates for database images
- [ ] Encrypt data at rest
- [ ] Use secrets manager (Vault, AWS Secrets Manager)

### Performance

- [ ] Tune PostgreSQL connection pool sizes
- [ ] Add appropriate indexes
- [ ] Enable query caching in Redis
- [ ] Monitor slow queries
- [ ] Set up read replicas for PostgreSQL
- [ ] Use connection pooling (PgBouncer)

### High Availability

- [ ] PostgreSQL replication (primary-replica)
- [ ] MongoDB replica set
- [ ] Redis Sentinel or Cluster
- [ ] Regular backups (automated)
- [ ] Disaster recovery plan
- [ ] Load balancing

### Monitoring

- [ ] Database metrics (CPU, memory, disk)
- [ ] Query performance monitoring
- [ ] Connection pool monitoring
- [ ] Cache hit rate monitoring
- [ ] Set up alerts for anomalies
- [ ] Log aggregation and analysis

## Resources

- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [MongoDB Documentation](https://docs.mongodb.com/)
- [Redis Documentation](https://redis.io/documentation)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [Motor (async MongoDB) Documentation](https://motor.readthedocs.io/)
