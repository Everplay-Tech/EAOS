"""
MOE - The Orchestrator Stooge
"Why I oughta..." - Moe tells everyone what to do

Routes and orchestrates requests between services.
Handles multi-service workflows and coordinates execution.

Now with enterprise-grade service mesh resilience!
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import logging
from pathlib import Path
from llama_cpp import Llama
import httpx
import asyncio

# Import resilience patterns from matrix
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from matrix.config import settings
from matrix.resilience import (
    ResilientHttpClient,
    CircuitBreakerError,
    RetryExhaustedError,
    BulkheadFullError
)
from matrix.observability import setup_instrumentation
from matrix.health import setup_health_endpoints
from matrix.validation import setup_validation_middleware
from matrix.errors import ValidationError
from pydantic import ValidationError as PydanticValidationError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Moe - Orchestrator Stooge")

# Setup comprehensive observability and health endpoints
setup_instrumentation(app, service_name="moe", service_version="1.0.0")
setup_validation_middleware(app)
setup_health_endpoints(app, service_name="moe", version="1.0.0")

# Load PHI2 model
MODEL_PATH = Path("./models/phi2/model.gguf")
llm = None

# Service registry
SERVICES = {
    "osteon": "http://osteon:8001",
    "synapse": "http://synapse:8003",
    "myocyte": "http://myocyte:8002",
    "nucleus": "http://nucleus:8005",
    "chaperone": "http://chaperone:8006",
    "circadian": "http://circadian:8004",
}

# Resilient HTTP clients for each service
resilient_clients: Dict[str, ResilientHttpClient] = {}


@app.on_event("startup")
async def load_model():
    """Load Moe's PHI2 brain and initialize resilient clients on startup."""
    global llm, resilient_clients

    # Load LLM model
    if MODEL_PATH.exists():
        logger.info(f"🎭 Moe is waking up... Loading model from {MODEL_PATH}")
        llm = Llama(
            model_path=str(MODEL_PATH),
            n_ctx=2048,
            n_gpu_layers=0,
            verbose=False
        )
        logger.info("🎭 Moe's brain loaded! 'Why I oughta...'")
    else:
        logger.warning(f"⚠️  Moe's brain not found at {MODEL_PATH}")
        logger.warning("   Run: ./scripts/download-models.sh stooges")

    # Initialize resilient HTTP clients for each service
    logger.info("🎭 Moe initializing resilient service clients...")

    for service_name, service_url in SERVICES.items():
        # Configure resilience patterns per service
        circuit_breaker_kwargs = {
            'failure_threshold': settings.circuit_breaker_failure_threshold,
            'success_threshold': settings.circuit_breaker_success_threshold,
            'timeout': settings.circuit_breaker_timeout,
            'failure_rate_threshold': settings.circuit_breaker_failure_rate_threshold,
            'window_size': settings.circuit_breaker_window_size
        } if settings.circuit_breaker_enabled else None

        retry_kwargs = {
            'max_attempts': settings.retry_max_attempts,
            'initial_delay': settings.retry_initial_delay,
            'max_delay': settings.retry_max_delay,
            'exponential_base': settings.retry_exponential_base,
            'jitter': settings.retry_jitter
        } if settings.retry_enabled else None

        bulkhead_kwargs = {
            'max_concurrent': settings.bulkhead_max_concurrent,
            'queue_size': settings.bulkhead_queue_size,
            'timeout': settings.bulkhead_timeout
        } if settings.bulkhead_enabled else None

        resilient_clients[service_name] = ResilientHttpClient(
            service_name=f"moe->{service_name}",
            base_url=service_url,
            timeout=settings.service_timeout_default,
            circuit_breaker_kwargs=circuit_breaker_kwargs,
            retry_kwargs=retry_kwargs,
            bulkhead_kwargs=bulkhead_kwargs,
            enable_circuit_breaker=settings.circuit_breaker_enabled,
            enable_retry=settings.retry_enabled,
            enable_bulkhead=settings.bulkhead_enabled
        )

        logger.info(f"   ✅ Resilient client for {service_name}")

    logger.info("🎭 Moe is ready with full resilience!")


@app.on_event("shutdown")
async def cleanup():
    """Cleanup resilient clients on shutdown."""
    global resilient_clients

    logger.info("🎭 Moe cleaning up...")

    for service_name, client in resilient_clients.items():
        await client.aclose()
        logger.info(f"   ✅ Closed client for {service_name}")

    resilient_clients.clear()
    logger.info("🎭 Moe out! 'Wise guy, eh?'")


class WorkflowRequest(BaseModel):
    """Multi-service workflow request."""
    goal: str
    context: Optional[Dict[str, Any]] = None
    services: Optional[List[str]] = None


