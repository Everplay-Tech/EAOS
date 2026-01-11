#!/usr/bin/env python3
"""
Generate self-signed TLS certificates for development.

WARNING: These certificates are for DEVELOPMENT ONLY!
DO NOT use self-signed certificates in production.

For production, use certificates from a trusted Certificate Authority:
- Let's Encrypt (free, automated)
- DigiCert, GlobalSign, etc. (commercial)

Usage:
    python scripts/generate_certs.py
    python scripts/generate_certs.py --domain example.com
    python scripts/generate_certs.py --output ./my-certs
"""
import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from matrix.tls import generate_self_signed_cert, TLSConfig


def main():
    parser = argparse.ArgumentParser(
        description="Generate self-signed TLS certificates for development"
    )
    parser.add_argument(
        "--output",
        default="./certs",
        help="Output directory for certificates (default: ./certs)",
    )
    parser.add_argument(
        "--domain",
        default="localhost",
        help="Common name / domain (default: localhost)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="Certificate validity in days (default: 365)",
    )
    parser.add_argument(
        "--organization",
        default="BIOwerk Development",
        help="Organization name (default: BIOwerk Development)",
    )
    parser.add_argument(
        "--country",
        default="US",
        help="Country code (default: US)",
    )
    parser.add_argument(
        "--state",
        default="California",
        help="State/Province (default: California)",
    )
    parser.add_argument(
        "--locality",
        default="San Francisco",
        help="City/Locality (default: San Francisco)",
    )
    parser.add_argument(
        "--san-dns",
        nargs="*",
        help="Additional DNS names for Subject Alternative Name (e.g., --san-dns api.example.com www.example.com)",
    )
    parser.add_argument(
        "--san-ip",
        nargs="*",
        help="IP addresses for Subject Alternative Name (e.g., --san-ip 192.168.1.100)",
    )

    args = parser.parse_args()

    # Prepare file paths
    output_dir = Path(args.output)
    cert_file = str(output_dir / "cert.pem")
    key_file = str(output_dir / "key.pem")

    print("=" * 70)
    print("BIOwerk Development Certificate Generator")
    print("=" * 70)
    print()
    print("⚠️  WARNING: Self-signed certificates are for DEVELOPMENT ONLY!")
    print("⚠️  DO NOT use these certificates in production environments!")
    print()
    print("Configuration:")
    print(f"  Common Name: {args.domain}")
    print(f"  Organization: {args.organization}")
    print(f"  Country: {args.country}")
    print(f"  State: {args.state}")
    print(f"  Locality: {args.locality}")
    print(f"  Validity: {args.days} days")
    print(f"  Output directory: {output_dir}")
    print()

    if args.san_dns:
        print(f"  Additional DNS names: {', '.join(args.san_dns)}")
    if args.san_ip:
        print(f"  Additional IP addresses: {', '.join(args.san_ip)}")
    print()

    # Generate certificate
    try:
        generate_self_signed_cert(
            cert_file=cert_file,
            key_file=key_file,
            days_valid=args.days,
            country=args.country,
            state=args.state,
            locality=args.locality,
            organization=args.organization,
            common_name=args.domain,
            san_dns=args.san_dns,
            san_ips=args.san_ip,
        )

        print("✓ Certificate generation successful!")
        print()
        print("Files created:")
        print(f"  Certificate: {cert_file}")
        print(f"  Private key: {key_file}")
        print()

        # Validate the generated certificate
        print("Validating certificate...")
        metadata = TLSConfig.validate_certificate(cert_file)

        print()
        print("Certificate details:")
        print(f"  Subject: {metadata['subject']}")
        print(f"  Issuer: {metadata['issuer']}")
        print(f"  Valid from: {metadata['not_before']}")
        print(f"  Valid until: {metadata['not_after']}")
        print(f"  Days remaining: {metadata['days_remaining']}")
        print(f"  Self-signed: {metadata['is_self_signed']}")
        print()

        print("Next steps:")
        print("  1. Update your .env file:")
        print("     TLS_ENABLED=true")
        print(f"     TLS_CERT_FILE={cert_file}")
        print(f"     TLS_KEY_FILE={key_file}")
        print()
        print("  2. Restart your services:")
        print("     docker-compose down")
        print("     docker-compose up -d")
        print()
        print("  3. Access your services via HTTPS:")
        print(f"     https://{args.domain}:8080 (or your configured port)")
        print()
        print("  4. Your browser will show a security warning (expected for self-signed certs)")
        print("     - Chrome/Edge: Click 'Advanced' → 'Proceed to site'")
        print("     - Firefox: Click 'Advanced' → 'Accept the Risk'")
        print()

        return 0

    except Exception as e:
        print(f"❌ Error generating certificate: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
