from fastapi import FastAPI, HTTPException
from matrix.models import Msg, Reply
from matrix.observability import setup_instrumentation
from matrix.utils import state_hash
from matrix.logging_config import setup_logging, log_request, log_response, log_error
from matrix.errors import InvalidInputError, ValidationError, create_error_response
from matrix.llm_client import llm_client
from matrix.database import get_session_manager
from matrix.api_models import (
    OutlineRequest,
    DraftRequest,
    EditRequest,
    SummarizeRequest,
    ExportRequest
)
from matrix.validation import setup_validation_middleware
from pydantic import ValidationError as PydanticValidationError
import time
import json

app = FastAPI(title="Osteon")
setup_instrumentation(app, service_name="osteon", service_version="1.0.0")
setup_validation_middleware(app)
logger = setup_logging("osteon")

# Setup comprehensive health and readiness endpoints
from matrix.health import setup_health_endpoints
setup_health_endpoints(app, service_name="osteon", version="1.0.0")

# Redis-based session manager for persistent state across requests
# Uses 1-hour TTL for document generation workflows
session_mgr = get_session_manager("default")

# ============================================================================
# Internal Handler Functions
# ============================================================================

async def _outline_handler(msg: Msg) -> Reply:
    """Generate a structured outline for a document based on the goal/topic."""
    start_time = time.time()
    log_request(logger, msg.id, "osteon", "outline")

    try:
        # Validate input using Pydantic model
        try:
            req = OutlineRequest(**msg.input)
            req.validate_required_fields()
        except PydanticValidationError as e:
            raise ValidationError(
                "Invalid input for outline request",
                {"validation_errors": e.errors()}
            )

        goal = req.goal
        topic = req.topic or goal
        context = req.context

        # Generate outline using LLM
        system_prompt = """You are an expert content strategist. Generate a detailed, well-structured outline for the given topic.
Return your response as a JSON object with an 'outline' array containing section titles.
Each section should be a string representing a major section or chapter title.
Example: {"outline": ["Introduction", "Background", "Main Analysis", "Case Studies", "Conclusions"]}"""

        prompt = f"""Create a detailed outline for the following topic:

Topic: {topic}
{f"Context: {context}" if context else ""}

Generate a comprehensive outline with 5-8 main sections that would make for a well-structured document."""

        response_text = await llm_client.generate_json(
            prompt=prompt,
            system_prompt=system_prompt
        )

        output = json.loads(response_text)

        # Store outline in Redis session for later retrieval
        await session_mgr.set(msg.id, {"outline": output.get("outline", [])})

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "osteon", True, duration_ms)

        return Reply(id=msg.id, ts=time.time(), agent="osteon", ok=True, output=output, state_hash=state_hash(output))
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON response: {e}")
        # Fallback output
        output = {"outline": ["Introduction", "Main Content", "Conclusion"]}
        return Reply(id=msg.id, ts=time.time(), agent="osteon", ok=True, output=output, state_hash=state_hash(output))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "osteon", e))

async def _draft_handler(msg: Msg) -> Reply:
    """Generate draft content for sections."""
    start_time = time.time()
    log_request(logger, msg.id, "osteon", "draft")

    try:
        # Validate input using Pydantic model
        try:
            req = DraftRequest(**msg.input)
            req.validate_required_fields()
        except PydanticValidationError as e:
            raise ValidationError(
                "Invalid input for draft request",
                {"validation_errors": e.errors()}
            )

        goal = req.goal
        section_title = req.section_title
        outline = req.outline
        context = req.context

        # Generate content using LLM
        system_prompt = """You are an expert writer. Generate high-quality, detailed content for the given section.
Your writing should be clear, informative, and well-structured."""

        if section_title:
            prompt = f"""Write detailed content for the following section:

Section Title: {section_title}
{f"Overall Goal: {goal}" if goal else ""}
{f"Document Outline: {', '.join(outline)}" if outline else ""}
{f"Context: {context}" if context else ""}

Write 2-3 paragraphs of high-quality content for this section."""
        else:
            prompt = f"""Write an introductory section for a document with the following goal:

Goal: {goal}
{f"Outline: {', '.join(outline)}" if outline else ""}
{f"Context: {context}" if context else ""}

Write 2-3 paragraphs introducing the topic and setting the stage."""

        content_text = await llm_client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=system_prompt
        )

        sections = [{
            "id": f"s_{int(time.time())}",
            "title": section_title or "Introduction",
            "text": content_text.strip()
        }]

        output = {
            "sections": sections,
            "toc": [s["title"] for s in sections],
            "citations": []
        }

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "osteon", True, duration_ms)

        return Reply(id=msg.id, ts=time.time(), agent="osteon", ok=True, output=output, state_hash=state_hash(output))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "osteon", e))

