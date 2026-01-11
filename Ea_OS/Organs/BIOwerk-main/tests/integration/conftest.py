"""
Integration Test Configuration and Fixtures

Integration tests verify service-to-service communication and contracts.
These fixtures provide utilities for testing multi-service workflows.
"""
import os
import asyncio
import uuid
from typing import Dict, Any, AsyncGenerator
import pytest
import httpx

# Import E2E fixtures to reuse (integration tests also need full stack)
pytest_plugins = ["tests.e2e.conftest"]


@pytest.fixture
def msg_factory():
    """
    Factory for creating Msg-formatted requests.

    Usage:
        msg = msg_factory(target="osteon", intent="generate", input={"prompt": "test"})
    """
    def _create_msg(
        target: str,
        intent: str,
        input: Dict[str, Any],
        origin: str = "test_client",
        api_version: str = "v1"
    ) -> Dict[str, Any]:
        return {
            "id": str(uuid.uuid4()),
            "ts": 1234567890.0,
            "origin": origin,
            "target": target,
            "intent": intent,
            "input": input,
            "api_version": api_version
        }
    return _create_msg


@pytest.fixture
def reply_validator():
    """
    Validator for Reply message format.

    Usage:
        reply_validator(response.json(), expected_agent="osteon")
    """
    def _validate_reply(
        reply: Dict[str, Any],
        expected_agent: str = None,
        expected_ok: bool = None
    ) -> bool:
        # Validate required fields
        required_fields = ["id", "agent", "ok", "output", "state_hash"]
        for field in required_fields:
            assert field in reply, f"Reply missing required field: {field}"

        # Validate types
        assert isinstance(reply["id"], str), "Reply.id must be string"
        assert isinstance(reply["agent"], str), "Reply.agent must be string"
        assert isinstance(reply["ok"], bool), "Reply.ok must be boolean"
        assert isinstance(reply["output"], dict), "Reply.output must be dict"
        assert isinstance(reply["state_hash"], str), "Reply.state_hash must be string"

        # Validate state_hash format (BLAKE3 is 64 hex chars)
        assert len(reply["state_hash"]) == 64, \
            f"state_hash should be 64 chars (BLAKE3), got {len(reply['state_hash'])}"

        # Validate expected values
        if expected_agent is not None:
            assert reply["agent"] == expected_agent, \
                f"Expected agent={expected_agent}, got {reply['agent']}"

        if expected_ok is not None:
            assert reply["ok"] == expected_ok, \
                f"Expected ok={expected_ok}, got {reply['ok']}"

        return True

    return _validate_reply


@pytest.fixture
async def service_health_checker(http_client: httpx.AsyncClient):
    """
    Utility to check individual service health.

    Usage:
        is_healthy = await service_health_checker("osteon")
    """
    async def _check_health(service_name: str) -> bool:
        try:
            response = await http_client.get(
                f"/v1/{service_name}/health",
                timeout=5.0
            )
            return response.status_code == 200
        except Exception:
            return False

    return _check_health


@pytest.fixture
async def multi_service_request():
    """
    Utility to make requests to multiple services in parallel.

    Usage:
        results = await multi_service_request([
            ("osteon", "generate", {"prompt": "test"}),
            ("myocyte", "analyze", {"data": [1, 2, 3]})
        ])
    """
    async def _make_requests(
        client: httpx.AsyncClient,
        requests: list[tuple[str, str, Dict[str, Any]]]
    ) -> list[tuple[str, int, Dict[str, Any]]]:
        async def make_request(service: str, intent: str, input_data: Dict[str, Any]):
            msg_id = str(uuid.uuid4())
            request_data = {
                "id": msg_id,
                "ts": 1234567890.0,
                "origin": "test_client",
                "target": service,
                "intent": intent,
                "input": input_data,
                "api_version": "v1"
            }
            try:
                response = await client.post(
                    f"/v1/{service}/{intent}",
                    json=request_data,
                    timeout=30.0
                )
                return (service, response.status_code, response.json())
            except Exception as e:
                return (service, 0, {"error": str(e)})

        tasks = [make_request(svc, intent, inp) for svc, intent, inp in requests]
        return await asyncio.gather(*tasks)

    return _make_requests


@pytest.fixture
def integration_test_config():
    """
    Configuration for integration tests.
    """
    return {
        "services": {
            "osteon": {"port": 8001, "name": "Osteon (Document Agent)"},
            "myocyte": {"port": 8002, "name": "Myocyte (Data Agent)"},
            "synapse": {"port": 8003, "name": "Synapse (Presentation Agent)"},
            "circadian": {"port": 8004, "name": "Circadian (Scheduler Agent)"},
            "nucleus": {"port": 8005, "name": "Nucleus (Director Agent)"},
            "chaperone": {"port": 8006, "name": "Chaperone (Import/Export Agent)"},
            "larry": {"port": 8007, "name": "Larry (Conversational Interface)"},
            "moe": {"port": 8008, "name": "Moe (Orchestrator)"},
            "harry": {"port": 8009, "name": "Harry (Monitor)"},
            "gdpr": {"port": 8010, "name": "GDPR (Compliance Service)"},
        },
        "mesh": {
            "port": 8080,
            "https_port": 8443
        },
        "timeouts": {
            "health_check": 5.0,
            "standard_request": 30.0,
            "long_request": 60.0,
            "orchestration": 120.0
        },
        "resilience": {
            "circuit_breaker": {
                "failure_threshold": 5,
                "success_threshold": 2,
                "timeout": 60
            },
            "retry": {
                "max_attempts": 3,
                "initial_delay": 0.1,
                "max_delay": 10.0
            },
            "bulkhead": {
                "max_concurrent": 10,
                "queue_size": 5,
                "timeout": 5.0
            }
        }
    }


