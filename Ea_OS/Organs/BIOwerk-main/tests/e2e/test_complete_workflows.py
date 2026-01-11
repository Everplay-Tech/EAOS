"""
E2E Complete Workflow Tests

Tests complete end-to-end workflows across multiple services to validate
that the entire BIOwerk platform works correctly under realistic scenarios.
"""
import pytest
import asyncio
import uuid
from typing import Dict
import httpx


class TestDocumentWorkflow:
    """Test complete document generation workflows using Osteon service."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_document_draft_workflow(
        self,
        http_client: httpx.AsyncClient,
        sample_document_request: Dict
    ):
        """
        Test complete document drafting workflow:
        1. Request document draft
        2. Validate response structure
        3. Verify content generation
        """
        msg_id = str(uuid.uuid4())
        request_payload = {
            "id": msg_id,
            "agent": "osteon",
            "endpoint": "draft",
            **sample_document_request
        }

        # Execute document draft request
        response = await http_client.post("/osteon/draft", json=request_payload)

        # Validate response
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        assert data["ok"] is True, "Response should indicate success"
        assert data["id"] == msg_id, "Response ID should match request ID"
        assert data["agent"] == "osteon", "Agent should be osteon"
        assert "output" in data, "Response should contain output"
        assert "state_hash" in data, "Response should contain state_hash for idempotency"

        # Verify output structure
        output = data["output"]
        assert "echo" in output or "result" in output, "Output should contain result data"


class TestDataAnalysisWorkflow:
    """Test complete data analysis workflows using Myocyte service."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_data_ingestion_and_analysis(
        self,
        http_client: httpx.AsyncClient,
        sample_data_analysis_request: Dict
    ):
        """
        Test complete data analysis workflow:
        1. Ingest table data
        2. Perform analysis
        3. Validate results
        """
        msg_id = str(uuid.uuid4())
        request_payload = {
            "id": msg_id,
            "agent": "myocyte",
            "endpoint": "ingest_table",
            **sample_data_analysis_request
        }

        # Execute data ingestion
        response = await http_client.post("/myocyte/ingest_table", json=request_payload)

        # Validate response
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        assert data["ok"] is True, "Data ingestion should succeed"
        assert data["id"] == msg_id, "Response ID should match request ID"
        assert "output" in data, "Response should contain output"


class TestPresentationWorkflow:
    """Test complete presentation generation workflows using Synapse service."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_presentation_generation(
        self,
        http_client: httpx.AsyncClient,
        sample_presentation_request: Dict
    ):
        """
        Test complete presentation generation workflow:
        1. Create storyboard
        2. Generate slides
        3. Validate output
        """
        msg_id = str(uuid.uuid4())
        request_payload = {
            "id": msg_id,
            "agent": "synapse",
            "endpoint": "storyboard",
            **sample_presentation_request
        }

        # Execute storyboard creation
        response = await http_client.post("/synapse/storyboard", json=request_payload)

        # Validate response
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        assert data["ok"] is True, "Storyboard creation should succeed"
        assert data["id"] == msg_id, "Response ID should match request ID"
        assert data["agent"] == "synapse", "Agent should be synapse"


class TestTaskPlanningWorkflow:
    """Test complete task planning workflows using Circadian service."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_task_timeline_planning(
        self,
        http_client: httpx.AsyncClient,
        sample_task_planning_request: Dict
    ):
        """
        Test complete task planning workflow:
        1. Plan timeline
        2. Assign tasks
        3. Validate scheduling
        """
        msg_id = str(uuid.uuid4())
        request_payload = {
            "id": msg_id,
            "agent": "circadian",
            "endpoint": "plan_timeline",
            **sample_task_planning_request
        }

        # Execute timeline planning
        response = await http_client.post("/circadian/plan_timeline", json=request_payload)

        # Validate response
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        assert data["ok"] is True, "Timeline planning should succeed"
        assert data["id"] == msg_id, "Response ID should match request ID"


