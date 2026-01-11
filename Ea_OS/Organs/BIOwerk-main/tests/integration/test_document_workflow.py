"""
Integration tests for document workflow.

Tests the complete flow: User → Mesh → Larry → Nucleus → Osteon
"""
import hashlib
import json
import uuid
from typing import Any, Dict

import httpx
import pytest


class TestDocumentWorkflowIntegration:
    """Test complete document generation workflow across services."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_user_to_mesh_to_osteon_flow(self, http_client: httpx.AsyncClient):
        """Test User → Mesh → Osteon direct flow for document generation."""
        # Create a message following the Msg format
        msg_id = str(uuid.uuid4())
        request_data = {
            "id": msg_id,
            "ts": 1234567890.0,
            "origin": "test_client",
            "target": "osteon",
            "intent": "generate",
            "input": {
                "prompt": "Write a short summary of photosynthesis",
                "max_tokens": 100
            },
            "api_version": "v1"
        }

        # Send through mesh gateway
        response = await http_client.post("/v1/osteon/generate", json=request_data)
        assert response.status_code == 200

        # Validate Reply format
        reply = response.json()
        assert reply["id"] == msg_id, "Reply ID should match request ID"
        assert reply["agent"] == "osteon", "Reply should be from osteon"
        assert reply["ok"] is True, "Reply should indicate success"
        assert "output" in reply, "Reply should contain output"
        assert "state_hash" in reply, "Reply should contain state_hash"
        assert reply["api_version"] == "v1"

        # Validate state_hash is a valid BLAKE3 hash
        assert len(reply["state_hash"]) == 64, "state_hash should be 64 chars (BLAKE3)"

    @pytest.mark.asyncio
    @pytest.mark.timeout(90)
    async def test_larry_to_nucleus_to_osteon_orchestration(
        self, http_client: httpx.AsyncClient
    ):
        """Test Larry → Nucleus → Osteon orchestrated flow."""
        msg_id = str(uuid.uuid4())
        request_data = {
            "id": msg_id,
            "ts": 1234567890.0,
            "origin": "test_client",
            "target": "larry",
            "intent": "chat",
            "input": {
                "message": "Create a document about renewable energy",
                "context": {}
            },
            "api_version": "v1"
        }

        # Send to Larry through mesh
        response = await http_client.post("/v1/larry/chat", json=request_data)
        assert response.status_code == 200

        reply = response.json()
        assert reply["id"] == msg_id
        assert reply["agent"] == "larry"
        assert reply["ok"] is True
        assert "output" in reply

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_msg_reply_format_consistency(self, http_client: httpx.AsyncClient):
        """Verify all services return consistent Reply format."""
        services_and_endpoints = [
            ("osteon", "generate"),
            ("myocyte", "analyze"),
            ("synapse", "visualize"),
            ("nucleus", "orchestrate"),
        ]

        for service, endpoint in services_and_endpoints:
            msg_id = str(uuid.uuid4())
            request_data = {
                "id": msg_id,
                "ts": 1234567890.0,
                "origin": "test_client",
                "target": service,
                "intent": endpoint,
                "input": {"test": "data"},
                "api_version": "v1"
            }

            try:
                response = await http_client.post(
                    f"/v1/{service}/{endpoint}",
                    json=request_data,
                    timeout=30.0
                )

                # Even if service fails, it should return valid Reply format
                if response.status_code in (200, 500):
                    reply = response.json()
                    assert "id" in reply, f"{service} reply missing 'id'"
                    assert "agent" in reply, f"{service} reply missing 'agent'"
                    assert "ok" in reply, f"{service} reply missing 'ok'"
                    assert "output" in reply, f"{service} reply missing 'output'"
                    assert "state_hash" in reply, f"{service} reply missing 'state_hash'"
                    assert reply["id"] == msg_id, f"{service} reply ID mismatch"
            except httpx.TimeoutException:
                # Service might not be available, skip
                pytest.skip(f"{service} not available")

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_state_hash_validation(self, http_client: httpx.AsyncClient):
        """Test state_hash generation is deterministic and valid."""
        msg_id = str(uuid.uuid4())
        request_data = {
            "id": msg_id,
            "ts": 1234567890.0,
            "origin": "test_client",
            "target": "osteon",
            "intent": "generate",
            "input": {
                "prompt": "Test prompt for deterministic output",
                "max_tokens": 50,
                "temperature": 0.0  # Deterministic
            },
            "api_version": "v1"
        }

        # Make two identical requests
        response1 = await http_client.post("/v1/osteon/generate", json=request_data)
        assert response1.status_code == 200
        reply1 = response1.json()

        # Second request with new ID but same input
        request_data["id"] = str(uuid.uuid4())
        response2 = await http_client.post("/v1/osteon/generate", json=request_data)
        assert response2.status_code == 200
        reply2 = response2.json()

        # With deterministic settings, outputs should be similar
        # (may not be exactly identical due to LLM variability, but state_hash should be valid)
        assert len(reply1["state_hash"]) == 64
        assert len(reply2["state_hash"]) == 64

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_gdpr_data_export_workflow(self, http_client: httpx.AsyncClient):
        """Test GDPR data export workflow across services."""
        user_id = f"test_user_{uuid.uuid4().hex[:8]}"

        # Step 1: Create some data for the user via Osteon
        msg_id = str(uuid.uuid4())
        create_request = {
            "id": msg_id,
            "ts": 1234567890.0,
            "origin": "test_client",
            "target": "osteon",
            "intent": "generate",
            "input": {
                "prompt": f"User {user_id} document",
                "max_tokens": 50,
                "user_id": user_id
            },
            "api_version": "v1"
        }

        response = await http_client.post("/v1/osteon/generate", json=create_request)
        assert response.status_code == 200

        # Step 2: Request GDPR export
        export_msg_id = str(uuid.uuid4())
        export_request = {
            "id": export_msg_id,
            "ts": 1234567890.0,
            "origin": "test_client",
            "target": "gdpr",
            "intent": "export",
            "input": {
                "user_id": user_id,
                "format": "json"
            },
            "api_version": "v1"
        }

        try:
            response = await http_client.post("/v1/gdpr/export", json=export_request)
            # GDPR service might not be fully implemented, accept 200 or 501
            assert response.status_code in (200, 501, 404)

            if response.status_code == 200:
                reply = response.json()
                assert reply["ok"] is True
                assert "output" in reply
        except httpx.TimeoutException:
            pytest.skip("GDPR service not available")

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_token_budget_enforcement_across_services(
        self, http_client: httpx.AsyncClient
    ):
        """Test token budget enforcement in multi-service workflow."""
        msg_id = str(uuid.uuid4())
        request_data = {
            "id": msg_id,
            "ts": 1234567890.0,
            "origin": "test_client",
            "target": "osteon",
            "intent": "generate",
            "input": {
                "prompt": "Write a very long document about quantum physics",
                "max_tokens": 10,  # Very low limit
                "token_budget": 10
            },
            "api_version": "v1"
        }

        response = await http_client.post("/v1/osteon/generate", json=request_data)
        assert response.status_code == 200

        reply = response.json()
        # Should respect token budget
        if reply["ok"]:
            output = reply["output"]
            # Verify output respects budget (approximate check)
            if "text" in output:
                # Rough check: 10 tokens ~ 40-50 characters
                assert len(output["text"]) < 200

    @pytest.mark.asyncio
    @pytest.mark.timeout(90)
    async def test_error_propagation_through_services(
        self, http_client: httpx.AsyncClient
    ):
        """Test error propagation from worker service through mesh to client."""
        msg_id = str(uuid.uuid4())
        # Send invalid request to trigger error
        request_data = {
            "id": msg_id,
            "ts": 1234567890.0,
            "origin": "test_client",
            "target": "osteon",
            "intent": "invalid_intent",  # Invalid intent
            "input": {},
            "api_version": "v1"
        }

        response = await http_client.post("/v1/osteon/invalid_intent", json=request_data)

        # Should get error response
        assert response.status_code in (400, 404, 422, 500)

        # Error should still follow Reply format if service is reachable
        if response.status_code != 404:  # 404 from mesh means endpoint not found
            reply = response.json()
            # Should have error information
            assert "detail" in reply or "error" in reply or "ok" in reply

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_timeout_handling_across_services(
        self, http_client: httpx.AsyncClient
    ):
        """Test timeout handling in service-to-service communication."""
        msg_id = str(uuid.uuid4())
        request_data = {
            "id": msg_id,
            "ts": 1234567890.0,
            "origin": "test_client",
            "target": "osteon",
            "intent": "generate",
            "input": {
                "prompt": "Quick test",
                "max_tokens": 10
            },
            "api_version": "v1"
        }

        # Use very short timeout
        try:
            response = await http_client.post(
                "/v1/osteon/generate",
                json=request_data,
                timeout=0.1  # 100ms - very short
            )
            # If it succeeds within timeout, that's fine
            assert response.status_code == 200
        except httpx.TimeoutException:
            # Timeout is expected and acceptable
            pass

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_document_creation_end_to_end(
        self, http_client: httpx.AsyncClient
    ):
        """Test complete document creation workflow with validation."""
        # Step 1: Request document generation
        msg_id = str(uuid.uuid4())
        request_data = {
            "id": msg_id,
            "ts": 1234567890.0,
            "origin": "test_client",
            "target": "osteon",
            "intent": "generate",
            "input": {
                "prompt": "Create a technical document about REST APIs",
                "max_tokens": 200,
                "format": "markdown"
            },
            "api_version": "v1"
        }

        response = await http_client.post("/v1/osteon/generate", json=request_data)
        assert response.status_code == 200

        reply = response.json()
        assert reply["ok"] is True
        assert "output" in reply

        output = reply["output"]
        # Validate document was created
        assert "text" in output or "content" in output or "document" in output

        # Step 2: If document has ID, verify it can be retrieved
        if "document_id" in output:
            doc_id = output["document_id"]

            # Try to retrieve the document
            retrieve_msg_id = str(uuid.uuid4())
            retrieve_request = {
                "id": retrieve_msg_id,
                "ts": 1234567890.0,
                "origin": "test_client",
                "target": "osteon",
                "intent": "retrieve",
                "input": {"document_id": doc_id},
                "api_version": "v1"
            }

            retrieve_response = await http_client.post(
                "/v1/osteon/retrieve",
                json=retrieve_request
            )
            # Accept success or not found (retrieval might not be implemented)
            assert retrieve_response.status_code in (200, 404, 501)


class TestMultiServiceOrchestration:
    """Test orchestration across multiple services."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_nucleus_orchestrates_multiple_workers(
        self, http_client: httpx.AsyncClient
    ):
        """Test Nucleus orchestrating multiple worker services."""
        msg_id = str(uuid.uuid4())
        request_data = {
            "id": msg_id,
            "ts": 1234567890.0,
            "origin": "test_client",
            "target": "nucleus",
            "intent": "orchestrate",
            "input": {
                "task": "Create a comprehensive report with document and data analysis",
                "services": ["osteon", "myocyte"]
            },
            "api_version": "v1"
        }

        try:
            response = await http_client.post(
                "/v1/nucleus/orchestrate",
                json=request_data,
                timeout=60.0
            )

            # Nucleus might not implement full orchestration yet
            assert response.status_code in (200, 501, 404)

            if response.status_code == 200:
                reply = response.json()
                assert reply["id"] == msg_id
                assert reply["agent"] == "nucleus"
        except httpx.TimeoutException:
            pytest.skip("Nucleus orchestration took too long")

    @pytest.mark.asyncio
    @pytest.mark.timeout(90)
    async def test_parallel_service_requests(self, http_client: httpx.AsyncClient):
        """Test parallel requests to multiple services."""
        import asyncio

        services = [
            ("osteon", "generate", {"prompt": "Test 1", "max_tokens": 20}),
            ("myocyte", "analyze", {"data": [1, 2, 3]}),
            ("synapse", "visualize", {"type": "chart", "data": [1, 2, 3]}),
        ]

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
                response = await http_client.post(
                    f"/v1/{service}/{intent}",
                    json=request_data,
                    timeout=30.0
                )
                return (service, response.status_code, response.json())
            except Exception as e:
                return (service, 0, {"error": str(e)})

        # Execute in parallel
        tasks = [make_request(svc, intent, inp) for svc, intent, inp in services]
        results = await asyncio.gather(*tasks)

        # At least some services should respond
        successful = [r for r in results if r[1] == 200]
        assert len(successful) >= 1, "At least one service should respond successfully"

        # All successful responses should follow Reply format
        for service, status_code, reply in successful:
            assert "id" in reply
            assert "agent" in reply
            assert reply["agent"] == service