@pytest.fixture
async def resilience_test_helper(http_client: httpx.AsyncClient):
    """
    Helper for testing resilience patterns.

    Usage:
        await resilience_test_helper.trigger_circuit_breaker("osteon")
    """
    class ResilienceTestHelper:
        def __init__(self, client: httpx.AsyncClient):
            self.client = client

        async def trigger_circuit_breaker(
            self,
            service: str,
            num_failures: int = 6
        ) -> int:
            """Make enough failing requests to open circuit breaker."""
            failures = 0
            for _ in range(num_failures):
                msg_id = str(uuid.uuid4())
                request_data = {
                    "id": msg_id,
                    "ts": 1234567890.0,
                    "origin": "circuit_breaker_test",
                    "target": service,
                    "intent": "nonexistent_intent",
                    "input": {},
                    "api_version": "v1"
                }
                try:
                    response = await self.client.post(
                        f"/v1/{service}/nonexistent_intent",
                        json=request_data,
                        timeout=5.0
                    )
                    if response.status_code >= 400:
                        failures += 1
                except Exception:
                    failures += 1

                await asyncio.sleep(0.1)

            return failures

        async def check_circuit_state(self, service: str) -> str:
            """
            Check circuit breaker state for a service.
            Returns: "CLOSED", "OPEN", or "HALF_OPEN"
            """
            # Try to make a request and infer state from response
            msg_id = str(uuid.uuid4())
            request_data = {
                "id": msg_id,
                "ts": 1234567890.0,
                "origin": "state_check",
                "target": service,
                "intent": "health",
                "input": {},
                "api_version": "v1"
            }
            try:
                response = await self.client.get(
                    f"/v1/{service}/health",
                    timeout=5.0
                )
                # If we get quick 503, circuit is likely OPEN
                if response.status_code == 503:
                    return "OPEN"
                # If we get 200, circuit is likely CLOSED
                return "CLOSED"
            except Exception:
                return "UNKNOWN"

        async def concurrent_load(
            self,
            service: str,
            intent: str,
            input_data: Dict[str, Any],
            num_requests: int = 20
        ) -> tuple[int, int, int]:
            """
            Send concurrent requests to test bulkhead.
            Returns: (successful, failed, timed_out)
            """
            async def make_request(index: int):
                msg_id = str(uuid.uuid4())
                request_data = {
                    "id": msg_id,
                    "ts": 1234567890.0,
                    "origin": f"load_test_{index}",
                    "target": service,
                    "intent": intent,
                    "input": input_data,
                    "api_version": "v1"
                }
                try:
                    response = await self.client.post(
                        f"/v1/{service}/{intent}",
                        json=request_data,
                        timeout=30.0
                    )
                    return response.status_code
                except httpx.TimeoutException:
                    return -1
                except Exception:
                    return 0

            tasks = [make_request(i) for i in range(num_requests)]
            results = await asyncio.gather(*tasks)

            successful = sum(1 for r in results if r == 200)
            failed = sum(1 for r in results if 400 <= r < 600)
            timed_out = sum(1 for r in results if r == -1)

            return (successful, failed, timed_out)

    return ResilienceTestHelper(http_client)


@pytest.fixture
def sample_integration_requests():
    """
    Sample requests for common integration test scenarios.
    """
    return {
        "document_workflow": {
            "target": "osteon",
            "intent": "generate",
            "input": {
                "prompt": "Write a summary of renewable energy",
                "max_tokens": 100
            }
        },
        "data_analysis": {
            "target": "myocyte",
            "intent": "analyze",
            "input": {
                "data": [10, 20, 30, 40, 50],
                "operation": "statistics"
            }
        },
        "presentation": {
            "target": "synapse",
            "intent": "visualize",
            "input": {
                "type": "chart",
                "data": [1, 2, 3, 4, 5]
            }
        },
        "orchestration": {
            "target": "nucleus",
            "intent": "orchestrate",
            "input": {
                "task": "Multi-service workflow test",
                "services": ["osteon", "myocyte"]
            }
        },
        "conversation": {
            "target": "larry",
            "intent": "chat",
            "input": {
                "message": "Hello, how are you?",
                "context": {}
            }
        }
    }


@pytest.fixture
async def database_test_helper():
    """
    Helper for database integration tests.
    Provides utilities for creating/cleaning test data.
    """
    class DatabaseTestHelper:
        def __init__(self):
            self.test_entities = []

        def create_test_id(self, prefix: str = "test") -> str:
            """Create a unique test ID."""
            test_id = f"{prefix}_{uuid.uuid4().hex[:8]}"
            self.test_entities.append(test_id)
            return test_id

        async def cleanup(self, client: httpx.AsyncClient):
            """Clean up test entities (best effort)."""
            # In a real implementation, would delete created entities
            # For now, just clear the list
            self.test_entities.clear()

    helper = DatabaseTestHelper()
    yield helper
    # Cleanup would happen here if needed


# Mark all integration tests with integration marker
def pytest_collection_modifyitems(items):
    """Automatically mark all tests in integration/ as integration tests."""
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.asyncio)


# Configure pytest-asyncio
def pytest_configure(config):
    """Configure integration test markers."""
    config.addinivalue_line(
        "markers",
        "integration: mark test as an integration test requiring full service stack"
    )
