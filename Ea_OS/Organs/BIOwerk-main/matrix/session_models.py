"""Pydantic models for session data structures."""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime


class SessionBase(BaseModel):
    """Base model for all session data."""
    created_at: float = Field(default_factory=lambda: datetime.now().timestamp())
    updated_at: float = Field(default_factory=lambda: datetime.now().timestamp())


class OsteonOutlineSession(SessionBase):
    """Session data for Osteon document outline generation."""
    outline: List[str] = Field(default_factory=list, description="Document section titles")
    topic: Optional[str] = Field(None, description="Document topic")
    goal: Optional[str] = Field(None, description="Document goal")

    class Config:
        json_schema_extra = {
            "example": {
                "outline": ["Introduction", "Background", "Analysis", "Conclusions"],
                "topic": "Machine Learning in Healthcare",
                "goal": "Create comprehensive guide",
                "created_at": 1700000000.0,
                "updated_at": 1700000000.0
            }
        }


class OsteonDraftSession(SessionBase):
    """Session data for Osteon document drafting workflow."""
    sections: List[Dict[str, Any]] = Field(default_factory=list, description="Generated sections")
    outline: List[str] = Field(default_factory=list, description="Document outline")
    current_section_index: int = Field(0, description="Index of section being drafted")

    class Config:
        json_schema_extra = {
            "example": {
                "sections": [
                    {"id": "s_1", "title": "Introduction", "text": "..."},
                    {"id": "s_2", "title": "Background", "text": "..."}
                ],
                "outline": ["Introduction", "Background", "Analysis"],
                "current_section_index": 2,
                "created_at": 1700000000.0,
                "updated_at": 1700000000.0
            }
        }


class WorkflowSession(SessionBase):
    """Generic workflow session for multi-step processes."""
    workflow_type: str = Field(..., description="Type of workflow (e.g., 'document', 'analysis')")
    current_step: int = Field(0, description="Current step index")
    total_steps: int = Field(0, description="Total number of steps")
    step_data: Dict[str, Any] = Field(default_factory=dict, description="Step-specific data")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        json_schema_extra = {
            "example": {
                "workflow_type": "document_generation",
                "current_step": 2,
                "total_steps": 5,
                "step_data": {"outline_generated": True, "sections_drafted": 2},
                "metadata": {"user_id": "user123", "project_id": "proj456"},
                "created_at": 1700000000.0,
                "updated_at": 1700000000.0
            }
        }


class ConversationSession(SessionBase):
    """Session data for conversational context across requests."""
    messages: List[Dict[str, str]] = Field(default_factory=list, description="Message history")
    context: Dict[str, Any] = Field(default_factory=dict, description="Conversation context")
    user_id: Optional[str] = Field(None, description="User identifier")

    class Config:
        json_schema_extra = {
            "example": {
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi! How can I help?"}
                ],
                "context": {"topic": "Python programming", "expertise_level": "intermediate"},
                "user_id": "user123",
                "created_at": 1700000000.0,
                "updated_at": 1700000000.0
            }
        }


class CacheSession(SessionBase):
    """Session data for temporary caching of computation results."""
    data: Dict[str, Any] = Field(default_factory=dict, description="Cached data")
    computation_time_ms: Optional[float] = Field(None, description="Time taken to compute")

    class Config:
        json_schema_extra = {
            "example": {
                "data": {"result": [1, 2, 3], "processed": True},
                "computation_time_ms": 1234.56,
                "created_at": 1700000000.0,
                "updated_at": 1700000000.0
            }
        }
