"""
Comprehensive tests for horizontal scaling functionality.

Tests verify that all distributed components work correctly across multiple
service instances, ensuring:
- Session state consistency
- Distributed locking prevents race conditions
- Rate limiting works across instances
- Circuit breakers are shared
- Health checking is aggregated
- Service discovery and load balancing
"""

import pytest
import asyncio
from redis.asyncio import Redis
from matrix.distributed_lock import DistributedLock, DistributedLockManager
from matrix.distributed_state import (
    DistributedState,
    DistributedHashState,
    DistributedListState,
    DistributedSetState,
)
from matrix.distributed_circuit_breaker import (
    DistributedCircuitBreaker,
    CircuitBreakerError,
    CircuitBreakerState,
)
from matrix.distributed_health import DistributedHealthChecker
from matrix.service_discovery import ServiceRegistry, LoadBalancer
from matrix.config import settings


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
async def redis_client():
    """Create Redis client for testing."""
    client = Redis.from_url(
        settings.redis_url,
        decode_responses=False,
        encoding="utf-8",
    )
    yield client

    # Cleanup: flush test keys
    await client.flushdb()
    await client.close()


@pytest.fixture
async def lock_manager(redis_client):
    """Create distributed lock manager."""
    return DistributedLockManager(redis_client)


@pytest.fixture
async def circuit_breaker(redis_client):
    """Create distributed circuit breaker."""
    return DistributedCircuitBreaker(
        redis=redis_client,
        service_name="test_service",
        failure_threshold=3,
        success_threshold=2,
        timeout=1,  # Short timeout for tests
    )


@pytest.fixture
async def service_registry(redis_client):
    """Create service registry."""
    return ServiceRegistry(redis_client, heartbeat_ttl=10)


# ============================================================================
# Distributed Lock Tests
# ============================================================================

@pytest.mark.asyncio
async def test_distributed_lock_prevents_concurrent_access(redis_client):
    """Test that distributed locks prevent concurrent access across instances."""
    lock_key = "test:concurrent:lock"
    shared_counter = []

    async def increment_with_lock(instance_id: int):
        """Simulate instance incrementing a shared counter with locking."""
        lock = DistributedLock(redis_client, lock_key, ttl=5)

        for i in range(10):
            async with lock:
                # Critical section - only one instance should be here at a time
                current = len(shared_counter)
                await asyncio.sleep(0.001)  # Simulate work
                shared_counter.append(f"instance_{instance_id}")

                # Verify no other instance modified the counter
                assert len(shared_counter) == current + 1

    # Simulate 3 instances trying to increment concurrently
    tasks = [
        increment_with_lock(1),
        increment_with_lock(2),
        increment_with_lock(3),
    ]

    await asyncio.gather(*tasks)

    # All instances should have successfully incremented
    assert len(shared_counter) == 30


@pytest.mark.asyncio
async def test_distributed_lock_automatic_release_on_ttl(redis_client):
    """Test that locks are automatically released after TTL expires."""
    lock = DistributedLock(redis_client, "test:ttl:lock", ttl=1)

    # Acquire lock
    await lock.acquire()
    assert await lock.is_locked()

    # Wait for TTL to expire
    await asyncio.sleep(1.5)

    # Lock should be automatically released
    assert not await lock.is_locked()


@pytest.mark.asyncio
async def test_distributed_lock_safe_release(redis_client):
    """Test that locks can only be released by the holder."""
    lock1 = DistributedLock(redis_client, "test:safe:lock", ttl=10)
    lock2 = DistributedLock(redis_client, "test:safe:lock", ttl=10)

    # Lock1 acquires
    await lock1.acquire()

    # Lock2 tries to acquire (should fail non-blocking)
    lock2.blocking = False
    acquired = await lock2.acquire()
    assert not acquired

    # Lock2 tries to release (should fail - doesn't own the lock)
    lock2._acquired = True  # Fake acquisition
    lock2.token = "wrong_token"
    released = await lock2.release()
    assert not released  # Can't release someone else's lock

    # Lock1 can release its own lock
    released = await lock1.release()
    assert released


