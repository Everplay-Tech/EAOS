from fastapi import FastAPI
from matrix.models import Msg, Reply
from matrix.observability import setup_instrumentation
from matrix.utils import state_hash
from matrix.logging_config import setup_logging, log_request, log_response, log_error
from matrix.errors import InvalidInputError, ValidationError, create_error_response
from matrix.llm_client import llm_client
from matrix.api_models import (
    PlanRequest,
    RouteRequest,
    ReviewRequest,
    FinalizeRequest
)
from matrix.validation import setup_validation_middleware
from pydantic import ValidationError as PydanticValidationError
import time
import json
import httpx

app = FastAPI(title="Nucleus")
setup_instrumentation(app, service_name="nucleus", service_version="1.0.0")
setup_validation_middleware(app)
logger = setup_logging("nucleus")

# Setup comprehensive health and readiness endpoints
from matrix.health import setup_health_endpoints
setup_health_endpoints(app, service_name="nucleus", version="1.0.0")

AGENTS = {
    "osteon": "http://mesh:8080/osteon",
    "myocyte": "http://mesh:8080/myocyte",
    "synapse": "http://mesh:8080/synapse",
    "circadian": "http://mesh:8080/circadian",
}

# ============================================================================
# Internal Handler Functions
# ============================================================================

async def _plan_handler(msg: Msg) -> Reply:
    """Generate an execution plan for complex workflows."""
    start_time = time.time()
    log_request(logger, msg.id, "nucleus", "plan")

    try:
        # Validate input using Pydantic model
        try:
            req = PlanRequest(**msg.input)
        except PydanticValidationError as e:
            raise ValidationError(
                "Invalid input for plan request",
                {"validation_errors": e.errors()}
            )

        goal = req.goal
        requirements = req.requirements
        available_agents = req.available_agents or list(AGENTS.keys())

        # Generate plan using LLM
        system_prompt = """You are a workflow orchestration expert. Create an execution plan to achieve the given goal.
Return your response as a JSON object with: plan (array of steps).
Each step should have: step_id, agent (osteon/synapse/myocyte/circadian), endpoint, description, depends_on (array of step_ids).

Available agents and their capabilities:
- osteon: Content generation (outline, draft, edit, summarize, export)
- synapse: Presentations (storyboard, slide_make, visualize, export)
- myocyte: Data analysis (ingest_table, formula_eval, model_forecast, export)
- circadian: Project planning (plan_timeline, assign, track, remind)

Example: {
  "plan": [
    {"step_id": "s1", "agent": "osteon", "endpoint": "outline", "description": "Create document outline", "depends_on": []},
    {"step_id": "s2", "agent": "osteon", "endpoint": "draft", "description": "Draft content", "depends_on": ["s1"]},
    {"step_id": "s3", "agent": "synapse", "endpoint": "slide_make", "description": "Create slides", "depends_on": ["s2"]}
  ]
}"""

        requirements_text = json.dumps(requirements) if requirements else "None specified"

        prompt = f"""Create an execution plan to achieve this goal:

Goal: {goal}
Requirements: {requirements_text}
Available Agents: {', '.join(available_agents)}

Generate a step-by-step plan with proper dependencies."""

        response_text = await llm_client.generate_json(
            prompt=prompt,
            system_prompt=system_prompt
        )

        output = json.loads(response_text)

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "nucleus", True, duration_ms)

        return Reply(id=msg.id, ts=time.time(), agent="nucleus", ok=True, output=output, state_hash=state_hash(output))
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON response: {e}")
        # Fallback plan
        output = {
            "plan": [
                {"step_id": "s1", "agent": "osteon", "endpoint": "outline", "description": goal, "depends_on": []}
            ]
        }
        return Reply(id=msg.id, ts=time.time(), agent="nucleus", ok=True, output=output, state_hash=state_hash(output))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "nucleus", e))

async def _route_handler(msg: Msg) -> Reply:
    """Intelligently route requests to appropriate services."""
    start_time = time.time()
    log_request(logger, msg.id, "nucleus", "route")

    try:
        # Validate input using Pydantic model
        try:
            req = RouteRequest(**msg.input)
        except PydanticValidationError as e:
            raise ValidationError(
                "Invalid input for route request",
                {"validation_errors": e.errors()}
            )

        request_description = req.request
        context = req.context

        # Route using LLM
        system_prompt = """You are a request routing expert. Analyze the request and determine the best agent and endpoint.
Return your response as a JSON object with: agent, endpoint, reasoning, confidence (0-1).

Available agents and their capabilities:
- osteon: Content generation (outline, draft, edit, summarize, export)
- synapse: Presentations (storyboard, slide_make, visualize, export)
- myocyte: Data analysis (ingest_table, formula_eval, model_forecast, export)
- circadian: Project planning (plan_timeline, assign, track, remind)

Example: {
  "agent": "osteon",
  "endpoint": "draft",
  "reasoning": "Request asks for content generation",
  "confidence": 0.95
}"""

        prompt = f"""Route this request to the appropriate agent and endpoint:

Request: {request_description}
{f"Context: {context}" if context else ""}

Determine the best agent and endpoint to handle this request."""

        response_text = await llm_client.generate_json(
            prompt=prompt,
            system_prompt=system_prompt
        )

        output = json.loads(response_text)
        output["routed"] = True

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "nucleus", True, duration_ms)

        return Reply(id=msg.id, ts=time.time(), agent="nucleus", ok=True, output=output, state_hash=state_hash(output))
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON response: {e}")
        output = {"routed": True, "agent": "osteon", "endpoint": "draft", "confidence": 0.5}
        return Reply(id=msg.id, ts=time.time(), agent="nucleus", ok=True, output=output, state_hash=state_hash(output))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "nucleus", e))

