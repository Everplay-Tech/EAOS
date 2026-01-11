"""
HARRY - The Monitor Stooge
"Nyuk nyuk nyuk!" - Harry watches everything

Monitors and coordinates service health.
Tracks system state, service availability, and performance.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import logging
from pathlib import Path
from llama_cpp import Llama
import httpx
import asyncio
from datetime import datetime

# Import BIOwerk matrix modules for observability and health
from matrix.observability import setup_instrumentation
from matrix.health import setup_health_endpoints
from matrix.validation import setup_validation_middleware
from matrix.errors import ValidationError
from pydantic import ValidationError as PydanticValidationError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Harry - Monitor Stooge")

# Setup comprehensive observability and health endpoints
setup_instrumentation(app, service_name="harry", service_version="1.0.0")
setup_validation_middleware(app)
setup_health_endpoints(app, service_name="harry", version="1.0.0")

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
    "larry": "http://larry:8007",
    "moe": "http://moe:8008",
}

# Health tracking
health_history = {}


@app.on_event("startup")
async def load_model():
    """Load Harry's PHI2 brain on startup."""
    global llm
    if MODEL_PATH.exists():
        logger.info(f"🎭 Harry is waking up... Loading model from {MODEL_PATH}")
        llm = Llama(
            model_path=str(MODEL_PATH),
            n_ctx=2048,
            n_gpu_layers=0,
            verbose=False
        )
        logger.info("🎭 Harry is ready! 'Nyuk nyuk nyuk!'")
    else:
        logger.warning(f"⚠️  Harry's brain not found at {MODEL_PATH}")
        logger.warning("   Run: ./scripts/download-models.sh stooges")


class ServiceStatus(BaseModel):
    """Status of a single service."""
    service: str
    status: str  # healthy, unhealthy, unknown
    response_time: Optional[float] = None
    last_check: str
    details: Optional[Dict[str, Any]] = None


class SystemReport(BaseModel):
    """Overall system health report."""
    timestamp: str
    overall_status: str
    services: List[ServiceStatus]
    recommendations: Optional[List[str]] = None


@app.get("/health")
async def health():
    """Check if Harry is alive."""
    return {
        "status": "healthy",
        "stooge": "harry",
        "role": "monitor",
        "model_loaded": llm is not None,
        "catchphrase": "Nyuk nyuk nyuk!",
        "monitoring": list(SERVICES.keys())
    }


async def _check_service_handler(service: str):
    """Check health of a specific service."""
    if service not in SERVICES:
        raise HTTPException(status_code=404, detail=f"Unknown service: {service}")

    url = f"{SERVICES[service]}/health"
    logger.info(f"🎭 Harry checking {service}...")

    start_time = datetime.now()

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=5.0)
            response.raise_for_status()

            response_time = (datetime.now() - start_time).total_seconds()

            status = ServiceStatus(
                service=service,
                status="healthy",
                response_time=response_time,
                last_check=datetime.now().isoformat(),
                details=response.json()
            )

            # Track history
            if service not in health_history:
                health_history[service] = []
            health_history[service].append({
                "timestamp": datetime.now().isoformat(),
                "status": "healthy",
                "response_time": response_time
            })

            logger.info(f"✅ {service} is healthy ({response_time:.3f}s)")

            return status

    except Exception as e:
        logger.error(f"❌ {service} check failed: {str(e)}")

        status = ServiceStatus(
            service=service,
            status="unhealthy",
            response_time=None,
            last_check=datetime.now().isoformat(),
            details={"error": str(e)}
        )

        # Track history
        if service not in health_history:
            health_history[service] = []
        health_history[service].append({
            "timestamp": datetime.now().isoformat(),
            "status": "unhealthy",
            "error": str(e)
        })

        return status