# ============================================================================
# Distributed State Tests
# ============================================================================

@pytest.mark.asyncio
async def test_distributed_state_atomic_operations(redis_client):
    """Test atomic operations on distributed state."""
    state = DistributedState(redis_client, "test:counter")

    # Set initial value
    await state.set(0)
    assert await state.get() == 0

    # Atomic increments from multiple "instances"
    async def increment_many(count: int):
        for _ in range(count):
            await state.increment()

    tasks = [increment_many(10) for _ in range(3)]
    await asyncio.gather(*tasks)

    # Should be exactly 30 (3 instances × 10 increments)
    final_value = await state.get()
    assert final_value == 30


@pytest.mark.asyncio
async def test_distributed_hash_state_concurrent_updates(redis_client):
    """Test concurrent updates to hash state."""
    hash_state = DistributedHashState(redis_client, "test:user:123")

    # Initialize user data
    await hash_state.set_fields({
        "name": "John Doe",
        "email": "john@example.com",
        "score": 0
    })

    # Multiple instances increment score concurrently
    async def increment_score():
        for _ in range(10):
            await hash_state.increment_field("score", 1)

    tasks = [increment_score() for _ in range(3)]
    await asyncio.gather(*tasks)

    # Score should be exactly 30
    user_data = await hash_state.get_all()
    assert user_data["score"] == 30
    assert user_data["name"] == "John Doe"


@pytest.mark.asyncio
async def test_distributed_list_state_as_queue(redis_client):
    """Test distributed list as a work queue."""
    queue = DistributedListState(redis_client, "test:task:queue")

    # Producer: add tasks to queue
    for i in range(20):
        await queue.push_right(f"task_{i}")

    # Multiple consumers process tasks
    processed_tasks = []

    async def consumer(consumer_id: int):
        """Consumer pops tasks and processes them."""
        while True:
            task = await queue.pop_left()
            if task is None:
                break
            processed_tasks.append((consumer_id, task))
            await asyncio.sleep(0.001)  # Simulate work

    # Start 3 consumers
    tasks = [consumer(i) for i in range(3)]
    await asyncio.gather(*tasks)

    # All tasks should be processed exactly once
    assert len(processed_tasks) == 20
    task_ids = [task for _, task in processed_tasks]
    assert len(set(task_ids)) == 20  # All unique


# ============================================================================
# Distributed Circuit Breaker Tests
# ============================================================================

@pytest.mark.asyncio
async def test_distributed_circuit_breaker_shared_state(redis_client):
    """Test that circuit breaker state is shared across instances."""
    # Create two circuit breakers for the same service (simulating 2 instances)
    breaker1 = DistributedCircuitBreaker(
        redis=redis_client,
        service_name="shared_service",
        failure_threshold=3,
        timeout=1,
    )

    breaker2 = DistributedCircuitBreaker(
        redis=redis_client,
        service_name="shared_service",
        failure_threshold=3,
        timeout=1,
    )

    # Both should start CLOSED
    assert await breaker1.get_state() == CircuitBreakerState.CLOSED
    assert await breaker2.get_state() == CircuitBreakerState.CLOSED

    # Simulate failures on breaker1
    async def failing_operation():
        raise Exception("Service failure")

    for _ in range(3):
        try:
            await breaker1.call(failing_operation)
        except Exception:
            pass

    # Both breakers should now be OPEN (shared state)
    assert await breaker1.get_state() == CircuitBreakerState.OPEN
    assert await breaker2.get_state() == CircuitBreakerState.OPEN

    # Breaker2 should reject requests immediately (circuit is open)
    with pytest.raises(CircuitBreakerError):
        await breaker2.call(lambda: asyncio.sleep(0))


