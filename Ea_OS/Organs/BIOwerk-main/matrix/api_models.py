"""Pydantic request models for comprehensive input validation across all services.

This module provides validated request models to prevent injection attacks including:
- SQL injection
- NoSQL injection
- Command injection
- XSS attacks
- Path traversal
"""

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Any, Dict, List, Optional
import re
from matrix.errors import ValidationError


# Maximum string length to prevent DoS attacks
MAX_STRING_LENGTH = 10000
MAX_LIST_LENGTH = 1000

# Pattern to detect potentially dangerous characters for injection attacks
DANGEROUS_PATTERN = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f]|"  # Control characters
    r"(<script|javascript:|onerror=|onload=)|"  # XSS patterns
    r"(\$\{|\$\(|`)|"  # Command injection
    r"(union\s+select|insert\s+into|drop\s+table|delete\s+from)|"  # SQL injection
    r"(\$where|\$ne|\$gt|\$lt|\.\.\/|\.\.\\)",  # NoSQL & path traversal
    re.IGNORECASE
)


def validate_safe_string(value: str, field_name: str = "field") -> str:
    """Validate that a string doesn't contain injection attack patterns.

    Args:
        value: String to validate
        field_name: Name of the field for error messages

    Returns:
        The validated string

    Raises:
        ValidationError: If string contains dangerous patterns
    """
    if not isinstance(value, str):
        raise ValidationError(
            f"{field_name} must be a string",
            {"field": field_name, "type": type(value).__name__}
        )

    if len(value) > MAX_STRING_LENGTH:
        raise ValidationError(
            f"{field_name} exceeds maximum length of {MAX_STRING_LENGTH} characters",
            {"field": field_name, "length": len(value), "max_length": MAX_STRING_LENGTH}
        )

    if DANGEROUS_PATTERN.search(value):
        raise ValidationError(
            f"{field_name} contains invalid or potentially dangerous characters",
            {"field": field_name}
        )

    return value


def validate_safe_list(value: List[Any], field_name: str = "field") -> List[Any]:
    """Validate that a list doesn't exceed size limits.

    Args:
        value: List to validate
        field_name: Name of the field for error messages

    Returns:
        The validated list

    Raises:
        ValidationError: If list is too large
    """
    if not isinstance(value, list):
        raise ValidationError(
            f"{field_name} must be a list",
            {"field": field_name, "type": type(value).__name__}
        )

    if len(value) > MAX_LIST_LENGTH:
        raise ValidationError(
            f"{field_name} exceeds maximum length of {MAX_LIST_LENGTH} items",
            {"field": field_name, "length": len(value), "max_length": MAX_LIST_LENGTH}
        )

    return value


# =============================================================================
# Osteon Service Models (Content Generation)
# =============================================================================

class OutlineRequest(BaseModel):
    """Request model for generating document outlines."""

    model_config = ConfigDict(strict=True, extra="forbid")

    goal: Optional[str] = Field(default="", max_length=MAX_STRING_LENGTH)
    topic: Optional[str] = Field(default="", max_length=MAX_STRING_LENGTH)
    context: Optional[str] = Field(default="", max_length=MAX_STRING_LENGTH)

    @field_validator("goal", "topic", "context")
    @classmethod
    def validate_strings(cls, v: str, info) -> str:
        if v:
            return validate_safe_string(v, info.field_name)
        return v

    def validate_required_fields(self):
        """Ensure at least topic or goal is provided."""
        if not self.topic and not self.goal:
            raise ValidationError(
                "Either 'topic' or 'goal' is required",
                {"required_fields": ["topic", "goal"]}
            )


class DraftRequest(BaseModel):
    """Request model for generating draft content."""

    model_config = ConfigDict(strict=True, extra="forbid")

    goal: Optional[str] = Field(default="", max_length=MAX_STRING_LENGTH)
    section_title: Optional[str] = Field(default="", max_length=MAX_STRING_LENGTH)
    outline: Optional[List[str]] = Field(default_factory=list)
    context: Optional[str] = Field(default="", max_length=MAX_STRING_LENGTH)

    @field_validator("goal", "section_title", "context")
    @classmethod
    def validate_strings(cls, v: str, info) -> str:
        if v:
            return validate_safe_string(v, info.field_name)
        return v

    @field_validator("outline")
    @classmethod
    def validate_outline(cls, v: List[str]) -> List[str]:
        validate_safe_list(v, "outline")
        for item in v:
            if isinstance(item, str):
                validate_safe_string(item, "outline item")
        return v

    def validate_required_fields(self):
        """Ensure at least goal or section_title is provided."""
        if not self.goal and not self.section_title:
            raise ValidationError(
                "Either 'goal' or 'section_title' is required",
                {"required_fields": ["goal", "section_title"]}
            )


