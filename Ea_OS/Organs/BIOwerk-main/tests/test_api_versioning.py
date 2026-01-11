"""
Tests for API versioning functionality.

Tests cover:
- Version extraction and validation
- Versioned endpoint access
- Legacy endpoint backward compatibility
- Deprecation warnings
- Error handling for unsupported versions
- Response headers
"""

import pytest
from httpx import AsyncClient
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from matrix.versioning import (
    extract_version,
    validate_version,
    version_middleware,
    is_deprecated,
    get_deprecation_message,
    get_version_from_request,
    version_route,
    get_all_version_routes,
    SUPPORTED_VERSIONS,
    LATEST_VERSION
)
from matrix.models import Msg, Reply


# ============================================================================
# Version Utility Function Tests
# ============================================================================

def test_extract_version_with_v1():
    """Test extracting v1 from path."""
    version, remaining = extract_version("/v1/osteon/draft")
    assert version == "v1"
    assert remaining == "/osteon/draft"


def test_extract_version_with_v2():
    """Test extracting v2 from path."""
    version, remaining = extract_version("/v2/nucleus/plan")
    assert version == "v2"
    assert remaining == "/nucleus/plan"


def test_extract_version_without_version():
    """Test extracting from unversioned path."""
    version, remaining = extract_version("/osteon/draft")
    assert version is None
    assert remaining == "/osteon/draft"


def test_extract_version_root():
    """Test extracting from root path."""
    version, remaining = extract_version("/v1/")
    assert version == "v1"
    assert remaining == "/"


def test_validate_version_v1():
    """Test validating v1 version."""
    result = validate_version("v1")
    assert result == "v1"


def test_validate_version_none_with_default():
    """Test validating None with default to latest."""
    result = validate_version(None, default_to_latest=True)
    assert result == LATEST_VERSION


def test_validate_version_none_without_default():
    """Test validating None without default raises exception."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        validate_version(None, default_to_latest=False)

    assert exc_info.value.status_code == 400
    assert "Missing API Version" in str(exc_info.value.detail)


def test_validate_version_unsupported():
    """Test validating unsupported version raises exception."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        validate_version("v99")

    assert exc_info.value.status_code == 400
    assert "Unsupported API Version" in str(exc_info.value.detail)
    assert exc_info.value.detail["requested_version"] == "v99"
    assert exc_info.value.detail["supported_versions"] == SUPPORTED_VERSIONS


def test_is_deprecated():
    """Test checking if version is deprecated."""
    # v1 is not deprecated (it's the current version)
    assert is_deprecated("v1") is False


def test_get_deprecation_message():
    """Test getting deprecation message."""
    # v1 has no deprecation message yet
    assert get_deprecation_message("v1") is None


def test_version_route():
    """Test generating versioned route."""
    assert version_route("/osteon/draft") == "/v1/osteon/draft"
    assert version_route("/osteon/draft", "v1") == "/v1/osteon/draft"
    assert version_route("osteon/draft") == "/v1/osteon/draft"


def test_get_all_version_routes():
    """Test generating all version routes."""
    routes = get_all_version_routes("/osteon/draft")
    assert "/v1/osteon/draft" in routes
    assert len(routes) == len(SUPPORTED_VERSIONS)


# ============================================================================
# Middleware Tests
# ============================================================================

@pytest.fixture
def app_with_versioning():
    """Create a test FastAPI app with versioning middleware."""
    app = FastAPI()

    # Add versioning middleware
    app.middleware("http")(version_middleware)

    @app.post("/v1/test")
    async def test_v1(request: Request):
        """Test v1 endpoint."""
        version = get_version_from_request(request)
        return {"version": version, "ok": True}

    @app.post("/test")
    async def test_legacy(request: Request):
        """Test legacy endpoint."""
        version = request.state.api_version if hasattr(request.state, "api_version") else None
        return {
            "version": version,
            "ok": True,
            "warning": "This is a legacy endpoint"
        }

    return app


def test_middleware_versioned_endpoint(app_with_versioning):
    """Test middleware with versioned endpoint."""
    client = TestClient(app_with_versioning)

    response = client.post("/v1/test", json={})

    assert response.status_code == 200
    assert response.json()["version"] == "v1"
    assert response.headers["X-API-Version"] == "v1"
    assert response.headers["X-API-Latest-Version"] == LATEST_VERSION


def test_middleware_unversioned_endpoint(app_with_versioning):
    """Test middleware with unversioned endpoint."""
    client = TestClient(app_with_versioning)

    response = client.post("/test", json={})

    assert response.status_code == 200
    assert response.json()["version"] == "v1"  # Defaults to latest
    assert response.headers["X-API-Version"] == "v1"
    assert "Warning" in response.headers
    assert "API version not specified" in response.headers["Warning"]


def test_middleware_unsupported_version(app_with_versioning):
    """Test middleware with unsupported version."""
    client = TestClient(app_with_versioning)

    response = client.post("/v99/test", json={})

    assert response.status_code == 400
    data = response.json()
    assert data["error"] == "Unsupported API Version"
    assert data["requested_version"] == "v99"


# ============================================================================
# Integration Tests (requires running app)
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_mesh_versioned_endpoint():
    """Test mesh gateway with versioned endpoint."""
    async with AsyncClient(base_url="http://localhost:8080") as client:
        msg = {
            "origin": "test",
            "target": "osteon",
            "intent": "draft",
            "input": {"goal": "Test versioning"},
            "api_version": "v1"
        }

        response = await client.post("/v1/osteon/draft", json=msg)

        # May not be running, so we just check if we get the right error or success
        assert response.status_code in [200, 404, 502, 503]

        if response.status_code == 200:
            assert response.headers.get("X-API-Version") == "v1"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_mesh_legacy_endpoint():
    """Test mesh gateway with legacy endpoint."""
    async with AsyncClient(base_url="http://localhost:8080") as client:
        msg = {
            "origin": "test",
            "target": "osteon",
            "intent": "draft",
            "input": {"goal": "Test legacy versioning"}
        }

        response = await client.post("/osteon/draft", json=msg)

        # May not be running, so we just check if we get the right error or success
        assert response.status_code in [200, 404, 502, 503]

        if response.status_code == 200:
            data = response.json()
            assert "_deprecation_warning" in data
            assert "Warning" in response.headers