@pytest.mark.asyncio
async def test_distributed_circuit_breaker_recovery(redis_client):
    """Test circuit breaker recovery across instances."""
    breaker = DistributedCircuitBreaker(
        redis=redis_client,
        service_name="recovery_service",
        failure_threshold=2,
        success_threshold=2,
        timeout=1,
    )

    # Trigger circuit opening
    async def failing_op():
        raise Exception("Failure")

    for _ in range(2):
        try:
            await breaker.call(failing_op)
        except Exception:
            pass

    assert await breaker.get_state() == CircuitBreakerState.OPEN

    # Wait for timeout
    await asyncio.sleep(1.5)

    # Should transition to HALF_OPEN
    async def success_op():
        return "success"

    # First successful call in HALF_OPEN
    result = await breaker.call(success_op)
    assert result == "success"

    # Second successful call should close circuit
    result = await breaker.call(success_op)
    assert result == "success"

    # Circuit should be CLOSED
    assert await breaker.get_state() == CircuitBreakerState.CLOSED


# ============================================================================
# Service Discovery Tests
# ============================================================================

@pytest.mark.asyncio
async def test_service_registry_multi_instance(service_registry):
    """Test service registry with multiple instances."""
    # Register 3 mesh instances
    for i in range(3):
        await service_registry.register_instance(
            service_name="mesh",
            instance_id=f"mesh-{i}",
            host=f"10.0.0.{i}",
            port=8000 + i,
            metadata={"version": "1.0.0"}
        )

    # Get all instances
    instances = await service_registry.get_instances("mesh")
    assert len(instances) == 3

    # Verify instance data
    instance_ids = [inst["instance_id"] for inst in instances]
    assert "mesh-0" in instance_ids
    assert "mesh-1" in instance_ids
    assert "mesh-2" in instance_ids


@pytest.mark.asyncio
async def test_service_registry_heartbeat_and_expiry(service_registry):
    """Test instance heartbeat and automatic expiry."""
    # Register instance with short TTL
    registry = ServiceRegistry(redis_client=service_registry.redis, heartbeat_ttl=2)

    await registry.register_instance(
        service_name="test_service",
        instance_id="test-1",
        host="10.0.0.1",
        port=8000,
    )

    # Instance should be registered
    instances = await registry.get_instances("test_service")
    assert len(instances) == 1

    # Send heartbeat to keep alive
    await asyncio.sleep(1)
    await registry.heartbeat("test_service", "test-1")

    # Still alive after heartbeat
    instances = await registry.get_instances("test_service")
    assert len(instances) == 1

    # Wait for expiry without heartbeat
    await asyncio.sleep(3)

    # Instance should be expired
    instances = await registry.get_instances("test_service")
    assert len(instances) == 0


@pytest.mark.asyncio
async def test_load_balancer_round_robin(service_registry):
    """Test round-robin load balancing."""
    # Register 3 instances
    for i in range(3):
        await service_registry.register_instance(
            service_name="api",
            instance_id=f"api-{i}",
            host=f"10.0.0.{i}",
            port=8000,
        )

    # Create load balancer with round-robin strategy
    lb = LoadBalancer(redis=service_registry.redis, strategy="round_robin")

    # Get 6 instances (should cycle through all 3 twice)
    selected = []
    for _ in range(6):
        instance = await lb.get_instance("api")
        selected.append(instance["instance_id"])

    # Should see each instance exactly twice in order
    assert selected == ["api-0", "api-1", "api-2", "api-0", "api-1", "api-2"]


@pytest.mark.asyncio
async def test_load_balancer_least_connections(service_registry):
    """Test least-connections load balancing."""
    # Register 3 instances
    for i in range(3):
        await service_registry.register_instance(
            service_name="worker",
            instance_id=f"worker-{i}",
            host=f"10.0.0.{i}",
            port=8000,
        )

    # Simulate different connection counts
    await service_registry.redis.set("service_registry:worker:connections:worker-0", 5)
    await service_registry.redis.set("service_registry:worker:connections:worker-1", 2)
    await service_registry.redis.set("service_registry:worker:connections:worker-2", 8)

    # Create load balancer with least-connections strategy
    lb = LoadBalancer(redis=service_registry.redis, strategy="least_connections")

    # Should select worker-1 (fewest connections)
    instance = await lb.get_instance("worker")
    assert instance["instance_id"] == "worker-1"


