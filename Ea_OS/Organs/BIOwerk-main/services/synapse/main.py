from fastapi import FastAPI
from matrix.models import Msg, Reply
from matrix.observability import setup_instrumentation
from matrix.utils import state_hash
from matrix.logging_config import setup_logging, log_request, log_response, log_error
from matrix.errors import InvalidInputError, ValidationError, create_error_response
from matrix.llm_client import llm_client
from matrix.api_models import (
    StoryboardRequest,
    SlideMakeRequest,
    VisualizeRequest,
    ExportRequest
)
from matrix.validation import setup_validation_middleware
from pydantic import ValidationError as PydanticValidationError
import time
import json

app = FastAPI(title="Synapse")
setup_instrumentation(app, service_name="synapse", service_version="1.0.0")
setup_validation_middleware(app)
logger = setup_logging("synapse")

# Setup comprehensive health and readiness endpoints
from matrix.health import setup_health_endpoints
setup_health_endpoints(app, service_name="synapse", version="1.0.0")

# ============================================================================
# Internal Handler Functions
# ============================================================================

async def _storyboard_handler(msg: Msg) -> Reply:
    """Generate a storyboard (slide outline) for a presentation."""
    start_time = time.time()
    log_request(logger, msg.id, "synapse", "storyboard")

    try:
        # Validate input using Pydantic model
        try:
            req = StoryboardRequest(**msg.input)
            req.validate_required_fields()
        except PydanticValidationError as e:
            raise ValidationError(
                "Invalid input for storyboard request",
                {"validation_errors": e.errors()}
            )

        topic = req.topic
        goal = req.goal
        audience = req.audience
        num_slides = req.num_slides

        # Generate storyboard using LLM
        system_prompt = """You are an expert presentation designer. Create a compelling storyboard for a presentation.
Return your response as a JSON object with a 'storyboard' array containing slide objects.
Each slide should have: title, description, and slide_type (title, content, image, data, conclusion).
Example: {"storyboard": [{"title": "Introduction", "description": "Hook audience with key problem", "slide_type": "title"}]}"""

        prompt = f"""Create a storyboard for a {num_slides}-slide presentation:

Topic: {topic or goal}
Audience: {audience}
{f"Goal: {goal}" if goal and topic else ""}

Generate a compelling storyboard with diverse slide types."""

        response_text = await llm_client.generate_json(
            prompt=prompt,
            system_prompt=system_prompt
        )

        output = json.loads(response_text)

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "synapse", True, duration_ms)

        return Reply(id=msg.id, ts=time.time(), agent="synapse", ok=True, output=output, state_hash=state_hash(output))
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON response: {e}")
        # Fallback output
        output = {"storyboard": [{"title": "Introduction", "description": topic or goal, "slide_type": "title"}]}
        return Reply(id=msg.id, ts=time.time(), agent="synapse", ok=True, output=output, state_hash=state_hash(output))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "synapse", e))

async def _slide_make_handler(msg: Msg) -> Reply:
    """Generate actual slide content from storyboard."""
    start_time = time.time()
    log_request(logger, msg.id, "synapse", "slide_make")

    try:
        # Validate input using Pydantic model
        try:
            req = SlideMakeRequest(**msg.input)
        except PydanticValidationError as e:
            raise ValidationError(
                "Invalid input for slide_make request",
                {"validation_errors": e.errors()}
            )

        storyboard = req.storyboard
        topic = req.topic

        # Generate slides using LLM
        system_prompt = """You are an expert presentation content writer. Create detailed slide content based on the storyboard.
Return your response as a JSON object with 'slides' array containing slide objects.
Each slide should have: id, title, content (array of bullet points or paragraphs), and slide_type.
Also include 'speaker_notes' array with notes for each slide.
Example: {
  "slides": [{"id": "slide-1", "title": "Introduction", "content": ["Point 1", "Point 2"], "slide_type": "content"}],
  "speaker_notes": ["Introduce yourself and the topic..."]
}"""

        storyboard_text = json.dumps(storyboard, indent=2)

        prompt = f"""Create detailed slide content for this storyboard:

Topic: {topic}

Storyboard:
{storyboard_text}

Generate complete slides with content and speaker notes."""

        response_text = await llm_client.generate_json(
            prompt=prompt,
            system_prompt=system_prompt
        )

        output = json.loads(response_text)

        # Add layout graph (simple sequential layout)
        num_slides = len(output.get("slides", []))
        layout_graph = {
            "nodes": [{"id": f"slide-{i}", "position": i} for i in range(num_slides)],
            "edges": [{"from": f"slide-{i}", "to": f"slide-{i+1}"} for i in range(num_slides - 1)]
        }
        output["layout_graph"] = layout_graph

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "synapse", True, duration_ms)

        return Reply(id=msg.id, ts=time.time(), agent="synapse", ok=True, output=output, state_hash=state_hash(output))
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON response: {e}")
        # Fallback output
        output = {
            "slides": [{"id": "slide-1", "title": storyboard[0].get("title", "Slide 1"), "content": ["Content here"], "slide_type": "content"}],
            "layout_graph": {},
            "speaker_notes": ["Notes here"]
        }
        return Reply(id=msg.id, ts=time.time(), agent="synapse", ok=True, output=output, state_hash=state_hash(output))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "synapse", e))

