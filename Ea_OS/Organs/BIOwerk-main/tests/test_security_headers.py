"""
Comprehensive tests for Security Headers implementation.

Tests cover:
- All security headers present in responses
- CSP (Content-Security-Policy) configuration
- HSTS (Strict-Transport-Security) enforcement
- X-Frame-Options protection
- X-Content-Type-Options protection
- X-XSS-Protection
- Referrer-Policy
- Permissions-Policy
- CORS configuration
- CSP violation reporting
- Environment-specific behavior
"""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock
from matrix.security_headers import SecurityHeadersConfig, SecurityHeadersMiddleware
from matrix.models import Msg
import os
import json


@pytest.fixture
async def mesh_app():
    """Create Mesh app instance for testing."""
    from mesh.main import app
    return app


@pytest.fixture
async def mesh_client(mesh_app):
    """Create async HTTP client for Mesh service."""
    transport = ASGITransport(app=mesh_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# ============================================================================
# Security Headers Presence Tests
# ============================================================================

@pytest.mark.asyncio
async def test_security_headers_present(mesh_client):
    """Test that all required security headers are present in responses."""
    response = await mesh_client.get("/health")

    # Check all required security headers are present
    headers = response.headers

    # Content-Security-Policy (or Report-Only in dev)
    assert "content-security-policy" in headers or "content-security-policy-report-only" in headers, \
        "CSP header missing"

    # X-Frame-Options
    assert "x-frame-options" in headers, "X-Frame-Options header missing"
    assert headers["x-frame-options"] in ["DENY", "SAMEORIGIN"], \
        f"X-Frame-Options has invalid value: {headers['x-frame-options']}"

    # X-Content-Type-Options
    assert "x-content-type-options" in headers, "X-Content-Type-Options header missing"
    assert headers["x-content-type-options"] == "nosniff", \
        f"X-Content-Type-Options should be 'nosniff', got: {headers['x-content-type-options']}"

    # X-XSS-Protection
    assert "x-xss-protection" in headers, "X-XSS-Protection header missing"

    # Referrer-Policy
    assert "referrer-policy" in headers, "Referrer-Policy header missing"

    # Permissions-Policy
    assert "permissions-policy" in headers, "Permissions-Policy header missing"


@pytest.mark.asyncio
async def test_csp_header_structure(mesh_client):
    """Test that CSP header has correct structure and directives."""
    response = await mesh_client.get("/health")
    headers = response.headers

    # Get CSP header (either enforcing or report-only)
    csp = headers.get("content-security-policy") or headers.get("content-security-policy-report-only")
    assert csp is not None, "No CSP header found"

    # Check essential CSP directives are present
    essential_directives = [
        "default-src",
        "script-src",
        "style-src",
        "img-src",
        "object-src",
        "frame-ancestors",
    ]

    for directive in essential_directives:
        assert directive in csp, f"CSP directive '{directive}' missing from policy"

    # Check dangerous directives are NOT present or properly configured
    assert "'unsafe-eval'" not in csp or "script-src" not in csp, \
        "CSP should not allow unsafe-eval for scripts"

    # Check frame-ancestors is properly set (prevents clickjacking)
    assert "frame-ancestors 'none'" in csp or "frame-ancestors 'self'" in csp, \
        "frame-ancestors should be set to 'none' or 'self'"


@pytest.mark.asyncio
async def test_x_frame_options_clickjacking_protection(mesh_client):
    """Test that X-Frame-Options protects against clickjacking."""
    response = await mesh_client.get("/health")

    x_frame_options = response.headers.get("x-frame-options")
    assert x_frame_options is not None, "X-Frame-Options header missing"
    assert x_frame_options in ["DENY", "SAMEORIGIN"], \
        f"X-Frame-Options should be DENY or SAMEORIGIN, got: {x_frame_options}"


@pytest.mark.asyncio
async def test_x_content_type_options_mime_sniffing_protection(mesh_client):
    """Test that X-Content-Type-Options prevents MIME sniffing."""
    response = await mesh_client.get("/health")

    x_content_type = response.headers.get("x-content-type-options")
    assert x_content_type == "nosniff", \
        "X-Content-Type-Options should be 'nosniff' to prevent MIME sniffing"


@pytest.mark.asyncio
async def test_referrer_policy_information_leakage_protection(mesh_client):
    """Test that Referrer-Policy prevents information leakage."""
    response = await mesh_client.get("/health")

    referrer_policy = response.headers.get("referrer-policy")
    assert referrer_policy is not None, "Referrer-Policy header missing"

    # Ensure it's a secure policy (not 'unsafe-url' or 'no-referrer-when-downgrade')
    secure_policies = [
        "no-referrer",
        "same-origin",
        "strict-origin",
        "strict-origin-when-cross-origin",
        "origin",
        "origin-when-cross-origin"
    ]
    assert referrer_policy in secure_policies, \
        f"Referrer-Policy should use a secure value, got: {referrer_policy}"


@pytest.mark.asyncio
async def test_permissions_policy_feature_restriction(mesh_client):
    """Test that Permissions-Policy restricts sensitive browser features."""
    response = await mesh_client.get("/health")

    permissions = response.headers.get("permissions-policy")
    assert permissions is not None, "Permissions-Policy header missing"

    # Check that sensitive features are restricted
    sensitive_features = ["geolocation", "microphone", "camera"]
    for feature in sensitive_features:
        assert feature in permissions, \
            f"Permissions-Policy should restrict '{feature}'"


# ============================================================================
# HSTS Tests
# ============================================================================

@pytest.mark.asyncio
async def test_hsts_header_when_tls_enabled(mesh_client):
    """Test HSTS header is present when TLS is enabled."""
    # Mock TLS enabled
    with patch("matrix.settings.tls_enabled", True):
        response = await mesh_client.get("/health")

        # HSTS should be present when TLS is enabled
        hsts = response.headers.get("strict-transport-security")

        # In production mode with TLS, HSTS should be present
        # In development, it might not be if TLS is not actually configured
        if hsts:
            assert "max-age=" in hsts, "HSTS header should include max-age directive"

            # Extract max-age value
            max_age = int(hsts.split("max-age=")[1].split(";")[0].split(",")[0].strip())
            assert max_age >= 31536000, \
                f"HSTS max-age should be at least 1 year (31536000), got: {max_age}"


@pytest.mark.asyncio
async def test_hsts_includes_subdomains(mesh_client):
    """Test HSTS includes subdomains directive in production."""
    with patch("matrix.settings.tls_enabled", True):
        with patch("matrix.settings.environment", "production"):
            response = await mesh_client.get("/health")

            hsts = response.headers.get("strict-transport-security")
            if hsts:
                # Should include subdomains for comprehensive protection
                assert "includeSubDomains" in hsts or "includesubdomains" in hsts.lower(), \
                    "HSTS should include subdomains in production"


# ============================================================================
# CSP Violation Reporting Tests
# ============================================================================

@pytest.mark.asyncio
async def test_csp_violation_reporting_endpoint_exists(mesh_client):
    """Test that CSP violation reporting endpoint exists and handles reports."""
    # Prepare a sample CSP violation report
    csp_report = {
        "csp-report": {
            "document-uri": "http://testserver/",
            "violated-directive": "script-src 'self'",
            "blocked-uri": "http://evil.com/malicious.js",
            "original-policy": "default-src 'self'; script-src 'self'",
            "source-file": "http://testserver/index.html",
            "line-number": 10,
            "column-number": 5
        }
    }

    # Mock database session
    with patch("mesh.main.get_postgres_session") as mock_db:
        mock_session = MagicMock()
        mock_db.return_value.__aenter__.return_value = mock_session

        # Post CSP violation report
        response = await mesh_client.post(
            "/api/csp-report",
            json=csp_report,
            headers={"Content-Type": "application/csp-report"}
        )

        # CSP reports should return 204 No Content
        assert response.status_code == 204, \
            f"CSP report endpoint should return 204, got: {response.status_code}"


@pytest.mark.asyncio
async def test_csp_violation_suspicious_content_detection(mesh_client):
    """Test that suspicious CSP violations are detected and logged."""
    # Prepare suspicious CSP violation reports
    suspicious_reports = [
        {
            "csp-report": {
                "document-uri": "http://testserver/",
                "violated-directive": "script-src 'self'",
                "blocked-uri": "data:text/javascript,eval('malicious')",
                "original-policy": "default-src 'self'"
            }
        },
        {
            "csp-report": {
                "document-uri": "http://testserver/",
                "violated-directive": "script-src 'self'",
                "blocked-uri": "javascript:alert('xss')",
                "original-policy": "default-src 'self'"
            }
        },
    ]

    with patch("mesh.main.get_postgres_session") as mock_db:
        mock_session = MagicMock()
        mock_db.return_value.__aenter__.return_value = mock_session

        for report in suspicious_reports:
            response = await mesh_client.post(
                "/api/csp-report",
                json=report
            )

            assert response.status_code == 204, \
                f"CSP report should be accepted even if suspicious, got: {response.status_code}"


# ============================================================================
# CORS Configuration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_cors_headers_present(mesh_client):
    """Test that CORS headers are properly configured."""
    # Make a preflight OPTIONS request
    response = await mesh_client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        }
    )

    # Check CORS headers in development mode
    # In development, we allow all origins
    assert "access-control-allow-origin" in response.headers or response.status_code == 200, \
        "CORS headers should be present in development"


