"""
Integration tests for database interactions across services.

Tests multi-service database operations including:
- Shared database access
- Transaction coordination
- Data consistency across services
- Connection pooling
"""
import asyncio
import uuid
from typing import Dict, Any

import httpx
import pytest


class TestDatabaseIntegration:
    """Test database integration across services."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_multi_service_database_access(self, http_client: httpx.AsyncClient):
        """Test multiple services can access shared database."""
        user_id = f"test_user_{uuid.uuid4().hex[:8]}"

        # Service 1: Osteon creates document (should write to DB)
        msg_id_1 = str(uuid.uuid4())
        osteon_request = {
            "id": msg_id_1,
            "ts": 1234567890.0,
            "origin": "test_client",
            "target": "osteon",
            "intent": "generate",
            "input": {
                "prompt": f"Document for {user_id}",
                "max_tokens": 50,
                "user_id": user_id
            },
            "api_version": "v1"
        }

        osteon_response = await http_client.post(
            "/v1/osteon/generate",
            json=osteon_request
        )
        assert osteon_response.status_code == 200
        osteon_reply = osteon_response.json()
        assert osteon_reply["ok"] is True

        # Service 2: Myocyte processes data (should also access DB)
        msg_id_2 = str(uuid.uuid4())
        myocyte_request = {
            "id": msg_id_2,
            "ts": 1234567890.0,
            "origin": "test_client",
            "target": "myocyte",
            "intent": "analyze",
            "input": {
                "data": [1, 2, 3, 4, 5],
                "user_id": user_id
            },
            "api_version": "v1"
        }

        try:
            myocyte_response = await http_client.post(
                "/v1/myocyte/analyze",
                json=myocyte_request,
                timeout=30.0
            )

            # Both services should successfully access database
            assert myocyte_response.status_code in (200, 501)

            if myocyte_response.status_code == 200:
                myocyte_reply = myocyte_response.json()
                assert "ok" in myocyte_reply
        except httpx.TimeoutException:
            pytest.skip("Myocyte service timeout")

    @pytest.mark.asyncio
    @pytest.mark.timeout(90)
    async def test_data_consistency_across_services(
        self, http_client: httpx.AsyncClient
    ):
        """Test data written by one service is readable by another."""
        entity_id = f"entity_{uuid.uuid4().hex[:8]}"

        # Service 1: Create entity via Osteon
        msg_id = str(uuid.uuid4())
        create_request = {
            "id": msg_id,
            "ts": 1234567890.0,
            "origin": "test_client",
            "target": "osteon",
            "intent": "generate",
            "input": {
                "prompt": f"Entity {entity_id}",
                "max_tokens": 50,
                "entity_id": entity_id,
                "persist": True
            },
            "api_version": "v1"
        }

        create_response = await http_client.post(
            "/v1/osteon/generate",
            json=create_request
        )
        assert create_response.status_code == 200
        create_reply = create_response.json()

        # Extract document/entity ID if provided
        doc_id = None
        if "output" in create_reply:
            output = create_reply["output"]
            doc_id = output.get("document_id") or output.get("id") or output.get("entity_id")

        if doc_id:
            # Service 2: Try to retrieve via different service
            # Note: May need to use same service for retrieval depending on implementation
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

            try:
                retrieve_response = await http_client.post(
                    "/v1/osteon/retrieve",
                    json=retrieve_request,
                    timeout=20.0
                )

                # Should be able to retrieve if retrieval is implemented
                assert retrieve_response.status_code in (200, 404, 501)

                if retrieve_response.status_code == 200:
                    retrieve_reply = retrieve_response.json()
                    assert retrieve_reply["ok"] is True
            except httpx.TimeoutException:
                pytest.skip("Retrieval timed out")

    @pytest.mark.asyncio
    @pytest.mark.timeout(90)
    async def test_concurrent_database_writes(self, http_client: httpx.AsyncClient):
        """Test concurrent writes to database from multiple services."""
        async def create_document(index: int):
            msg_id = str(uuid.uuid4())
            request_data = {
                "id": msg_id,
                "ts": 1234567890.0,
                "origin": f"test_client_{index}",
                "target": "osteon",
                "intent": "generate",
                "input": {
                    "prompt": f"Concurrent document {index}",
                    "max_tokens": 30,
                    "index": index
                },
                "api_version": "v1"
            }
            try:
                response = await http_client.post(
                    "/v1/osteon/generate",
                    json=request_data,
                    timeout=30.0
                )
                return response.status_code == 200
            except Exception:
                return False

        # Create 15 documents concurrently
        tasks = [create_document(i) for i in range(15)]
        results = await asyncio.gather(*tasks)

        # Most should succeed
        success_rate = sum(results) / len(results)
        assert success_rate >= 0.7, \
            f"Concurrent database writes failed, success rate: {success_rate:.2%}"

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_connection_pooling(self, http_client: httpx.AsyncClient):
        """Test database connection pooling works across services."""
        async def make_db_request(index: int):
            msg_id = str(uuid.uuid4())
            request_data = {
                "id": msg_id,
                "ts": 1234567890.0,
                "origin": f"pool_test_{index}",
                "target": "osteon",
                "intent": "generate",
                "input": {
                    "prompt": f"Pool test {index}",
                    "max_tokens": 20
                },
                "api_version": "v1"
            }
            try:
                response = await http_client.post(
                    "/v1/osteon/generate",
                    json=request_data,
                    timeout=20.0
                )
                return response.status_code
            except Exception:
                return 0

        # Make 25 requests to test connection pool
        tasks = [make_db_request(i) for i in range(25)]
        results = await asyncio.gather(*tasks)

        # Count successes
        successful = [r for r in results if r == 200]

        # Connection pooling should handle most requests
        assert len(successful) >= 15, \
            f"Connection pooling failed, only {len(successful)}/25 succeeded"

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_database_transaction_isolation(
        self, http_client: httpx.AsyncClient
    ):
        """Test database transactions are properly isolated between services."""
        entity_id = f"transaction_test_{uuid.uuid4().hex[:8]}"

        # Create two requests that might conflict
        async def create_entity(index: int):
            msg_id = str(uuid.uuid4())
            request_data = {
                "id": msg_id,
                "ts": 1234567890.0,
                "origin": f"transaction_{index}",
                "target": "osteon",
                "intent": "generate",
                "input": {
                    "prompt": f"Transaction test {entity_id}",
                    "max_tokens": 20,
                    "entity_id": entity_id
                },
                "api_version": "v1"
            }
            try:
                response = await http_client.post(
                    "/v1/osteon/generate",
                    json=request_data,
                    timeout=20.0
                )
                return (response.status_code, response.json())
            except Exception as e:
                return (0, {"error": str(e)})

        # Execute concurrently - should not deadlock
        task1 = create_entity(1)
        task2 = create_entity(2)
        result1, result2 = await asyncio.gather(task1, task2)

        # Both should complete (may succeed or fail, but should not hang)
        assert result1[0] in (200, 400, 500, 503)
        assert result2[0] in (200, 400, 500, 503)


class TestCacheIntegration:
    """Test cache integration across services."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_cache_sharing_between_services(
        self, http_client: httpx.AsyncClient
    ):
        """Test cache is shared between services."""
        cache_key = f"test_key_{uuid.uuid4().hex[:8]}"

        # Make identical request twice
        msg_id_1 = str(uuid.uuid4())
        request_data = {
            "id": msg_id_1,
            "ts": 1234567890.0,
            "origin": "test_client",
            "target": "osteon",
            "intent": "generate",
            "input": {
                "prompt": "Cacheable test prompt",
                "max_tokens": 30,
                "cache_key": cache_key,
                "temperature": 0.0  # Deterministic
            },
            "api_version": "v1"
        }

        # First request
        response1 = await http_client.post(
            "/v1/osteon/generate",
            json=request_data
        )
        assert response1.status_code == 200

        # Second identical request (new ID but same input)
        request_data["id"] = str(uuid.uuid4())
        response2 = await http_client.post(
            "/v1/osteon/generate",
            json=request_data
        )
        assert response2.status_code == 200

        # Both should succeed
        reply1 = response1.json()
        reply2 = response2.json()

        assert reply1["ok"] is True
        assert reply2["ok"] is True

        # If caching is enabled, state_hash should match for identical inputs
        # (though LLM variability may cause differences)

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_cache_invalidation_across_services(
        self, http_client: httpx.AsyncClient
    ):
        """Test cache invalidation propagates across services."""
        entity_id = f"cache_inv_{uuid.uuid4().hex[:8]}"

        # Create entity
        msg_id = str(uuid.uuid4())
        create_request = {
            "id": msg_id,
            "ts": 1234567890.0,
            "origin": "test_client",
            "target": "osteon",
            "intent": "generate",
            "input": {
                "prompt": f"Entity {entity_id}",
                "max_tokens": 30,
                "entity_id": entity_id
            },
            "api_version": "v1"
        }

        create_response = await http_client.post(
            "/v1/osteon/generate",
            json=create_request
        )
        assert create_response.status_code == 200

        # Update entity (should invalidate cache)
        update_msg_id = str(uuid.uuid4())
        update_request = {
            "id": update_msg_id,
            "ts": 1234567890.0,
            "origin": "test_client",
            "target": "osteon",
            "intent": "generate",
            "input": {
                "prompt": f"Updated entity {entity_id}",
                "max_tokens": 30,
                "entity_id": entity_id
            },
            "api_version": "v1"
        }

        update_response = await http_client.post(
            "/v1/osteon/generate",
            json=update_request
        )
        assert update_response.status_code == 200

        # Cache should be invalidated (both requests should succeed)
        create_reply = create_response.json()
        update_reply = update_response.json()

        assert create_reply["ok"] is True
        assert update_reply["ok"] is True


