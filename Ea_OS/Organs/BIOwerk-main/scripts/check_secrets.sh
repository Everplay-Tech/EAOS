#!/bin/bash
#
# Secret Security Validation Script
# Detects hardcoded secrets, weak passwords, and unsafe configurations
#
# Usage: ./scripts/check_secrets.sh
# Exit codes:
#   0 - No issues found
#   1 - Security violations detected
#

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Track violations
VIOLATIONS=0

echo "🔍 Starting secrets security validation..."
echo ""

# Define patterns for insecure secrets
INSECURE_PATTERNS=(
    "biowerk_dev_password"
    "dev-secret-key-change-in-production"
    "dev_key_change_in_production"
    "changeme"
    "admin:admin"
    "GRAFANA_ADMIN_PASSWORD:-admin"
    "your-pagerduty-service-key"
    "your-pagerduty-security-service-key"
)

# Define sensitive files to check
SENSITIVE_FILES=(
    "docker-compose.yml"
    ".env"
    ".env.local"
    ".env.development"
    ".env.production"
    "config/production.yml"
    "config/development.yml"
)

echo "📋 Checking for hardcoded secrets in sensitive files..."
echo ""

for pattern in "${INSECURE_PATTERNS[@]}"; do
    for file in "${SENSITIVE_FILES[@]}"; do
        if [[ -f "$file" ]]; then
            if grep -q "$pattern" "$file" 2>/dev/null; then
                echo -e "${RED}✗ VIOLATION:${NC} Found insecure pattern '$pattern' in $file"
                VIOLATIONS=$((VIOLATIONS + 1))

                # Show context (5 lines before and after)
                echo -e "${YELLOW}Context:${NC}"
                grep -n -B 2 -A 2 "$pattern" "$file" || true
                echo ""
            fi
        fi
    done
done

# Check for passwords in docker-compose.yml that aren't using environment variable syntax
echo "📋 Checking docker-compose.yml for non-environment variable passwords..."
echo ""

if [[ -f "docker-compose.yml" ]]; then
    # Check for PASSWORD= followed by anything that's not ${...}
    if grep -E '(PASSWORD|SECRET|KEY):\s*[^$\{]' docker-compose.yml | grep -v '${' | grep -v '#' | grep -v 'ro$' | grep -v 'changeme' >/dev/null 2>&1; then
        echo -e "${RED}✗ VIOLATION:${NC} Found hardcoded password/secret in docker-compose.yml"
        echo -e "${YELLOW}Lines with hardcoded secrets:${NC}"
        grep -n -E '(PASSWORD|SECRET|KEY):\s*[^$\{]' docker-compose.yml | grep -v '${' | grep -v '#' | grep -v 'ro$' || true
        VIOLATIONS=$((VIOLATIONS + 1))
        echo ""
    fi

    # Check for embedded credentials in connection strings
    if grep -E '(postgresql|mongodb|redis)://[^:]+:[^@]+@' docker-compose.yml >/dev/null 2>&1; then
        echo -e "${RED}✗ VIOLATION:${NC} Found hardcoded credentials in connection strings"
        echo -e "${YELLOW}Lines with embedded credentials:${NC}"
        grep -n -E '(postgresql|mongodb|redis)://[^:]+:[^@]+@' docker-compose.yml || true
        VIOLATIONS=$((VIOLATIONS + 1))
        echo ""
    fi
fi

# Check for .env file existence
echo "📋 Checking .env file safety..."
echo ""

if [[ -f ".env" ]]; then
    echo -e "${YELLOW}⚠ WARNING:${NC} .env file exists. Ensure it's in .gitignore"

    # Check if .env is in .gitignore
    if [[ -f ".gitignore" ]]; then
        if ! grep -q "^\.env$" .gitignore; then
            echo -e "${RED}✗ VIOLATION:${NC} .env file is NOT in .gitignore!"
            VIOLATIONS=$((VIOLATIONS + 1))
        else
            echo -e "${GREEN}✓${NC} .env is properly gitignored"
        fi
    fi
    echo ""
fi

# Check for weak password patterns in .env files
echo "📋 Checking for weak passwords in .env files..."
echo ""