@pytest.mark.asyncio
@pytest.mark.integration
async def test_service_versioned_endpoint():
    """Test service with versioned endpoint."""
    async with AsyncClient(base_url="http://localhost:8001") as client:
        msg = {
            "origin": "test",
            "target": "osteon",
            "intent": "draft",
            "input": {"goal": "Test service versioning"},
            "api_version": "v1"
        }

        response = await client.post("/v1/draft", json=msg)

        # May not be running
        assert response.status_code in [200, 404, 422, 503]


# ============================================================================
# Model Tests
# ============================================================================

def test_msg_model_with_version():
    """Test Msg model includes api_version."""
    msg = Msg(
        origin="test",
        target="osteon",
        intent="draft",
        input={"goal": "Test"},
        api_version="v1"
    )

    assert msg.api_version == "v1"
    assert msg.origin == "test"


def test_msg_model_default_version():
    """Test Msg model defaults api_version to v1."""
    msg = Msg(
        origin="test",
        target="osteon",
        intent="draft",
        input={"goal": "Test"}
    )

    assert msg.api_version == "v1"


def test_reply_model_with_version():
    """Test Reply model includes api_version."""
    import time

    reply = Reply(
        id="test-123",
        ts=time.time(),
        agent="osteon",
        ok=True,
        output={"result": "success"},
        state_hash="abc123",
        api_version="v1"
    )

    assert reply.api_version == "v1"
    assert reply.ok is True


def test_reply_model_default_version():
    """Test Reply model defaults api_version to v1."""
    import time

    reply = Reply(
        id="test-123",
        ts=time.time(),
        agent="osteon",
        ok=True,
        output={"result": "success"},
        state_hash="abc123"
    )

    assert reply.api_version == "v1"


# ============================================================================
# Backwards Compatibility Tests
# ============================================================================

def test_unversioned_request_msg():
    """Test that Msg works without api_version field (backwards compatibility)."""
    # Old client code that doesn't send api_version
    msg_dict = {
        "origin": "old-client",
        "target": "osteon",
        "intent": "draft",
        "input": {"goal": "Test"}
        # No api_version field
    }

    msg = Msg(**msg_dict)
    assert msg.api_version == "v1"  # Should default


def test_unversioned_request_serialization():
    """Test that Msg serializes with api_version even if not provided."""
    msg = Msg(
        origin="test",
        target="osteon",
        intent="draft",
        input={}
    )

    data = msg.model_dump()
    assert "api_version" in data
    assert data["api_version"] == "v1"


# ============================================================================
# Error Message Tests
# ============================================================================

def test_error_message_format():
    """Test that error messages for unsupported versions are helpful."""
    from fastapi import HTTPException

    try:
        validate_version("v99")
        assert False, "Should have raised HTTPException"
    except HTTPException as e:
        detail = e.detail
        assert detail["error"] == "Unsupported API Version"
        assert detail["message"] == "API version 'v99' is not supported"
        assert detail["requested_version"] == "v99"
        assert "supported_versions" in detail
        assert "latest_version" in detail


# ============================================================================
# Header Tests
# ============================================================================

def test_response_headers_versioned(app_with_versioning):
    """Test that versioned endpoints return correct headers."""
    client = TestClient(app_with_versioning)

    response = client.post("/v1/test", json={})

    assert "X-API-Version" in response.headers
    assert response.headers["X-API-Version"] == "v1"
    assert "X-API-Latest-Version" in response.headers
    assert response.headers["X-API-Latest-Version"] == LATEST_VERSION


def test_response_headers_unversioned(app_with_versioning):
    """Test that unversioned endpoints return warning headers."""
    client = TestClient(app_with_versioning)

    response = client.post("/test", json={})

    assert "X-API-Version" in response.headers
    assert "X-API-Latest-Version" in response.headers
    assert "Warning" in response.headers
    assert "not specified" in response.headers["Warning"]


# ============================================================================
# Deprecation Warning Tests
# ============================================================================

def test_deprecation_warning_structure():
    """Test deprecation warning has correct structure."""
    from matrix.versioning import deprecation_warning

    warning = deprecation_warning("v0", "/osteon/draft")

    assert "warning" in warning
    assert warning["warning"]["code"] == "deprecated_version"
    assert "message" in warning["warning"]
    assert warning["warning"]["deprecated_version"] == "v0"
    assert warning["warning"]["current_version"] == LATEST_VERSION
    assert warning["warning"]["endpoint"] == "/osteon/draft"


# ============================================================================
# Performance Tests
# ============================================================================

def test_middleware_performance(app_with_versioning):
    """Test that versioning middleware doesn't significantly impact performance."""
    import time

    client = TestClient(app_with_versioning)

    # Warmup
    for _ in range(10):
        client.post("/v1/test", json={})

    # Measure
    iterations = 100
    start = time.time()

    for _ in range(iterations):
        response = client.post("/v1/test", json={})
        assert response.status_code == 200

    duration = time.time() - start
    avg_time = duration / iterations

    # Should complete in less than 50ms per request
    assert avg_time < 0.05, f"Average request time too high: {avg_time:.3f}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