async def _check_all_handler():
    """Check health of all services."""
    logger.info("🎭 Harry checking all services...")

    tasks = [_check_service_handler(service) for service in SERVICES.keys()]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    statuses = []
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Check failed: {result}")
        else:
            statuses.append(result)

    # Determine overall status
    healthy_count = sum(1 for s in statuses if s.status == "healthy")
    total_count = len(statuses)

    if healthy_count == total_count:
        overall_status = "healthy"
    elif healthy_count > total_count / 2:
        overall_status = "degraded"
    else:
        overall_status = "unhealthy"

    return {
        "stooge": "harry",
        "overall_status": overall_status,
        "services": statuses,
        "summary": f"{healthy_count}/{total_count} services healthy",
        "catchphrase": "I'm watchin' everything!"
    }


async def _analyze_handler():
    """
    Use Harry's AI to analyze system health and provide recommendations.
    """
    if llm is None:
        raise HTTPException(status_code=503, detail="Harry's brain not loaded. Download phi2 model first.")

    logger.info("🎭 Harry analyzing system health...")

    # Get current status
    status_data = await check_all_services()

    system_prompt = """You are Harry, a monitoring AI. Analyze the system health data and provide:
1. Overall assessment
2. Specific issues found
3. Recommendations for improvement

Be concise but helpful. Respond in JSON format with: {assessment, issues, recommendations}"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Analyze this system status: {status_data}"}
    ]

    try:
        response = llm.create_chat_completion(
            messages=messages,
            temperature=0.3,
            max_tokens=512,
            response_format={"type": "json_object"}
        )

        result = response['choices'][0]['message']['content']
        logger.info(f"🎭 Harry's analysis: {result}")

        import json
        analysis = json.loads(result)

        return {
            "stooge": "harry",
            "timestamp": datetime.now().isoformat(),
            "status_data": status_data,
            "analysis": analysis,
            "catchphrase": "Nyuk nyuk nyuk!"
        }

    except Exception as e:
        logger.error(f"❌ Harry's analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


async def _history_handler(service: str, limit: int = 10):
    """Get health check history for a service."""
    if service not in SERVICES:
        raise HTTPException(status_code=404, detail=f"Unknown service: {service}")

    history = health_history.get(service, [])

    return {
        "stooge": "harry",
        "service": service,
        "history": history[-limit:],
        "total_checks": len(history)
    }


# ============================================================================
# API v1 Endpoints
# ============================================================================

@app.get("/v1/check/{service}")
async def check_service_v1(service: str):
    """Check health of a specific service (API v1)."""
    return await _check_service_handler(service)

@app.get("/v1/check-all")
async def check_all_v1():
    """Check health of all services (API v1)."""
    return await _check_all_handler()

@app.post("/v1/analyze")
async def analyze_v1():
    """Analyze system health using Harry's AI brain (API v1)."""
    return await _analyze_handler()

@app.get("/v1/history/{service}")
async def history_v1(service: str, limit: int = 10):
    """Get health check history for a service (API v1)."""
    return await _history_handler(service, limit)

# ============================================================================
# Legacy Endpoints (Backward Compatibility)
# ============================================================================

@app.get("/check/{service}")
async def check_service_legacy(service: str):
    """
    DEPRECATED: Use /v1/check/{service} instead.
    Check health of a specific service.
    """
    logger.warning(f"Deprecated endpoint /check/{service} used. Please migrate to /v1/check/{service}")
    return await _check_service_handler(service)

@app.get("/check-all")
async def check_all_legacy():
    """
    DEPRECATED: Use /v1/check-all instead.
    Check health of all services.
    """
    logger.warning("Deprecated endpoint /check-all used. Please migrate to /v1/check-all")
    return await _check_all_handler()

@app.post("/analyze")
async def analyze_legacy():
    """
    DEPRECATED: Use /v1/analyze instead.
    Analyze system health using Harry's AI brain.
    """
    logger.warning("Deprecated endpoint /analyze used. Please migrate to /v1/analyze")
    return await _analyze_handler()

@app.get("/history/{service}")
async def history_legacy(service: str, limit: int = 10):
    """
    DEPRECATED: Use /v1/history/{service} instead.
    Get health check history for a service.
    """
    logger.warning(f"Deprecated endpoint /history/{service} used. Please migrate to /v1/history/{service}")
    return await _history_handler(service, limit)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8009)
