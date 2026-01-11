"""Custom exceptions and error handling for BIOwerk services."""
from fastapi import HTTPException
from typing import Dict, Any


class BIOworkError(Exception):
    """Base exception for BIOwerk application errors."""

    def __init__(self, message: str, details: Dict[str, Any] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class InvalidInputError(BIOworkError):
    """Raised when input validation fails."""
    pass


class ValidationError(BIOworkError):
    """Raised when Pydantic validation fails or input sanitization detects malicious content."""
    pass


class AgentProcessingError(BIOworkError):
    """Raised when an agent fails to process a request."""
    pass


class AgentNotFoundError(BIOworkError):
    """Raised when a requested agent is not found."""
    pass


def create_error_response(msg_id: str, agent: str, error: Exception) -> Dict[str, Any]:
    """
    Create a standardized error response that doesn't leak system information.

    Args:
        msg_id: The message ID from the request
        agent: The agent name
        error: The exception that occurred

    Returns:
        Dictionary containing sanitized error details
    """
    import time
    from matrix.utils import state_hash

    # Sanitize error message to prevent information leakage
    error_type = type(error).__name__

    # Only include detailed messages for known safe error types
    safe_error_types = {
        "InvalidInputError",
        "ValidationError",
        "AgentNotFoundError",
        "BIOworkError"
    }

    if error_type in safe_error_types:
        error_message = str(error)
        error_details = getattr(error, "details", {})
    else:
        # Generic message for unexpected errors to prevent info leakage
        error_message = "An internal error occurred. Please contact support."
        error_details = {}

    error_output = {
        "error": error_type,
        "message": error_message,
        "details": error_details
    }

    return {
        "id": msg_id,
        "ts": time.time(),
        "agent": agent,
        "ok": False,
        "output": error_output,
        "state_hash": state_hash(error_output)
    }


def validate_msg_input(msg: Any, required_fields: list = None) -> None:
    """
    Validate that a message has the required input fields.

    Args:
        msg: The message object to validate
        required_fields: List of required field names in msg.input

    Raises:
        InvalidInputError: If validation fails
    """
    if required_fields is None:
        return

    if not msg.input:
        raise InvalidInputError(
            "Missing required input fields",
            {"required": required_fields, "provided": []}
        )

    missing_fields = [field for field in required_fields if field not in msg.input]
    if missing_fields:
        raise InvalidInputError(
            "Missing required input fields",
            {"required": required_fields, "missing": missing_fields}
        )
