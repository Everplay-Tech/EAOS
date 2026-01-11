"""
Data Retention Management Service

FastAPI microservice for managing data retention policies and compliance.
Provides REST API endpoints for policy management, archival, and compliance reporting.

Author: BIOwerk Security Team
Version: 1.0.0
"""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from matrix.database import get_db_session, async_session_maker
from matrix.encryption import EncryptionService
from matrix.audit import AuditLogger, EventType, EventCategory, EventAction, EventStatus, Severity
from matrix.auth_dependencies import get_current_active_user, require_admin
from matrix.db_models import User, RetentionPolicy as DBRetentionPolicy
from matrix.retention_policy import (
    DataType,
    RetentionAction,
    ComplianceFramework,
    RetentionPolicyEngine,
)
from matrix.retention_manager import RetentionPolicyManager
from matrix.retention_scheduler import start_retention_scheduler, stop_retention_scheduler
from matrix.config import Settings


# Pydantic models for API
class RetentionPolicyCreate(BaseModel):
    """Request model for creating a retention policy"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    data_type: DataType
    retention_period_days: int = Field(..., gt=0)
    action: RetentionAction
    compliance_framework: ComplianceFramework
    category_filter: Optional[List[str]] = None
    user_filter: Optional[List[str]] = None
    conditions: Optional[dict] = None
    archive_before_delete: bool = True
    regulatory_citation: Optional[str] = None
    priority: int = Field(default=0, ge=0)


class RetentionPolicyUpdate(BaseModel):
    """Request model for updating a retention policy"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    retention_period_days: Optional[int] = Field(None, gt=0)
    action: Optional[RetentionAction] = None
    category_filter: Optional[List[str]] = None
    user_filter: Optional[List[str]] = None
    conditions: Optional[dict] = None
    archive_before_delete: Optional[bool] = None
    regulatory_citation: Optional[str] = None
    priority: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None


class RetentionPolicyResponse(BaseModel):
    """Response model for retention policy"""
    id: str
    name: str
    description: Optional[str]
    data_type: str
    retention_period_days: int
    action: str
    compliance_framework: str
    archive_before_delete: bool
    priority: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_enforced_at: Optional[datetime]

    class Config:
        from_attributes = True


class LegalHoldRequest(BaseModel):
    """Request model for applying legal hold"""
    reason: str = Field(..., min_length=1)


class ArchiveRestoreRequest(BaseModel):
    """Request model for restoring from archive"""
    archive_id: UUID


class PolicyEvaluationRequest(BaseModel):
    """Request model for manual policy evaluation"""
    data_type: Optional[DataType] = None
    dry_run: bool = True


class ComplianceReportRequest(BaseModel):
    """Request model for compliance report"""
    framework: Optional[ComplianceFramework] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


# Initialize services
settings = Settings()
encryption_service = EncryptionService(
    master_key=settings.ENCRYPTION_MASTER_KEY,
    key_version=settings.ENCRYPTION_KEY_VERSION,
)
audit_logger = AuditLogger(
    db_session_maker=async_session_maker,
    encryption_service=encryption_service,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    # Startup
    app.state.scheduler = await start_retention_scheduler(
        session_maker=async_session_maker,
        encryption_service=encryption_service,
        audit_logger=audit_logger,
    )

    yield

    # Shutdown
    await stop_retention_scheduler()


# Create FastAPI app
app = FastAPI(
    title="BIOwerk Data Retention Service",
    description="Enterprise-grade data retention management for SOC2, HIPAA, GDPR, and PCI-DSS compliance",
    version="1.0.0",
    lifespan=lifespan,
)


# Health check
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "retention",
        "timestamp": datetime.utcnow().isoformat(),
    }