class EditRequest(BaseModel):
    """Request model for editing content."""

    model_config = ConfigDict(strict=True, extra="forbid")

    text: str = Field(..., min_length=1, max_length=MAX_STRING_LENGTH)
    feedback: Optional[str] = Field(default="", max_length=MAX_STRING_LENGTH)
    edit_type: Optional[str] = Field(default="improve", max_length=50)

    @field_validator("text", "feedback")
    @classmethod
    def validate_strings(cls, v: str, info) -> str:
        if v:
            return validate_safe_string(v, info.field_name)
        return v

    @field_validator("edit_type")
    @classmethod
    def validate_edit_type(cls, v: str) -> str:
        allowed_types = {"improve", "shorten", "expand", "formalize", "simplify"}
        if v and v not in allowed_types:
            # Allow the value but validate it's safe
            validate_safe_string(v, "edit_type")
        return v


class SummarizeRequest(BaseModel):
    """Request model for summarizing content."""

    model_config = ConfigDict(strict=True, extra="forbid")

    text: Optional[str] = Field(default="", max_length=MAX_STRING_LENGTH)
    sections: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    max_length: Optional[str] = Field(default="medium", max_length=20)

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        if v:
            return validate_safe_string(v, "text")
        return v

    @field_validator("sections")
    @classmethod
    def validate_sections(cls, v: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        validate_safe_list(v, "sections")
        return v

    @field_validator("max_length")
    @classmethod
    def validate_max_length(cls, v: str) -> str:
        allowed_values = {"short", "medium", "long"}
        if v and v not in allowed_values:
            validate_safe_string(v, "max_length")
        return v

    def validate_required_fields(self):
        """Ensure at least text or sections is provided."""
        if not self.text and not self.sections:
            raise ValidationError(
                "Either 'text' or 'sections' is required",
                {"required_fields": ["text", "sections"]}
            )


class ExportRequest(BaseModel):
    """Request model for exporting documents."""

    model_config = ConfigDict(strict=True, extra="forbid")

    title: Optional[str] = Field(default="Untitled Document", max_length=MAX_STRING_LENGTH)
    sections: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        return validate_safe_string(v, "title")

    @field_validator("sections")
    @classmethod
    def validate_sections(cls, v: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        validate_safe_list(v, "sections")
        return v


# =============================================================================
# Nucleus Service Models (Orchestration)
# =============================================================================

class PlanRequest(BaseModel):
    """Request model for creating execution plans."""

    model_config = ConfigDict(strict=True, extra="forbid")

    goal: str = Field(..., min_length=1, max_length=MAX_STRING_LENGTH)
    requirements: Optional[List[str]] = Field(default_factory=list)
    available_agents: Optional[List[str]] = Field(default_factory=list)

    @field_validator("goal")
    @classmethod
    def validate_goal(cls, v: str) -> str:
        return validate_safe_string(v, "goal")

    @field_validator("requirements", "available_agents")
    @classmethod
    def validate_lists(cls, v: List[str], info) -> List[str]:
        validate_safe_list(v, info.field_name)
        for item in v:
            if isinstance(item, str):
                validate_safe_string(item, f"{info.field_name} item")
        return v


class RouteRequest(BaseModel):
    """Request model for routing requests."""

    model_config = ConfigDict(strict=True, extra="forbid")

    request: str = Field(..., min_length=1, max_length=MAX_STRING_LENGTH, alias="request")
    context: Optional[str] = Field(default="", max_length=MAX_STRING_LENGTH)

    @field_validator("request", "context")
    @classmethod
    def validate_strings(cls, v: str, info) -> str:
        if v:
            return validate_safe_string(v, info.field_name)
        return v


class ReviewRequest(BaseModel):
    """Request model for reviewing content."""

    model_config = ConfigDict(strict=True, extra="forbid")

    content: Dict[str, Any] = Field(...)
    criteria: Optional[List[str]] = Field(default_factory=lambda: ["quality", "completeness", "accuracy"])

    @field_validator("criteria")
    @classmethod
    def validate_criteria(cls, v: List[str]) -> List[str]:
        validate_safe_list(v, "criteria")
        for item in v:
            if isinstance(item, str):
                validate_safe_string(item, "criteria item")
        return v


class FinalizeRequest(BaseModel):
    """Request model for finalizing workflows."""

    model_config = ConfigDict(strict=True, extra="forbid")

    workflow_results: List[Dict[str, Any]] = Field(...)
    goal: Optional[str] = Field(default="", max_length=MAX_STRING_LENGTH)

    @field_validator("workflow_results")
    @classmethod
    def validate_results(cls, v: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        validate_safe_list(v, "workflow_results")
        return v

    @field_validator("goal")
    @classmethod
    def validate_goal(cls, v: str) -> str:
        if v:
            return validate_safe_string(v, "goal")
        return v


# =============================================================================
# Myocyte Service Models (Data Analysis)
# =============================================================================

class IngestTableRequest(BaseModel):
    """Request model for ingesting table data."""

    model_config = ConfigDict(strict=True, extra="forbid")

    raw_data: Optional[str] = Field(default="", max_length=MAX_STRING_LENGTH)
    tables: Optional[List[Dict[str, Any]]] = Field(default_factory=list)

    @field_validator("raw_data")
    @classmethod
    def validate_raw_data(cls, v: str) -> str:
        if v:
            return validate_safe_string(v, "raw_data")
        return v

    @field_validator("tables")
    @classmethod
    def validate_tables(cls, v: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        validate_safe_list(v, "tables")
        return v

    def validate_required_fields(self):
        """Ensure at least raw_data or tables is provided."""
        if not self.raw_data and not self.tables:
            raise ValidationError(
                "Either 'raw_data' or 'tables' is required",
                {"required_fields": ["raw_data", "tables"]}
            )


class FormulaEvalRequest(BaseModel):
    """Request model for evaluating formulas."""

    model_config = ConfigDict(strict=True, extra="forbid")

    tables: List[Dict[str, Any]] = Field(...)
    formulas: Optional[List[Dict[str, Any]]] = Field(default_factory=list)

    @field_validator("tables", "formulas")
    @classmethod
    def validate_lists(cls, v: List[Dict[str, Any]], info) -> List[Dict[str, Any]]:
        validate_safe_list(v, info.field_name)
        return v


class ModelForecastRequest(BaseModel):
    """Request model for generating forecasts."""

    model_config = ConfigDict(strict=True, extra="forbid")

    data: Optional[List[Any]] = Field(default_factory=list)
    tables: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    forecast_type: Optional[str] = Field(default="trend", max_length=50)
    periods: Optional[int] = Field(default=5, ge=1, le=100)

    @field_validator("data", "tables")
    @classmethod
    def validate_lists(cls, v: List[Any], info) -> List[Any]:
        validate_safe_list(v, info.field_name)
        return v

    @field_validator("forecast_type")
    @classmethod
    def validate_forecast_type(cls, v: str) -> str:
        if v:
            return validate_safe_string(v, "forecast_type")
        return v

    def validate_required_fields(self):
        """Ensure at least data or tables is provided."""
        if not self.data and not self.tables:
            raise ValidationError(
                "Either 'data' or 'tables' is required",
                {"required_fields": ["data", "tables"]}
            )


# =============================================================================
# Synapse Service Models (Presentations)
# =============================================================================

class StoryboardRequest(BaseModel):
    """Request model for creating presentation storyboards."""

    model_config = ConfigDict(strict=True, extra="forbid")

    topic: Optional[str] = Field(default="", max_length=MAX_STRING_LENGTH)
    goal: Optional[str] = Field(default="", max_length=MAX_STRING_LENGTH)
    audience: Optional[str] = Field(default="general", max_length=MAX_STRING_LENGTH)
    num_slides: Optional[int] = Field(default=10, ge=1, le=100)

    @field_validator("topic", "goal", "audience")
    @classmethod
    def validate_strings(cls, v: str, info) -> str:
        if v:
            return validate_safe_string(v, info.field_name)
        return v

    def validate_required_fields(self):
        """Ensure at least topic or goal is provided."""
        if not self.topic and not self.goal:
            raise ValidationError(
                "Either 'topic' or 'goal' is required",
                {"required_fields": ["topic", "goal"]}
            )


class SlideMakeRequest(BaseModel):
    """Request model for creating slide content."""

    model_config = ConfigDict(strict=True, extra="forbid")

    storyboard: List[Dict[str, Any]] = Field(...)
    topic: Optional[str] = Field(default="", max_length=MAX_STRING_LENGTH)

    @field_validator("storyboard")
    @classmethod
    def validate_storyboard(cls, v: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        validate_safe_list(v, "storyboard")
        return v

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, v: str) -> str:
        if v:
            return validate_safe_string(v, "topic")
        return v


class VisualizeRequest(BaseModel):
    """Request model for creating data visualizations."""

    model_config = ConfigDict(strict=True, extra="forbid")

    data: Optional[List[Any]] = Field(default_factory=list)
    description: Optional[str] = Field(default="", max_length=MAX_STRING_LENGTH)
    viz_type: Optional[str] = Field(default="auto", max_length=50)

    @field_validator("data")
    @classmethod
    def validate_data(cls, v: List[Any]) -> List[Any]:
        if v:
            validate_safe_list(v, "data")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        if v:
            return validate_safe_string(v, "description")
        return v

    @field_validator("viz_type")
    @classmethod
    def validate_viz_type(cls, v: str) -> str:
        if v:
            return validate_safe_string(v, "viz_type")
        return v

    def validate_required_fields(self):
        """Ensure at least data or description is provided."""
        if not self.data and not self.description:
            raise ValidationError(
                "Either 'data' or 'description' is required",
                {"required_fields": ["data", "description"]}
            )


# =============================================================================
# Generic/Shared Models
# =============================================================================

class GenericRequest(BaseModel):
    """Generic request model for services without specific schemas."""

    model_config = ConfigDict(strict=True, extra="allow")

    # This model allows extra fields but validates known common patterns

    @field_validator("*")
    @classmethod
    def validate_all_strings(cls, v: Any, info) -> Any:
        """Validate all string fields for safety."""
        if isinstance(v, str) and v:
            validate_safe_string(v, info.field_name)
        elif isinstance(v, list):
            validate_safe_list(v, info.field_name)
        return v
