#!/usr/bin/env python3
"""
Enterprise security vulnerability scanner for BIOwerk.

This script performs comprehensive security scanning:
1. Dependency vulnerability scanning (using Safety)
2. TLS certificate validation
3. Configuration security audit
4. Docker image scanning recommendations

Usage:
    python scripts/security_scan.py
    python scripts/security_scan.py --full  # Full scan with all checks
    python scripts/security_scan.py --deps-only  # Only scan dependencies
"""
import argparse
import subprocess
import sys
import json
from pathlib import Path
from typing import Dict, List, Tuple
import os

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class Colors:
    """ANSI color codes for terminal output."""
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def print_header(text: str, color: str = Colors.CYAN):
    """Print a formatted header."""
    print()
    print(color + "=" * 70 + Colors.RESET)
    print(color + Colors.BOLD + text + Colors.RESET)
    print(color + "=" * 70 + Colors.RESET)
    print()


def print_status(status: str, message: str):
    """Print a status message with color."""
    if status == "PASS":
        print(f"{Colors.GREEN}✓ PASS{Colors.RESET}: {message}")
    elif status == "FAIL":
        print(f"{Colors.RED}✗ FAIL{Colors.RESET}: {message}")
    elif status == "WARN":
        print(f"{Colors.YELLOW}⚠ WARN{Colors.RESET}: {message}")
    elif status == "INFO":
        print(f"{Colors.BLUE}ℹ INFO{Colors.RESET}: {message}")


