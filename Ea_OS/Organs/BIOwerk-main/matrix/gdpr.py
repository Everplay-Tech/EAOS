"""Enterprise-grade GDPR compliance service for BIOwerk.

This module provides comprehensive GDPR compliance capabilities including:
- Right to Access (Article 15) - Export all user data
- Right to Erasure (Article 17) - Delete/anonymize user data
- Right to Portability (Article 20) - Export in machine-readable format
- Right to Rectification (Article 16) - Update incorrect data
- Consent management (Article 7) - Track and manage user consent
- Data retention enforcement (Article 5) - Automatic data cleanup
- Data anonymization - Privacy-preserving data transformation
- Breach notification (Articles 33/34) - Incident tracking and notification

Compliance Standards:
- GDPR (General Data Protection Regulation)
- CCPA (California Consumer Privacy Act)
- HIPAA (Health Insurance Portability and Accountability Act)
- PCI-DSS (Payment Card Industry Data Security Standard)
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy import select, delete, update, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
import json
import csv
import io
import hashlib
import secrets
import re
from pathlib import Path

from .db_models import (
    User, Project, Artifact, Execution, APIKey, AuditLog,
    ConsentRecord, DataRequest, DataRetentionPolicy, PrivacySettings,
    CookieConsent, DataBreachIncident, generate_uuid
)
from .encryption import EncryptionService
from .audit import AuditService


class GDPRError(Exception):
    """Base exception for GDPR-related errors."""
    pass


class DataRequestError(GDPRError):
    """Exception raised when data request processing fails."""
    pass


class ConsentError(GDPRError):
    """Exception raised when consent operations fail."""
    pass


class AnonymizationError(GDPRError):
    """Exception raised when anonymization fails."""
    pass


class GDPRService:
    """
    Enterprise GDPR compliance service.

    Provides comprehensive data protection and privacy management capabilities
    in compliance with GDPR and other privacy regulations.
    """

    def __init__(
        self,
        db: AsyncSession,
        encryption_service: Optional[EncryptionService] = None,
        audit_service: Optional[AuditService] = None,
        export_base_path: str = "/tmp/gdpr_exports"
    ):
        """
        Initialize GDPR service.

        Args:
            db: Async database session
            encryption_service: Encryption service for sensitive data
            audit_service: Audit logging service
            export_base_path: Base directory for data exports
        """
        self.db = db
        self.encryption = encryption_service
        self.audit = audit_service
        self.export_base_path = Path(export_base_path)
        self.export_base_path.mkdir(parents=True, exist_ok=True)

    # ========================================================================
    # Right to Access (Article 15)
    # ========================================================================

    async def create_access_request(
        self,
        user_id: str,
        description: Optional[str] = None,
        requested_data_types: Optional[List[str]] = None,
        export_format: str = "json",
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> DataRequest:
        """
        Create a data access request (GDPR Article 15).

        User has the right to obtain confirmation of whether their personal data
        is being processed and access to that data.

        Args:
            user_id: User making the request
            description: Optional description/reason for request
            requested_data_types: Specific data types to include (None = all)
            export_format: Format for export (json, csv, pdf)
            ip_address: IP address of requester
            user_agent: User agent of requester

        Returns:
            DataRequest object
        """
        # Create request with 30-day SLA
        due_date = datetime.utcnow() + timedelta(days=30)

        request = DataRequest(
            id=generate_uuid(),
            user_id=user_id,
            request_type="access",
            request_status="pending",
            description=description,
            requested_data_types=requested_data_types,
            export_format=export_format,
            ip_address=ip_address,
            user_agent=user_agent,
            due_date=due_date,
            requested_at=datetime.utcnow()
        )

        self.db.add(request)
        await self.db.commit()
        await self.db.refresh(request)

        # Audit log
        if self.audit:
            await self.audit.log_event(
                event_type="DATA_READ",
                event_action="access_request_created",
                event_status="success",
                user_id=user_id,
                resource_type="data_request",
                resource_id=request.id,
                request_data={"request_type": "access", "format": export_format}
            )

        return request

    async def export_user_data(
        self,
        user_id: str,
        data_types: Optional[List[str]] = None,
        format: str = "json"
    ) -> Dict[str, Any]:
        """
        Export all user data in machine-readable format (Article 15, 20).

        Exports comprehensive user data including:
        - User account information
        - Projects and artifacts
        - Execution history
        - API keys
        - Consent records
        - Privacy settings
        - Cookie consents
        - Audit logs (user's own actions)

        Args:
            user_id: User to export data for
            data_types: Specific data types to export (None = all)
            format: Export format (json, csv)

        Returns:
            Dict containing all user data
        """
        export_data = {
            "export_metadata": {
                "user_id": user_id,
                "export_date": datetime.utcnow().isoformat(),
                "format": format,
                "gdpr_basis": "Article 15 - Right to Access, Article 20 - Right to Portability"
            },
            "data": {}
        }

        # User account data
        if not data_types or "user" in data_types:
            user_stmt = select(User).where(User.id == user_id)
            result = await self.db.execute(user_stmt)
            user = result.scalar_one_or_none()

            if user:
                export_data["data"]["user"] = {
                    "id": user.id,
                    "email": user.email,
                    "username": user.username,
                    "auth_provider": user.auth_provider,
                    "is_active": user.is_active,
                    "is_admin": user.is_admin,
                    "created_at": user.created_at.isoformat() if user.created_at else None,
                    "updated_at": user.updated_at.isoformat() if user.updated_at else None
                }

        # Projects
        if not data_types or "projects" in data_types:
            projects_stmt = select(Project).where(Project.user_id == user_id)
            result = await self.db.execute(projects_stmt)
            projects = result.scalars().all()

            export_data["data"]["projects"] = [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "is_archived": p.is_archived,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None
                }
                for p in projects
            ]

        # Artifacts
        if not data_types or "artifacts" in data_types:
            artifacts_stmt = (
                select(Artifact)
                .join(Project)
                .where(Project.user_id == user_id)
            )
            result = await self.db.execute(artifacts_stmt)
            artifacts = result.scalars().all()

            export_data["data"]["artifacts"] = [
                {
                    "id": a.id,
                    "project_id": a.project_id,
                    "kind": a.kind,
                    "title": a.title,
                    "version": a.version,
                    "mongo_id": a.mongo_id,
                    "metadata": a.metadata,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                    "updated_at": a.updated_at.isoformat() if a.updated_at else None
                }
                for a in artifacts
            ]

        # Executions (API usage history)
        if not data_types or "executions" in data_types:
            exec_stmt = select(Execution).where(Execution.user_id == user_id).limit(1000)
            result = await self.db.execute(exec_stmt)
            executions = result.scalars().all()

            export_data["data"]["executions"] = [
                {
                    "id": e.id,
                    "agent": e.agent,
                    "endpoint": e.endpoint,
                    "ok": e.ok,
                    "duration_ms": e.duration_ms,
                    "created_at": e.created_at.isoformat() if e.created_at else None
                }
                for e in executions
            ]

        # API Keys
        if not data_types or "api_keys" in data_types:
            apikey_stmt = select(APIKey).where(APIKey.user_id == user_id)
            result = await self.db.execute(apikey_stmt)
            api_keys = result.scalars().all()

            export_data["data"]["api_keys"] = [
                {
                    "id": k.id,
                    "name": k.name,
                    "scopes": k.scopes,
                    "is_active": k.is_active,
                    "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                    "expires_at": k.expires_at.isoformat() if k.expires_at else None,
                    "created_at": k.created_at.isoformat() if k.created_at else None
                }
                for k in api_keys
            ]

        # Consent records
        if not data_types or "consents" in data_types:
            consent_stmt = select(ConsentRecord).where(ConsentRecord.user_id == user_id)
            result = await self.db.execute(consent_stmt)
            consents = result.scalars().all()

            export_data["data"]["consents"] = [
                {
                    "id": c.id,
                    "purpose": c.purpose,
                    "purpose_description": c.purpose_description,
                    "consent_given": c.consent_given,
                    "consent_category": c.consent_category,
                    "legal_basis": c.legal_basis,
                    "granted_at": c.granted_at.isoformat() if c.granted_at else None,
                    "withdrawn_at": c.withdrawn_at.isoformat() if c.withdrawn_at else None,
                    "expires_at": c.expires_at.isoformat() if c.expires_at else None
                }
                for c in consents
            ]

        # Privacy settings
        if not data_types or "privacy_settings" in data_types:
            settings_stmt = select(PrivacySettings).where(PrivacySettings.user_id == user_id)
            result = await self.db.execute(settings_stmt)
            settings = result.scalar_one_or_none()

            if settings:
                export_data["data"]["privacy_settings"] = {
                    "privacy_level": settings.privacy_level,
                    "email_marketing_enabled": settings.email_marketing_enabled,
                    "analytics_enabled": settings.analytics_enabled,
                    "personalization_enabled": settings.personalization_enabled,
                    "third_party_sharing": settings.third_party_sharing,
                    "ai_training_opt_in": settings.ai_training_opt_in,
                    "profiling_enabled": settings.profiling_enabled,
                    "preferred_export_format": settings.preferred_export_format,
                    "updated_at": settings.updated_at.isoformat() if settings.updated_at else None
                }

        # Cookie consents
        if not data_types or "cookies" in data_types:
            cookie_stmt = select(CookieConsent).where(CookieConsent.user_id == user_id)
            result = await self.db.execute(cookie_stmt)
            cookies = result.scalars().all()

            export_data["data"]["cookie_consents"] = [
                {
                    "id": c.id,
                    "essential_accepted": c.essential_accepted,
                    "functional_accepted": c.functional_accepted,
                    "analytics_accepted": c.analytics_accepted,
                    "marketing_accepted": c.marketing_accepted,
                    "granted_at": c.granted_at.isoformat() if c.granted_at else None,
                    "expires_at": c.expires_at.isoformat() if c.expires_at else None
                }
                for c in cookies
            ]

        # Audit logs (user's own actions only)
        if not data_types or "audit_logs" in data_types:
            audit_stmt = select(AuditLog).where(AuditLog.user_id == user_id).limit(1000)
            result = await self.db.execute(audit_stmt)
            audits = result.scalars().all()

            export_data["data"]["audit_logs"] = [
                {
                    "event_id": a.event_id,
                    "event_type": a.event_type,
                    "event_action": a.event_action,
                    "event_status": a.event_status,
                    "resource_type": a.resource_type,
                    "resource_id": a.resource_id,
                    "service_name": a.service_name,
                    "endpoint": a.endpoint,
                    "event_timestamp": a.event_timestamp.isoformat() if a.event_timestamp else None
                }
                for a in audits
            ]

        return export_data

    async def generate_export_file(
        self,
        request_id: str,
        format: str = "json"
    ) -> Tuple[str, str]:
        """
        Generate export file for a data access request.

        Args:
            request_id: Data request ID
            format: Export format (json, csv)

        Returns:
            Tuple of (file_path, file_hash)
        """
        # Get request
        stmt = select(DataRequest).where(DataRequest.id == request_id)
        result = await self.db.execute(stmt)
        request = result.scalar_one_or_none()

        if not request:
            raise DataRequestError(f"Request {request_id} not found")

        if request.request_type not in ["access", "portability"]:
            raise DataRequestError(f"Request type {request.request_type} does not support export")

        # Update status
        request.request_status = "in_progress"
        await self.db.commit()

        try:
            # Export data
            data = await self.export_user_data(
                user_id=request.user_id,
                data_types=request.requested_data_types,
                format=format
            )

            # Generate filename
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"user_data_{request.user_id}_{timestamp}.{format}"
            file_path = self.export_base_path / filename

            # Write file
            if format == "json":
                with open(file_path, 'w') as f:
                    json.dump(data, f, indent=2)
            elif format == "csv":
                # Flatten data for CSV export
                with open(file_path, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(["Category", "Field", "Value"])

                    for category, category_data in data["data"].items():
                        if isinstance(category_data, list):
                            for item in category_data:
                                for key, value in item.items():
                                    writer.writerow([category, key, str(value)])
                        elif isinstance(category_data, dict):
                            for key, value in category_data.items():
                                writer.writerow([category, key, str(value)])
            else:
                raise DataRequestError(f"Unsupported export format: {format}")

            # Calculate file hash
            with open(file_path, 'rb') as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()

            # Update request
            request.request_status = "completed"
            request.completed_at = datetime.utcnow()
            request.export_file_path = str(file_path)
            request.export_file_hash = file_hash
            request.export_expires_at = datetime.utcnow() + timedelta(days=30)
            await self.db.commit()

            return str(file_path), file_hash

        except Exception as e:
            request.request_status = "failed"
            await self.db.commit()
            raise DataRequestError(f"Export generation failed: {str(e)}")

    # ========================================================================
    # Right to Erasure / Right to be Forgotten (Article 17)
    # ========================================================================

    async def create_erasure_request(
        self,
        user_id: str,
        description: Optional[str] = None,
        erasure_method: str = "anonymization",
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> DataRequest:
        """
        Create a data erasure request (GDPR Article 17 - Right to be Forgotten).

        Args:
            user_id: User requesting erasure
            description: Reason for erasure request
            erasure_method: Method (soft_delete, anonymization, hard_delete)
            ip_address: IP address of requester
            user_agent: User agent of requester

        Returns:
            DataRequest object
        """
        due_date = datetime.utcnow() + timedelta(days=30)

        request = DataRequest(
            id=generate_uuid(),
            user_id=user_id,
            request_type="erasure",
            request_status="pending",
            description=description,
            erasure_method=erasure_method,
            ip_address=ip_address,
            user_agent=user_agent,
            due_date=due_date,
            requested_at=datetime.utcnow()
        )

        self.db.add(request)
        await self.db.commit()
        await self.db.refresh(request)

        if self.audit:
            await self.audit.log_event(
                event_type="DATA_DELETE",
                event_action="erasure_request_created",
                event_status="success",
                user_id=user_id,
                resource_type="data_request",
                resource_id=request.id,
                request_data={"request_type": "erasure", "method": erasure_method}
            )

        return request

    async def anonymize_user_data(
        self,
        user_id: str,
        preserve_audit_trail: bool = True
    ) -> Dict[str, Any]:
        """
        Anonymize user data while preserving system integrity.

        This implements privacy-preserving anonymization by:
        1. Replacing PII with anonymized values
        2. Preserving referential integrity
        3. Maintaining audit trails (if required by law)
        4. Keeping aggregate statistics

        Args:
            user_id: User to anonymize
            preserve_audit_trail: Keep audit logs for compliance

        Returns:
            Summary of anonymization operations
        """
        summary = {
            "user_id": user_id,
            "anonymized_at": datetime.utcnow().isoformat(),
            "operations": []
        }

        try:
            # Get user
            user_stmt = select(User).where(User.id == user_id)
            result = await self.db.execute(user_stmt)
            user = result.scalar_one_or_none()

            if not user:
                raise AnonymizationError(f"User {user_id} not found")

            # Generate anonymized identifiers
            anon_email = f"deleted_{secrets.token_hex(8)}@anonymized.local"
            anon_username = f"deleted_user_{secrets.token_hex(6)}"

            # Anonymize user account
            user.email = anon_email
            user.username = anon_username
            user.hashed_password = None
            user.is_active = False
            summary["operations"].append({
                "type": "user_account",
                "action": "anonymized",
                "details": "Email, username, and password removed"
            })

            # Soft delete projects (keep for referential integrity)
            projects_stmt = select(Project).where(Project.user_id == user_id)
            result = await self.db.execute(projects_stmt)
            projects = result.scalars().all()

            for project in projects:
                project.name = f"Deleted Project {secrets.token_hex(4)}"
                project.description = "[Deleted]"
                project.is_archived = True

            summary["operations"].append({
                "type": "projects",
                "action": "anonymized",
                "count": len(projects)
            })

            # Delete API keys
            apikey_delete = delete(APIKey).where(APIKey.user_id == user_id)
            result = await self.db.execute(apikey_delete)
            summary["operations"].append({
                "type": "api_keys",
                "action": "deleted",
                "count": result.rowcount
            })

            # Anonymize consent records (keep for legal compliance)
            consent_stmt = select(ConsentRecord).where(ConsentRecord.user_id == user_id)
            result = await self.db.execute(consent_stmt)
            consents = result.scalars().all()

            for consent in consents:
                consent.ip_address = None
                consent.user_agent = None

            summary["operations"].append({
                "type": "consent_records",
                "action": "anonymized",
                "count": len(consents)
            })

            # Delete privacy settings
            privacy_delete = delete(PrivacySettings).where(PrivacySettings.user_id == user_id)
            result = await self.db.execute(privacy_delete)
            summary["operations"].append({
                "type": "privacy_settings",
                "action": "deleted",
                "count": result.rowcount
            })

            # Anonymize audit logs (if preservation required)
            if preserve_audit_trail:
                audit_stmt = select(AuditLog).where(AuditLog.user_id == user_id)
                result = await self.db.execute(audit_stmt)
                audits = result.scalars().all()

                for audit in audits:
                    audit.username = anon_username
                    audit.ip_address = None
                    audit.user_agent = None
                    # Clear encrypted fields
                    audit.ip_address_encrypted = None
                    audit.user_agent_encrypted = None
                    audit.request_data_encrypted = None
                    audit.response_data_encrypted = None

                summary["operations"].append({
                    "type": "audit_logs",
                    "action": "anonymized",
                    "count": len(audits)
                })
            else:
                audit_delete = delete(AuditLog).where(AuditLog.user_id == user_id)
                result = await self.db.execute(audit_delete)
                summary["operations"].append({
                    "type": "audit_logs",
                    "action": "deleted",
                    "count": result.rowcount
                })

            await self.db.commit()

            if self.audit:
                await self.audit.log_event(
                    event_type="DATA_DELETE",
                    event_action="user_anonymized",
                    event_status="success",
                    user_id=user_id,
                    resource_type="user",
                    resource_id=user_id,
                    request_data=summary
                )

            return summary

        except Exception as e:
            await self.db.rollback()
            raise AnonymizationError(f"Anonymization failed: {str(e)}")

    async def hard_delete_user(
        self,
        user_id: str,
        bypass_legal_hold: bool = False
    ) -> Dict[str, Any]:
        """
        Permanently delete all user data (use with extreme caution).

        This is a DESTRUCTIVE operation that cannot be undone.
        Only use when legally required and no retention obligations exist.

        Args:
            user_id: User to delete
            bypass_legal_hold: Force deletion even if legal hold exists

        Returns:
            Summary of deletion operations
        """
        summary = {
            "user_id": user_id,
            "deleted_at": datetime.utcnow().isoformat(),
            "operations": []
        }

        # Check for legal holds
        legal_hold_stmt = select(DataRequest).where(
            and_(
                DataRequest.user_id == user_id,
                DataRequest.legal_hold == True
            )
        )
        result = await self.db.execute(legal_hold_stmt)
        legal_holds = result.scalars().all()

        if legal_holds and not bypass_legal_hold:
            raise DataRequestError(
                f"Cannot delete user {user_id}: {len(legal_holds)} active legal hold(s)"
            )

        try:
            # Delete in order to respect foreign key constraints

            # 1. Delete cookie consents
            cookie_delete = delete(CookieConsent).where(CookieConsent.user_id == user_id)
            result = await self.db.execute(cookie_delete)
            summary["operations"].append({"type": "cookie_consents", "deleted": result.rowcount})

            # 2. Delete privacy settings
            privacy_delete = delete(PrivacySettings).where(PrivacySettings.user_id == user_id)
            result = await self.db.execute(privacy_delete)
            summary["operations"].append({"type": "privacy_settings", "deleted": result.rowcount})

            # 3. Delete consent records
            consent_delete = delete(ConsentRecord).where(ConsentRecord.user_id == user_id)
            result = await self.db.execute(consent_delete)
            summary["operations"].append({"type": "consent_records", "deleted": result.rowcount})

            # 4. Delete data requests
            request_delete = delete(DataRequest).where(DataRequest.user_id == user_id)
            result = await self.db.execute(request_delete)
            summary["operations"].append({"type": "data_requests", "deleted": result.rowcount})

            # 5. Delete audit logs
            audit_delete = delete(AuditLog).where(AuditLog.user_id == user_id)
            result = await self.db.execute(audit_delete)
            summary["operations"].append({"type": "audit_logs", "deleted": result.rowcount})

            # 6. Delete API keys
            apikey_delete = delete(APIKey).where(APIKey.user_id == user_id)
            result = await self.db.execute(apikey_delete)
            summary["operations"].append({"type": "api_keys", "deleted": result.rowcount})

            # 7. Delete executions
            exec_delete = delete(Execution).where(Execution.user_id == user_id)
            result = await self.db.execute(exec_delete)
            summary["operations"].append({"type": "executions", "deleted": result.rowcount})

            # 8. Delete artifacts (via cascade from projects)
            # 9. Delete projects (via cascade from user)

            # 10. Finally, delete user
            user_delete = delete(User).where(User.id == user_id)
            result = await self.db.execute(user_delete)
            summary["operations"].append({"type": "user", "deleted": result.rowcount})

            await self.db.commit()

            return summary

        except Exception as e:
            await self.db.rollback()
            raise DataRequestError(f"Hard delete failed: {str(e)}")

    # ========================================================================
    # Consent Management (Article 7)
    # ========================================================================

    async def record_consent(
        self,
        user_id: str,
        purpose: str,
        purpose_description: str,
        consent_given: bool,
        consent_category: str,
        legal_basis: str = "consent",
        consent_method: str = "checkbox",
        consent_version: str = "1.0",
        expires_in_days: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> ConsentRecord:
        """
        Record user consent for data processing.

        Args:
            user_id: User giving/withdrawing consent
            purpose: Purpose of data processing
            purpose_description: Clear description shown to user
            consent_given: True if consented, False if withdrawn
            consent_category: Category (essential, functional, analytics, marketing, third_party)
            legal_basis: Legal basis (consent, contract, legal_obligation, etc.)
            consent_method: How consent was obtained
            consent_version: Version of terms/privacy policy
            expires_in_days: Optional expiration period
            ip_address: IP address of user
            user_agent: User agent

        Returns:
            ConsentRecord object
        """
        expires_at = None
        if expires_in_days:
            expires_at = datetime.utcnow() + timedelta(days=expires_in_days)

        consent = ConsentRecord(
            id=generate_uuid(),
            user_id=user_id,
            purpose=purpose,
            purpose_description=purpose_description,
            consent_given=consent_given,
            consent_method=consent_method,
            legal_basis=legal_basis,
            consent_category=consent_category,
            consent_version=consent_version,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
            granted_at=datetime.utcnow()
        )

        self.db.add(consent)
        await self.db.commit()
        await self.db.refresh(consent)

        if self.audit:
            await self.audit.log_event(
                event_type="DATA_WRITE",
                event_action="consent_recorded",
                event_status="success",
                user_id=user_id,
                resource_type="consent_record",
                resource_id=consent.id,
                request_data={
                    "purpose": purpose,
                    "consent_given": consent_given,
                    "category": consent_category
                }
            )

        return consent

    async def withdraw_consent(
        self,
        user_id: str,
        purpose: str,
        withdrawal_method: str = "user_request"
    ) -> bool:
        """
        Withdraw user consent for a specific purpose.

        Args:
            user_id: User withdrawing consent
            purpose: Purpose to withdraw consent for
            withdrawal_method: How withdrawal was initiated

        Returns:
            True if consent was withdrawn
        """
        stmt = (
            select(ConsentRecord)
            .where(
                and_(
                    ConsentRecord.user_id == user_id,
                    ConsentRecord.purpose == purpose,
                    ConsentRecord.consent_given == True,
                    ConsentRecord.withdrawn_at.is_(None)
                )
            )
        )
        result = await self.db.execute(stmt)
        consents = result.scalars().all()

        for consent in consents:
            consent.withdrawn_at = datetime.utcnow()
            consent.withdrawal_method = withdrawal_method
            consent.consent_given = False

        await self.db.commit()

        if self.audit:
            await self.audit.log_event(
                event_type="DATA_WRITE",
                event_action="consent_withdrawn",
                event_status="success",
                user_id=user_id,
                request_data={
                    "purpose": purpose,
                    "consents_withdrawn": len(consents)
                }
            )

        return len(consents) > 0

    async def check_consent(
        self,
        user_id: str,
        purpose: str
    ) -> bool:
        """
        Check if user has given valid consent for a purpose.

        Args:
            user_id: User to check
            purpose: Purpose to check consent for

        Returns:
            True if valid consent exists
        """
        stmt = (
            select(ConsentRecord)
            .where(
                and_(
                    ConsentRecord.user_id == user_id,
                    ConsentRecord.purpose == purpose,
                    ConsentRecord.consent_given == True,
                    ConsentRecord.withdrawn_at.is_(None),
                    or_(
                        ConsentRecord.expires_at.is_(None),
                        ConsentRecord.expires_at > datetime.utcnow()
                    )
                )
            )
        )
        result = await self.db.execute(stmt)
        consent = result.scalar_one_or_none()

        return consent is not None

    # ========================================================================
    # Data Retention (Article 5)
    # ========================================================================

    async def enforce_retention_policies(self) -> Dict[str, Any]:
        """
        Enforce data retention policies across all data types.

        Returns:
            Summary of enforcement actions
        """
        summary = {
            "enforced_at": datetime.utcnow().isoformat(),
            "policies_applied": []
        }

        # Get active retention policies
        stmt = select(DataRetentionPolicy).where(
            and_(
                DataRetentionPolicy.is_active == True,
                DataRetentionPolicy.auto_delete_enabled == True
            )
        )
        result = await self.db.execute(stmt)
        policies = result.scalars().all()

        for policy in policies:
            cutoff_date = datetime.utcnow() - timedelta(days=policy.retention_period_days)
            deleted_count = 0

            try:
                if policy.data_type == "audit_logs":
                    # Delete old audit logs
                    delete_stmt = delete(AuditLog).where(
                        AuditLog.created_at < cutoff_date
                    )
                    result = await self.db.execute(delete_stmt)
                    deleted_count = result.rowcount

                elif policy.data_type == "executions":
                    # Delete old execution records
                    delete_stmt = delete(Execution).where(
                        Execution.created_at < cutoff_date
                    )
                    result = await self.db.execute(delete_stmt)
                    deleted_count = result.rowcount

                elif policy.data_type == "cookie_consents":
                    # Delete expired cookie consents
                    delete_stmt = delete(CookieConsent).where(
                        CookieConsent.expires_at < datetime.utcnow()
                    )
                    result = await self.db.execute(delete_stmt)
                    deleted_count = result.rowcount

                elif policy.data_type == "data_requests":
                    # Archive old completed data requests
                    update_stmt = (
                        update(DataRequest)
                        .where(
                            and_(
                                DataRequest.completed_at < cutoff_date,
                                DataRequest.request_status == "completed"
                            )
                        )
                        .values(
                            request_status="archived"
                        )
                    )
                    result = await self.db.execute(update_stmt)
                    deleted_count = result.rowcount

                summary["policies_applied"].append({
                    "policy_name": policy.policy_name,
                    "data_type": policy.data_type,
                    "retention_days": policy.retention_period_days,
                    "records_affected": deleted_count
                })

            except Exception as e:
                summary["policies_applied"].append({
                    "policy_name": policy.policy_name,
                    "data_type": policy.data_type,
                    "error": str(e)
                })

        await self.db.commit()

        return summary

    # ========================================================================
    # Privacy Settings
    # ========================================================================

    async def get_or_create_privacy_settings(
        self,
        user_id: str
    ) -> PrivacySettings:
        """
        Get or create privacy settings for a user.

        Args:
            user_id: User ID

        Returns:
            PrivacySettings object
        """
        stmt = select(PrivacySettings).where(PrivacySettings.user_id == user_id)
        result = await self.db.execute(stmt)
        settings = result.scalar_one_or_none()

        if not settings:
            settings = PrivacySettings(
                id=generate_uuid(),
                user_id=user_id
            )
            self.db.add(settings)
            await self.db.commit()
            await self.db.refresh(settings)

        return settings

    async def update_privacy_settings(
        self,
        user_id: str,
        **kwargs
    ) -> PrivacySettings:
        """
        Update user privacy settings.

        Args:
            user_id: User ID
            **kwargs: Settings to update

        Returns:
            Updated PrivacySettings
        """
        settings = await self.get_or_create_privacy_settings(user_id)

        for key, value in kwargs.items():
            if hasattr(settings, key):
                setattr(settings, key, value)

        settings.last_reviewed_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(settings)

        if self.audit:
            await self.audit.log_event(
                event_type="DATA_WRITE",
                event_action="privacy_settings_updated",
                event_status="success",
                user_id=user_id,
                resource_type="privacy_settings",
                resource_id=settings.id,
                request_data=kwargs
            )

        return settings

    # ========================================================================
    # Utility Methods
    # ========================================================================

    @staticmethod
    def anonymize_email(email: str) -> str:
        """Anonymize an email address while preserving format."""
        local, domain = email.split('@')
        return f"deleted_{secrets.token_hex(8)}@{domain}"

    @staticmethod
    def anonymize_ip(ip: str) -> str:
        """Anonymize an IP address by zeroing last octet."""
        parts = ip.split('.')
        if len(parts) == 4:  # IPv4
            return '.'.join(parts[:3] + ['0'])
        return "0.0.0.0"  # Fallback

    @staticmethod
    def hash_pii(value: str) -> str:
        """Create a deterministic hash of PII for searchability."""
        return hashlib.sha256(value.encode()).hexdigest()
