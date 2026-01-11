"""GDPR Compliance Service for BIOwerk.

This service provides comprehensive GDPR compliance endpoints for:
- Data Subject Access Requests (DSAR)
- Right to be Forgotten / Data Erasure
- Data Portability
- Consent Management
- Privacy Settings
- Cookie Consent
- Data Retention
- Breach Notification

Compliance: GDPR, CCPA, HIPAA, PCI-DSS
"""

from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.responses import FileResponse
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import time

from matrix.models import Msg, Reply
from matrix.observability import setup_instrumentation
from matrix.utils import state_hash
from matrix.logging_config import setup_logging, log_request, log_response, log_error
from matrix.errors import create_error_response, ValidationError
from matrix.database import get_db, get_session_manager
from matrix.encryption import EncryptionService
from matrix.audit import AuditService
from matrix.gdpr import GDPRService, GDPRError, DataRequestError, ConsentError
from matrix.auth import get_current_user
from matrix.validation import setup_validation_middleware
from pydantic import ValidationError as PydanticValidationError

app = FastAPI(
    title="GDPR Compliance Service",
    description="Enterprise GDPR compliance and privacy management",
    version="1.0.0"
)
setup_instrumentation(app, service_name="gdpr", service_version="1.0.0")
setup_validation_middleware(app)
logger = setup_logging("gdpr")
session_mgr = get_session_manager("long")  # 8-hour sessions for long-running operations

# Setup comprehensive health and readiness endpoints
from matrix.health import setup_health_endpoints
setup_health_endpoints(app, service_name="gdpr", version="1.0.0")


# ============================================================================
# Helper Functions
# ============================================================================

async def get_gdpr_service(db = Depends(get_db)) -> GDPRService:
    """Dependency to get GDPR service instance."""
    # Initialize encryption service (use environment variable for master key)
    import os
    master_key = os.getenv("ENCRYPTION_MASTER_KEY", "dev_key_change_in_production_min_32_chars")
    encryption = EncryptionService(master_key=master_key)

    # Initialize audit service
    audit = AuditService(db=db, encryption_service=encryption)

    # Initialize GDPR service
    return GDPRService(
        db=db,
        encryption_service=encryption,
        audit_service=audit,
        export_base_path="/var/gdpr_exports"
    )


def get_client_info(request: Request) -> Dict[str, str]:
    """Extract client information from request."""
    return {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent")
    }


# ============================================================================
# Data Access Requests (Article 15)
# ============================================================================

# ============================================================================
# Internal Handler Functions
# ============================================================================

async def _create_access_request_handler(
    msg: Msg,
    request: Request,
    gdpr: GDPRService = Depends(get_gdpr_service)
):
    """
    Create a data access request (GDPR Article 15 - Right to Access).

    User can request a copy of all their personal data.
    Response must be provided within 30 days.
    """
    start_time = time.time()
    log_request(logger, msg.id, "gdpr", "create_access_request")

    try:
        inp = msg.input or {}
        user_id = inp.get("user_id")
        description = inp.get("description")
        data_types = inp.get("data_types")  # Optional: specific data types
        export_format = inp.get("format", "json")

        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")

        client_info = get_client_info(request)

        data_request = await gdpr.create_access_request(
            user_id=user_id,
            description=description,
            requested_data_types=data_types,
            export_format=export_format,
            ip_address=client_info["ip_address"],
            user_agent=client_info["user_agent"]
        )

        output = {
            "request_id": data_request.id,
            "request_type": data_request.request_type,
            "status": data_request.request_status,
            "due_date": data_request.due_date.isoformat(),
            "message": "Access request created. You will be notified when your data is ready (within 30 days)."
        }

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "gdpr", True, duration_ms)

        return Reply(
            id=msg.id,
            ts=time.time(),
            agent="gdpr",
            ok=True,
            output=output,
            state_hash=state_hash(output)
        )

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "gdpr", e))