def scan_dependencies() -> Tuple[bool, int]:
    """
    Scan Python dependencies for known vulnerabilities using Safety.

    Returns:
        Tuple of (success, vulnerability_count)
    """
    print_header("Dependency Vulnerability Scan", Colors.CYAN)

    requirements_file = Path("requirements.txt")
    if not requirements_file.exists():
        print_status("FAIL", "requirements.txt not found")
        return False, 0

    print_status("INFO", f"Scanning dependencies from {requirements_file}")
    print()

    try:
        # Run safety check
        result = subprocess.run(
            ["safety", "check", "--file", str(requirements_file), "--json"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Parse JSON output
        try:
            vulnerabilities = json.loads(result.stdout) if result.stdout else []
        except json.JSONDecodeError:
            # Try non-JSON output
            print(result.stdout)
            if result.returncode == 0:
                print_status("PASS", "No known vulnerabilities found")
                return True, 0
            else:
                print_status("FAIL", "Safety check failed")
                print(result.stderr)
                return False, 0

        vuln_count = len(vulnerabilities)

        if vuln_count == 0:
            print_status("PASS", "No known vulnerabilities found")
            print_status("INFO", "All dependencies are secure")
            return True, 0

        print_status("FAIL", f"Found {vuln_count} vulnerabilities")
        print()

        # Display vulnerabilities
        for vuln in vulnerabilities:
            package = vuln.get("package", "Unknown")
            installed = vuln.get("installed_version", "Unknown")
            affected = vuln.get("affected_versions", "Unknown")
            vulnerability_id = vuln.get("vulnerability_id", "Unknown")
            cve = vuln.get("CVE", "N/A")

            print(f"{Colors.RED}Package:{Colors.RESET} {package} ({installed})")
            print(f"{Colors.RED}Vulnerability:{Colors.RESET} {vulnerability_id}")
            if cve != "N/A":
                print(f"{Colors.RED}CVE:{Colors.RESET} {cve}")
            print(f"{Colors.YELLOW}Affected versions:{Colors.RESET} {affected}")
            print(f"{Colors.GREEN}Recommendation:{Colors.RESET} {vuln.get('more_info_url', 'See safety output')}")
            print()

        return False, vuln_count

    except subprocess.TimeoutExpired:
        print_status("FAIL", "Safety scan timed out")
        return False, 0
    except FileNotFoundError:
        print_status("FAIL", "Safety not installed. Install with: pip install safety")
        print_status("INFO", "Running alternative scan...")

        # Fallback: pip-audit if available
        try:
            result = subprocess.run(
                ["pip-audit", "--requirement", str(requirements_file)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            print(result.stdout)
            return result.returncode == 0, 0
        except FileNotFoundError:
            print_status("WARN", "Neither safety nor pip-audit is installed")
            print_status("INFO", "Install with: pip install safety")
            return False, 0
    except Exception as e:
        print_status("FAIL", f"Error during dependency scan: {e}")
        return False, 0


def validate_tls_certificates() -> bool:
    """Validate TLS certificate configuration."""
    print_header("TLS Certificate Validation", Colors.CYAN)

    try:
        from matrix.config import settings
        from matrix.tls import TLSConfig

        if not settings.tls_enabled:
            print_status("INFO", "TLS is disabled (development mode)")
            print_status("WARN", "Enable TLS for production deployments")
            return True

        cert_file = Path(settings.tls_cert_file)
        key_file = Path(settings.tls_key_file)

        # Check certificate file
        if not cert_file.exists():
            print_status("FAIL", f"Certificate file not found: {cert_file}")
            print_status("INFO", "Generate certificates with: python scripts/generate_certs.py")
            return False

        print_status("PASS", f"Certificate file found: {cert_file}")

        # Check key file
        if not key_file.exists():
            print_status("FAIL", f"Private key file not found: {key_file}")
            return False

        print_status("PASS", f"Private key file found: {key_file}")

        # Validate certificate
        try:
            metadata = TLSConfig.validate_certificate(str(cert_file))

            print()
            print("Certificate details:")
            print(f"  Subject: {metadata['subject']}")
            print(f"  Issuer: {metadata['issuer']}")
            print(f"  Valid from: {metadata['not_before']}")
            print(f"  Valid until: {metadata['not_after']}")
            print(f"  Days remaining: {metadata['days_remaining']}")
            print()

            # Check expiration
            if metadata['is_expired']:
                print_status("FAIL", "Certificate is EXPIRED")
                return False
            elif metadata['days_remaining'] < 7:
                print_status("FAIL", f"Certificate expires in {metadata['days_remaining']} days")
                return False
            elif metadata['days_remaining'] < 30:
                print_status("WARN", f"Certificate expires in {metadata['days_remaining']} days")
            else:
                print_status("PASS", f"Certificate is valid ({metadata['days_remaining']} days remaining)")

            # Check self-signed
            if metadata['is_self_signed']:
                print_status("WARN", "Certificate is self-signed (development only)")
                if os.getenv("ENVIRONMENT", "development") == "production":
                    print_status("FAIL", "Self-signed certificates should NOT be used in production")
                    return False

            return True

        except Exception as e:
            print_status("FAIL", f"Certificate validation failed: {e}")
            return False

    except Exception as e:
        print_status("FAIL", f"Error during TLS validation: {e}")
        return False


def audit_security_config() -> bool:
    """Audit security configuration settings."""
    print_header("Security Configuration Audit", Colors.CYAN)

    try:
        from matrix.config import settings

        all_passed = True

        # Check JWT secret
        if settings.jwt_secret_key == "dev-secret-key-change-in-production":
            print_status("FAIL", "JWT secret is using default value")
            print_status("INFO", "Set JWT_SECRET_KEY in .env to a strong random value")
            all_passed = False
        else:
            if len(settings.jwt_secret_key) < 32:
                print_status("WARN", f"JWT secret is short ({len(settings.jwt_secret_key)} chars, recommended: 32+)")
            else:
                print_status("PASS", "JWT secret is configured")

        # Check authentication
        if settings.require_auth:
            print_status("PASS", "Authentication is required for all endpoints")
        else:
            print_status("WARN", "Authentication is not required (development mode)")
            if os.getenv("ENVIRONMENT", "development") == "production":
                print_status("FAIL", "Authentication should be required in production")
                all_passed = False

        # Check rate limiting
        if settings.rate_limit_enabled:
            print_status("PASS", f"Rate limiting enabled: {settings.rate_limit_requests} req/{settings.rate_limit_window}s")
        else:
            print_status("WARN", "Rate limiting is disabled")

        # Check TLS
        if settings.tls_enabled:
            print_status("PASS", "TLS/HTTPS is enabled")
            if settings.tls_min_version == "TLSv1.3":
                print_status("PASS", "TLS 1.3 minimum version (excellent)")
            elif settings.tls_min_version == "TLSv1.2":
                print_status("PASS", "TLS 1.2 minimum version (good)")
            else:
                print_status("WARN", f"Old TLS version: {settings.tls_min_version}")
        else:
            print_status("WARN", "TLS/HTTPS is disabled (development mode)")
            if os.getenv("ENVIRONMENT", "development") == "production":
                print_status("FAIL", "TLS should be enabled in production")
                all_passed = False

        # Check environment
        env = settings.environment
        print_status("INFO", f"Environment: {env}")

        if env == "production":
            # Additional production checks
            if not settings.tls_enabled:
                print_status("FAIL", "TLS must be enabled in production")
                all_passed = False
            if not settings.require_auth:
                print_status("FAIL", "Authentication must be required in production")
                all_passed = False
            if settings.log_level == "DEBUG":
                print_status("WARN", "Debug logging should be disabled in production")

        return all_passed

    except Exception as e:
        print_status("FAIL", f"Error during configuration audit: {e}")
        return False


def print_recommendations():
    """Print security recommendations."""
    print_header("Security Recommendations", Colors.MAGENTA)

    print(f"{Colors.BOLD}Production Deployment Checklist:{Colors.RESET}")
    print()
    print("1. TLS/HTTPS Configuration:")
    print("   ✓ Use certificates from a trusted CA (Let's Encrypt, DigiCert, etc.)")
    print("   ✓ Enable TLS 1.2 minimum (TLS 1.3 preferred)")
    print("   ✓ Set TLS_ENABLED=true in .env")
    print()

    print("2. Authentication & Authorization:")
    print("   ✓ Set strong JWT_SECRET_KEY (32+ random characters)")
    print("   ✓ Enable REQUIRE_AUTH=true")
    print("   ✓ Use strong password policies")
    print("   ✓ Implement multi-factor authentication (MFA)")
    print()

    print("3. Rate Limiting:")
    print("   ✓ Enable rate limiting (RATE_LIMIT_ENABLED=true)")
    print("   ✓ Configure appropriate limits for your use case")
    print("   ✓ Use Redis for distributed rate limiting")
    print()

    print("4. Database Security:")
    print("   ✓ Use strong database passwords")
    print("   ✓ Enable SSL/TLS for database connections")
    print("   ✓ Restrict database network access")
    print("   ✓ Regular backups and encryption at rest")
    print()

    print("5. Dependency Management:")
    print("   ✓ Regular dependency updates")
    print("   ✓ Automated vulnerability scanning (GitHub Dependabot, Snyk)")
    print("   ✓ Pin dependency versions in production")
    print()

    print("6. Infrastructure Security:")
    print("   ✓ Use firewall rules (restrict ports)")
    print("   ✓ Enable Docker security scanning")
    print("   ✓ Run containers as non-root user")
    print("   ✓ Use secrets management (HashiCorp Vault, AWS Secrets Manager)")
    print()

    print("7. Monitoring & Logging:")
    print("   ✓ Enable audit logging")
    print("   ✓ Monitor for suspicious activity")
    print("   ✓ Set up alerts for security events")
    print("   ✓ Regular security reviews")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Enterprise security scanner for BIOwerk"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run full security scan (all checks)",
    )
    parser.add_argument(
        "--deps-only",
        action="store_true",
        help="Only scan dependencies for vulnerabilities",
    )
    parser.add_argument(
        "--no-recommendations",
        action="store_true",
        help="Skip printing security recommendations",
    )

    args = parser.parse_args()

    print()
    print(Colors.BOLD + Colors.CYAN + "BIOwerk Enterprise Security Scanner" + Colors.RESET)
    print()

    results = {}

    # Dependency scan (always run unless specific checks requested)
    if not args.full and not args.deps_only:
        deps_ok, vuln_count = scan_dependencies()
        results["dependencies"] = deps_ok
    elif args.deps_only:
        deps_ok, vuln_count = scan_dependencies()
        results["dependencies"] = deps_ok
    elif args.full:
        deps_ok, vuln_count = scan_dependencies()
        results["dependencies"] = deps_ok

        # TLS validation
        tls_ok = validate_tls_certificates()
        results["tls"] = tls_ok

        # Config audit
        config_ok = audit_security_config()
        results["config"] = config_ok

    # Print summary
    print_header("Security Scan Summary", Colors.CYAN)

    total_checks = len(results)
    passed_checks = sum(1 for v in results.values() if v)
    failed_checks = total_checks - passed_checks

    print(f"Total checks: {total_checks}")
    print(f"{Colors.GREEN}Passed: {passed_checks}{Colors.RESET}")
    if failed_checks > 0:
        print(f"{Colors.RED}Failed: {failed_checks}{Colors.RESET}")
    print()

    # Detailed results
    for check, passed in results.items():
        if passed:
            print_status("PASS", check.capitalize())
        else:
            print_status("FAIL", check.capitalize())

    # Recommendations
    if not args.no_recommendations:
        print_recommendations()

    # Exit code
    if all(results.values()):
        print()
        print(f"{Colors.GREEN}{Colors.BOLD}✓ All security checks passed!{Colors.RESET}")
        print()
        return 0
    else:
        print()
        print(f"{Colors.RED}{Colors.BOLD}✗ Some security checks failed. Please address the issues above.{Colors.RESET}")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