class WorkflowPlan(BaseModel):
    """Orchestration plan created by Moe."""
    steps: List[Dict[str, Any]]
    estimated_time: Optional[int] = None
    dependencies: Optional[Dict[str, List[str]]] = None


@app.get("/health")
async def health():
    """Check if Moe is alive."""
    return {
        "status": "healthy",
        "stooge": "moe",
        "role": "orchestrator",
        "model_loaded": llm is not None,
        "catchphrase": "Why I oughta...",
        "available_services": list(SERVICES.keys())
    }


async def _plan_handler(request: WorkflowRequest) -> WorkflowPlan:
    """
    Create an orchestration plan for multi-service workflows.

    Example:
        "Create a blog post, schedule it, and monitor engagement" →
        [
            {step: 1, service: "osteon", action: "generate_post"},
            {step: 2, service: "circadian", action: "schedule"},
            {step: 3, service: "chaperone", action: "monitor"}
        ]
    """
    if llm is None:
        raise HTTPException(status_code=503, detail="Moe's brain not loaded. Download phi2 model first.")

    logger.info(f"🎭 Moe planning workflow: {request.goal}")

    system_prompt = f"""You are Moe, the orchestrator. You plan multi-service workflows.

Available services: {', '.join(SERVICES.keys())}

Create a workflow plan as JSON with:
- steps: array of {{step, service, action, params}}
- estimated_time: seconds
- dependencies: which steps depend on others

Respond with ONLY valid JSON."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Plan this workflow: {request.goal}"}
    ]

    try:
        response = llm.create_chat_completion(
            messages=messages,
            temperature=0.2,
            max_tokens=1024,
            response_format={"type": "json_object"}
        )

        result = response['choices'][0]['message']['content']
        logger.info(f"🎭 Moe's plan: {result}")

        import json
        parsed = json.loads(result)

        return WorkflowPlan(**parsed)

    except Exception as e:
        logger.error(f"❌ Moe failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Planning failed: {str(e)}")


async def _execute_handler(plan: WorkflowPlan):
    """
    Execute a workflow plan by orchestrating service calls.
    Moe calls the shots with enterprise-grade resilience!

    Features:
    - Circuit breakers per service
    - Automatic retries with exponential backoff
    - Bulkhead pattern to prevent resource exhaustion
    - Detailed error reporting
    """
    logger.info(f"🎭 Moe executing {len(plan.steps)} steps...")

    results = []
    total_failures = 0
    circuit_breaker_failures = 0

    for step in plan.steps:
        service = step.get("service")
        action = step.get("action")
        step_num = step.get("step", len(results) + 1)

        if service not in SERVICES:
            logger.warning(f"⚠️  Unknown service: {service}")
            results.append({
                "step": step_num,
                "service": service,
                "action": action,
                "status": "failed",
                "error": f"Unknown service: {service}",
                "error_type": "invalid_service"
            })
            total_failures += 1
            continue

        logger.info(f"🎭 Moe calling {service}: {action}")

        # Get resilient client for this service
        client = resilient_clients.get(service)

        if not client:
            # Fallback to basic client if resilient client not initialized
            logger.warning(f"⚠️  Resilient client not found for {service}, using fallback")
            try:
                async with httpx.AsyncClient(timeout=settings.service_timeout_default) as fallback_client:
                    url = f"{SERVICES[service]}/{action}"
                    response = await fallback_client.post(url, json=step.get("params", {}))
                    response.raise_for_status()

                    results.append({
                        "step": step_num,
                        "service": service,
                        "action": action,
                        "status": "success",
                        "result": response.json(),
                        "resilience_used": False
                    })

                    logger.info(f"✅ Step {step_num} complete")

            except Exception as e:
                logger.error(f"❌ Step {step_num} failed: {str(e)}")
                results.append({
                    "step": step_num,
                    "service": service,
                    "action": action,
                    "status": "failed",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "resilience_used": False
                })
                total_failures += 1

            continue

        # Use resilient client with all patterns
        try:
            url = f"/{action}"
            response = await client.post(url, json=step.get("params", {}))

            results.append({
                "step": step_num,
                "service": service,
                "action": action,
                "status": "success",
                "result": response.json(),
                "resilience_used": True,
                "patterns": {
                    "circuit_breaker": settings.circuit_breaker_enabled,
                    "retry": settings.retry_enabled,
                    "bulkhead": settings.bulkhead_enabled
                }
            })

            logger.info(f"✅ Step {step_num} complete")

        except CircuitBreakerError as e:
            # Circuit breaker open - service is down
            logger.error(f"❌ Step {step_num} failed: Circuit breaker OPEN for {service}")
            results.append({
                "step": step_num,
                "service": service,
                "action": action,
                "status": "failed",
                "error": f"Circuit breaker is OPEN for {service}. Service temporarily unavailable.",
                "error_type": "circuit_breaker_open",
                "resilience_used": True,
                "retry_after": settings.circuit_breaker_timeout
            })
            total_failures += 1
            circuit_breaker_failures += 1

        except RetryExhaustedError as e:
            # All retries exhausted
            logger.error(f"❌ Step {step_num} failed: All retries exhausted for {service}")
            results.append({
                "step": step_num,
                "service": service,
                "action": action,
                "status": "failed",
                "error": f"All {settings.retry_max_attempts} retry attempts exhausted for {service}",
                "error_type": "retry_exhausted",
                "resilience_used": True,
                "max_attempts": settings.retry_max_attempts
            })
            total_failures += 1

        except BulkheadFullError as e:
            # Too many concurrent requests
            logger.error(f"❌ Step {step_num} failed: Bulkhead full for {service}")
            results.append({
                "step": step_num,
                "service": service,
                "action": action,
                "status": "failed",
                "error": f"Too many concurrent requests to {service}. Bulkhead at capacity.",
                "error_type": "bulkhead_full",
                "resilience_used": True,
                "max_concurrent": settings.bulkhead_max_concurrent
            })
            total_failures += 1

        except httpx.HTTPStatusError as e:
            # HTTP error from service
            logger.error(f"❌ Step {step_num} failed: HTTP {e.response.status_code} from {service}")
            results.append({
                "step": step_num,
                "service": service,
                "action": action,
                "status": "failed",
                "error": str(e),
                "error_type": "http_error",
                "status_code": e.response.status_code,
                "resilience_used": True
            })
            total_failures += 1

        except Exception as e:
            # Unexpected error
            logger.error(f"❌ Step {step_num} failed: {type(e).__name__}: {str(e)}")
            results.append({
                "step": step_num,
                "service": service,
                "action": action,
                "status": "failed",
                "error": str(e),
                "error_type": type(e).__name__,
                "resilience_used": True
            })
            total_failures += 1

    # Determine overall workflow status
    total_steps = len(plan.steps)
    success_count = total_steps - total_failures

    if total_failures == 0:
        workflow_status = "completed_successfully"
        catchphrase = "That'll learn ya!"
    elif success_count > 0:
        workflow_status = "partially_completed"
        catchphrase = "I'll moida ya!" if circuit_breaker_failures > 0 else "Spread out!"
    else:
        workflow_status = "failed"
        catchphrase = "Why you little...!"

    return {
        "stooge": "moe",
        "workflow_status": workflow_status,
        "total_steps": total_steps,
        "successful_steps": success_count,
        "failed_steps": total_failures,
        "circuit_breaker_failures": circuit_breaker_failures,
        "results": results,
        "catchphrase": catchphrase,
        "resilience_summary": {
            "circuit_breaker_enabled": settings.circuit_breaker_enabled,
            "retry_enabled": settings.retry_enabled,
            "bulkhead_enabled": settings.bulkhead_enabled,
            "max_retries": settings.retry_max_attempts if settings.retry_enabled else 0,
            "circuit_breaker_timeout": settings.circuit_breaker_timeout if settings.circuit_breaker_enabled else 0
        }
    }


# ============================================================================
# API v1 Endpoints
# ============================================================================

@app.post("/v1/plan", response_model=WorkflowPlan)
async def plan_v1(request: WorkflowRequest):
    """Create an orchestration plan for multi-service workflows (API v1)."""
    return await _plan_handler(request)

@app.post("/v1/execute")
async def execute_v1(plan: WorkflowPlan):
    """Execute a workflow plan by orchestrating service calls (API v1)."""
    return await _execute_handler(plan)

# ============================================================================
# Legacy Endpoints (Backward Compatibility)
# ============================================================================

@app.post("/plan", response_model=WorkflowPlan)
async def plan_legacy(request: WorkflowRequest):
    """
    DEPRECATED: Use /v1/plan instead.
    Create an orchestration plan for multi-service workflows.
    """
    logger.warning("Deprecated endpoint /plan used. Please migrate to /v1/plan")
    return await _plan_handler(request)

@app.post("/execute")
async def execute_legacy(plan: WorkflowPlan):
    """
    DEPRECATED: Use /v1/execute instead.
    Execute a workflow plan by orchestrating service calls.
    """
    logger.warning("Deprecated endpoint /execute used. Please migrate to /v1/execute")
    return await _execute_handler(plan)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8008)
