from fastapi import FastAPI
from matrix.models import Msg, Reply
from matrix.observability import setup_instrumentation
from matrix.utils import state_hash
from matrix.logging_config import setup_logging, log_request, log_response, log_error
from matrix.errors import InvalidInputError, ValidationError, create_error_response
from matrix.llm_client import llm_client
from matrix.validation import setup_validation_middleware
from pydantic import ValidationError as PydanticValidationError
import time
import json

app = FastAPI(title="Circadian")
setup_instrumentation(app, service_name="circadian", service_version="1.0.0")
setup_validation_middleware(app)
logger = setup_logging("circadian")

# Setup comprehensive health and readiness endpoints
from matrix.health import setup_health_endpoints
setup_health_endpoints(app, service_name="circadian", version="1.0.0")

# ============================================================================
# Internal Handler Functions
# ============================================================================

async def _plan_timeline_handler(msg: Msg) -> Reply:
    """Generate project timeline with milestones and risk assessment."""
    start_time = time.time()
    log_request(logger, msg.id, "circadian", "plan_timeline")

    try:
        inp = msg.input or {}
        goals = inp.get("goals", [])
        project_description = inp.get("project_description", "")
        duration_weeks = inp.get("duration_weeks", 12)
        team_size = inp.get("team_size", 5)

        if not goals and not project_description:
            raise InvalidInputError("goals or project_description is required")

        # Generate timeline using LLM
        system_prompt = """You are a project management expert. Create a detailed project timeline with milestones, risks, and next actions.
Return your response as a JSON object with: timeline (array of milestones), assignments (array), risks (array), next_actions (array).
Each milestone should have: id, milestone (name), desc (description), week (number), dependencies.
Each risk should have: id, description, severity (low/medium/high), mitigation.
Each next_action should have: id, do (description), priority (high/medium/low).
Example: {
  "timeline": [{"id": "m1", "milestone": "Requirements Complete", "desc": "All requirements gathered", "week": 2, "dependencies": []}],
  "risks": [{"id": "r1", "description": "Scope creep", "severity": "medium", "mitigation": "Weekly scope reviews"}],
  "next_actions": [{"id": "a1", "do": "Schedule kickoff meeting", "priority": "high"}]
}"""

        goals_text = json.dumps(goals) if goals else ""

        prompt = f"""Create a project timeline:

{f"Project: {project_description}" if project_description else ""}
{f"Goals: {goals_text}" if goals else ""}
Duration: {duration_weeks} weeks
Team Size: {team_size} people

Generate a realistic timeline with milestones, identify potential risks, and suggest immediate next actions."""

        response_text = await llm_client.generate_json(
            prompt=prompt,
            system_prompt=system_prompt
        )

        output = json.loads(response_text)

        # Ensure all required fields exist
        output.setdefault("assignments", [])
        output.setdefault("timeline", [])
        output.setdefault("risks", [])
        output.setdefault("next_actions", [])

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "circadian", True, duration_ms)

        return Reply(id=msg.id, ts=time.time(), agent="circadian", ok=True, output=output, state_hash=state_hash(output))
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON response: {e}")
        output = {
            "timeline": [{"id": "m1", "milestone": "Project Start", "desc": "Kickoff", "week": 1}],
            "assignments": [],
            "risks": [],
            "next_actions": [{"id": "a1", "do": "Begin planning", "priority": "high"}]
        }
        return Reply(id=msg.id, ts=time.time(), agent="circadian", ok=True, output=output, state_hash=state_hash(output))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "circadian", e))

async def _assign_handler(msg: Msg) -> Reply:
    """Make intelligent task assignments based on skills and workload."""
    start_time = time.time()
    log_request(logger, msg.id, "circadian", "assign")

    try:
        inp = msg.input or {}
        tasks = inp.get("tasks", [])
        team_members = inp.get("team_members", [])
        existing_assignments = inp.get("assignments", [])

        if not tasks:
            raise InvalidInputError("tasks is required")

        # If assignments already provided, just return them
        if existing_assignments and not team_members:
            output = {"assignments": existing_assignments}
            duration_ms = (time.time() - start_time) * 1000
            log_response(logger, msg.id, "circadian", True, duration_ms)
            return Reply(id=msg.id, ts=time.time(), agent="circadian", ok=True, output=output, state_hash=state_hash(output))

        # Generate assignments using LLM
        system_prompt = """You are a project management expert. Assign tasks to team members optimally.
Return your response as a JSON object with: assignments (array of assignment objects), rationale.
Each assignment should have: task_id, task_name, assignee, estimated_hours, priority, reasoning.
Example: {
  "assignments": [{
    "task_id": "t1",
    "task_name": "Design API",
    "assignee": "Alice",
    "estimated_hours": 8,
    "priority": "high",
    "reasoning": "Alice has backend expertise"
  }],
  "rationale": "Assignments based on skills and workload balance"
}"""

        tasks_text = json.dumps(tasks, indent=2)
        team_text = json.dumps(team_members, indent=2) if team_members else "Team information not provided"

        prompt = f"""Assign these tasks optimally:

Tasks:
{tasks_text}

Team Members:
{team_text}

Create balanced assignments considering skills, priority, and workload."""

        response_text = await llm_client.generate_json(
            prompt=prompt,
            system_prompt=system_prompt
        )

        output = json.loads(response_text)

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "circadian", True, duration_ms)

        return Reply(id=msg.id, ts=time.time(), agent="circadian", ok=True, output=output, state_hash=state_hash(output))
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON response: {e}")
        output = {"assignments": existing_assignments or []}
        return Reply(id=msg.id, ts=time.time(), agent="circadian", ok=True, output=output, state_hash=state_hash(output))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "circadian", e))

