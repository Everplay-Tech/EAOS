"""
Enterprise-grade TLS/HTTPS configuration and certificate management.

This module provides:
- SSL context configuration with secure defaults
- Certificate validation and loading
- mTLS (mutual TLS) support
- Certificate generation utilities for development
- Production-ready TLS settings
"""
import ssl
import os
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class TLSConfig:
    """Enterprise TLS configuration with security best practices."""

    # Secure TLS cipher suites (OWASP recommended)
    # Prioritizes forward secrecy (ECDHE) and modern ciphers (AES-GCM, ChaCha20)
    SECURE_CIPHERS = ":".join([
        # TLS 1.3 ciphers (preferred)
        "TLS_AES_256_GCM_SHA384",
        "TLS_AES_128_GCM_SHA256",
        "TLS_CHACHA20_POLY1305_SHA256",
        # TLS 1.2 ciphers (backward compatibility)
        "ECDHE-RSA-AES256-GCM-SHA384",
        "ECDHE-RSA-AES128-GCM-SHA256",
        "ECDHE-ECDSA-AES256-GCM-SHA384",
        "ECDHE-ECDSA-AES128-GCM-SHA256",
    ])

    # TLS version mapping
    TLS_VERSIONS = {
        "TLSv1.2": ssl.TLSVersion.TLSv1_2,
        "TLSv1.3": ssl.TLSVersion.TLSv1_3,
    }

    @classmethod
    def create_ssl_context(
        cls,
        cert_file: str,
        key_file: str,
        ca_file: Optional[str] = None,
        verify_client: bool = False,
        min_version: str = "TLSv1.2",
        ciphers: Optional[str] = None,
    ) -> ssl.SSLContext:
        """
        Create a secure SSL context for HTTPS servers.

        Args:
            cert_file: Path to server certificate file (PEM format)
            key_file: Path to server private key file (PEM format)
            ca_file: Path to CA certificate for client verification (optional)
            verify_client: Require and verify client certificates (mTLS)
            min_version: Minimum TLS version ("TLSv1.2" or "TLSv1.3")
            ciphers: Custom cipher suite (None = use secure defaults)

        Returns:
            Configured SSL context

        Raises:
            FileNotFoundError: If certificate or key files don't exist
            ssl.SSLError: If certificate/key loading fails
            ValueError: If configuration is invalid
        """
        # Validate certificate files exist
        cert_path = Path(cert_file)
        key_path = Path(key_file)

        if not cert_path.exists():
            raise FileNotFoundError(f"Certificate file not found: {cert_file}")
        if not key_path.exists():
            raise FileNotFoundError(f"Private key file not found: {key_file}")

        # Validate CA file if client verification is enabled
        if verify_client:
            if not ca_file:
                raise ValueError("ca_file is required when verify_client=True")
            ca_path = Path(ca_file)
            if not ca_path.exists():
                raise FileNotFoundError(f"CA certificate file not found: {ca_file}")

        # Create SSL context with secure defaults
        # PROTOCOL_TLS_SERVER: Modern protocol selection, server mode
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)

        # Load server certificate and private key
        try:
            context.load_cert_chain(
                certfile=str(cert_path),
                keyfile=str(key_path)
            )
            logger.info(f"Loaded TLS certificate: {cert_file}")
        except ssl.SSLError as e:
            logger.error(f"Failed to load TLS certificate/key: {e}")
            raise

        # Configure minimum TLS version
        if min_version not in cls.TLS_VERSIONS:
            raise ValueError(
                f"Invalid TLS version: {min_version}. "
                f"Must be one of: {list(cls.TLS_VERSIONS.keys())}"
            )

        context.minimum_version = cls.TLS_VERSIONS[min_version]
        logger.info(f"Minimum TLS version: {min_version}")

        # Set secure cipher suite
        cipher_suite = ciphers or cls.SECURE_CIPHERS
        try:
            context.set_ciphers(cipher_suite)
            logger.info("Configured secure TLS cipher suite")
        except ssl.SSLError as e:
            logger.warning(f"Failed to set custom ciphers, using defaults: {e}")

        # Configure client certificate verification (mTLS)
        if verify_client:
            context.verify_mode = ssl.CERT_REQUIRED
            context.load_verify_locations(cafile=ca_file)
            logger.info(f"Client certificate verification enabled (mTLS)")
            logger.info(f"Loaded CA certificate: {ca_file}")
        else:
            context.verify_mode = ssl.CERT_NONE
            logger.info("Client certificate verification disabled")

        # Security hardening options
        context.options |= ssl.OP_NO_SSLv2  # Disable SSLv2 (insecure)
        context.options |= ssl.OP_NO_SSLv3  # Disable SSLv3 (POODLE vulnerability)
        context.options |= ssl.OP_NO_TLSv1  # Disable TLSv1.0 (deprecated)
        context.options |= ssl.OP_NO_TLSv1_1  # Disable TLSv1.1 (deprecated)
        context.options |= ssl.OP_NO_COMPRESSION  # Disable compression (CRIME attack)
        context.options |= ssl.OP_CIPHER_SERVER_PREFERENCE  # Server chooses cipher
        context.options |= ssl.OP_SINGLE_DH_USE  # Use new DH key for each session
        context.options |= ssl.OP_SINGLE_ECDH_USE  # Use new ECDH key for each session

        logger.info("SSL context created with enterprise security settings")
        return context

    @classmethod
    def validate_certificate(cls, cert_file: str) -> dict:
        """
        Validate a certificate and extract metadata.

        Args:
            cert_file: Path to certificate file

        Returns:
            Dictionary with certificate metadata:
            - subject: Certificate subject
            - issuer: Certificate issuer
            - not_before: Certificate valid from date
            - not_after: Certificate expiration date
            - days_remaining: Days until expiration
            - is_expired: Whether certificate is expired
            - is_self_signed: Whether certificate is self-signed

        Raises:
            FileNotFoundError: If certificate file doesn't exist
            ssl.SSLError: If certificate is invalid
        """
        import cryptography.x509
        from cryptography.hazmat.backends import default_backend

        cert_path = Path(cert_file)
        if not cert_path.exists():
            raise FileNotFoundError(f"Certificate file not found: {cert_file}")

        # Load certificate
        with open(cert_path, "rb") as f:
            cert_data = f.read()
            cert = cryptography.x509.load_pem_x509_certificate(
                cert_data, default_backend()
            )

        # Extract metadata
        subject = cert.subject.rfc4514_string()
        issuer = cert.issuer.rfc4514_string()
        not_before = cert.not_valid_before_utc
        not_after = cert.not_valid_after_utc

        now = datetime.now(not_after.tzinfo)
        days_remaining = (not_after - now).days
        is_expired = now > not_after
        is_self_signed = subject == issuer

        metadata = {
            "subject": subject,
            "issuer": issuer,
            "not_before": not_before.isoformat(),
            "not_after": not_after.isoformat(),
            "days_remaining": days_remaining,
            "is_expired": is_expired,
            "is_self_signed": is_self_signed,
        }

        # Log warnings
        if is_expired:
            logger.error(f"Certificate is EXPIRED: {cert_file}")
        elif days_remaining < 30:
            logger.warning(
                f"Certificate expires soon ({days_remaining} days): {cert_file}"
            )

        if is_self_signed:
            logger.warning(f"Certificate is self-signed: {cert_file}")

        return metadata