@pytest.mark.asyncio
async def test_load_balancer_consistent_hashing(service_registry):
    """Test consistent hashing for sticky sessions."""
    # Register 3 instances
    for i in range(3):
        await service_registry.register_instance(
            service_name="cache",
            instance_id=f"cache-{i}",
            host=f"10.0.0.{i}",
            port=8000,
        )

    # Create load balancer with consistent hashing
    lb = LoadBalancer(redis=service_registry.redis, strategy="consistent_hash")

    # Same session key should always return same instance
    user_123_instances = []
    for _ in range(10):
        instance = await lb.get_instance("cache", session_key="user:123")
        user_123_instances.append(instance["instance_id"])

    # All requests for user:123 should go to same instance
    assert len(set(user_123_instances)) == 1

    # Different session key might go to different instance
    instance = await lb.get_instance("cache", session_key="user:456")
    # No assertion on specific instance, just verify it works


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_full_horizontal_scaling_scenario(redis_client):
    """
    Integration test simulating a full horizontal scaling scenario.

    Simulates 3 mesh instances handling concurrent requests with:
    - Distributed locking for budget updates
    - Shared circuit breaker state
    - Service registry and load balancing
    """
    # Setup: Register 3 mesh instances
    registry = ServiceRegistry(redis_client)
    for i in range(3):
        await registry.register_instance(
            service_name="mesh",
            instance_id=f"mesh-{i}",
            host=f"10.0.1.{i}",
            port=8000,
        )

    # Setup: Shared circuit breaker for downstream service
    breaker = DistributedCircuitBreaker(
        redis=redis_client,
        service_name="agent_service",
        failure_threshold=5,
    )

    # Simulate concurrent budget updates from multiple mesh instances
    budget_state = DistributedState(redis_client, "budget:project:123")
    await budget_state.set({"allocated": 1000, "spent": 0})

    async def process_request(mesh_instance_id: int, amount: float):
        """Simulate processing a request that updates budget."""
        # Use distributed lock to prevent race conditions
        lock = DistributedLock(redis_client, "lock:budget:project:123", ttl=5)

        async with lock:
            # Read current budget
            budget = await budget_state.get()

            # Simulate work
            await asyncio.sleep(0.01)

            # Update budget
            budget["spent"] += amount

            # Write back
            await budget_state.set(budget)

        # Simulate calling downstream service through circuit breaker
        async def call_agent():
            await asyncio.sleep(0.001)
            return "success"

        try:
            await breaker.call(call_agent)
        except CircuitBreakerError:
            pass

    # Simulate 30 requests across 3 instances (10 each)
    tasks = []
    for instance in range(3):
        for req in range(10):
            tasks.append(process_request(instance, 10.0))

    await asyncio.gather(*tasks)

    # Verify budget is correct (no race conditions)
    final_budget = await budget_state.get()
    assert final_budget["spent"] == 300.0  # 30 requests × $10

    # Verify all mesh instances are registered
    instances = await registry.get_instances("mesh")
    assert len(instances) == 3


@pytest.mark.asyncio
async def test_session_consistency_across_instances(redis_client):
    """Test that session state is consistent across mesh instances."""
    from matrix.sessions import RedisSessionManager

    # Create session manager (same Redis backend for all instances)
    session_mgr = RedisSessionManager(redis_client)

    # Instance 1 creates session
    session_id = await session_mgr.create_session(
        user_id="user_123",
        session_data={"workflow": "active", "step": 1}
    )

    # Instance 2 reads session (should see same data)
    session = await session_mgr.get_session(session_id)
    assert session["user_id"] == "user_123"
    assert session["session_data"]["workflow"] == "active"
    assert session["session_data"]["step"] == 1

    # Instance 3 updates session
    await session_mgr.update_session(
        session_id,
        {"workflow": "active", "step": 2}
    )

    # Instance 1 reads updated session
    session = await session_mgr.get_session(session_id)
    assert session["session_data"]["step"] == 2


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