async def _generate_export_handler(
    msg: Msg,
    gdpr: GDPRService = Depends(get_gdpr_service)
):
    """
    Generate export file for an access request.

    Admin/system endpoint to process pending access requests.
    """
    start_time = time.time()
    log_request(logger, msg.id, "gdpr", "generate_export")

    try:
        inp = msg.input or {}
        request_id = inp.get("request_id")
        export_format = inp.get("format", "json")

        if not request_id:
            raise HTTPException(status_code=400, detail="request_id is required")

        file_path, file_hash = await gdpr.generate_export_file(
            request_id=request_id,
            format=export_format
        )

        output = {
            "request_id": request_id,
            "file_path": file_path,
            "file_hash": file_hash,
            "format": export_format,
            "status": "completed",
            "message": "Export file generated successfully"
        }

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "gdpr", True, duration_ms)

        return Reply(
            id=msg.id,
            ts=time.time(),
            agent="gdpr",
            ok=True,
            output=output,
            state_hash=state_hash(output)
        )

    except DataRequestError as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "gdpr", e))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "gdpr", e))


async def _export_user_data_handler(
    msg: Msg,
    gdpr: GDPRService = Depends(get_gdpr_service)
):
    """
    Export user data directly (without creating a formal request).

    Useful for immediate data portability needs.
    """
    start_time = time.time()
    log_request(logger, msg.id, "gdpr", "export_user_data")

    try:
        inp = msg.input or {}
        user_id = inp.get("user_id")
        data_types = inp.get("data_types")
        export_format = inp.get("format", "json")

        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")

        data = await gdpr.export_user_data(
            user_id=user_id,
            data_types=data_types,
            format=export_format
        )

        output = {
            "export_data": data,
            "format": export_format
        }

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "gdpr", True, duration_ms)

        return Reply(
            id=msg.id,
            ts=time.time(),
            agent="gdpr",
            ok=True,
            output=output,
            state_hash=state_hash(output)
        )

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "gdpr", e))


# ============================================================================
# Right to Erasure / Right to be Forgotten (Article 17)
# ============================================================================

async def _create_erasure_request_handler(
    msg: Msg,
    request: Request,
    gdpr: GDPRService = Depends(get_gdpr_service)
):
    """
    Create a data erasure request (GDPR Article 17 - Right to be Forgotten).

    User can request deletion or anonymization of their personal data.
    """
    start_time = time.time()
    log_request(logger, msg.id, "gdpr", "create_erasure_request")

    try:
        inp = msg.input or {}
        user_id = inp.get("user_id")
        description = inp.get("description")
        erasure_method = inp.get("method", "anonymization")  # soft_delete, anonymization, hard_delete

        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")

        if erasure_method not in ["soft_delete", "anonymization", "hard_delete"]:
            raise HTTPException(status_code=400, detail="Invalid erasure method")

        client_info = get_client_info(request)

        data_request = await gdpr.create_erasure_request(
            user_id=user_id,
            description=description,
            erasure_method=erasure_method,
            ip_address=client_info["ip_address"],
            user_agent=client_info["user_agent"]
        )

        output = {
            "request_id": data_request.id,
            "request_type": data_request.request_type,
            "status": data_request.request_status,
            "erasure_method": erasure_method,
            "due_date": data_request.due_date.isoformat(),
            "message": "Erasure request created. Your data will be processed within 30 days.",
            "warning": "This action cannot be undone. Please review carefully."
        }

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "gdpr", True, duration_ms)

        return Reply(
            id=msg.id,
            ts=time.time(),
            agent="gdpr",
            ok=True,
            output=output,
            state_hash=state_hash(output)
        )

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "gdpr", e))


async def _anonymize_user_handler(
    msg: Msg,
    gdpr: GDPRService = Depends(get_gdpr_service)
):
    """
    Anonymize user data (Right to be Forgotten implementation).

    Replaces PII with anonymized values while preserving system integrity.
    """
    start_time = time.time()
    log_request(logger, msg.id, "gdpr", "anonymize_user")

    try:
        inp = msg.input or {}
        user_id = inp.get("user_id")
        preserve_audit = inp.get("preserve_audit_trail", True)

        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")

        summary = await gdpr.anonymize_user_data(
            user_id=user_id,
            preserve_audit_trail=preserve_audit
        )

        output = {
            "user_id": user_id,
            "anonymized": True,
            "summary": summary,
            "message": "User data has been anonymized successfully"
        }

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "gdpr", True, duration_ms)

        return Reply(
            id=msg.id,
            ts=time.time(),
            agent="gdpr",
            ok=True,
            output=output,
            state_hash=state_hash(output)
        )

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "gdpr", e))


# ============================================================================
# Consent Management (Article 7)
# ============================================================================