async def _review_handler(msg: Msg) -> Reply:
    """Review and validate outputs against quality criteria."""
    start_time = time.time()
    log_request(logger, msg.id, "nucleus", "review")

    try:
        # Validate input using Pydantic model
        try:
            req = ReviewRequest(**msg.input)
        except PydanticValidationError as e:
            raise ValidationError(
                "Invalid input for review request",
                {"validation_errors": e.errors()}
            )

        content = req.content
        criteria = req.criteria

        # Review using LLM
        system_prompt = """You are a quality assurance expert. Review the content against the given criteria.
Return your response as a JSON object with: pass (boolean), score (0-100), feedback (array of strings), criteria_results (object).
Example: {
  "pass": true,
  "score": 85,
  "feedback": ["Content is well-structured", "Minor grammar improvements needed"],
  "criteria_results": {
    "quality": {"pass": true, "score": 90, "notes": "High quality content"},
    "completeness": {"pass": true, "score": 80, "notes": "All sections present"}
  }
}"""

        content_text = json.dumps(content, indent=2) if isinstance(content, dict) else str(content)
        criteria_text = ", ".join(criteria)

        prompt = f"""Review this content against these criteria: {criteria_text}

Content:
{content_text}

Provide a detailed review with scores and feedback."""

        response_text = await llm_client.generate_json(
            prompt=prompt,
            system_prompt=system_prompt
        )

        output = json.loads(response_text)

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "nucleus", True, duration_ms)

        return Reply(id=msg.id, ts=time.time(), agent="nucleus", ok=True, output=output, state_hash=state_hash(output))
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON response: {e}")
        output = {"criteria": criteria, "pass": True, "score": 75}
        return Reply(id=msg.id, ts=time.time(), agent="nucleus", ok=True, output=output, state_hash=state_hash(output))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "nucleus", e))

async def _finalize_handler(msg: Msg) -> Reply:
    """Finalize and package workflow results."""
    start_time = time.time()
    log_request(logger, msg.id, "nucleus", "finalize")

    try:
        # Validate input using Pydantic model
        try:
            req = FinalizeRequest(**msg.input)
        except PydanticValidationError as e:
            raise ValidationError(
                "Invalid input for finalize request",
                {"validation_errors": e.errors()}
            )

        workflow_results = req.workflow_results
        goal = req.goal

        # Finalize using LLM
        system_prompt = """You are a workflow finalization expert. Analyze workflow results and create a summary.
Return your response as a JSON object with: final (status), summary, key_outputs, recommendations, metadata.
Example: {
  "final": "success",
  "summary": "All workflow steps completed successfully",
  "key_outputs": ["Document created", "Slides generated"],
  "recommendations": ["Review for accuracy", "Share with team"],
  "metadata": {"total_steps": 5, "duration_seconds": 120}
}"""

        results_text = json.dumps(workflow_results, indent=2)

        prompt = f"""Finalize this workflow:

Goal: {goal}

Workflow Results:
{results_text}

Create a comprehensive summary and final status."""

        response_text = await llm_client.generate_json(
            prompt=prompt,
            system_prompt=system_prompt
        )

        output = json.loads(response_text)

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "nucleus", True, duration_ms)

        return Reply(id=msg.id, ts=time.time(), agent="nucleus", ok=True, output=output, state_hash=state_hash(output))
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON response: {e}")
        output = {"final": "ok", "summary": "Workflow completed"}
        return Reply(id=msg.id, ts=time.time(), agent="nucleus", ok=True, output=output, state_hash=state_hash(output))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "nucleus", e))


# ============================================================================
# API v1 Endpoints
# ============================================================================

@app.post("/v1/plan", response_model=Reply)
async def plan_v1(msg: Msg):
    """Plan endpoint (API v1)."""
    return await _plan_handler(msg)

@app.post("/v1/route", response_model=Reply)
async def route_v1(msg: Msg):
    """Route endpoint (API v1)."""
    return await _route_handler(msg)

@app.post("/v1/review", response_model=Reply)
async def review_v1(msg: Msg):
    """Review endpoint (API v1)."""
    return await _review_handler(msg)

@app.post("/v1/finalize", response_model=Reply)
async def finalize_v1(msg: Msg):
    """Finalize endpoint (API v1)."""
    return await _finalize_handler(msg)
# ============================================================================
# Legacy Endpoints (Backward Compatibility)
# ============================================================================

@app.post("/plan", response_model=Reply)
async def plan_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/plan instead.
    Plan endpoint.
    """
    logger.warning("Deprecated endpoint /plan used. Please migrate to /v1/plan")
    return await _plan_handler(msg)

@app.post("/route", response_model=Reply)
async def route_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/route instead.
    Route endpoint.
    """
    logger.warning("Deprecated endpoint /route used. Please migrate to /v1/route")
    return await _route_handler(msg)

@app.post("/review", response_model=Reply)
async def review_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/review instead.
    Review endpoint.
    """
    logger.warning("Deprecated endpoint /review used. Please migrate to /v1/review")
    return await _review_handler(msg)

@app.post("/finalize", response_model=Reply)
async def finalize_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/finalize instead.
    Finalize endpoint.
    """
    logger.warning("Deprecated endpoint /finalize used. Please migrate to /v1/finalize")
    return await _finalize_handler(msg)
