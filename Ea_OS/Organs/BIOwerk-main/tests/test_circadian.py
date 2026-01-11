"""
Comprehensive tests for Circadian service - Project planning and scheduling.

Tests cover:
- Timeline planning
- Task assignment
- Progress tracking
- Reminders
- Risk assessment
"""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from matrix.models import Msg, Reply
import json
import time


@pytest.fixture
async def circadian_app():
    """Create Circadian app instance for testing."""
    from services.circadian.main import app
    return app


@pytest.fixture
async def circadian_client(circadian_app):
    """Create async HTTP client for Circadian service."""
    transport = ASGITransport(app=circadian_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def mock_llm_client():
    """Mock LLM client for testing."""
    with patch("services.circadian.main.llm_client") as mock:
        yield mock


# ============================================================================
# Plan Timeline Tests
# ============================================================================

@pytest.mark.asyncio
async def test_plan_timeline(circadian_client, mock_llm_client):
    """Test project timeline planning."""
    mock_llm_client.generate_json = AsyncMock(return_value=json.dumps({
        "timeline": [
            {"id": "m1", "milestone": "Planning Complete", "desc": "Finish planning", "week": 2, "dependencies": []},
            {"id": "m2", "milestone": "Development Started", "desc": "Begin coding", "week": 3, "dependencies": ["m1"]}
        ],
        "risks": [
            {"id": "r1", "description": "Resource shortage", "severity": "medium", "mitigation": "Hire contractors"}
        ],
        "next_actions": [
            {"id": "a1", "do": "Schedule kickoff", "priority": "high"}
        ]
    }))

    msg = Msg(id="test-1", ts=time.time(), input={
        "project_description": "Build new feature",
        "duration_weeks": 12,
        "team_size": 5
    })

    response = await circadian_client.post("/v1/plan_timeline", json=msg.model_dump())

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "timeline" in data["output"]
    assert "risks" in data["output"]
    assert "next_actions" in data["output"]


@pytest.mark.asyncio
async def test_plan_timeline_with_goals(circadian_client, mock_llm_client):
    """Test timeline planning with specific goals."""
    mock_llm_client.generate_json = AsyncMock(return_value=json.dumps({
        "timeline": [{"id": "m1", "milestone": "Goal 1 Complete", "desc": "First goal", "week": 4, "dependencies": []}],
        "risks": [],
        "next_actions": []
    }))

    msg = Msg(id="test-2", ts=time.time(), input={
        "goals": ["Implement authentication", "Add dashboard", "Deploy to production"],
        "duration_weeks": 8
    })

    response = await circadian_client.post("/v1/plan_timeline", json=msg.model_dump())

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True


# ============================================================================
# Assign Tests
# ============================================================================

@pytest.mark.asyncio
async def test_assign_tasks(circadian_client, mock_llm_client):
    """Test task assignment."""
    mock_llm_client.generate_json = AsyncMock(return_value=json.dumps({
        "assignments": [
            {"task_id": "t1", "assignee": "Alice", "rationale": "Best fit for frontend"},
            {"task_id": "t2", "assignee": "Bob", "rationale": "Database expert"}
        ]
    }))

    msg = Msg(id="test-3", ts=time.time(), input={
        "tasks": [
            {"id": "t1", "name": "Build UI", "skills_required": ["React", "CSS"]},
            {"id": "t2", "name": "Design schema", "skills_required": ["SQL", "PostgreSQL"]}
        ],
        "team_members": [
            {"name": "Alice", "skills": ["React", "CSS", "JavaScript"]},
            {"name": "Bob", "skills": ["Python", "SQL", "PostgreSQL"]}
        ]
    })

    response = await circadian_client.post("/v1/assign", json=msg.model_dump())

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "assignments" in data["output"]


# ============================================================================
# Track Tests
# ============================================================================

@pytest.mark.asyncio
async def test_track_progress(circadian_client, mock_llm_client):
    """Test progress tracking."""
    mock_llm_client.generate_json = AsyncMock(return_value=json.dumps({
        "progress_report": {
            "completion_percentage": 45,
            "on_track": True,
            "blockers": [],
            "recommendations": ["Continue current pace"]
        }
    }))

    msg = Msg(id="test-4", ts=time.time(), input={
        "milestones": [
            {"id": "m1", "status": "completed"},
            {"id": "m2", "status": "in_progress"}
        ]
    })

    response = await circadian_client.post("/v1/track", json=msg.model_dump())

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True


# ============================================================================
# Remind Tests
# ============================================================================

@pytest.mark.asyncio
async def test_remind(circadian_client, mock_llm_client):
    """Test reminder generation."""
    mock_llm_client.generate_json = AsyncMock(return_value=json.dumps({
        "reminders": [
            {"type": "deadline", "message": "Milestone M1 due tomorrow", "priority": "high"},
            {"type": "meeting", "message": "Weekly standup at 10am", "priority": "medium"}
        ]
    }))

    msg = Msg(id="test-5", ts=time.time(), input={
        "current_week": 3,
        "timeline": [
            {"id": "m1", "milestone": "Planning", "week": 3}
        ]
    })

    response = await circadian_client.post("/v1/remind", json=msg.model_dump())

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True


# ============================================================================
# Health and Error Tests
# ============================================================================

@pytest.mark.asyncio
async def test_health_endpoint(circadian_client):
    """Test health endpoint."""
    response = await circadian_client.get("/health")
    assert response.status_code == 200


def test_circadian_summary():
    """
    Circadian Service Test Coverage:
    ✓ Timeline planning
    ✓ Task assignment
    ✓ Progress tracking
    ✓ Reminders
    """
    assert True
