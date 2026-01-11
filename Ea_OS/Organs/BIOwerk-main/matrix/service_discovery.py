"""Service discovery and load balancing for horizontal scaling.

This module provides service discovery and load balancing capabilities for
distributed deployments with multiple service replicas. It supports:

- Service instance registration and heartbeats
- Automatic instance deregistration on failure
- Multiple load balancing algorithms (round-robin, least-connections, consistent hashing)
- Sticky sessions with consistent hashing
- Health-aware routing
- Service instance metadata

Key Features:
- Redis-backed service registry
- Automatic instance health tracking with TTL
- Round-robin load balancing
- Least-connections load balancing
- Consistent hashing for sticky sessions
- Integration with distributed health checking

Usage:
    # Service instance registration
    registry = ServiceRegistry(redis)
    await registry.register_instance(
        service_name="mesh",
        instance_id="mesh-1",
        host="10.0.1.1",
        port=8000,
        metadata={"version": "1.0.0"}
    )

    # Keep instance alive with heartbeats
    await registry.heartbeat("mesh", "mesh-1")

    # Load balancing
    balancer = LoadBalancer(redis, strategy="round_robin")
    instance = await balancer.get_instance("mesh")
    # Returns: {"instance_id": "mesh-1", "host": "10.0.1.1", "port": 8000}

    # Sticky sessions with consistent hashing
    balancer = LoadBalancer(redis, strategy="consistent_hash")
    instance = await balancer.get_instance("mesh", session_key="user:123")
    # Always returns same instance for same session_key
"""

import time
import hashlib
import bisect
from typing import Optional, Dict, Any, List, Literal
from redis.asyncio import Redis
from prometheus_client import Counter, Gauge
import structlog

logger = structlog.get_logger(__name__)


# Prometheus metrics
service_instances = Gauge(
    'service_instances_total',
    'Total number of registered service instances',
    ['service']
)

service_instance_registrations = Counter(
    'service_instance_registrations_total',
    'Total number of service instance registrations',
    ['service']
)

service_instance_deregistrations = Counter(
    'service_instance_deregistrations_total',
    'Total number of service instance deregistrations',
    ['service', 'reason']
)

load_balancer_requests = Counter(
    'load_balancer_requests_total',
    'Total number of load balancer requests',
    ['service', 'strategy']
)