# Retention Policy Management
@app.post(
    "/api/v1/retention/policies",
    response_model=RetentionPolicyResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Policies"],
    dependencies=[Depends(require_admin)],
)
async def create_retention_policy(
    policy: RetentionPolicyCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Create a new data retention policy (Admin only)"""
    manager = RetentionPolicyManager(
        db_session=db,
        audit_logger=audit_logger,
    )

    try:
        db_policy = await manager.create_policy(
            name=policy.name,
            description=policy.description,
            data_type=policy.data_type,
            retention_period_days=policy.retention_period_days,
            action=policy.action,
            compliance_framework=policy.compliance_framework,
            created_by_user_id=UUID(current_user.id),
            category_filter=policy.category_filter,
            user_filter=policy.user_filter,
            conditions=policy.conditions,
            archive_before_delete=policy.archive_before_delete,
            regulatory_citation=policy.regulatory_citation,
            priority=policy.priority,
        )

        return RetentionPolicyResponse.from_orm(db_policy)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.get(
    "/api/v1/retention/policies",
    response_model=List[RetentionPolicyResponse],
    tags=["Policies"],
)
async def list_retention_policies(
    data_type: Optional[DataType] = None,
    compliance_framework: Optional[ComplianceFramework] = None,
    is_active: Optional[bool] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """List retention policies with optional filters"""
    manager = RetentionPolicyManager(
        db_session=db,
        audit_logger=audit_logger,
    )

    policies = await manager.list_policies(
        data_type=data_type,
        compliance_framework=compliance_framework,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )

    return [RetentionPolicyResponse.from_orm(p) for p in policies]


@app.get(
    "/api/v1/retention/policies/{policy_id}",
    response_model=RetentionPolicyResponse,
    tags=["Policies"],
)
async def get_retention_policy(
    policy_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get a specific retention policy"""
    manager = RetentionPolicyManager(
        db_session=db,
        audit_logger=audit_logger,
    )

    policy = await manager.get_policy(policy_id)

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy {policy_id} not found",
        )

    return RetentionPolicyResponse.from_orm(policy)


