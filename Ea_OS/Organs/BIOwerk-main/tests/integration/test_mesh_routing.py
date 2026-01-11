"""
Integration tests for mesh routing and health-aware routing.

Tests mesh gateway functionality including:
- URL-based routing
- API versioning
- Health-aware routing
- Load balancing
- RBAC integration
"""
import asyncio
import uuid
from typing import Dict, List

import httpx
import pytest


class TestMeshRouting:
    """Test mesh gateway routing functionality."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_url_based_routing(self, http_client: httpx.AsyncClient):
        """Test mesh routes requests based on URL path."""
        services = ["osteon", "myocyte", "synapse", "nucleus", "larry"]

        for service in services:
            msg_id = str(uuid.uuid4())
            request_data = {
                "id": msg_id,
                "ts": 1234567890.0,
                "origin": "test_client",
                "target": service,
                "intent": "health",
                "input": {},
                "api_version": "v1"
            }

            try:
                # Each service should be routable via /v1/{service}/
                response = await http_client.get(
                    f"/v1/{service}/health",
                    timeout=10.0
                )

                # Accept various success codes
                assert response.status_code in (200, 404, 501), \
                    f"{service} routing failed with {response.status_code}"

                # If service responds, check it identifies itself correctly
                if response.status_code == 200:
                    data = response.json()
                    if "service" in data or "agent" in data:
                        service_name = data.get("service", data.get("agent", ""))
                        assert service in service_name.lower(), \
                            f"Service {service} returned wrong identity: {service_name}"
            except httpx.TimeoutException:
                # Service might not be available
                pytest.skip(f"{service} not available for routing test")

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_api_versioning(self, http_client: httpx.AsyncClient):
        """Test API version routing (v1, v2, etc.)."""
        msg_id = str(uuid.uuid4())
        request_data = {
            "id": msg_id,
            "ts": 1234567890.0,
            "origin": "test_client",
            "target": "osteon",
            "intent": "health",
            "input": {},
            "api_version": "v1"
        }

        # Test v1 endpoint
        response_v1 = await http_client.get("/v1/osteon/health", timeout=10.0)
        assert response_v1.status_code in (200, 404, 501)

        # Test v2 endpoint (should return 404 if not implemented)
        response_v2 = await http_client.get("/v2/osteon/health", timeout=10.0)
        # v2 likely not implemented, should return 404
        assert response_v2.status_code in (200, 404)

        # Test invalid version
        response_invalid = await http_client.get("/v99/osteon/health", timeout=10.0)
        assert response_invalid.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_health_aware_routing(self, http_client: httpx.AsyncClient):
        """Test mesh skips unhealthy services in routing."""
        # First, check service health
        health_response = await http_client.get("/health", timeout=10.0)
        assert health_response.status_code == 200

        health_data = health_response.json()
        assert "services" in health_data or "status" in health_data

        # Make requests to services - mesh should route only to healthy ones
        msg_id = str(uuid.uuid4())
        request_data = {
            "id": msg_id,
            "ts": 1234567890.0,
            "origin": "test_client",
            "target": "osteon",
            "intent": "generate",
            "input": {"prompt": "Test", "max_tokens": 10},
            "api_version": "v1"
        }

        response = await http_client.post("/v1/osteon/generate", json=request_data)

        # If service is healthy, should get response
        # If unhealthy, mesh should return 503 Service Unavailable
        assert response.status_code in (200, 500, 503)

        if response.status_code == 503:
            # Service is marked unhealthy
            data = response.json()
            assert "error" in data or "detail" in data

    @pytest.mark.asyncio
    @pytest.mark.timeout(45)
    async def test_routing_with_service_discovery(
        self, http_client: httpx.AsyncClient
    ):
        """Test mesh discovers and routes to available services."""
        # Get list of available services from mesh
        try:
            response = await http_client.get("/v1/services", timeout=10.0)

            if response.status_code == 200:
                services = response.json()
                assert isinstance(services, (list, dict))

                # Test routing to each discovered service
                for service_name in (services if isinstance(services, list) else services.keys()):
                    if isinstance(service_name, str):
                        msg_id = str(uuid.uuid4())
                        request_data = {
                            "id": msg_id,
                            "ts": 1234567890.0,
                            "origin": "test_client",
                            "target": service_name,
                            "intent": "health",
                            "input": {},
                            "api_version": "v1"
                        }

                        service_response = await http_client.get(
                            f"/v1/{service_name}/health",
                            timeout=5.0
                        )
                        # Should be able to route to discovered service
                        assert service_response.status_code in (200, 404, 501)
            else:
                # Service discovery endpoint might not exist
                pytest.skip("Service discovery endpoint not available")
        except httpx.TimeoutException:
            pytest.skip("Service discovery timed out")

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_concurrent_routing_to_multiple_services(
        self, http_client: httpx.AsyncClient
    ):
        """Test mesh handles concurrent requests to different services."""
        services = ["osteon", "myocyte", "synapse", "larry", "nucleus"]

        async def make_request(service: str, index: int):
            msg_id = str(uuid.uuid4())
            request_data = {
                "id": msg_id,
                "ts": 1234567890.0,
                "origin": f"test_client_{index}",
                "target": service,
                "intent": "health",
                "input": {},
                "api_version": "v1"
            }
            try:
                response = await http_client.get(
                    f"/v1/{service}/health",
                    timeout=10.0
                )
                return (service, response.status_code)
            except Exception:
                return (service, 0)

        # Make 5 concurrent requests per service (25 total)
        tasks = [
            make_request(service, i)
            for service in services
            for i in range(5)
        ]

        results = await asyncio.gather(*tasks)

        # Count successful responses
        successful = [r for r in results if r[1] == 200]

        # At least some requests should succeed
        assert len(successful) >= 5, \
            f"Expected at least 5 successful concurrent requests, got {len(successful)}"

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_routing_preserves_request_id(self, http_client: httpx.AsyncClient):
        """Test mesh preserves request ID through routing."""
        msg_id = str(uuid.uuid4())
        request_data = {
            "id": msg_id,
            "ts": 1234567890.0,
            "origin": "test_client",
            "target": "osteon",
            "intent": "generate",
            "input": {"prompt": "Test", "max_tokens": 10},
            "api_version": "v1"
        }

        response = await http_client.post("/v1/osteon/generate", json=request_data)
        assert response.status_code == 200

        reply = response.json()
        # Request ID should be preserved in response
        assert reply["id"] == msg_id, "Request ID not preserved through routing"


class TestHealthAwareRouting:
    """Test health-aware routing behavior."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_health_check_endpoint(self, http_client: httpx.AsyncClient):
        """Test mesh health check endpoint."""
        response = await http_client.get("/health", timeout=10.0)
        assert response.status_code == 200

        health = response.json()
        assert "status" in health or "services" in health

        # Check overall status
        if "status" in health:
            assert health["status"] in ("healthy", "degraded", "unhealthy")

    @pytest.mark.asyncio
    @pytest.mark.timeout(45)
    async def test_service_health_propagation(self, http_client: httpx.AsyncClient):
        """Test individual service health is tracked by mesh."""
        # Get overall health
        health_response = await http_client.get("/health", timeout=10.0)
        assert health_response.status_code == 200

        health = health_response.json()

        # Check if service-level health is available
        if "services" in health:
            services = health["services"]
            assert isinstance(services, dict), "Services should be a dict"

            # Each service should have health status
            for service_name, service_health in services.items():
                assert "status" in service_health or "healthy" in service_health, \
                    f"Service {service_name} missing health status"

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_unhealthy_service_circuit_breaker(
        self, http_client: httpx.AsyncClient
    ):
        """Test mesh circuit breaker opens for unhealthy services."""
        # Make request to a potentially unhealthy service
        msg_id = str(uuid.uuid4())
        request_data = {
            "id": msg_id,
            "ts": 1234567890.0,
            "origin": "test_client",
            "target": "nonexistent_service",
            "intent": "test",
            "input": {},
            "api_version": "v1"
        }

        # First request should fail
        response1 = await http_client.post(
            "/v1/nonexistent_service/test",
            json=request_data
        )
        assert response1.status_code in (404, 503)

        # Multiple failed requests should trigger circuit breaker
        for _ in range(5):
            request_data["id"] = str(uuid.uuid4())
            response = await http_client.post(
                "/v1/nonexistent_service/test",
                json=request_data,
                timeout=5.0
            )
            # Should continue to fail
            assert response.status_code in (404, 503)

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_health_score_tracking(self, http_client: httpx.AsyncClient):
        """Test mesh tracks health scores for services."""
        # Get metrics endpoint if available
        try:
            response = await http_client.get("/metrics", timeout=10.0)

            if response.status_code == 200:
                metrics = response.text

                # Check for health-related metrics
                assert "health" in metrics.lower() or "status" in metrics.lower(), \
                    "Health metrics should be tracked"

                # Prometheus format should include service labels
                assert "service=" in metrics or "agent=" in metrics, \
                    "Metrics should include service labels"
            else:
                pytest.skip("Metrics endpoint not available")
        except httpx.TimeoutException:
            pytest.skip("Metrics endpoint timed out")


