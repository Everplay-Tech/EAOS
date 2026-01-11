"""MongoDB repository for artifact storage."""
from typing import Optional, List, Dict, Any
from datetime import datetime
from bson import ObjectId

from .database import get_mongo_db


class ArtifactRepository:
    """Repository for managing artifacts in MongoDB."""

    def __init__(self):
        self.db = get_mongo_db()
        self.collection = self.db.artifacts

    async def create_artifact(self, artifact_data: Dict[str, Any]) -> str:
        """
        Create a new artifact in MongoDB.

        Args:
            artifact_data: Artifact data (osteon, myotab, or synslide format)

        Returns:
            MongoDB document ID as string
        """
        # Add timestamp
        artifact_data["_created_at"] = datetime.utcnow()
        artifact_data["_updated_at"] = datetime.utcnow()

        result = await self.collection.insert_one(artifact_data)
        return str(result.inserted_id)

    async def get_artifact(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve an artifact by ID.

        Args:
            artifact_id: MongoDB document ID as string

        Returns:
            Artifact data or None if not found
        """
        try:
            obj_id = ObjectId(artifact_id)
            artifact = await self.collection.find_one({"_id": obj_id})
            if artifact:
                artifact["_id"] = str(artifact["_id"])
            return artifact
        except Exception:
            return None

    async def update_artifact(self, artifact_id: str, artifact_data: Dict[str, Any]) -> bool:
        """
        Update an existing artifact.

        Args:
            artifact_id: MongoDB document ID as string
            artifact_data: Updated artifact data

        Returns:
            True if updated, False if not found
        """
        try:
            obj_id = ObjectId(artifact_id)
            artifact_data["_updated_at"] = datetime.utcnow()

            result = await self.collection.update_one(
                {"_id": obj_id},
                {"$set": artifact_data}
            )
            return result.modified_count > 0
        except Exception:
            return False

    async def delete_artifact(self, artifact_id: str) -> bool:
        """
        Delete an artifact by ID.

        Args:
            artifact_id: MongoDB document ID as string

        Returns:
            True if deleted, False if not found
        """
        try:
            obj_id = ObjectId(artifact_id)
            result = await self.collection.delete_one({"_id": obj_id})
            return result.deleted_count > 0
        except Exception:
            return False

    async def list_artifacts_by_kind(self, kind: str, limit: int = 100, skip: int = 0) -> List[Dict[str, Any]]:
        """
        List artifacts by kind.

        Args:
            kind: Artifact kind (osteon, myotab, synslide)
            limit: Maximum number of artifacts to return
            skip: Number of artifacts to skip

        Returns:
            List of artifacts
        """
        cursor = self.collection.find(
            {"kind": kind}
        ).sort("_created_at", -1).skip(skip).limit(limit)

        artifacts = []
        async for artifact in cursor:
            artifact["_id"] = str(artifact["_id"])
            artifacts.append(artifact)

        return artifacts

    async def search_artifacts(
        self,
        query: Dict[str, Any],
        limit: int = 100,
        skip: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Search artifacts with custom query.

        Args:
            query: MongoDB query filter
            limit: Maximum number of artifacts to return
            skip: Number of artifacts to skip

        Returns:
            List of artifacts
        """
        cursor = self.collection.find(query).sort("_created_at", -1).skip(skip).limit(limit)

        artifacts = []
        async for artifact in cursor:
            artifact["_id"] = str(artifact["_id"])
            artifacts.append(artifact)

        return artifacts


class ExecutionLogRepository:
    """Repository for detailed execution logs in MongoDB (optional, for large payloads)."""

    def __init__(self):
        self.db = get_mongo_db()
        self.collection = self.db.execution_logs

    async def create_execution_log(self, execution_id: str, log_data: Dict[str, Any]) -> str:
        """
        Create detailed execution log.

        Args:
            execution_id: Execution ID from PostgreSQL
            log_data: Detailed log data (full request/response)

        Returns:
            MongoDB document ID as string
        """
        log_data["execution_id"] = execution_id
        log_data["_created_at"] = datetime.utcnow()

        result = await self.collection.insert_one(log_data)
        return str(result.inserted_id)

    async def get_execution_log(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve execution log by execution ID.

        Args:
            execution_id: Execution ID from PostgreSQL

        Returns:
            Log data or None if not found
        """
        log = await self.collection.find_one({"execution_id": execution_id})
        if log:
            log["_id"] = str(log["_id"])
        return log

    async def list_execution_logs(
        self,
        agent: Optional[str] = None,
        limit: int = 100,
        skip: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List execution logs with optional filtering.

        Args:
            agent: Filter by agent name
            limit: Maximum number of logs to return
            skip: Number of logs to skip

        Returns:
            List of execution logs
        """
        query = {}
        if agent:
            query["agent"] = agent

        cursor = self.collection.find(query).sort("_created_at", -1).skip(skip).limit(limit)

        logs = []
        async for log in cursor:
            log["_id"] = str(log["_id"])
            logs.append(log)

        return logs