def generate_self_signed_cert(
    cert_file: str = "./certs/cert.pem",
    key_file: str = "./certs/key.pem",
    days_valid: int = 365,
    country: str = "US",
    state: str = "California",
    locality: str = "San Francisco",
    organization: str = "BIOwerk",
    common_name: str = "localhost",
    san_dns: Optional[list[str]] = None,
    san_ips: Optional[list[str]] = None,
) -> None:
    """
    Generate a self-signed certificate for development/testing.

    WARNING: Self-signed certificates should NEVER be used in production!
    For production, use certificates from a trusted CA (Let's Encrypt, DigiCert, etc.)

    Args:
        cert_file: Output path for certificate file
        key_file: Output path for private key file
        days_valid: Number of days the certificate is valid
        country: Country name (2-letter code)
        state: State or province name
        locality: Locality or city name
        organization: Organization name
        common_name: Common name (hostname/domain)
        san_dns: Subject Alternative Names (DNS)
        san_ips: Subject Alternative Names (IP addresses)
    """
    from cryptography import x509
    from cryptography.x509.oid import NameOID, ExtensionOID
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
    import ipaddress

    # Create output directory
    cert_path = Path(cert_file)
    key_path = Path(key_file)
    cert_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate private key (RSA 4096-bit for development)
    logger.info("Generating RSA 4096-bit private key...")
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096,
        backend=default_backend()
    )

    # Build subject and issuer (same for self-signed)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, country),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, state),
        x509.NameAttribute(NameOID.LOCALITY_NAME, locality),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])

    # Build Subject Alternative Names (SAN)
    san_list = []

    # Add common name to SAN
    san_list.append(x509.DNSName(common_name))

    # Add additional DNS names
    if san_dns:
        for dns in san_dns:
            san_list.append(x509.DNSName(dns))

    # Add IP addresses
    if san_ips:
        for ip in san_ips:
            san_list.append(x509.IPAddress(ipaddress.ip_address(ip)))

    # Always include localhost and 127.0.0.1 for development
    if common_name != "localhost":
        san_list.append(x509.DNSName("localhost"))
    san_list.append(x509.IPAddress(ipaddress.ip_address("127.0.0.1")))

    # Build certificate
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=days_valid))
        .add_extension(
            x509.SubjectAlternativeName(san_list),
            critical=False,
        )
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=True,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([
                x509.oid.ExtendedKeyUsageOID.SERVER_AUTH,
                x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH,
            ]),
            critical=False,
        )
        .sign(private_key, hashes.SHA256(), backend=default_backend())
    )

    # Write private key to file (PEM format, no encryption for dev)
    with open(key_path, "wb") as f:
        f.write(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
    os.chmod(key_path, 0o600)  # Restrict permissions (owner read/write only)
    logger.info(f"Private key written to: {key_file}")

    # Write certificate to file (PEM format)
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    logger.info(f"Certificate written to: {cert_file}")

    logger.warning(
        "Self-signed certificate generated. "
        "This is suitable for development ONLY. "
        "DO NOT use self-signed certificates in production!"
    )
    logger.info(f"Certificate valid for {days_valid} days")
    logger.info(f"Common Name: {common_name}")
    logger.info(f"Subject Alternative Names: {[str(san) for san in san_list]}")


# Convenience function for FastAPI/Uvicorn integration
def get_ssl_config_for_uvicorn(
    cert_file: str,
    key_file: str,
    ca_file: Optional[str] = None,
    verify_client: bool = False,
    min_version: str = "TLSv1.2",
) -> dict:
    """
    Get SSL configuration dictionary for Uvicorn server.

    Args:
        cert_file: Path to certificate file
        key_file: Path to private key file
        ca_file: Path to CA certificate (for client verification)
        verify_client: Require client certificates (mTLS)
        min_version: Minimum TLS version

    Returns:
        Dictionary with Uvicorn SSL configuration:
        - ssl_certfile
        - ssl_keyfile
        - ssl_ca_certs (if verify_client=True)
        - ssl_cert_reqs (if verify_client=True)
        - ssl_version

    Example:
        >>> ssl_config = get_ssl_config_for_uvicorn("cert.pem", "key.pem")
        >>> uvicorn.run(app, host="0.0.0.0", port=8443, **ssl_config)
    """
    config = {
        "ssl_certfile": cert_file,
        "ssl_keyfile": key_file,
    }

    if verify_client:
        if not ca_file:
            raise ValueError("ca_file is required when verify_client=True")
        config["ssl_ca_certs"] = ca_file
        config["ssl_cert_reqs"] = ssl.CERT_REQUIRED

    # Map TLS version to ssl module constant
    if min_version == "TLSv1.3":
        config["ssl_version"] = ssl.PROTOCOL_TLS_SERVER
        config["ssl_min_version"] = ssl.TLSVersion.TLSv1_3
    else:  # TLSv1.2
        config["ssl_version"] = ssl.PROTOCOL_TLS_SERVER
        config["ssl_min_version"] = ssl.TLSVersion.TLSv1_2

    return config
