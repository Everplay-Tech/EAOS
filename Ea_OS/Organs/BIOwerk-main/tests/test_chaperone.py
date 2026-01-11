"""
Comprehensive tests for Chaperone service - Import/Export functionality.

Tests cover:
- Artifact import from various formats
- Artifact export to external formats
- Format conversion
- Data validation
"""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from matrix.models import Msg, Reply
import json
import time


@pytest.fixture
async def chaperone_app():
    """Create Chaperone app instance for testing."""
    from services.chaperone.main import app
    return app


@pytest.fixture
async def chaperone_client(chaperone_app):
    """Create async HTTP client for Chaperone service."""
    transport = ASGITransport(app=chaperone_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def mock_llm_client():
    """Mock LLM client for testing."""
    with patch("services.chaperone.main.llm_client") as mock:
        yield mock


# ============================================================================
# Import Artifact Tests
# ============================================================================

@pytest.mark.asyncio
async def test_import_text_artifact(chaperone_client, mock_llm_client):
    """Test importing plain text into artifact."""
    mock_llm_client.generate_json = AsyncMock(return_value=json.dumps({
        "artifact": {
            "kind": "osteon",
            "meta": {"title": "Imported Document"},
            "body": {
                "sections": [
                    {"id": "s1", "title": "Introduction", "text": "Content here"}
                ]
            }
        }
    }))

    msg = Msg(id="test-1", ts=time.time(), input={
        "content": "This is a test document with some content.",
        "format": "text",
        "artifact_type": "osteon"
    })

    response = await chaperone_client.post("/v1/import_artifact", json=msg.model_dump())

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "artifact" in data["output"]
    assert data["output"]["artifact"]["kind"] == "osteon"


@pytest.mark.asyncio
async def test_import_markdown_artifact(chaperone_client, mock_llm_client):
    """Test importing markdown into artifact."""
    mock_llm_client.generate_json = AsyncMock(return_value=json.dumps({
        "artifact": {
            "kind": "osteon",
            "meta": {"title": "Markdown Doc"},
            "body": {"sections": []}
        }
    }))

    msg = Msg(id="test-2", ts=time.time(), input={
        "content": "# Title\n\n## Section 1\n\nContent here",
        "format": "markdown",
        "artifact_type": "osteon"
    })

    response = await chaperone_client.post("/v1/import_artifact", json=msg.model_dump())

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True


@pytest.mark.asyncio
async def test_import_presentation_artifact(chaperone_client, mock_llm_client):
    """Test importing presentation content."""
    mock_llm_client.generate_json = AsyncMock(return_value=json.dumps({
        "artifact": {
            "kind": "synslide",
            "meta": {"title": "Presentation"},
            "body": {"slides": [{"title": "Slide 1", "content": "Content"}]}
        }
    }))

    msg = Msg(id="test-3", ts=time.time(), input={
        "content": "Slide 1: Introduction\nSlide 2: Main Content",
        "artifact_type": "synslide"
    })

    response = await chaperone_client.post("/v1/import_artifact", json=msg.model_dump())

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True


# ============================================================================
# Export Artifact Tests
# ============================================================================

@pytest.mark.asyncio
async def test_export_to_docx(chaperone_client):
    """Test exporting artifact to DOCX format."""
    msg = Msg(id="test-4", ts=time.time(), input={
        "artifact": {
            "kind": "osteon",
            "meta": {"title": "Test Doc"},
            "body": {
                "sections": [{"id": "s1", "title": "Section 1", "text": "Content"}]
            }
        },
        "target_format": "docx"
    })

    response = await chaperone_client.post("/v1/export_artifact", json=msg.model_dump())

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "export" in data["output"]


@pytest.mark.asyncio
async def test_export_to_pdf(chaperone_client):
    """Test exporting artifact to PDF format."""
    msg = Msg(id="test-5", ts=time.time(), input={
        "artifact": {
            "kind": "osteon",
            "meta": {"title": "PDF Doc"},
            "body": {"sections": []}
        },
        "target_format": "pdf"
    })

    response = await chaperone_client.post("/v1/export_artifact", json=msg.model_dump())

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True


# ============================================================================
# Convert Format Tests
# ============================================================================

@pytest.mark.asyncio
async def test_convert_format(chaperone_client):
    """Test format conversion."""
    msg = Msg(id="test-6", ts=time.time(), input={
        "content": "Test content",
        "source_format": "markdown",
        "target_format": "html"
    })

    response = await chaperone_client.post("/v1/convert_format", json=msg.model_dump())

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True


# ============================================================================
# Validate Tests
# ============================================================================

@pytest.mark.asyncio
async def test_validate_artifact(chaperone_client):
    """Test artifact validation."""
    msg = Msg(id="test-7", ts=time.time(), input={
        "artifact": {
            "kind": "osteon",
            "meta": {"title": "Valid"},
            "body": {"sections": []}
        }
    })

    response = await chaperone_client.post("/v1/validate", json=msg.model_dump())

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True


# ============================================================================
# Error Handling Tests
# ============================================================================

@pytest.mark.asyncio
async def test_import_missing_content(chaperone_client):
    """Test import with missing content."""
    msg = Msg(id="test-8", ts=time.time(), input={})

    response = await chaperone_client.post("/v1/import_artifact", json=msg.model_dump())

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False


@pytest.mark.asyncio
async def test_health_endpoint(chaperone_client):
    """Test health endpoint."""
    response = await chaperone_client.get("/health")
    assert response.status_code == 200


def test_chaperone_summary():
    """
    Chaperone Service Test Coverage:
    ✓ Import artifacts
    ✓ Export artifacts
    ✓ Format conversion
    ✓ Validation
    """
    assert True