async def _record_consent_handler(
    msg: Msg,
    request: Request,
    gdpr: GDPRService = Depends(get_gdpr_service)
):
    """
    Record user consent for data processing.

    Consent must be freely given, specific, informed, and unambiguous.
    """
    start_time = time.time()
    log_request(logger, msg.id, "gdpr", "record_consent")

    try:
        inp = msg.input or {}
        user_id = inp.get("user_id")
        purpose = inp.get("purpose")
        purpose_description = inp.get("purpose_description")
        consent_given = inp.get("consent_given", True)
        consent_category = inp.get("category", "functional")
        legal_basis = inp.get("legal_basis", "consent")
        consent_method = inp.get("method", "checkbox")
        consent_version = inp.get("version", "1.0")
        expires_in_days = inp.get("expires_in_days")

        if not all([user_id, purpose, purpose_description]):
            raise HTTPException(
                status_code=400,
                detail="user_id, purpose, and purpose_description are required"
            )

        client_info = get_client_info(request)

        consent = await gdpr.record_consent(
            user_id=user_id,
            purpose=purpose,
            purpose_description=purpose_description,
            consent_given=consent_given,
            consent_category=consent_category,
            legal_basis=legal_basis,
            consent_method=consent_method,
            consent_version=consent_version,
            expires_in_days=expires_in_days,
            ip_address=client_info["ip_address"],
            user_agent=client_info["user_agent"]
        )

        output = {
            "consent_id": consent.id,
            "user_id": user_id,
            "purpose": purpose,
            "consent_given": consent_given,
            "granted_at": consent.granted_at.isoformat(),
            "expires_at": consent.expires_at.isoformat() if consent.expires_at else None,
            "message": "Consent recorded successfully"
        }

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "gdpr", True, duration_ms)

        return Reply(
            id=msg.id,
            ts=time.time(),
            agent="gdpr",
            ok=True,
            output=output,
            state_hash=state_hash(output)
        )

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "gdpr", e))


async def _withdraw_consent_handler(
    msg: Msg,
    gdpr: GDPRService = Depends(get_gdpr_service)
):
    """
    Withdraw user consent for a specific purpose.

    Users have the right to withdraw consent at any time.
    """
    start_time = time.time()
    log_request(logger, msg.id, "gdpr", "withdraw_consent")

    try:
        inp = msg.input or {}
        user_id = inp.get("user_id")
        purpose = inp.get("purpose")
        withdrawal_method = inp.get("method", "user_request")

        if not all([user_id, purpose]):
            raise HTTPException(status_code=400, detail="user_id and purpose are required")

        withdrawn = await gdpr.withdraw_consent(
            user_id=user_id,
            purpose=purpose,
            withdrawal_method=withdrawal_method
        )

        output = {
            "user_id": user_id,
            "purpose": purpose,
            "withdrawn": withdrawn,
            "message": "Consent withdrawn successfully" if withdrawn else "No active consent found"
        }

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "gdpr", True, duration_ms)

        return Reply(
            id=msg.id,
            ts=time.time(),
            agent="gdpr",
            ok=True,
            output=output,
            state_hash=state_hash(output)
        )

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "gdpr", e))


async def _check_consent_handler(
    msg: Msg,
    gdpr: GDPRService = Depends(get_gdpr_service)
):
    """
    Check if user has given valid consent for a purpose.
    """
    start_time = time.time()
    log_request(logger, msg.id, "gdpr", "check_consent")

    try:
        inp = msg.input or {}
        user_id = inp.get("user_id")
        purpose = inp.get("purpose")

        if not all([user_id, purpose]):
            raise HTTPException(status_code=400, detail="user_id and purpose are required")

        has_consent = await gdpr.check_consent(user_id=user_id, purpose=purpose)

        output = {
            "user_id": user_id,
            "purpose": purpose,
            "has_consent": has_consent
        }

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "gdpr", True, duration_ms)

        return Reply(
            id=msg.id,
            ts=time.time(),
            agent="gdpr",
            ok=True,
            output=output,
            state_hash=state_hash(output)
        )

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "gdpr", e))


# ============================================================================
# Privacy Settings
# ============================================================================