async def _edit_handler(msg: Msg) -> Reply:
    """Edit and improve content based on feedback."""
    start_time = time.time()
    log_request(logger, msg.id, "osteon", "edit")

    try:
        # Validate input using Pydantic model
        try:
            req = EditRequest(**msg.input)
        except PydanticValidationError as e:
            raise ValidationError(
                "Invalid input for edit request",
                {"validation_errors": e.errors()}
            )

        original_text = req.text
        feedback = req.feedback
        edit_type = req.edit_type

        # Generate edited content using LLM
        system_prompt = """You are an expert editor. Review and improve the given text based on the feedback provided.
Return the edited version of the text."""

        if feedback:
            prompt = f"""Edit the following text based on this feedback:

Feedback: {feedback}

Original Text:
{original_text}

Provide the improved version of the text."""
        else:
            edit_instructions = {
                "improve": "Improve the clarity, flow, and quality of the text.",
                "shorten": "Make the text more concise while preserving key information.",
                "expand": "Expand the text with more detail and examples.",
                "formalize": "Make the tone more formal and professional.",
                "simplify": "Simplify the language to make it more accessible."
            }

            instruction = edit_instructions.get(edit_type, edit_instructions["improve"])

            prompt = f"""{instruction}

Original Text:
{original_text}

Provide the edited version."""

        edited_text = await llm_client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=system_prompt
        )

        output = {
            "edited_text": edited_text.strip(),
            "original_text": original_text,
            "diff": "text_replaced"
        }

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "osteon", True, duration_ms)

        return Reply(id=msg.id, ts=time.time(), agent="osteon", ok=True, output=output, state_hash=state_hash(output))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "osteon", e))

async def _summarize_handler(msg: Msg) -> Reply:
    """Summarize content."""
    start_time = time.time()
    log_request(logger, msg.id, "osteon", "summarize")

    try:
        # Validate input using Pydantic model
        try:
            req = SummarizeRequest(**msg.input)
            req.validate_required_fields()
        except PydanticValidationError as e:
            raise ValidationError(
                "Invalid input for summarize request",
                {"validation_errors": e.errors()}
            )

        text = req.text
        sections = req.sections
        max_length = req.max_length

        # Combine sections if provided
        if sections:
            text = "\n\n".join([f"{s.get('title', '')}\n{s.get('text', '')}" for s in sections])

        # Generate summary using LLM
        system_prompt = """You are an expert at creating concise, informative summaries.
Extract the key points and present them clearly."""

        length_guidance = {
            "short": "in 2-3 sentences",
            "medium": "in 1-2 paragraphs",
            "long": "in 3-4 paragraphs"
        }

        guidance = length_guidance.get(max_length, length_guidance["medium"])

        prompt = f"""Summarize the following text {guidance}:

{text}

Provide a clear, comprehensive summary."""

        summary_text = await llm_client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=system_prompt
        )

        output = {
            "summary": summary_text.strip(),
            "length": max_length,
            "original_length": len(text)
        }

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "osteon", True, duration_ms)

        return Reply(id=msg.id, ts=time.time(), agent="osteon", ok=True, output=output, state_hash=state_hash(output))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "osteon", e))

async def _export_handler(msg: Msg) -> Reply:
    """Export the complete artifact with all sections."""
    start_time = time.time()
    log_request(logger, msg.id, "osteon", "export")

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
        sections = req.sections
        metadata = req.metadata

        output = {
            "artifact": {
                "kind": "osteon",
                "meta": {
                    "title": title,
                    "created_at": time.time(),
                    **metadata
                },
                "body": {
                    "sections": sections,
                    "toc": [s.get("title", "") for s in sections]
                }
            }
        }

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "osteon", True, duration_ms)

        return Reply(id=msg.id, ts=time.time(), agent="osteon", ok=True, output=output, state_hash=state_hash(output))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "osteon", e))

# ============================================================================
# API v1 Endpoints
# ============================================================================

@app.post("/v1/outline", response_model=Reply)
async def outline_v1(msg: Msg):
    """Generate a structured outline for a document based on the goal/topic (API v1)."""
    return await _outline_handler(msg)

@app.post("/v1/draft", response_model=Reply)
async def draft_v1(msg: Msg):
    """Generate draft content for sections (API v1)."""
    return await _draft_handler(msg)

@app.post("/v1/edit", response_model=Reply)
async def edit_v1(msg: Msg):
    """Edit and improve content based on feedback (API v1)."""
    return await _edit_handler(msg)

@app.post("/v1/summarize", response_model=Reply)
async def summarize_v1(msg: Msg):
    """Summarize content (API v1)."""
    return await _summarize_handler(msg)

@app.post("/v1/export", response_model=Reply)
async def export_v1(msg: Msg):
    """Export the complete artifact with all sections (API v1)."""
    return await _export_handler(msg)

# ============================================================================
# Legacy Endpoints (Backward Compatibility)
# ============================================================================

@app.post("/outline", response_model=Reply)
async def outline_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/outline instead.
    Generate a structured outline for a document based on the goal/topic.
    """
    logger.warning("Deprecated endpoint /outline used. Please migrate to /v1/outline")
    return await _outline_handler(msg)

@app.post("/draft", response_model=Reply)
async def draft_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/draft instead.
    Generate draft content for sections.
    """
    logger.warning("Deprecated endpoint /draft used. Please migrate to /v1/draft")
    return await _draft_handler(msg)

@app.post("/edit", response_model=Reply)
async def edit_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/edit instead.
    Edit and improve content based on feedback.
    """
    logger.warning("Deprecated endpoint /edit used. Please migrate to /v1/edit")
    return await _edit_handler(msg)

@app.post("/summarize", response_model=Reply)
async def summarize_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/summarize instead.
    Summarize content.
    """
    logger.warning("Deprecated endpoint /summarize used. Please migrate to /v1/summarize")
    return await _summarize_handler(msg)

@app.post("/export", response_model=Reply)
async def export_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/export instead.
    Export the complete artifact with all sections.
    """
    logger.warning("Deprecated endpoint /export used. Please migrate to /v1/export")
    return await _export_handler(msg)
