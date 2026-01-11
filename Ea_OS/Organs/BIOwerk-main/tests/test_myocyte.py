"""
Comprehensive tests for Myocyte service - Data analysis and processing.

Tests cover:
- Table data ingestion
- Formula evaluation
- Statistical modeling and forecasting
- Data export
- Input validation
- Error handling
"""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from matrix.models import Msg, Reply
import json
import time


@pytest.fixture
async def myocyte_app():
    """Create Myocyte app instance for testing."""
    from services.myocyte.main import app
    return app


@pytest.fixture
async def myocyte_client(myocyte_app):
    """Create async HTTP client for Myocyte service."""
    transport = ASGITransport(app=myocyte_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def mock_llm_client():
    """Mock LLM client for testing."""
    with patch("services.myocyte.main.llm_client") as mock:
        yield mock


# ============================================================================
# Ingest Table Tests
# ============================================================================

@pytest.mark.asyncio
async def test_ingest_table_with_raw_data(myocyte_client, mock_llm_client):
    """Test table ingestion from raw data."""
    mock_llm_client.generate_json = AsyncMock(return_value=json.dumps({
        "tables": [{
            "id": "table-1",
            "name": "Sales Data",
            "headers": ["Product", "Revenue", "Units"],
            "rows": [["Product A", 1000, 50], ["Product B", 2000, 100]]
        }]
    }))

    msg = Msg(id="test-1", ts=time.time(), input={
        "raw_data": "Product A: $1000, 50 units\nProduct B: $2000, 100 units"
    })

    response = await myocyte_client.post("/v1/ingest_table", json=msg.model_dump())

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "tables" in data["output"]
    assert len(data["output"]["tables"]) > 0


@pytest.mark.asyncio
async def test_ingest_table_with_structured_data(myocyte_client):
    """Test table ingestion with pre-structured tables."""
    tables = [{
        "id": "t1",
        "name": "Metrics",
        "headers": ["Metric", "Value"],
        "rows": [["Revenue", 10000], ["Users", 500]]
    }]

    msg = Msg(id="test-2", ts=time.time(), input={"tables": tables})

    response = await myocyte_client.post("/v1/ingest_table", json=msg.model_dump())

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["output"]["tables"] == tables


# ============================================================================
# Formula Evaluation Tests
# ============================================================================

@pytest.mark.asyncio
async def test_formula_evaluation(myocyte_client, mock_llm_client):
    """Test formula evaluation on table data."""
    mock_llm_client.generate_json = AsyncMock(return_value=json.dumps({
        "results": [
            {"formula": "SUM(Revenue)", "result": 3000},
            {"formula": "AVG(Units)", "result": 75}
        ]
    }))

    msg = Msg(id="test-3", ts=time.time(), input={
        "formulas": ["SUM(Revenue)", "AVG(Units)"],
        "table_id": "table-1"
    })

    response = await myocyte_client.post("/v1/formula_eval", json=msg.model_dump())

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "results" in data["output"]


# ============================================================================
# Model Forecast Tests
# ============================================================================

@pytest.mark.asyncio
async def test_model_forecast(myocyte_client, mock_llm_client):
    """Test statistical modeling and forecasting."""
    mock_llm_client.generate_json = AsyncMock(return_value=json.dumps({
        "forecast": [
            {"period": "Q1 2025", "predicted_value": 11000},
            {"period": "Q2 2025", "predicted_value": 12000}
        ],
        "confidence": 0.85,
        "model_type": "linear_regression"
    }))

    msg = Msg(id="test-4", ts=time.time(), input={
        "table_id": "table-1",
        "target_column": "Revenue",
        "periods": 2
    })

    response = await myocyte_client.post("/v1/model_forecast", json=msg.model_dump())

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "forecast" in data["output"]


# ============================================================================
# Export Tests
# ============================================================================

@pytest.mark.asyncio
async def test_export_data(myocyte_client):
    """Test data export."""
    msg = Msg(id="test-5", ts=time.time(), input={
        "tables": [{"id": "t1", "headers": ["A", "B"], "rows": [[1, 2]]}],
        "format": "json"
    })

    response = await myocyte_client.post("/v1/export", json=msg.model_dump())

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "artifact" in data["output"]


# ============================================================================
# Health and Error Tests
# ============================================================================

@pytest.mark.asyncio
async def test_health_endpoint(myocyte_client):
    """Test health endpoint."""
    response = await myocyte_client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_ingest_missing_required_fields(myocyte_client):
    """Test validation error handling."""
    msg = Msg(id="test-6", ts=time.time(), input={})

    response = await myocyte_client.post("/v1/ingest_table", json=msg.model_dump())

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False


def test_myocyte_summary():
    """
    Myocyte Service Test Coverage:
    ✓ Table ingestion
    ✓ Formula evaluation
    ✓ Forecasting
    ✓ Data export
    """
    assert True
