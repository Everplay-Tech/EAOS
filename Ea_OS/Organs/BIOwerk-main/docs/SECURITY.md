# BIOwerk Security Documentation

**Enterprise-Grade Security Features and Best Practices**

Version: 1.0
Last Updated: 2025-11-16

---

## Table of Contents

1. [Overview](#overview)
2. [TLS/HTTPS Configuration](#tlshttps-configuration)
3. [Rate Limiting](#rate-limiting)
4. [Dependency Vulnerability Scanning](#dependency-vulnerability-scanning)
5. [Authentication & Authorization](#authentication--authorization)
6. [Security Best Practices](#security-best-practices)
7. [Incident Response](#incident-response)
8. [Compliance & Auditing](#compliance--auditing)

---

## Overview

BIOwerk implements enterprise-grade security features to protect your microservices architecture from common threats:

- **TLS/HTTPS**: End-to-end encryption with modern TLS protocols
- **Rate Limiting**: DDoS protection and API abuse prevention
- **Dependency Scanning**: Automated vulnerability detection in dependencies
- **JWT Authentication**: Secure token-based authentication
- **API Key Management**: Per-user API keys with scopes and expiration
- **Service Mesh Resilience**: Circuit breakers, retries, and bulkheads
- **Automated Security Scanning**: CI/CD integration for continuous security

### Security Layers

```
┌─────────────────────────────────────────────────────────┐
│                    Internet / Clients                    │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Layer 1: TLS/HTTPS Encryption (TLSv1.2/1.3)            │
│  - Certificate validation                                │
│  - Secure cipher suites                                  │
│  - Optional mTLS for client verification                │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Layer 2: Rate Limiting (Redis-backed)                  │
│  - Per-IP rate limiting                                  │
│  - Per-user rate limiting                                │
│  - Sliding window / Token bucket strategies              │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Layer 3: Authentication & Authorization                │
│  - JWT token validation (HS256/RS256)                    │
│  - API key verification                                  │
│  - Role-based access control (RBAC)                      │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Layer 4: Service Mesh Resilience                       │
│  - Circuit breakers                                      │
│  - Retry with exponential backoff                        │
│  - Bulkhead isolation                                    │
│  - Health-aware routing                                  │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│              Microservices (Agents)                      │
│  Osteon, Myocyte, Synapse, Circadian, Nucleus, etc.     │
└─────────────────────────────────────────────────────────┘
```

---

## TLS/HTTPS Configuration

### Overview

BIOwerk supports enterprise-grade TLS/HTTPS encryption with:
- **TLS 1.2 and TLS 1.3** support (configurable minimum version)
- **Secure cipher suites** (OWASP recommended)
- **Self-signed certificates** for development
- **CA-signed certificates** for production
- **Mutual TLS (mTLS)** for client certificate verification

### Quick Start

#### 1. Generate Development Certificates

For development and testing, generate self-signed certificates:

```bash
python scripts/generate_certs.py
```

This creates:
- `./certs/cert.pem` - Server certificate
- `./certs/key.pem` - Private key

#### 2. Enable TLS in Configuration

Update `.env`:

```bash
TLS_ENABLED=true
TLS_CERT_FILE=./certs/cert.pem
TLS_KEY_FILE=./certs/key.pem
TLS_MIN_VERSION=TLSv1.2
```

#### 3. Restart Services

```bash
docker-compose down
docker-compose up -d
```

#### 4. Access via HTTPS

```bash
# Mesh gateway
curl -k https://localhost:8443/health

# With certificate verification disabled (-k) for self-signed certs
```

### Production Certificate Setup

**NEVER use self-signed certificates in production!**

For production, use certificates from a trusted Certificate Authority:

#### Option 1: Let's Encrypt (Free, Automated)

```bash
# Install certbot
sudo apt-get install certbot

# Obtain certificate (HTTP-01 challenge)
sudo certbot certonly --standalone -d yourdomain.com

# Certificates will be in:
# /etc/letsencrypt/live/yourdomain.com/fullchain.pem
# /etc/letsencrypt/live/yourdomain.com/privkey.pem
```

Update `.env`:

```bash
TLS_ENABLED=true
TLS_CERT_FILE=/etc/letsencrypt/live/yourdomain.com/fullchain.pem
TLS_KEY_FILE=/etc/letsencrypt/live/yourdomain.com/privkey.pem
TLS_MIN_VERSION=TLSv1.3
```

#### Option 2: Commercial CA (DigiCert, GlobalSign, etc.)

1. Generate a Certificate Signing Request (CSR)
2. Submit CSR to your CA
3. Receive signed certificate
4. Configure paths in `.env`

### Mutual TLS (mTLS)

For client certificate verification (highest security):

```bash
# Enable mTLS
TLS_ENABLED=true
TLS_VERIFY_CLIENT=true
TLS_CA_FILE=./certs/ca.pem
```

This requires:
- Server certificate and key
- CA certificate for verifying client certificates
- Clients must present valid certificates signed by the CA

### TLS Configuration Reference

| Setting | Description | Values | Default |
|---------|-------------|--------|---------|
| `TLS_ENABLED` | Enable TLS/HTTPS | `true`/`false` | `false` |
| `TLS_CERT_FILE` | Path to certificate file | Path to PEM file | `./certs/cert.pem` |
| `TLS_KEY_FILE` | Path to private key | Path to PEM file | `./certs/key.pem` |
| `TLS_CA_FILE` | CA cert for client verification | Path to PEM file | `None` |
| `TLS_VERIFY_CLIENT` | Require client certificates (mTLS) | `true`/`false` | `false` |
| `TLS_MIN_VERSION` | Minimum TLS version | `TLSv1.2`, `TLSv1.3` | `TLSv1.2` |
| `TLS_CIPHERS` | Custom cipher suite | Cipher string | Secure defaults |

### Certificate Validation

Validate certificates before deployment:

```bash
# Run security scan
python scripts/security_scan.py --full

# Check certificate details
openssl x509 -in ./certs/cert.pem -text -noout

# Verify certificate chain
openssl verify -CAfile ./certs/ca.pem ./certs/cert.pem
```

### Certificate Rotation

**Production certificates expire!** Implement certificate rotation:

1. **Monitor expiration**: Set alerts for 30 days before expiry
2. **Automate renewal**: Use certbot with cron for Let's Encrypt
3. **Zero-downtime rotation**: Update cert files, gracefully reload services

Example certbot auto-renewal:

```bash
# Add to crontab
0 0 * * * certbot renew --quiet --deploy-hook "docker-compose restart mesh"
```

---

## Rate Limiting

### Overview

Rate limiting protects your API from:
- **DDoS attacks**: Prevent overwhelming the system
- **API abuse**: Limit excessive usage
- **Brute force attacks**: Slow down password guessing
- **Resource exhaustion**: Ensure fair resource allocation

### Features

- **Multiple strategies**:
  - Fixed window: Simple counter reset at intervals
  - Sliding window: Accurate, no boundary bursts (recommended)
  - Token bucket: Allows bursts, smooth traffic shaping
- **Redis-backed**: Distributed rate limiting across instances
- **Per-IP limiting**: Limit requests by client IP address
- **Per-user limiting**: Limit authenticated users separately
- **Configurable exclusions**: Exclude health checks, metrics, etc.
- **Standard headers**: Returns `X-RateLimit-*` headers

### Configuration

Update `.env`:

```bash
# Enable rate limiting
RATE_LIMIT_ENABLED=true

# Allow 100 requests per 60 seconds
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=60

# Strategy: sliding_window (recommended)
RATE_LIMIT_STRATEGY=sliding_window

# Apply per IP and per user
RATE_LIMIT_PER_IP=true
RATE_LIMIT_PER_USER=true

# Burst size (for token bucket strategy)
RATE_LIMIT_BURST=20
```

### Strategy Comparison

| Strategy | Accuracy | Memory | Bursts | Use Case |
|----------|----------|--------|--------|----------|
| **Fixed Window** | Low | Low | Boundary bursts | Simple APIs, low traffic |
| **Sliding Window** | High | Medium | Prevented | Production APIs (recommended) |
| **Token Bucket** | High | Medium | Allowed | APIs with burst tolerance |

### Rate Limit Responses

When rate limit is exceeded, clients receive:

**HTTP 429 Too Many Requests**

```json
{
  "detail": "Rate limit exceeded: 100 requests per 60s"
}
```

**Response Headers:**

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1699999999
Retry-After: 45
```

### Integration Example

```python
from matrix.rate_limiter import RateLimitMiddleware
from matrix.cache import get_redis_client

# In your FastAPI app
redis_client = await get_redis_client()

app.add_middleware(
    RateLimitMiddleware,
    redis_client=redis_client,
    requests=100,
    window=60,
    strategy="sliding_window",
    per_ip=True,
    per_user=True,
    exclude_paths=["/health", "/metrics"],
)
```

### Production Tuning

Adjust rate limits based on your use case:

| Scenario | Requests | Window | Strategy |
|----------|----------|--------|----------|
| Public API | 100 | 60s | sliding_window |
| Internal services | 1000 | 60s | token_bucket |
| Admin endpoints | 10 | 60s | sliding_window |
| Authentication | 5 | 300s | sliding_window |
| File uploads | 10 | 3600s | token_bucket |

---

## Dependency Vulnerability Scanning

### Overview

Automated scanning for known vulnerabilities in Python dependencies using:
- **Safety**: Commercial-grade vulnerability database
- **pip-audit**: Python Package Index (PyPI) vulnerability scanner
- **GitHub Actions**: CI/CD integration
- **Pre-commit hooks**: Local validation before commits

### Manual Scanning

Run security scan locally:

```bash
# Full security scan (dependencies + TLS + config)
python scripts/security_scan.py --full

# Dependencies only
python scripts/security_scan.py --deps-only

# Install security tools
pip install safety pip-audit
```

### CI/CD Integration

Automated scanning runs on:
- Every push to `main`, `develop`, or `claude/**` branches
- Every pull request
- Daily at 2 AM UTC
- Manual workflow dispatch

**GitHub Actions Workflow**: `.github/workflows/security.yml`

Includes:
1. **Dependency scan** (Safety + pip-audit)
2. **Docker image scan** (Trivy)
3. **Secrets scan** (TruffleHog)
4. **Code quality** (Bandit + Flake8)

### Pre-commit Hooks

Install pre-commit for local validation:

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

Pre-commit checks:
- ✓ Secret detection (detect-secrets)
- ✓ Dependency vulnerabilities (Safety)
- ✓ Security linting (Bandit)
- ✓ Code formatting (Black, isort)
- ✓ Code quality (Flake8)
- ✓ Dockerfile linting (Hadolint)

### Vulnerability Response

When vulnerabilities are detected:

1. **Assess severity**:
   - CRITICAL: Immediate fix required
   - HIGH: Fix within 24 hours
   - MEDIUM: Fix within 7 days
   - LOW: Fix in next maintenance window

2. **Update dependencies**:
   ```bash
   # Update specific package
   pip install --upgrade <package>

   # Update requirements.txt
   pip freeze | grep <package> >> requirements.txt
   ```

3. **Test changes**:
   ```bash
   pytest tests/
   ```

4. **Deploy**:
   ```bash
   docker-compose build
   docker-compose up -d
   ```

### Automated Updates

Use Dependabot for automated dependency updates:

**`.github/dependabot.yml`** (create this file):

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 10
    reviewers:
      - "your-team"
    labels:
      - "dependencies"
      - "security"
```

---

## Authentication & Authorization

### JWT Authentication

BIOwerk uses JSON Web Tokens (JWT) for stateless authentication:

```python
# Login and get token
POST /auth/login
{
  "username": "user@example.com",
  "password": "secure-password"
}

# Response
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}

# Use token in requests
GET /api/resource
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

**Configuration:**

```bash
# Generate strong secret (32+ characters)
JWT_SECRET_KEY=$(openssl rand -hex 32)

# Token expiration
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Require authentication for all endpoints
REQUIRE_AUTH=true
```

### API Keys

For service-to-service or long-lived access:

```python
# Create API key
POST /auth/api-keys
{
  "name": "Service A",
  "scopes": ["read", "write"],
  "expires_days": 365
}

# Response
{
  "key": "sk_live_abc123...",
  "key_id": "key_xyz789"
}

# Use API key
GET /api/resource
X-API-Key: sk_live_abc123...
```

### Role-Based Access Control (RBAC)

Protect endpoints by role:

```python
from matrix.auth_dependencies import require_admin

@app.get("/admin/users")
async def list_users(current_user: User = Depends(require_admin)):
    # Only admins can access
    return users
```

---

## Security Best Practices

### Production Deployment Checklist

#### 1. TLS/HTTPS
- [ ] Enable TLS (`TLS_ENABLED=true`)
- [ ] Use CA-signed certificates (not self-signed)
- [ ] Set minimum TLS 1.2 or 1.3
- [ ] Configure certificate rotation
- [ ] Monitor certificate expiration

#### 2. Authentication
- [ ] Change `JWT_SECRET_KEY` to strong random value
- [ ] Enable `REQUIRE_AUTH=true`
- [ ] Implement strong password policies
- [ ] Consider multi-factor authentication (MFA)
- [ ] Rotate JWT secrets periodically

#### 3. Rate Limiting
- [ ] Enable rate limiting (`RATE_LIMIT_ENABLED=true`)
- [ ] Configure appropriate limits for your use case
- [ ] Use Redis for distributed rate limiting
- [ ] Monitor rate limit metrics

#### 4. Database Security
- [ ] Use strong database passwords
- [ ] Enable SSL/TLS for database connections
- [ ] Restrict database network access (firewall rules)
- [ ] Regular backups
- [ ] Enable encryption at rest

#### 5. Infrastructure
- [ ] Use firewall rules (restrict ports)
- [ ] Enable Docker security scanning
- [ ] Run containers as non-root user
- [ ] Use secrets management (Vault, AWS Secrets Manager)
- [ ] Implement network segmentation

#### 6. Dependency Management
- [ ] Regular dependency updates
- [ ] Automated vulnerability scanning (GitHub Dependabot)
- [ ] Pin dependency versions in production
- [ ] Monitor security advisories

#### 7. Monitoring & Logging
- [ ] Enable audit logging
- [ ] Monitor for suspicious activity
- [ ] Set up alerts for security events
- [ ] Regular security reviews
- [ ] Implement SIEM integration

### Secure Configuration

**Development:**
```bash
ENVIRONMENT=development
TLS_ENABLED=false
REQUIRE_AUTH=false
LOG_LEVEL=DEBUG
```

**Production:**
```bash
ENVIRONMENT=production
TLS_ENABLED=true
TLS_MIN_VERSION=TLSv1.3
REQUIRE_AUTH=true
JWT_SECRET_KEY=<strong-random-value>
LOG_LEVEL=INFO
RATE_LIMIT_ENABLED=true
```

### Password Security

**Strong password requirements:**
- Minimum 12 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one number
- At least one special character
- No common passwords (use password strength checker)

**Implementation:**
```python
from passlib.hash import bcrypt

# Hash password
hashed = bcrypt.hash(plain_password)

# Verify password
bcrypt.verify(plain_password, hashed)
```

### Secret Management

**NEVER commit secrets to git!**

Use environment variables or dedicated secret management:

```bash
# .env (gitignored)
JWT_SECRET_KEY=<secret>
OPENAI_API_KEY=<secret>
POSTGRES_PASSWORD=<secret>
```

**Production secret management options:**
- HashiCorp Vault
- AWS Secrets Manager
- Azure Key Vault
- Google Cloud Secret Manager
- Kubernetes Secrets

---

## Incident Response

### Security Incident Response Plan

#### 1. Detection
- Monitor logs and alerts
- Watch for unusual activity patterns
- Review security scan results
- Respond to customer reports

#### 2. Containment
- Isolate affected systems
- Revoke compromised credentials
- Block malicious IP addresses
- Enable additional rate limiting

#### 3. Investigation
- Collect logs and evidence
- Identify attack vector
- Determine scope of breach
- Document timeline

#### 4. Remediation
- Patch vulnerabilities
- Update compromised credentials
- Apply security hardening
- Restore from clean backups if needed

#### 5. Recovery
- Gradually restore services
- Monitor for continued attacks
- Verify system integrity
- Communicate with stakeholders

#### 6. Post-Incident Review
- Document lessons learned
- Update security procedures
- Improve detection mechanisms
- Train team on new threats

### Emergency Contacts

Maintain an incident response contact list:
- Security team lead
- Infrastructure team
- Legal/compliance team
- Public relations (for public disclosures)
- External security consultants

---

## Compliance & Auditing

### Audit Logging

Enable comprehensive audit logging:

```python
from matrix.logging_config import setup_logging

logger = setup_logging("service-name")

# Log security events
logger.info("User login", extra={
    "user_id": user.id,
    "ip_address": request.client.host,
    "user_agent": request.headers.get("user-agent")
})
```

### Compliance Frameworks

BIOwerk security features support compliance with:

- **GDPR**: Data protection, encryption, access controls
- **HIPAA**: Healthcare data protection, audit trails
- **PCI DSS**: Payment card security, encryption, access logs
- **SOC 2**: Security, availability, confidentiality
- **ISO 27001**: Information security management

### Security Audits

Regular security audit checklist:

- [ ] Review access logs
- [ ] Check for unauthorized access attempts
- [ ] Verify certificate validity
- [ ] Review dependency vulnerabilities
- [ ] Check rate limit effectiveness
- [ ] Validate authentication mechanisms
- [ ] Review firewall rules
- [ ] Verify backup integrity
- [ ] Test incident response procedures
- [ ] Review and update security policies

### Penetration Testing

Conduct regular penetration testing:

1. **Automated scanning**: Run tools like OWASP ZAP, Nmap
2. **Manual testing**: Hire security professionals
3. **Bug bounty programs**: Engage ethical hackers
4. **Red team exercises**: Simulate real attacks

---

## Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
- [CIS Controls](https://www.cisecurity.org/controls)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [Docker Security](https://docs.docker.com/engine/security/)

---

## Support

For security issues:
- **Email**: security@biowerk.example.com
- **GitHub Security Advisories**: [Private disclosure](https://github.com/your-org/biowerk/security)

**Please DO NOT open public issues for security vulnerabilities!**

---

*Last updated: 2025-11-16*
*Version: 1.0*
*Maintained by: BIOwerk Security Team*
