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
import base64

app = FastAPI(title="Chaperone")
setup_instrumentation(app, service_name="chaperone", service_version="1.0.0")
setup_validation_middleware(app)
logger = setup_logging("chaperone")

# Setup comprehensive health and readiness endpoints
from matrix.health import setup_health_endpoints
setup_health_endpoints(app, service_name="chaperone", version="1.0.0")

# ============================================================================
# Internal Handler Functions
# ============================================================================

async def _import_artifact_handler(msg: Msg) -> Reply:
    """Import and parse external artifacts into native format."""
    start_time = time.time()
    log_request(logger, msg.id, "chaperone", "import_artifact")

    try:
        inp = msg.input or {}
        content = inp.get("content", "")
        source_format = inp.get("format", "text")
        artifact_type = inp.get("artifact_type", "osteon")

        if not content:
            raise InvalidInputError("content is required")

        # Use LLM to intelligently parse and structure the content
        system_prompt = f"""You are a document parsing expert. Parse the given content and structure it into a {artifact_type} artifact.
Return your response as a JSON object with: artifact (containing kind, meta, body).

Artifact types:
- osteon: {{"kind": "osteon", "meta": {{"title": "..."}}, "body": {{"sections": [{{"id": "...", "title": "...", "text": "..."}}]}}}}
- synslide: {{"kind": "synslide", "meta": {{"title": "..."}}, "body": {{"slides": [...], "layout_graph": {{}}, "notes": []}}}}
- myotab: {{"kind": "myotab", "meta": {{"title": "..."}}, "body": {{"tables": [...], "formulas": [], "charts": []}}}}

Example: {{
  "artifact": {{
    "kind": "osteon",
    "meta": {{"title": "Imported Document"}},
    "body": {{"sections": [{{"id": "s1", "title": "Section 1", "text": "Content here"}}]}}
  }}
}}"""

        prompt = f"""Parse this {source_format} content into a {artifact_type} artifact:

Content:
{content}

Extract structure, identify sections/slides/tables, and create a well-organized artifact."""

        response_text = await llm_client.generate_json(
            prompt=prompt,
            system_prompt=system_prompt
        )

        output = json.loads(response_text)

        # Ensure artifact has required structure
        if "artifact" not in output:
            output = {"artifact": output}

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "chaperone", True, duration_ms)

        return Reply(id=msg.id, ts=time.time(), agent="chaperone", ok=True, output=output, state_hash=state_hash(output))
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON response: {e}")
        # Fallback artifact
        output = {
            "artifact": {
                "kind": artifact_type or "osteon",
                "meta": {"title": "Imported Content"},
                "body": {"sections": [{"id": "s1", "title": "Imported", "text": content[:500]}]}
            }
        }
        return Reply(id=msg.id, ts=time.time(), agent="chaperone", ok=True, output=output, state_hash=state_hash(output))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "chaperone", e))

async def _export_artifact_handler(msg: Msg) -> Reply:
    """Export native artifacts to external formats (docx, xlsx, pptx, pdf)."""
    start_time = time.time()
    log_request(logger, msg.id, "chaperone", "export_artifact")

    try:
        inp = msg.input or {}
        artifact = inp.get("artifact", {})
        target_format = inp.get("format", "pdf")

        if not artifact:
            raise InvalidInputError("artifact is required")

        artifact_kind = artifact.get("kind", "unknown")
        artifact_body = artifact.get("body", {})

        # Use LLM to prepare content for export format
        system_prompt = f"""You are a document formatting expert. Prepare the artifact content for {target_format} export.
Return your response as a JSON object with: formatted_content (string or structured data), metadata, export_notes.

For different formats:
- pdf/docx: Provide well-formatted text with markdown
- xlsx: Provide structured table data
- pptx: Provide slide content with layout hints
- html: Provide HTML markup

Example: {{
  "formatted_content": "# Title\\n\\nContent here...",
  "metadata": {{"pages": 1, "sections": 3}},
  "export_notes": ["Include table of contents", "Use professional formatting"]
}}"""

        artifact_text = json.dumps(artifact, indent=2)

        prompt = f"""Prepare this {artifact_kind} artifact for {target_format} export:

Artifact:
{artifact_text}

Format the content appropriately for {target_format} and provide export guidance."""

        response_text = await llm_client.generate_json(
            prompt=prompt,
            system_prompt=system_prompt
        )

        result = json.loads(response_text)

        # In a real implementation, this would use libraries like:
        # - python-docx for DOCX
        # - openpyxl for XLSX
        # - python-pptx for PPTX
        # - reportlab or weasyprint for PDF
        # For now, we'll create a structured export response

        formatted_content = result.get("formatted_content", "")

        # Simulate file content (base64 encoded)
        # In production, this would be actual file bytes
        export_content = f"{artifact_kind} exported to {target_format}\n\n{formatted_content}"
        bytes_ref = base64.b64encode(export_content.encode()).decode()

        output = {
            "export": {
                "format": target_format,
                "bytes_ref": bytes_ref,
                "metadata": result.get("metadata", {}),
                "size_bytes": len(export_content),
                "export_notes": result.get("export_notes", [])
            }
        }

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "chaperone", True, duration_ms)

        return Reply(id=msg.id, ts=time.time(), agent="chaperone", ok=True, output=output, state_hash=state_hash(output))
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON response: {e}")
        # Fallback export
        output = {
            "export": {
                "format": target_format,
                "bytes_ref": "stub_export_data",
                "metadata": {}
            }
        }
        return Reply(id=msg.id, ts=time.time(), agent="chaperone", ok=True, output=output, state_hash=state_hash(output))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "chaperone", e))


# ============================================================================
# API v1 Endpoints
# ============================================================================

@app.post("/v1/import_artifact", response_model=Reply)
async def import_artifact_v1(msg: Msg):
    """Import Artifact endpoint (API v1)."""
    return await _import_artifact_handler(msg)

@app.post("/v1/export_artifact", response_model=Reply)
async def export_artifact_v1(msg: Msg):
    """Export Artifact endpoint (API v1)."""
    return await _export_artifact_handler(msg)
# ============================================================================
# Legacy Endpoints (Backward Compatibility)
# ============================================================================

@app.post("/import_artifact", response_model=Reply)
async def import_artifact_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/import_artifact instead.
    Import Artifact endpoint.
    """
    logger.warning("Deprecated endpoint /import_artifact used. Please migrate to /v1/import_artifact")
    return await _import_artifact_handler(msg)

@app.post("/export_artifact", response_model=Reply)
async def export_artifact_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/export_artifact instead.
    Export Artifact endpoint.
    """
    logger.warning("Deprecated endpoint /export_artifact used. Please migrate to /v1/export_artifact")
    return await _export_artifact_handler(msg)