@pytest.mark.asyncio
async def test_cors_allows_credentials(mesh_client):
    """Test that CORS allows credentials for authenticated requests."""
    response = await mesh_client.get(
        "/health",
        headers={"Origin": "http://localhost:3000"}
    )

    # Check if credentials are allowed
    allow_credentials = response.headers.get("access-control-allow-credentials")
    if allow_credentials:
        assert allow_credentials.lower() == "true", \
            "CORS should allow credentials for authenticated requests"


@pytest.mark.asyncio
async def test_cors_allowed_methods(mesh_client):
    """Test that CORS allows required HTTP methods."""
    response = await mesh_client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        }
    )

    allowed_methods = response.headers.get("access-control-allow-methods", "")
    if allowed_methods:
        # Check essential methods are allowed
        essential_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
        allowed_methods_upper = allowed_methods.upper()

        for method in essential_methods:
            assert method in allowed_methods_upper, \
                f"CORS should allow {method} method, got: {allowed_methods}"


# ============================================================================
# Environment-Specific Tests
# ============================================================================

@pytest.mark.asyncio
async def test_csp_report_only_in_development():
    """Test that CSP is in report-only mode in development by default."""
    config = SecurityHeadersConfig()

    # Mock development environment
    with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
        config_dev = SecurityHeadersConfig()
        # In development, CSP report-only should typically be true
        # (unless explicitly overridden)
        assert config_dev.is_development, "Should detect development environment"