async def _get_privacy_settings_handler(
    msg: Msg,
    gdpr: GDPRService = Depends(get_gdpr_service)
):
    """Get user privacy settings."""
    start_time = time.time()
    log_request(logger, msg.id, "gdpr", "get_privacy_settings")

    try:
        inp = msg.input or {}
        user_id = inp.get("user_id")

        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")

        settings = await gdpr.get_or_create_privacy_settings(user_id=user_id)

        output = {
            "user_id": user_id,
            "privacy_level": settings.privacy_level,
            "email_marketing_enabled": settings.email_marketing_enabled,
            "analytics_enabled": settings.analytics_enabled,
            "personalization_enabled": settings.personalization_enabled,
            "third_party_sharing": settings.third_party_sharing,
            "ai_training_opt_in": settings.ai_training_opt_in,
            "profiling_enabled": settings.profiling_enabled,
            "preferred_export_format": settings.preferred_export_format,
            "cookies": {
                "essential": settings.essential_cookies,
                "functional": settings.functional_cookies,
                "analytics": settings.analytics_cookies,
                "marketing": settings.marketing_cookies
            },
            "updated_at": settings.updated_at.isoformat() if settings.updated_at else None
        }

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "gdpr", True, duration_ms)

        return Reply(
            id=msg.id,
            ts=time.time(),
            agent="gdpr",
            ok=True,
            output=output,
            state_hash=state_hash(output)
        )

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "gdpr", e))


async def _update_privacy_settings_handler(
    msg: Msg,
    gdpr: GDPRService = Depends(get_gdpr_service)
):
    """Update user privacy settings."""
    start_time = time.time()
    log_request(logger, msg.id, "gdpr", "update_privacy_settings")

    try:
        inp = msg.input or {}
        user_id = inp.get("user_id")

        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")

        # Extract settings to update
        updates = {k: v for k, v in inp.items() if k != "user_id"}

        settings = await gdpr.update_privacy_settings(user_id=user_id, **updates)

        output = {
            "user_id": user_id,
            "updated": True,
            "message": "Privacy settings updated successfully"
        }

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "gdpr", True, duration_ms)

        return Reply(
            id=msg.id,
            ts=time.time(),
            agent="gdpr",
            ok=True,
            output=output,
            state_hash=state_hash(output)
        )

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "gdpr", e))


# ============================================================================
# Data Retention (Article 5)
# ============================================================================

async def _enforce_retention_policies_handler(
    msg: Msg,
    gdpr: GDPRService = Depends(get_gdpr_service)
):
    """
    Enforce data retention policies (admin endpoint).

    Automatically deletes data that has exceeded retention periods.
    """
    start_time = time.time()
    log_request(logger, msg.id, "gdpr", "enforce_retention_policies")

    try:
        summary = await gdpr.enforce_retention_policies()

        output = {
            "enforced": True,
            "summary": summary,
            "message": "Data retention policies enforced successfully"
        }

        duration_ms = (time.time() - start_time) * 1000
        log_response(logger, msg.id, "gdpr", True, duration_ms)

        return Reply(
            id=msg.id,
            ts=time.time(),
            agent="gdpr",
            ok=True,
            output=output,
            state_hash=state_hash(output)
        )

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(logger, msg.id, e, duration_ms=duration_ms)
        return Reply(**create_error_response(msg.id, "gdpr", e))


# ============================================================================
# Health Check
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "service": "gdpr",
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "compliance_standards": ["GDPR", "CCPA", "HIPAA", "PCI-DSS"]
    }




# ============================================================================
# API v1 Endpoints
# ============================================================================

@app.post("/v1/request/access", response_model=Reply)
async def create_access_request_v1(msg: Msg):
    """Create Access Request (API v1)."""
    return await _create_access_request_handler(msg)

@app.post("/v1/export/generate", response_model=Reply)
async def generate_export_v1(msg: Msg):
    """Generate Export (API v1)."""
    return await _generate_export_handler(msg)

@app.post("/v1/export/data", response_model=Reply)
async def export_user_data_v1(msg: Msg):
    """Export User Data (API v1)."""
    return await _export_user_data_handler(msg)

@app.post("/v1/request/erasure", response_model=Reply)
async def create_erasure_request_v1(msg: Msg):
    """Create Erasure Request (API v1)."""
    return await _create_erasure_request_handler(msg)

@app.post("/v1/anonymize", response_model=Reply)
async def anonymize_user_v1(msg: Msg):
    """Anonymize User (API v1)."""
    return await _anonymize_user_handler(msg)

@app.post("/v1/consent/record", response_model=Reply)
async def record_consent_v1(msg: Msg):
    """Record Consent (API v1)."""
    return await _record_consent_handler(msg)

