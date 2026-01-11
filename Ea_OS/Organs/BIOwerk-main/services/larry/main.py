"""
LARRY - The Conversational Stooge
"Wise guy, eh?" - Larry understands what you want

Translates natural language user requests into structured service calls.
Acts as the conversational interface between users and the BIOwerk system.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import logging
from pathlib import Path
from llama_cpp import Llama

# Import BIOwerk matrix modules for observability and health
from matrix.observability import setup_instrumentation
from matrix.health import setup_health_endpoints
from matrix.validation import setup_validation_middleware
from matrix.errors import ValidationError
from pydantic import ValidationError as PydanticValidationError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Larry - Conversational Stooge")

# Setup comprehensive observability and health endpoints
setup_instrumentation(app, service_name="larry", service_version="1.0.0")
setup_validation_middleware(app)
setup_health_endpoints(app, service_name="larry", version="1.0.0")

# Load PHI2 model
MODEL_PATH = Path("./models/phi2/model.gguf")
llm = None

@app.on_event("startup")
async def load_model():
    """Load Larry's PHI2 brain on startup."""
    global llm
    if MODEL_PATH.exists():
        logger.info(f"🎭 Larry is waking up... Loading model from {MODEL_PATH}")
        llm = Llama(
            model_path=str(MODEL_PATH),
            n_ctx=2048,
            n_gpu_layers=0,
            verbose=False
        )
        logger.info("🎭 Larry is ready! 'Wise guy, eh?'")
    else:
        logger.warning(f"⚠️  Larry's brain not found at {MODEL_PATH}")
        logger.warning("   Run: ./scripts/download-models.sh stooges")


class UserRequest(BaseModel):
    """Natural language request from user."""
    text: str
    context: Optional[Dict[str, Any]] = None


class ServiceCall(BaseModel):
    """Structured service call translated by Larry."""
    service: str
    intent: str
    parameters: Dict[str, Any]
    confidence: float


@app.get("/health")
async def health():
    """Check if Larry is alive."""
    return {
        "status": "healthy",
        "stooge": "larry",
        "role": "conversational",
        "model_loaded": llm is not None,
        "catchphrase": "Wise guy, eh?"
    }


async def _translate_handler(request: UserRequest) -> ServiceCall:
    """
    Translate natural language into structured service calls.

    Example:
        "Generate a blog post about AI" →
        {service: "osteon", intent: "outline", parameters: {topic: "AI"}}
    """
    if llm is None:
        raise HTTPException(status_code=503, detail="Larry's brain not loaded. Download phi2 model first.")

    logger.info(f"🎭 Larry translating: {request.text}")

    # System prompt for translation
    system_prompt = """You are Larry, a conversational AI that translates user requests into service calls.

Available services:
- osteon: Content generation (outlines, blog posts)
- synapse: Workflow management
- myocyte: Task execution
- nucleus: Data processing
- chaperone: Monitoring
- circadian: Scheduling

Translate the user's request into a JSON object with:
- service: which service to call
- intent: what action to perform
- parameters: relevant parameters
- confidence: 0-1 score

Respond with ONLY valid JSON, no explanations."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Translate this request: {request.text}"}
    ]

    try:
        response = llm.create_chat_completion(
            messages=messages,
            temperature=0.3,
            max_tokens=512,
            response_format={"type": "json_object"}
        )

        result = response['choices'][0]['message']['content']
        logger.info(f"🎭 Larry says: {result}")

        # Parse and return
        import json
        parsed = json.loads(result)

        return ServiceCall(**parsed)

    except Exception as e:
        logger.error(f"❌ Larry failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")


async def _chat_handler(request: UserRequest):
    """
    Have a conversation with Larry.
    He'll help you understand what you can do with BIOwerk.
    """
    if llm is None:
        raise HTTPException(status_code=503, detail="Larry's brain not loaded.")

    logger.info(f"🎭 Larry chatting: {request.text}")

    system_prompt = """You are Larry from The Three Stooges, working as a friendly AI assistant for BIOwerk.
You help users understand the system and figure out what they want to do.
Be helpful, conversational, and occasionally add some classic Larry personality.
Keep responses concise but friendly."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": request.text}
    ]

    try:
        response = llm.create_chat_completion(
            messages=messages,
            temperature=0.7,
            max_tokens=512
        )

        result = response['choices'][0]['message']['content']

        return {
            "stooge": "larry",
            "response": result,
            "catchphrase": "Wise guy, eh?"
        }

    except Exception as e:
        logger.error(f"❌ Larry failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


# ============================================================================
# API v1 Endpoints
# ============================================================================

@app.post("/v1/translate", response_model=ServiceCall)
async def translate_v1(request: UserRequest):
    """Translate natural language into structured service calls (API v1)."""
    return await _translate_handler(request)

@app.post("/v1/chat")
async def chat_v1(request: UserRequest):
    """Have a conversation with Larry (API v1)."""
    return await _chat_handler(request)

# ============================================================================
# Legacy Endpoints (Backward Compatibility)
# ============================================================================

@app.post("/translate", response_model=ServiceCall)
async def translate_legacy(request: UserRequest):
    """
    DEPRECATED: Use /v1/translate instead.
    Translate natural language into structured service calls.
    """
    logger.warning("Deprecated endpoint /translate used. Please migrate to /v1/translate")
    return await _translate_handler(request)

@app.post("/chat")
async def chat_legacy(request: UserRequest):
    """
    DEPRECATED: Use /v1/chat instead.
    Have a conversation with Larry.
    """
    logger.warning("Deprecated endpoint /chat used. Please migrate to /v1/chat")
    return await _chat_handler(request)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8007)