@app.put(
    "/api/v1/retention/policies/{policy_id}",
    response_model=RetentionPolicyResponse,
    tags=["Policies"],
    dependencies=[Depends(require_admin)],
)
async def update_retention_policy(
    policy_id: UUID,
    policy: RetentionPolicyUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Update a retention policy (Admin only)"""
    manager = RetentionPolicyManager(
        db_session=db,
        audit_logger=audit_logger,
    )

    try:
        # Convert to dict and remove None values
        updates = {k: v for k, v in policy.dict().items() if v is not None}

        db_policy = await manager.update_policy(
            policy_id=policy_id,
            updated_by_user_id=UUID(current_user.id),
            **updates,
        )

        return RetentionPolicyResponse.from_orm(db_policy)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if "not found" in str(e) else status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.delete(
    "/api/v1/retention/policies/{policy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Policies"],
    dependencies=[Depends(require_admin)],
)
async def delete_retention_policy(
    policy_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Delete a retention policy (Admin only)"""
    manager = RetentionPolicyManager(
        db_session=db,
        audit_logger=audit_logger,
    )

    try:
        await manager.delete_policy(
            policy_id=policy_id,
            deleted_by_user_id=UUID(current_user.id),
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


# Policy Evaluation
@app.post(
    "/api/v1/retention/evaluate",
    tags=["Evaluation"],
    dependencies=[Depends(require_admin)],
)
async def evaluate_retention_policies(
    request: PolicyEvaluationRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Manually trigger retention policy evaluation (Admin only)"""
    engine = RetentionPolicyEngine(
        db_session=db,
        encryption_service=encryption_service,
        audit_logger=audit_logger,
    )

    if request.data_type:
        # Evaluate specific data type
        results = await engine.evaluate_retention_policies(
            data_type=request.data_type,
            dry_run=request.dry_run,
        )
        return results
    else:
        # Evaluate all data types
        all_results = {}
        for data_type in DataType:
            try:
                results = await engine.evaluate_retention_policies(
                    data_type=data_type,
                    dry_run=request.dry_run,
                )
                all_results[data_type] = results
            except Exception as e:
                all_results[data_type] = {"error": str(e)}

        return all_results


# Legal Holds
@app.post(
    "/api/v1/retention/legal-holds/{data_type}/{data_id}",
    tags=["Legal Holds"],
    dependencies=[Depends(require_admin)],
)
async def apply_legal_hold(
    data_type: DataType,
    data_id: UUID,
    request: LegalHoldRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Apply a legal hold to prevent data deletion (Admin only)"""
    engine = RetentionPolicyEngine(
        db_session=db,
        encryption_service=encryption_service,
        audit_logger=audit_logger,
    )

    schedule = await engine.apply_legal_hold(
        data_type=data_type,
        data_id=data_id,
        reason=request.reason,
        applied_by_user_id=UUID(current_user.id),
    )

    return {
        "status": "success",
        "message": f"Legal hold applied to {data_type} {data_id}",
        "schedule_id": str(schedule.id),
    }


@app.delete(
    "/api/v1/retention/legal-holds/{data_type}/{data_id}",
    tags=["Legal Holds"],
    dependencies=[Depends(require_admin)],
)
async def remove_legal_hold(
    data_type: DataType,
    data_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Remove a legal hold (Admin only)"""
    engine = RetentionPolicyEngine(
        db_session=db,
        encryption_service=encryption_service,
        audit_logger=audit_logger,
    )

    try:
        schedule = await engine.remove_legal_hold(
            data_type=data_type,
            data_id=data_id,
            removed_by_user_id=UUID(current_user.id),
        )

        return {
            "status": "success",
            "message": f"Legal hold removed from {data_type} {data_id}",
            "schedule_id": str(schedule.id),
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@app.get(
    "/api/v1/retention/legal-holds",
    tags=["Legal Holds"],
)
async def list_legal_holds(
    data_type: Optional[DataType] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """List all data under legal hold"""
    manager = RetentionPolicyManager(
        db_session=db,
        audit_logger=audit_logger,
    )

    holds = await manager.get_legal_holds(
        data_type=data_type,
        limit=limit,
        offset=offset,
    )

    return [
        {
            "id": str(hold.id),
            "data_type": hold.data_type,
            "data_id": hold.data_id,
            "reason": hold.legal_hold_reason,
            "applied_at": hold.legal_hold_applied_at.isoformat() if hold.legal_hold_applied_at else None,
            "applied_by": str(hold.legal_hold_applied_by) if hold.legal_hold_applied_by else None,
        }
        for hold in holds
    ]


# Archives
@app.get(
    "/api/v1/retention/archives",
    tags=["Archives"],
    dependencies=[Depends(require_admin)],
)
async def list_archives(
    data_type: Optional[DataType] = None,
    archive_status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """List archived data (Admin only)"""
    manager = RetentionPolicyManager(
        db_session=db,
        audit_logger=audit_logger,
    )

    archives = await manager.get_archives(
        data_type=data_type,
        archive_status=archive_status,
        limit=limit,
        offset=offset,
    )

    return [
        {
            "id": str(archive.id),
            "data_type": archive.data_type,
            "data_id": archive.data_id,
            "status": archive.archive_status,
            "archived_at": archive.archived_at.isoformat(),
            "expires_at": archive.expires_at.isoformat() if archive.expires_at else None,
        }
        for archive in archives
    ]


@app.post(
    "/api/v1/retention/archives/{archive_id}/restore",
    tags=["Archives"],
    dependencies=[Depends(require_admin)],
)
async def restore_from_archive(
    archive_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Restore data from archive (Admin only)"""
    engine = RetentionPolicyEngine(
        db_session=db,
        encryption_service=encryption_service,
        audit_logger=audit_logger,
    )

    try:
        data = await engine.restore_from_archive(
            archive_id=archive_id,
            user_id=UUID(current_user.id),
        )

        return {
            "status": "success",
            "message": f"Archive {archive_id} restored successfully",
            "data": data,
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if "not found" in str(e) else status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# Compliance Reporting
@app.post(
    "/api/v1/retention/compliance/report",
    tags=["Compliance"],
    dependencies=[Depends(require_admin)],
)
async def get_compliance_report(
    request: ComplianceReportRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Generate compliance report (Admin only)"""
    engine = RetentionPolicyEngine(
        db_session=db,
        encryption_service=encryption_service,
        audit_logger=audit_logger,
    )

    if request.framework:
        # Generate report for specific framework
        report = await engine.get_compliance_report(
            framework=request.framework,
            start_date=request.start_date,
            end_date=request.end_date,
        )
        return report
    else:
        # Generate reports for all frameworks
        reports = {}
        for framework in ComplianceFramework:
            try:
                report = await engine.get_compliance_report(
                    framework=framework,
                    start_date=request.start_date,
                    end_date=request.end_date,
                )
                reports[framework] = report
            except Exception as e:
                reports[framework] = {"error": str(e)}

        return reports


@app.get(
    "/api/v1/retention/statistics",
    tags=["Compliance"],
)
async def get_retention_statistics(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get retention statistics"""
    manager = RetentionPolicyManager(
        db_session=db,
        audit_logger=audit_logger,
    )

    stats = await manager.get_retention_statistics(
        start_date=start_date,
        end_date=end_date,
    )

    return stats


@app.get(
    "/api/v1/retention/conflicts",
    tags=["Compliance"],
    dependencies=[Depends(require_admin)],
)
async def detect_policy_conflicts(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Detect conflicts between retention policies (Admin only)"""
    manager = RetentionPolicyManager(
        db_session=db,
        audit_logger=audit_logger,
    )

    conflicts = await manager.detect_policy_conflicts()

    return {
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "retention_service:app",
        host="0.0.0.0",
        port=8010,
        reload=True,
        log_level="info",
    )
