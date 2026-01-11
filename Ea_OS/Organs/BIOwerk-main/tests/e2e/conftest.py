"""
E2E Test Configuration and Fixtures
"""
import os
import asyncio
import pytest
import httpx
from typing import Dict, AsyncGenerator


@pytest.fixture(scope="session")
def mesh_url() -> str:
    """Get the mesh service URL from environment or use default."""
    return os.getenv("MESH_URL", "http://localhost:8080")


@pytest.fixture(scope="session")
def test_timeout() -> int:
    """Default timeout for E2E tests in seconds."""
    return 120


@pytest.fixture(scope="session")
async def http_client(mesh_url: str) -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    Provides an async HTTP client for E2E tests with proper timeouts and retries.
    """
    timeout = httpx.Timeout(
        connect=10.0,
        read=60.0,
        write=30.0,
        pool=10.0
    )

    transport = httpx.AsyncHTTPTransport(
        retries=3,
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
    )

    async with httpx.AsyncClient(
        base_url=mesh_url,
        timeout=timeout,
        transport=transport,
        follow_redirects=True
    ) as client:
        yield client


@pytest.fixture(scope="session")
async def wait_for_services(mesh_url: str) -> None:
    """
    Wait for all services to be ready before running tests.
    Implements exponential backoff retry logic.
    """
    max_retries = 30
    retry_delay = 2

    async with httpx.AsyncClient(timeout=10.0) as client:
        for attempt in range(max_retries):
            try:
                # Check mesh health endpoint
                response = await client.get(f"{mesh_url}/health")
                if response.status_code == 200:
                    health_data = response.json()
                    if health_data.get("status") == "healthy":
                        print(f"✓ Services ready after {attempt + 1} attempts")
                        return
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 1.5, 30)  # Exponential backoff
                else:
                    raise RuntimeError(
                        f"Services not ready after {max_retries} attempts: {e}"
                    )

        raise RuntimeError("Services health check never returned healthy status")


@pytest.fixture(autouse=True)
async def ensure_services_ready(wait_for_services):
    """Auto-use fixture to ensure services are ready for each test."""
    pass


@pytest.fixture
def sample_document_request() -> Dict:
    """Sample request for document generation workflow."""
    return {
        "input": {
            "type": "business_report",
            "topic": "Q4 Financial Summary",
            "sections": ["executive_summary", "financial_data", "projections"],
            "length": "medium"
        }
    }


@pytest.fixture
def sample_data_analysis_request() -> Dict:
    """Sample request for data analysis workflow."""
    return {
        "input": {
            "type": "sales_analysis",
            "data": [
                {"month": "Jan", "sales": 1000, "costs": 600},
                {"month": "Feb", "sales": 1200, "costs": 650},
                {"month": "Mar", "sales": 1100, "costs": 620}
            ],
            "metrics": ["total_revenue", "profit_margin", "trend"]
        }
    }


@pytest.fixture
def sample_presentation_request() -> Dict:
    """Sample request for presentation generation workflow."""
    return {
        "input": {
            "title": "Product Launch Strategy",
            "slides": [
                {"type": "title", "content": "New Product Launch"},
                {"type": "agenda", "items": ["Market Analysis", "Strategy", "Timeline"]},
                {"type": "content", "heading": "Market Opportunity", "points": [
                    "Growing demand in target segment",
                    "Competitive advantage",
                    "Revenue projections"
                ]}
            ]
        }
    }


@pytest.fixture
def sample_task_planning_request() -> Dict:
    """Sample request for task planning workflow."""
    return {
        "input": {
            "project": "Website Redesign",
            "deadline": "2025-12-31",
            "tasks": [
                {"name": "Design mockups", "duration": 5, "priority": "high"},
                {"name": "Develop frontend", "duration": 10, "priority": "high"},
                {"name": "Backend integration", "duration": 7, "priority": "medium"},
                {"name": "Testing", "duration": 3, "priority": "high"}
            ]
        }
    }