@app.post("/v1/consent/withdraw", response_model=Reply)
async def withdraw_consent_v1(msg: Msg):
    """Withdraw Consent (API v1)."""
    return await _withdraw_consent_handler(msg)

@app.post("/v1/consent/check", response_model=Reply)
async def check_consent_v1(msg: Msg):
    """Check Consent (API v1)."""
    return await _check_consent_handler(msg)

@app.post("/v1/privacy/settings/get", response_model=Reply)
async def get_privacy_settings_v1(msg: Msg):
    """Get Privacy Settings (API v1)."""
    return await _get_privacy_settings_handler(msg)

@app.post("/v1/privacy/settings/update", response_model=Reply)
async def update_privacy_settings_v1(msg: Msg):
    """Update Privacy Settings (API v1)."""
    return await _update_privacy_settings_handler(msg)

@app.post("/v1/retention/enforce", response_model=Reply)
async def enforce_retention_policies_v1(msg: Msg):
    """Enforce Retention Policies (API v1)."""
    return await _enforce_retention_policies_handler(msg)

# ============================================================================
# Legacy Endpoints (Backward Compatibility)
# ============================================================================

@app.post("/request/access", response_model=Reply)
async def create_access_request_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/request/access instead.
    Create Access Request.
    """
    logger.warning("Deprecated endpoint /request/access used. Please migrate to /v1/request/access")
    return await _create_access_request_handler(msg)

@app.post("/export/generate", response_model=Reply)
async def generate_export_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/export/generate instead.
    Generate Export.
    """
    logger.warning("Deprecated endpoint /export/generate used. Please migrate to /v1/export/generate")
    return await _generate_export_handler(msg)

@app.post("/export/data", response_model=Reply)
async def export_user_data_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/export/data instead.
    Export User Data.
    """
    logger.warning("Deprecated endpoint /export/data used. Please migrate to /v1/export/data")
    return await _export_user_data_handler(msg)

@app.post("/request/erasure", response_model=Reply)
async def create_erasure_request_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/request/erasure instead.
    Create Erasure Request.
    """
    logger.warning("Deprecated endpoint /request/erasure used. Please migrate to /v1/request/erasure")
    return await _create_erasure_request_handler(msg)

@app.post("/anonymize", response_model=Reply)
async def anonymize_user_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/anonymize instead.
    Anonymize User.
    """
    logger.warning("Deprecated endpoint /anonymize used. Please migrate to /v1/anonymize")
    return await _anonymize_user_handler(msg)

@app.post("/consent/record", response_model=Reply)
async def record_consent_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/consent/record instead.
    Record Consent.
    """
    logger.warning("Deprecated endpoint /consent/record used. Please migrate to /v1/consent/record")
    return await _record_consent_handler(msg)

@app.post("/consent/withdraw", response_model=Reply)
async def withdraw_consent_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/consent/withdraw instead.
    Withdraw Consent.
    """
    logger.warning("Deprecated endpoint /consent/withdraw used. Please migrate to /v1/consent/withdraw")
    return await _withdraw_consent_handler(msg)

@app.post("/consent/check", response_model=Reply)
async def check_consent_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/consent/check instead.
    Check Consent.
    """
    logger.warning("Deprecated endpoint /consent/check used. Please migrate to /v1/consent/check")
    return await _check_consent_handler(msg)

@app.post("/privacy/settings/get", response_model=Reply)
async def get_privacy_settings_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/privacy/settings/get instead.
    Get Privacy Settings.
    """
    logger.warning("Deprecated endpoint /privacy/settings/get used. Please migrate to /v1/privacy/settings/get")
    return await _get_privacy_settings_handler(msg)

@app.post("/privacy/settings/update", response_model=Reply)
async def update_privacy_settings_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/privacy/settings/update instead.
    Update Privacy Settings.
    """
    logger.warning("Deprecated endpoint /privacy/settings/update used. Please migrate to /v1/privacy/settings/update")
    return await _update_privacy_settings_handler(msg)

@app.post("/retention/enforce", response_model=Reply)
async def enforce_retention_policies_legacy(msg: Msg):
    """
    DEPRECATED: Use /v1/retention/enforce instead.
    Enforce Retention Policies.
    """
    logger.warning("Deprecated endpoint /retention/enforce used. Please migrate to /v1/retention/enforce")
    return await _enforce_retention_policies_handler(msg)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8010)