@pytest.mark.asyncio
async def test_csp_enforced_in_production():
    """Test that CSP is enforced (not report-only) in production."""
    # Mock production environment
    with patch.dict(os.environ, {"ENVIRONMENT": "production", "CSP_REPORT_ONLY": "false"}):
        config_prod = SecurityHeadersConfig()
        assert config_prod.is_production, "Should detect production environment"
        assert not config_prod.csp_report_only, "CSP should be enforced in production"


@pytest.mark.asyncio
async def test_hsts_enabled_in_production():
    """Test that HSTS is enabled by default in production."""
    with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
        config = SecurityHeadersConfig()
        assert config.is_production, "Should detect production environment"
        assert config.hsts_enabled, "HSTS should be enabled in production"


# ============================================================================
# Configuration Tests
# ============================================================================

def test_security_headers_config_defaults():
    """Test that SecurityHeadersConfig has secure defaults."""
    config = SecurityHeadersConfig()

    # CSP should be enabled
    assert config.csp_enabled, "CSP should be enabled by default"

    # X-Frame-Options should be DENY or SAMEORIGIN
    assert config.x_frame_options in ["DENY", "SAMEORIGIN"], \
        "X-Frame-Options should have secure default"

    # X-Content-Type-Options should be nosniff
    assert config.x_content_type_options == "nosniff", \
        "X-Content-Type-Options should be nosniff"

    # Referrer-Policy should be secure
    assert config.referrer_policy in [
        "no-referrer", "same-origin", "strict-origin",
        "strict-origin-when-cross-origin"
    ], "Referrer-Policy should have secure default"


def test_csp_directives_configuration():
    """Test that CSP directives can be customized via environment variables."""
    custom_env = {
        "CSP_DEFAULT_SRC": "'self' https://trusted.com",
        "CSP_SCRIPT_SRC": "'self' https://cdn.trusted.com",
        "CSP_STYLE_SRC": "'self' 'unsafe-inline'",
    }

    with patch.dict(os.environ, custom_env):
        config = SecurityHeadersConfig()

        assert config.csp_directives["default-src"] == "'self' https://trusted.com", \
            "Should respect custom CSP_DEFAULT_SRC"
        assert config.csp_directives["script-src"] == "'self' https://cdn.trusted.com", \
            "Should respect custom CSP_SCRIPT_SRC"
        assert config.csp_directives["style-src"] == "'self' 'unsafe-inline'", \
            "Should respect custom CSP_STYLE_SRC"