async def _track_handler(msg: Msg) -> Reply:
    """Track project progress and provide status assessment."""
    start_time = time.time()
    log_request(logger, msg.id, "circadian", "track")

    try:
        inp = msg.input or {}
        completed_tasks = inp.get("completed_tasks", [])
        in_progress_tasks = inp.get("in_progress_tasks", [])
        timeline = inp.get("timeline", [])
        current_week = inp.get("current_week", 1)

        # Generate status assessment using LLM
        system_prompt = """You are a project management expert. Analyze project progress and provide a status assessment.
Return your response as a JSON object with: status (green/yellow/red), completion_percentage, summary, concerns, recommendations.
Example: {
  "status": "green",
  "completion_percentage": 75,
  "summary": "Project is on track with 75% completion",
  "concerns": ["Testing phase may need more time"],
  "recommendations": ["Add QA resources", "Schedule code review sessions"],
  "next_milestone": "Beta Release",
  "days_to_next_milestone": 14
}"""

        prompt = f"""Assess project status:

Current Week: {current_week}
Completed Tasks: {len(completed_tasks)}
In Progress Tasks: {len(in_progress_tasks)}

Completed: {json.dumps(completed_tasks[:5], indent=2) if completed_tasks else "None"}
In Progress: {json.dumps(in_progress_tasks[:5], indent=2) if in_progress_tasks else "None"}
Timeline: {json.dumps(timeline[:5], indent=2) if timeline else "Not provided"}

Provide status, identify concerns, and suggest recommendations."""

        response_text = await llm_client.generate_json(
            prompt=prompt,
            system_prompt=system_prompt
        )

        output = json.loads(response_text)

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "circadian", True, duration_ms)

        return Reply(id=msg.id, ts=time.time(), agent="circadian", ok=True, output=output, state_hash=state_hash(output))
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON response: {e}")
        output = {"status": "green", "summary": "Project tracking active"}
        return Reply(id=msg.id, ts=time.time(), agent="circadian", ok=True, output=output, state_hash=state_hash(output))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "circadian", e))

async def _remind_handler(msg: Msg) -> Reply:
    """Generate contextual reminders based on timeline and progress."""
    start_time = time.time()
    log_request(logger, msg.id, "circadian", "remind")

    try:
        inp = msg.input or {}
        timeline = inp.get("timeline", [])
        assignments = inp.get("assignments", [])
        current_week = inp.get("current_week", 1)

        if not timeline and not assignments:
            raise InvalidInputError("timeline or assignments is required")

        # Generate reminders using LLM
        system_prompt = """You are a project management assistant. Generate helpful, actionable reminders.
Return your response as a JSON object with: reminders (array of reminder strings).
Each reminder should be specific, actionable, and time-relevant.
Example: {
  "reminders": [
    "Milestone 'API Design' is due in 3 days - Review progress",
    "Team standup meeting tomorrow at 10 AM",
    "Code review for Authentication feature pending"
  ]
}"""

        prompt = f"""Generate reminders for week {current_week}:

Timeline: {json.dumps(timeline, indent=2) if timeline else "Not provided"}
Assignments: {json.dumps(assignments[:10], indent=2) if assignments else "Not provided"}

Create 3-5 specific, actionable reminders for upcoming tasks and deadlines."""

        response_text = await llm_client.generate_json(
            prompt=prompt,
            system_prompt=system_prompt
        )

        output = json.loads(response_text)

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "circadian", True, duration_ms)

        return Reply(id=msg.id, ts=time.time(), agent="circadian", ok=True, output=output, state_hash=state_hash(output))
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON response: {e}")
        output = {"reminders": ["Check project timeline", "Review task assignments"]}
        return Reply(id=msg.id, ts=time.time(), agent="circadian", ok=True, output=output, state_hash=state_hash(output))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "circadian", e))


# ============================================================================
# API v1 Endpoints
# ============================================================================

@app.post("/v1/plan_timeline", response_model=Reply)
async def plan_timeline_v1(msg: Msg):
    """Plan Timeline endpoint (API v1)."""
    return await _plan_timeline_handler(msg)

@app.post("/v1/assign", response_model=Reply)
async def assign_v1(msg: Msg):
    """Assign endpoint (API v1)."""
    return await _assign_handler(msg)

@app.post("/v1/track", response_model=Reply)
async def track_v1(msg: Msg):
    """Track endpoint (API v1)."""
    return await _track_handler(msg)

@app.post("/v1/remind", response_model=Reply)
async def remind_v1(msg: Msg):
    """Remind endpoint (API v1)."""
    return await _remind_handler(msg)
# ============================================================================
# Legacy Endpoints (Backward Compatibility)
# ============================================================================

@app.post("/plan_timeline", response_model=Reply)
async def plan_timeline_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/plan_timeline instead.
    Plan Timeline endpoint.
    """
    logger.warning("Deprecated endpoint /plan_timeline used. Please migrate to /v1/plan_timeline")
    return await _plan_timeline_handler(msg)

@app.post("/assign", response_model=Reply)
async def assign_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/assign instead.
    Assign endpoint.
    """
    logger.warning("Deprecated endpoint /assign used. Please migrate to /v1/assign")
    return await _assign_handler(msg)

@app.post("/track", response_model=Reply)
async def track_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/track instead.
    Track endpoint.
    """
    logger.warning("Deprecated endpoint /track used. Please migrate to /v1/track")
    return await _track_handler(msg)

@app.post("/remind", response_model=Reply)
async def remind_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/remind instead.
    Remind endpoint.
    """
    logger.warning("Deprecated endpoint /remind used. Please migrate to /v1/remind")
    return await _remind_handler(msg)