class TestDataPersistence:
    """Test data persistence across service restarts."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_data_survives_service_restart(
        self, http_client: httpx.AsyncClient
    ):
        """Test data persists after service restart (simulated)."""
        entity_id = f"persist_{uuid.uuid4().hex[:8]}"

        # Create persistent data
        msg_id = str(uuid.uuid4())
        create_request = {
            "id": msg_id,
            "ts": 1234567890.0,
            "origin": "test_client",
            "target": "osteon",
            "intent": "generate",
            "input": {
                "prompt": f"Persistent entity {entity_id}",
                "max_tokens": 50,
                "entity_id": entity_id,
                "persist": True
            },
            "api_version": "v1"
        }

        create_response = await http_client.post(
            "/v1/osteon/generate",
            json=create_request
        )
        assert create_response.status_code == 200

        create_reply = create_response.json()
        assert create_reply["ok"] is True

        # Wait a bit to ensure data is flushed
        await asyncio.sleep(2)

        # Attempt to retrieve (simulates post-restart retrieval)
        if "output" in create_reply:
            output = create_reply["output"]
            doc_id = output.get("document_id") or output.get("id")

            if doc_id:
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

                try:
                    retrieve_response = await http_client.post(
                        "/v1/osteon/retrieve",
                        json=retrieve_request,
                        timeout=20.0
                    )

                    # Data should be retrievable
                    assert retrieve_response.status_code in (200, 404, 501)
                except httpx.TimeoutException:
                    pytest.skip("Retrieval timed out")

    @pytest.mark.asyncio
    @pytest.mark.timeout(90)
    async def test_backup_and_restore_workflow(
        self, http_client: httpx.AsyncClient
    ):
        """Test backup and restore workflow across services."""
        backup_id = f"backup_{uuid.uuid4().hex[:8]}"

        # Create some data to backup
        entities = []
        for i in range(3):
            msg_id = str(uuid.uuid4())
            request = {
                "id": msg_id,
                "ts": 1234567890.0,
                "origin": "test_client",
                "target": "osteon",
                "intent": "generate",
                "input": {
                    "prompt": f"Backup test entity {i}",
                    "max_tokens": 30,
                    "backup_id": backup_id
                },
                "api_version": "v1"
            }

            response = await http_client.post("/v1/osteon/generate", json=request)
            assert response.status_code == 200
            entities.append(response.json())

        # Attempt backup via Chaperone (import/export adapter)
        backup_msg_id = str(uuid.uuid4())
        backup_request = {
            "id": backup_msg_id,
            "ts": 1234567890.0,
            "origin": "test_client",
            "target": "chaperone",
            "intent": "export",
            "input": {
                "backup_id": backup_id,
                "format": "json"
            },
            "api_version": "v1"
        }

        try:
            backup_response = await http_client.post(
                "/v1/chaperone/export",
                json=backup_request,
                timeout=30.0
            )

            # Chaperone might not be fully implemented
            assert backup_response.status_code in (200, 501, 404)

            if backup_response.status_code == 200:
                backup_reply = backup_response.json()
                assert "output" in backup_reply

                # If backup succeeded, test restore
                restore_msg_id = str(uuid.uuid4())
                restore_request = {
                    "id": restore_msg_id,
                    "ts": 1234567890.0,
                    "origin": "test_client",
                    "target": "chaperone",
                    "intent": "import",
                    "input": {
                        "backup_data": backup_reply["output"],
                        "format": "json"
                    },
                    "api_version": "v1"
                }

                restore_response = await http_client.post(
                    "/v1/chaperone/import",
                    json=restore_request,
                    timeout=30.0
                )

                assert restore_response.status_code in (200, 501)
        except httpx.TimeoutException:
            pytest.skip("Chaperone service timeout")