async def _visualize_handler(msg: Msg) -> Reply:
    """Generate data visualization specifications."""
    start_time = time.time()
    log_request(logger, msg.id, "synapse", "visualize")

    try:
        # Validate input using Pydantic model
        try:
            req = VisualizeRequest(**msg.input)
            req.validate_required_fields()
        except PydanticValidationError as e:
            raise ValidationError(
                "Invalid input for visualize request",
                {"validation_errors": e.errors()}
            )

        data = req.data
        description = req.description
        viz_type = req.viz_type

        # Generate visualization spec using LLM
        system_prompt = """You are a data visualization expert. Create appropriate visualization specifications.
Return your response as a JSON object with 'viz' containing: type (bar, line, pie, scatter, etc.), data, labels, and config.
Example: {
  "viz": {
    "type": "bar",
    "data": [10, 20, 30],
    "labels": ["A", "B", "C"],
    "config": {"title": "Chart Title", "xLabel": "X Axis", "yLabel": "Y Axis"}
  }
}"""

        if data:
            prompt = f"""Create a visualization specification for this data:

Data: {json.dumps(data)}
{f"Description: {description}" if description else ""}
{f"Preferred type: {viz_type}" if viz_type != "auto" else ""}

Choose the best visualization type and generate the complete spec."""
        else:
            prompt = f"""Create a visualization specification based on this description:

Description: {description}
{f"Preferred type: {viz_type}" if viz_type != "auto" else ""}

Generate sample data and visualization spec."""

        response_text = await llm_client.generate_json(
            prompt=prompt,
            system_prompt=system_prompt
        )

        output = json.loads(response_text)

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "synapse", True, duration_ms)

        return Reply(id=msg.id, ts=time.time(), agent="synapse", ok=True, output=output, state_hash=state_hash(output))
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON response: {e}")
        # Fallback output
        output = {"viz": {"type": "bar", "data": data or [1, 2, 3], "labels": ["A", "B", "C"]}}
        return Reply(id=msg.id, ts=time.time(), agent="synapse", ok=True, output=output, state_hash=state_hash(output))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "synapse", e))

async def _export__handler(msg: Msg) -> Reply:
    """Export the complete presentation artifact."""
    start_time = time.time()
    log_request(logger, msg.id, "synapse", "export")

    try:
        # Validate input using Pydantic model
        try:
            req = ExportRequest(**msg.input)
        except PydanticValidationError as e:
            raise ValidationError(
                "Invalid input for export request",
                {"validation_errors": e.errors()}
            )

        title = req.title
        metadata = req.metadata

        # For synapse, we expect slides/layout_graph/notes in metadata or sections
        slides = metadata.get("slides", []) if isinstance(metadata, dict) else []
        layout_graph = metadata.get("layout_graph", {}) if isinstance(metadata, dict) else {}
        notes = metadata.get("notes", []) if isinstance(metadata, dict) else []

        output = {
            "artifact": {
                "kind": "synslide",
                "meta": {
                    "title": title,
                    "created_at": time.time(),
                    **metadata
                },
                "body": {
                    "slides": slides,
                    "layout_graph": layout_graph,
                    "notes": notes
                }
            }
        }

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "synapse", True, duration_ms)

        return Reply(id=msg.id, ts=time.time(), agent="synapse", ok=True, output=output, state_hash=state_hash(output))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "synapse", e))


# ============================================================================
# API v1 Endpoints
# ============================================================================

@app.post("/v1/storyboard", response_model=Reply)
async def storyboard_v1(msg: Msg):
    """Storyboard endpoint (API v1)."""
    return await _storyboard_handler(msg)

@app.post("/v1/slide_make", response_model=Reply)
async def slide_make_v1(msg: Msg):
    """Slide Make endpoint (API v1)."""
    return await _slide_make_handler(msg)

@app.post("/v1/visualize", response_model=Reply)
async def visualize_v1(msg: Msg):
    """Visualize endpoint (API v1)."""
    return await _visualize_handler(msg)

@app.post("/v1/export", response_model=Reply)
async def export__v1(msg: Msg):
    """Export  endpoint (API v1)."""
    return await _export__handler(msg)
# ============================================================================
# Legacy Endpoints (Backward Compatibility)
# ============================================================================

@app.post("/storyboard", response_model=Reply)
async def storyboard_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/storyboard instead.
    Storyboard endpoint.
    """
    logger.warning("Deprecated endpoint /storyboard used. Please migrate to /v1/storyboard")
    return await _storyboard_handler(msg)

@app.post("/slide_make", response_model=Reply)
async def slide_make_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/slide_make instead.
    Slide Make endpoint.
    """
    logger.warning("Deprecated endpoint /slide_make used. Please migrate to /v1/slide_make")
    return await _slide_make_handler(msg)

@app.post("/visualize", response_model=Reply)
async def visualize_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/visualize instead.
    Visualize endpoint.
    """
    logger.warning("Deprecated endpoint /visualize used. Please migrate to /v1/visualize")
    return await _visualize_handler(msg)

@app.post("/export", response_model=Reply)
async def export__legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/export instead.
    Export  endpoint.
    """
    logger.warning("Deprecated endpoint /export used. Please migrate to /v1/export")
    return await _export__handler(msg)