for env_file in .env .env.local .env.development; do
    if [[ -f "$env_file" ]]; then
        # Check for passwords shorter than 16 characters (crude check)
        while IFS= read -r line; do
            if [[ $line =~ ^[A-Z_]+PASSWORD=(.+)$ ]]; then
                password="${BASH_REMATCH[1]}"
                if [[ ${#password} -lt 16 ]]; then
                    echo -e "${YELLOW}⚠ WARNING:${NC} Weak password detected in $env_file (length < 16)"
                    echo "  Line: $line"
                    echo ""
                fi
            fi
        done < "$env_file"
    fi
done

# Check for AWS credentials in code
echo "📋 Checking for AWS credentials in code..."
echo ""

if grep -r "AKIA[0-9A-Z]{16}" . --exclude-dir=node_modules --exclude-dir=.git --exclude="*.sh" 2>/dev/null; then
    echo -e "${RED}✗ VIOLATION:${NC} Found potential AWS access key"
    VIOLATIONS=$((VIOLATIONS + 1))
    echo ""
fi

# Check for private keys
echo "📋 Checking for private keys..."
echo ""

if grep -r "BEGIN.*PRIVATE KEY" . --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=certs 2>/dev/null; then
    echo -e "${RED}✗ VIOLATION:${NC} Found private key in repository"
    VIOLATIONS=$((VIOLATIONS + 1))
    echo ""
fi

# Check for JWT secrets
echo "📋 Checking for weak JWT secrets..."
echo ""

if grep -r "JWT_SECRET.*=.*secret" . --include="*.yml" --include="*.yaml" --exclude-dir=node_modules 2>/dev/null; then
    echo -e "${YELLOW}⚠ WARNING:${NC} Found potentially weak JWT secret"
    echo ""
fi

# Verify required environment variables are documented
echo "📋 Checking for .env.example..."
echo ""

if [[ ! -f ".env.example" ]]; then
    echo -e "${RED}✗ VIOLATION:${NC} .env.example file not found"
    VIOLATIONS=$((VIOLATIONS + 1))
else
    echo -e "${GREEN}✓${NC} .env.example exists"

    # Check that .env.example doesn't contain real secrets
    if grep -E "(biowerk_dev_password|changeme)" .env.example >/dev/null 2>&1; then
        echo -e "${RED}✗ VIOLATION:${NC} .env.example contains real secrets (should use placeholders)"
        VIOLATIONS=$((VIOLATIONS + 1))
    fi
fi
echo ""

# Check GitHub Actions workflows for secrets
echo "📋 Checking GitHub Actions workflows..."
echo ""

if [[ -d ".github/workflows" ]]; then
    for workflow in .github/workflows/*.yml; do
        if [[ -f "$workflow" ]]; then
            # Check if secrets are used directly instead of secrets context
            if grep -E "(password|secret|key):\s+['\"][^$]" "$workflow" 2>/dev/null; then
                echo -e "${RED}✗ VIOLATION:${NC} Found potential hardcoded secret in $workflow"
                grep -n -E "(password|secret|key):\s+['\"][^$]" "$workflow" || true
                VIOLATIONS=$((VIOLATIONS + 1))
                echo ""
            fi
        fi
    done
fi

# Final report
echo "=================================="
echo "📊 Security Validation Summary"
echo "=================================="
echo ""

if [[ $VIOLATIONS -eq 0 ]]; then
    echo -e "${GREEN}✓ No security violations detected${NC}"
    echo ""
    echo "All checks passed:"
    echo "  ✓ No hardcoded secrets found"
    echo "  ✓ No weak passwords detected"
    echo "  ✓ .env.example exists and is clean"
    echo "  ✓ No exposed credentials in connection strings"
    echo ""
    exit 0
else
    echo -e "${RED}✗ Found $VIOLATIONS security violation(s)${NC}"
    echo ""
    echo "Please fix the issues above before committing."
    echo ""
    echo "Security best practices:"
    echo "  • Never commit real passwords or secrets"
    echo "  • Use environment variables with \${VAR:?required} syntax"
    echo "  • Use strong, randomly generated passwords (32+ chars)"
    echo "  • Keep .env files in .gitignore"
    echo "  • Use secrets management tools (Vault, AWS Secrets Manager) in production"
    echo ""
    exit 1
fi