class ServiceRegistry:
    """Service registry for tracking service instances across the cluster.

    Uses Redis to maintain a registry of all service instances, their locations,
    and metadata. Instances must send periodic heartbeats to remain registered.

    Attributes:
        redis: Redis client instance
        heartbeat_ttl: TTL for instance registration in seconds (default: 30)
    """

    KEY_PREFIX = "service_registry:"

    def __init__(self, redis: Redis, heartbeat_ttl: int = 30):
        """Initialize service registry.

        Args:
            redis: Redis client instance
            heartbeat_ttl: Instance registration TTL in seconds
        """
        self.redis = redis
        self.heartbeat_ttl = heartbeat_ttl

    def _get_service_key(self, service_name: str) -> str:
        """Get Redis key for service instances."""
        return f"{self.KEY_PREFIX}{service_name}:instances"

    def _get_instance_key(self, service_name: str, instance_id: str) -> str:
        """Get Redis key for instance data."""
        return f"{self.KEY_PREFIX}{service_name}:instance:{instance_id}"

    def _get_connections_key(self, service_name: str, instance_id: str) -> str:
        """Get Redis key for instance connection count."""
        return f"{self.KEY_PREFIX}{service_name}:connections:{instance_id}"

    async def register_instance(
        self,
        service_name: str,
        instance_id: str,
        host: str,
        port: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register a service instance.

        Args:
            service_name: Service name (e.g., "mesh", "agent")
            instance_id: Unique instance identifier (e.g., "mesh-1", "mesh-pod-abc123")
            host: Instance host/IP address
            port: Instance port
            metadata: Optional metadata (version, region, etc.)
        """
        instance_key = self._get_instance_key(service_name, instance_id)
        service_key = self._get_service_key(service_name)

        # Store instance data
        instance_data = {
            "instance_id": instance_id,
            "host": host,
            "port": port,
            "registered_at": int(time.time()),
            "last_heartbeat": int(time.time()),
        }

        if metadata:
            instance_data["metadata"] = metadata

        # Use Redis hash to store instance data with TTL
        pipeline = self.redis.pipeline()
        pipeline.hset(instance_key, mapping=instance_data)
        pipeline.expire(instance_key, self.heartbeat_ttl)

        # Add instance to service set with score (timestamp)
        pipeline.zadd(service_key, {instance_id: time.time()})
        pipeline.expire(service_key, self.heartbeat_ttl * 2)

        # Initialize connection count
        connections_key = self._get_connections_key(service_name, instance_id)
        pipeline.set(connections_key, 0, ex=self.heartbeat_ttl)

        await pipeline.execute()

        # Update metrics
        service_instance_registrations.labels(service=service_name).inc()
        await self._update_instance_count(service_name)

        logger.info(
            "service_instance_registered",
            service=service_name,
            instance_id=instance_id,
            host=host,
            port=port,
        )

    async def heartbeat(self, service_name: str, instance_id: str) -> bool:
        """Send heartbeat to keep instance registered.

        Args:
            service_name: Service name
            instance_id: Instance identifier

        Returns:
            True if heartbeat successful, False if instance not registered
        """
        instance_key = self._get_instance_key(service_name, instance_id)
        service_key = self._get_service_key(service_name)
        connections_key = self._get_connections_key(service_name, instance_id)

        # Update heartbeat timestamp and refresh TTL
        pipeline = self.redis.pipeline()
        pipeline.hset(instance_key, "last_heartbeat", int(time.time()))
        pipeline.expire(instance_key, self.heartbeat_ttl)
        pipeline.zadd(service_key, {instance_id: time.time()})
        pipeline.expire(service_key, self.heartbeat_ttl * 2)
        pipeline.expire(connections_key, self.heartbeat_ttl)

        results = await pipeline.execute()

        # Check if instance exists (hset returns 0 if field updated, not created)
        exists = await self.redis.exists(instance_key) > 0

        if exists:
            logger.debug(
                "service_instance_heartbeat",
                service=service_name,
                instance_id=instance_id,
            )
            return True
        else:
            logger.warning(
                "service_instance_heartbeat_failed_not_registered",
                service=service_name,
                instance_id=instance_id,
            )
            return False

    async def deregister_instance(
        self,
        service_name: str,
        instance_id: str,
        reason: str = "manual",
    ) -> None:
        """Deregister a service instance.

        Args:
            service_name: Service name
            instance_id: Instance identifier
            reason: Deregistration reason (manual, timeout, health_check)
        """
        instance_key = self._get_instance_key(service_name, instance_id)
        service_key = self._get_service_key(service_name)
        connections_key = self._get_connections_key(service_name, instance_id)

        # Remove instance data
        pipeline = self.redis.pipeline()
        pipeline.delete(instance_key)
        pipeline.zrem(service_key, instance_id)
        pipeline.delete(connections_key)
        await pipeline.execute()

        # Update metrics
        service_instance_deregistrations.labels(
            service=service_name,
            reason=reason
        ).inc()
        await self._update_instance_count(service_name)

        logger.info(
            "service_instance_deregistered",
            service=service_name,
            instance_id=instance_id,
            reason=reason,
        )

    async def get_instances(self, service_name: str) -> List[Dict[str, Any]]:
        """Get all registered instances for a service.

        Args:
            service_name: Service name

        Returns:
            List of instance dictionaries
        """
        service_key = self._get_service_key(service_name)

        # Get all instance IDs
        instance_ids = await self.redis.zrange(service_key, 0, -1)

        if not instance_ids:
            return []

        # Get instance data for all instances
        instances = []
        for instance_id in instance_ids:
            instance_id_str = instance_id.decode() if isinstance(instance_id, bytes) else instance_id
            instance_key = self._get_instance_key(service_name, instance_id_str)
            instance_data = await self.redis.hgetall(instance_key)

            if instance_data:
                # Decode instance data
                decoded_data = {}
                for key, value in instance_data.items():
                    key_str = key.decode() if isinstance(key, bytes) else key
                    value_str = value.decode() if isinstance(value, bytes) else value
                    decoded_data[key_str] = value_str

                instances.append(decoded_data)

        return instances

    async def get_instance(
        self,
        service_name: str,
        instance_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get data for a specific instance.

        Args:
            service_name: Service name
            instance_id: Instance identifier

        Returns:
            Instance data dictionary or None if not found
        """
        instance_key = self._get_instance_key(service_name, instance_id)
        instance_data = await self.redis.hgetall(instance_key)

        if not instance_data:
            return None

        # Decode instance data
        decoded_data = {}
        for key, value in instance_data.items():
            key_str = key.decode() if isinstance(key, bytes) else key
            value_str = value.decode() if isinstance(value, bytes) else value
            decoded_data[key_str] = value_str

        return decoded_data

    async def increment_connections(self, service_name: str, instance_id: str) -> int:
        """Increment connection count for an instance.

        Args:
            service_name: Service name
            instance_id: Instance identifier

        Returns:
            New connection count
        """
        connections_key = self._get_connections_key(service_name, instance_id)
        return await self.redis.incr(connections_key)

    async def decrement_connections(self, service_name: str, instance_id: str) -> int:
        """Decrement connection count for an instance.

        Args:
            service_name: Service name
            instance_id: Instance identifier

        Returns:
            New connection count
        """
        connections_key = self._get_connections_key(service_name, instance_id)
        return await self.redis.decr(connections_key)

    async def get_connections(self, service_name: str, instance_id: str) -> int:
        """Get current connection count for an instance.

        Args:
            service_name: Service name
            instance_id: Instance identifier

        Returns:
            Current connection count
        """
        connections_key = self._get_connections_key(service_name, instance_id)
        count = await self.redis.get(connections_key)
        return int(count) if count else 0

    async def _update_instance_count(self, service_name: str) -> None:
        """Update Prometheus metric for instance count."""
        instances = await self.get_instances(service_name)
        service_instances.labels(service=service_name).set(len(instances))


LoadBalancingStrategy = Literal["round_robin", "least_connections", "consistent_hash"]


class LoadBalancer:
    """Load balancer for distributing requests across service instances.

    Supports multiple load balancing strategies:
    - round_robin: Distribute requests evenly in rotation
    - least_connections: Send to instance with fewest active connections
    - consistent_hash: Sticky sessions using consistent hashing

    Attributes:
        redis: Redis client instance
        strategy: Load balancing strategy
        registry: Service registry instance
    """

    def __init__(
        self,
        redis: Redis,
        strategy: LoadBalancingStrategy = "round_robin",
    ):
        """Initialize load balancer.

        Args:
            redis: Redis client instance
            strategy: Load balancing strategy
        """
        self.redis = redis
        self.strategy = strategy
        self.registry = ServiceRegistry(redis)

        # For round-robin
        self._round_robin_counters: Dict[str, int] = {}

        # For consistent hashing
        self._hash_rings: Dict[str, 'ConsistentHashRing'] = {}

        logger.info(
            "load_balancer_initialized",
            strategy=strategy,
        )

    async def get_instance(
        self,
        service_name: str,
        session_key: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get a service instance using the configured load balancing strategy.

        Args:
            service_name: Service name
            session_key: Optional session key for sticky sessions (consistent_hash strategy)

        Returns:
            Instance data dictionary or None if no instances available
        """
        instances = await self.registry.get_instances(service_name)

        if not instances:
            logger.warning(
                "load_balancer_no_instances",
                service=service_name,
            )
            return None

        load_balancer_requests.labels(
            service=service_name,
            strategy=self.strategy
        ).inc()

        if self.strategy == "round_robin":
            return await self._round_robin(service_name, instances)

        elif self.strategy == "least_connections":
            return await self._least_connections(service_name, instances)

        elif self.strategy == "consistent_hash":
            if not session_key:
                logger.warning(
                    "load_balancer_consistent_hash_no_session_key",
                    service=service_name,
                )
                # Fall back to round-robin
                return await self._round_robin(service_name, instances)

            return await self._consistent_hash(service_name, instances, session_key)

        else:
            logger.error(
                "load_balancer_unknown_strategy",
                strategy=self.strategy,
            )
            return instances[0]

    async def _round_robin(
        self,
        service_name: str,
        instances: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Round-robin load balancing.

        Args:
            service_name: Service name
            instances: List of available instances

        Returns:
            Selected instance
        """
        if service_name not in self._round_robin_counters:
            self._round_robin_counters[service_name] = 0

        index = self._round_robin_counters[service_name] % len(instances)
        self._round_robin_counters[service_name] += 1

        return instances[index]

    async def _least_connections(
        self,
        service_name: str,
        instances: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Least-connections load balancing.

        Args:
            service_name: Service name
            instances: List of available instances

        Returns:
            Instance with fewest connections
        """
        min_connections = float('inf')
        selected_instance = instances[0]

        for instance in instances:
            instance_id = instance["instance_id"]
            connections = await self.registry.get_connections(service_name, instance_id)

            if connections < min_connections:
                min_connections = connections
                selected_instance = instance

        return selected_instance

    async def _consistent_hash(
        self,
        service_name: str,
        instances: List[Dict[str, Any]],
        session_key: str,
    ) -> Dict[str, Any]:
        """Consistent hashing for sticky sessions.

        Args:
            service_name: Service name
            instances: List of available instances
            session_key: Session key (e.g., user ID, session ID)

        Returns:
            Consistently selected instance for this session
        """
        # Build or update hash ring for this service
        if service_name not in self._hash_rings:
            self._hash_rings[service_name] = ConsistentHashRing()

        ring = self._hash_rings[service_name]

        # Update ring with current instances
        instance_ids = [inst["instance_id"] for inst in instances]
        ring.update_nodes(instance_ids)

        # Get node for session
        selected_id = ring.get_node(session_key)

        # Find instance data for selected ID
        for instance in instances:
            if instance["instance_id"] == selected_id:
                return instance

        # Fallback (shouldn't happen)
        return instances[0]


class ConsistentHashRing:
    """Consistent hashing ring for sticky session routing.

    Implements consistent hashing with virtual nodes to ensure even
    distribution when instances are added or removed.
    """

    def __init__(self, virtual_nodes: int = 150):
        """Initialize consistent hash ring.

        Args:
            virtual_nodes: Number of virtual nodes per physical node
        """
        self.virtual_nodes = virtual_nodes
        self.ring: List[int] = []
        self.ring_map: Dict[int, str] = {}
        self.nodes: set[str] = set()

    def _hash(self, key: str) -> int:
        """Hash a key to a position on the ring."""
        return int(hashlib.md5(key.encode()).hexdigest(), 16)

    def add_node(self, node_id: str) -> None:
        """Add a node to the ring.

        Args:
            node_id: Node identifier
        """
        if node_id in self.nodes:
            return

        self.nodes.add(node_id)

        # Add virtual nodes
        for i in range(self.virtual_nodes):
            virtual_key = f"{node_id}:{i}"
            hash_value = self._hash(virtual_key)

            # Insert in sorted position
            bisect.insort(self.ring, hash_value)
            self.ring_map[hash_value] = node_id

    def remove_node(self, node_id: str) -> None:
        """Remove a node from the ring.

        Args:
            node_id: Node identifier
        """
        if node_id not in self.nodes:
            return

        self.nodes.remove(node_id)

        # Remove virtual nodes
        for i in range(self.virtual_nodes):
            virtual_key = f"{node_id}:{i}"
            hash_value = self._hash(virtual_key)

            if hash_value in self.ring_map:
                self.ring.remove(hash_value)
                del self.ring_map[hash_value]

    def update_nodes(self, node_ids: List[str]) -> None:
        """Update ring to match current node set.

        Args:
            node_ids: List of current node identifiers
        """
        current_nodes = set(node_ids)

        # Remove nodes no longer present
        for node_id in list(self.nodes):
            if node_id not in current_nodes:
                self.remove_node(node_id)

        # Add new nodes
        for node_id in current_nodes:
            if node_id not in self.nodes:
                self.add_node(node_id)

    def get_node(self, key: str) -> Optional[str]:
        """Get node for a given key.

        Args:
            key: Key to hash (e.g., session ID)

        Returns:
            Node identifier or None if ring is empty
        """
        if not self.ring:
            return None

        hash_value = self._hash(key)

        # Find next node in ring (clockwise)
        index = bisect.bisect(self.ring, hash_value)

        if index == len(self.ring):
            # Wrap around to first node
            index = 0

        return self.ring_map[self.ring[index]]
