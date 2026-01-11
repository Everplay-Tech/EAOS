# BIOwerk Security Scripts

This directory contains security-related scripts for certificate management, vulnerability scanning, and security automation.

## Available Scripts

### 1. Certificate Generation (`generate_certs.py`)

Generate self-signed TLS certificates for development.

**⚠️ WARNING**: Self-signed certificates are for DEVELOPMENT ONLY! Use CA-signed certificates in production.

**Basic Usage:**
```bash
# Generate default certificates (localhost)
python scripts/generate_certs.py

# Generate for custom domain
python scripts/generate_certs.py --domain api.example.com

# Generate with custom output directory
python scripts/generate_certs.py --output ./my-certs

# Generate with Subject Alternative Names
python scripts/generate_certs.py \
  --domain api.example.com \
  --san-dns www.example.com api.example.com \
  --san-ip 192.168.1.100
```

**Options:**
- `--output DIR`: Output directory (default: `./certs`)
- `--domain NAME`: Common name / domain (default: `localhost`)
- `--days N`: Certificate validity in days (default: `365`)
- `--organization NAME`: Organization name
- `--country CODE`: Country code (default: `US`)
- `--state NAME`: State/Province
- `--locality NAME`: City
- `--san-dns NAMES`: Additional DNS names for SAN
- `--san-ip ADDRS`: IP addresses for SAN

**Generated Files:**
- `cert.pem` - Server certificate (public)
- `key.pem` - Private key (keep secure!)

**Post-Generation:**
1. Update `.env`: Set `TLS_ENABLED=true`
2. Configure certificate paths
3. Restart services: `docker-compose restart`

---

### 2. Security Scanner (`security_scan.py`)

Comprehensive security vulnerability scanner.

**Features:**
- Dependency vulnerability scanning (Safety + pip-audit)
- TLS certificate validation
- Security configuration audit
- Security best practice recommendations

**Usage:**
```bash
# Full security scan (recommended)
python scripts/security_scan.py --full

# Dependencies only
python scripts/security_scan.py --deps-only

# Skip recommendations
python scripts/security_scan.py --no-recommendations
```

**Scan Components:**

**1. Dependency Scan**
- Uses Safety to check for known vulnerabilities
- Scans `requirements.txt` against CVE database
- Reports vulnerable packages with remediation

**2. TLS Validation**
- Checks certificate file existence
- Validates certificate expiration
- Warns about self-signed certificates
- Verifies TLS configuration

**3. Configuration Audit**
- JWT secret strength check
- Authentication requirements
- Rate limiting configuration
- TLS settings verification
- Environment-specific checks

**Example Output:**
```
=================================================================
BIOwerk Enterprise Security Scanner
=================================================================

=================================================================
Dependency Vulnerability Scan
=================================================================
✓ PASS: No known vulnerabilities found

=================================================================
TLS Certificate Validation
=================================================================
ℹ INFO: TLS is disabled (development mode)
⚠ WARN: Enable TLS for production deployments

=================================================================
Security Configuration Audit
=================================================================
✓ PASS: JWT secret is configured
⚠ WARN: Authentication is not required (development mode)
✓ PASS: Rate limiting enabled: 100 req/60s

=================================================================
Security Scan Summary
=================================================================
Total checks: 3
Passed: 3

✓ All security checks passed!
```

**CI/CD Integration:**
- Run in GitHub Actions (see `.github/workflows/security.yml`)
- Pre-commit hook integration (see `.pre-commit-config.yaml`)
- Exit code: 0 = pass, 1 = failures detected

---

## Installation

Install required dependencies:

```bash
# Core dependencies
pip install -r requirements.txt

# Additional security tools
pip install safety pip-audit pre-commit

# Pre-commit hooks (optional)
pre-commit install
```

---

## Production Certificate Setup

For production deployments, use certificates from a trusted Certificate Authority:

### Option 1: Let's Encrypt (Free, Automated)

```bash
# Install certbot
sudo apt-get install certbot

# Obtain certificate (standalone mode)
sudo certbot certonly --standalone -d yourdomain.com

# Certificates location:
# /etc/letsencrypt/live/yourdomain.com/fullchain.pem
# /etc/letsencrypt/live/yourdomain.com/privkey.pem

# Auto-renewal (add to crontab)
0 0 * * * certbot renew --quiet --deploy-hook "docker-compose restart mesh"
```

### Option 2: Commercial CA

1. Generate CSR (Certificate Signing Request)
2. Submit to CA (DigiCert, GlobalSign, etc.)
3. Receive signed certificate
4. Configure in `.env`

---

## Security Best Practices

### Certificate Management

1. **Development**:
   - Use self-signed certificates (generated with `generate_certs.py`)
   - Store in `./certs` directory (gitignored)
   - Rotate every 90 days

2. **Production**:
   - Use CA-signed certificates (Let's Encrypt, commercial)
   - Store securely (restrict permissions to 600/400)
   - Monitor expiration (alert 30 days before)
   - Automate renewal (certbot cron job)
   - Use TLS 1.3 minimum (`TLS_MIN_VERSION=TLSv1.3`)

### Vulnerability Scanning

1. **Local Development**:
   ```bash
   # Before every commit
   python scripts/security_scan.py --full
   ```

2. **CI/CD Pipeline**:
   - Automated scans on every PR
   - Fail builds on HIGH/CRITICAL vulnerabilities
   - Daily scheduled scans

3. **Production Monitoring**:
   - Weekly dependency scans
   - Immediate patches for CRITICAL vulnerabilities
   - Monthly security audits

### Secret Management

**NEVER commit:**
- Private keys (`*.key`, `*.pem`)
- Passwords or API keys
- JWT secrets

**Use:**
- `.env` files (gitignored)
- Environment variables
- Secrets management (Vault, AWS Secrets Manager)

---

## Troubleshooting

### Certificate Issues

**Problem**: "Certificate file not found"
```bash
# Solution: Generate certificates
python scripts/generate_certs.py
```

**Problem**: "Certificate is expired"
```bash
# Solution: Regenerate certificates
rm -rf ./certs
python scripts/generate_certs.py
```

**Problem**: Browser shows "Not Secure" warning
```
# Expected for self-signed certificates
# Click "Advanced" → "Proceed to site" (development only)
```

### Dependency Scan Issues

**Problem**: "Safety not installed"
```bash
# Solution: Install security tools
pip install safety pip-audit
```

**Problem**: "Vulnerabilities found"
```bash
# Solution: Update vulnerable packages
pip install --upgrade <package-name>

# Update requirements.txt
pip freeze | grep <package-name> >> requirements.txt

# Re-run scan
python scripts/security_scan.py --deps-only
```

---

## Additional Resources

- [Security Documentation](../docs/security.md)
- [TLS Best Practices](https://wiki.mozilla.org/Security/Server_Side_TLS)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)
- [Safety Database](https://github.com/pyupio/safety-db)

---

## Support

For security issues, please contact:
- **Email**: security@biowerk.example.com
- **GitHub**: [Private security advisories](https://github.com/your-org/biowerk/security)

**DO NOT open public issues for security vulnerabilities!**

---

*Last updated: 2025-11-16*