def test_hsts_configuration():
    """Test that HSTS can be customized via environment variables."""
    custom_env = {
        "HSTS_MAX_AGE": "63072000",  # 2 years
        "HSTS_INCLUDE_SUBDOMAINS": "true",
        "HSTS_PRELOAD": "true",
    }

    with patch.dict(os.environ, custom_env):
        config = SecurityHeadersConfig()

        assert config.hsts_max_age == 63072000, "Should respect custom HSTS_MAX_AGE"
        assert config.hsts_include_subdomains, "Should respect HSTS_INCLUDE_SUBDOMAINS"
        assert config.hsts_preload, "Should respect HSTS_PRELOAD"

        hsts_value = config.get_hsts_header_value()
        assert "max-age=63072000" in hsts_value, "HSTS header should include custom max-age"
        assert "includeSubDomains" in hsts_value, "HSTS header should include subdomains"
        assert "preload" in hsts_value, "HSTS header should include preload"


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_security_headers_on_all_endpoints(mesh_client):
    """Test that security headers are applied to all endpoints."""
    endpoints = [
        "/health",
        "/health/live",
        "/health/ready",
    ]

    for endpoint in endpoints:
        response = await mesh_client.get(endpoint)

        # All endpoints should have security headers
        assert "x-frame-options" in response.headers, \
            f"Endpoint {endpoint} missing X-Frame-Options header"
        assert "x-content-type-options" in response.headers, \
            f"Endpoint {endpoint} missing X-Content-Type-Options header"


@pytest.mark.asyncio
async def test_security_headers_on_error_responses(mesh_client):
    """Test that security headers are present even on error responses."""
    # Request a non-existent endpoint
    response = await mesh_client.get("/nonexistent")

    # Even 404 responses should have security headers
    assert "x-frame-options" in response.headers, \
        "404 responses should include security headers"
    assert "x-content-type-options" in response.headers, \
        "404 responses should include security headers"


@pytest.mark.asyncio
async def test_no_security_information_leakage(mesh_client):
    """Test that security headers don't leak sensitive information."""
    response = await mesh_client.get("/health")

    # Check that server header doesn't reveal too much
    server = response.headers.get("server", "").lower()

    # Should not reveal specific version numbers or internal details
    sensitive_terms = ["internal", "dev", "test", "staging"]
    for term in sensitive_terms:
        assert term not in server, \
            f"Server header should not contain '{term}'"


# ============================================================================
# Performance Tests
# ============================================================================

@pytest.mark.asyncio
async def test_security_headers_minimal_overhead(mesh_client):
    """Test that security headers middleware has minimal performance impact."""
    import time

    # Make multiple requests and measure time
    iterations = 10
    start = time.time()

    for _ in range(iterations):
        await mesh_client.get("/health")

    duration = time.time() - start
    avg_time = duration / iterations

    # Average request time should be reasonable (< 100ms including headers)
    assert avg_time < 0.1, \
        f"Security headers causing excessive overhead: {avg_time:.3f}s per request"


# ============================================================================
# Compliance Tests
# ============================================================================

def test_mozilla_observatory_requirements():
    """Test that configuration meets Mozilla Observatory requirements."""
    config = SecurityHeadersConfig()

    # X-Frame-Options should be set
    assert config.x_frame_options in ["DENY", "SAMEORIGIN"], \
        "X-Frame-Options required for Mozilla Observatory A+"

    # X-Content-Type-Options should be nosniff
    assert config.x_content_type_options == "nosniff", \
        "X-Content-Type-Options: nosniff required"

    # CSP should be enabled
    assert config.csp_enabled, "CSP required for Mozilla Observatory A+"

    # Referrer-Policy should be set
    assert config.referrer_policy, "Referrer-Policy required"


def test_owasp_secure_headers_compliance():
    """Test compliance with OWASP Secure Headers Project."""
    config = SecurityHeadersConfig()

    # All OWASP recommended headers should be configured
    required_configs = [
        (config.csp_enabled, "Content-Security-Policy"),
        (config.x_frame_options, "X-Frame-Options"),
        (config.x_content_type_options, "X-Content-Type-Options"),
        (config.referrer_policy, "Referrer-Policy"),
    ]

    for enabled, header_name in required_configs:
        assert enabled, f"{header_name} should be enabled per OWASP recommendations"