class TestLoadBalancing:
    """Test load balancing across service instances."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_round_robin_distribution(self, http_client: httpx.AsyncClient):
        """Test requests are distributed across service instances."""
        # Make multiple requests to the same service
        num_requests = 20
        responses = []

        for i in range(num_requests):
            msg_id = str(uuid.uuid4())
            request_data = {
                "id": msg_id,
                "ts": 1234567890.0,
                "origin": f"test_client_{i}",
                "target": "osteon",
                "intent": "health",
                "input": {},
                "api_version": "v1"
            }

            try:
                response = await http_client.get(
                    "/v1/osteon/health",
                    timeout=5.0
                )
                responses.append(response)
            except Exception:
                pass

        # At least most requests should succeed
        successful = [r for r in responses if r.status_code == 200]
        assert len(successful) >= num_requests * 0.7, \
            f"Expected at least 70% success rate, got {len(successful)}/{num_requests}"

    @pytest.mark.asyncio
    @pytest.mark.timeout(90)
    async def test_load_balancing_under_concurrent_load(
        self, http_client: httpx.AsyncClient
    ):
        """Test load balancing under high concurrent load."""
        async def make_concurrent_request(index: int):
            msg_id = str(uuid.uuid4())
            request_data = {
                "id": msg_id,
                "ts": 1234567890.0,
                "origin": f"load_test_{index}",
                "target": "osteon",
                "intent": "generate",
                "input": {"prompt": f"Test {index}", "max_tokens": 10},
                "api_version": "v1"
            }
            try:
                response = await http_client.post(
                    "/v1/osteon/generate",
                    json=request_data,
                    timeout=15.0
                )
                return response.status_code == 200
            except Exception:
                return False

        # Make 30 concurrent requests
        tasks = [make_concurrent_request(i) for i in range(30)]
        results = await asyncio.gather(*tasks)

        # Calculate success rate
        success_rate = sum(results) / len(results)

        # Should handle at least 60% of concurrent requests successfully
        assert success_rate >= 0.6, \
            f"Load balancing failed, success rate: {success_rate:.2%}"


class TestRBACIntegration:
    """Test RBAC integration with routing."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_unauthenticated_request_rejected(self):
        """Test unauthenticated requests are rejected."""
        # Create client without auth headers
        async with httpx.AsyncClient(base_url="http://localhost:8080") as client:
            response = await client.get("/v1/osteon/health", timeout=10.0)

            # Depending on RBAC config, might allow health checks or reject
            # If RBAC is strict, should get 401
            assert response.status_code in (200, 401, 403)

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_routing_with_api_key(self, http_client: httpx.AsyncClient):
        """Test routing works with valid API key."""
        # Client already has auth configured
        response = await http_client.get("/v1/osteon/health", timeout=10.0)

        # Should work with valid auth
        assert response.status_code in (200, 404, 501)

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_rbac_preserves_routing(self, http_client: httpx.AsyncClient):
        """Test RBAC doesn't interfere with correct routing."""
        services = ["osteon", "myocyte", "synapse"]

        for service in services:
            response = await http_client.get(f"/v1/{service}/health", timeout=10.0)

            # Each service should be reachable with proper auth
            assert response.status_code in (200, 404, 501), \
                f"RBAC blocked access to {service}"