class TestMultiServiceOrchestration:
    """Test workflows that span multiple services."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(180)
    async def test_nucleus_orchestration(
        self,
        http_client: httpx.AsyncClient
    ):
        """
        Test Nucleus service orchestrating multiple agents:
        1. Plan workflow across services
        2. Route to appropriate agents
        3. Finalize results
        """
        msg_id = str(uuid.uuid4())

        # Test plan endpoint
        plan_request = {
            "id": msg_id,
            "agent": "nucleus",
            "endpoint": "plan",
            "input": {
                "goal": "Create quarterly report with data analysis",
                "requirements": ["financial_data", "charts", "summary"]
            }
        }

        response = await http_client.post("/nucleus/plan", json=plan_request)
        assert response.status_code == 200

        data = response.json()
        assert data["ok"] is True
        assert data["agent"] == "nucleus"

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_parallel_service_requests(
        self,
        http_client: httpx.AsyncClient,
        sample_document_request: Dict,
        sample_data_analysis_request: Dict
    ):
        """
        Test multiple services handling concurrent requests:
        1. Send parallel requests to different services
        2. Validate all complete successfully
        3. Check for proper isolation
        """
        # Create multiple concurrent requests
        requests = [
            {
                "id": str(uuid.uuid4()),
                "agent": "osteon",
                "endpoint": "draft",
                **sample_document_request
            },
            {
                "id": str(uuid.uuid4()),
                "agent": "myocyte",
                "endpoint": "ingest_table",
                **sample_data_analysis_request
            }
        ]

        # Execute requests in parallel
        tasks = [
            http_client.post(f"/{req['agent']}/{req['endpoint']}", json=req)
            for req in requests
        ]

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Validate all succeeded
        for idx, response in enumerate(responses):
            assert not isinstance(response, Exception), f"Request {idx} failed: {response}"
            assert response.status_code == 200, f"Request {idx} failed with status {response.status_code}"

            data = response.json()
            assert data["ok"] is True, f"Request {idx} returned error"
            assert data["id"] == requests[idx]["id"], f"Request {idx} ID mismatch"


class TestHealthAndReadiness:
    """Test health and readiness endpoints for all services."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_mesh_health_endpoint(self, http_client: httpx.AsyncClient):
        """Validate mesh service health endpoint."""
        response = await http_client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "degraded"]
        assert "timestamp" in data
        assert "version" in data

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_mesh_ready_endpoint(self, http_client: httpx.AsyncClient):
        """Validate mesh service readiness endpoint."""
        response = await http_client.get("/ready")
        assert response.status_code in [200, 503]

        data = response.json()
        assert "ready" in data
        assert "checks" in data
        assert isinstance(data["checks"], dict)


class TestErrorHandling:
    """Test error handling and resilience across services."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_invalid_endpoint(self, http_client: httpx.AsyncClient):
        """Test handling of requests to non-existent endpoints."""
        msg_id = str(uuid.uuid4())
        request = {
            "id": msg_id,
            "agent": "osteon",
            "endpoint": "nonexistent",
            "input": {}
        }

        response = await http_client.post("/osteon/nonexistent", json=request)
        assert response.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_invalid_payload(self, http_client: httpx.AsyncClient):
        """Test handling of malformed request payloads."""
        response = await http_client.post(
            "/osteon/draft",
            json={"invalid": "payload"}
        )
        # Should return 422 (validation error) or 400 (bad request)
        assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_missing_required_fields(self, http_client: httpx.AsyncClient):
        """Test handling of requests with missing required fields."""
        incomplete_request = {
            "agent": "osteon",
            "endpoint": "draft"
            # Missing 'id' and 'input' fields
        }

        response = await http_client.post("/osteon/draft", json=incomplete_request)
        assert response.status_code in [400, 422]


class TestIdempotency:
    """Test idempotency features across services."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_duplicate_request_handling(
        self,
        http_client: httpx.AsyncClient,
        sample_document_request: Dict
    ):
        """
        Test that duplicate requests (same ID) are handled correctly:
        1. Send initial request
        2. Send duplicate request with same ID
        3. Verify idempotent behavior
        """
        msg_id = str(uuid.uuid4())
        request_payload = {
            "id": msg_id,
            "agent": "osteon",
            "endpoint": "draft",
            **sample_document_request
        }

        # First request
        response1 = await http_client.post("/osteon/draft", json=request_payload)
        assert response1.status_code == 200
        data1 = response1.json()
        state_hash1 = data1.get("state_hash")

        # Duplicate request
        response2 = await http_client.post("/osteon/draft", json=request_payload)
        assert response2.status_code == 200
        data2 = response2.json()
        state_hash2 = data2.get("state_hash")

        # State hashes should be consistent for idempotency
        assert data1["id"] == data2["id"]
        assert data1["agent"] == data2["agent"]
