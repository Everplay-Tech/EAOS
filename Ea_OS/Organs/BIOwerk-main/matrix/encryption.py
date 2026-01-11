"""Enterprise-grade encryption service for audit logs and sensitive data.

This module provides AES-256-GCM encryption for data at rest with:
- Field-level encryption for sensitive audit log data
- Envelope encryption pattern (DEK + KEK)
- Key rotation support
- Cryptographic integrity verification
- FIPS 140-2 compliant algorithms
"""

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
from cryptography.hazmat.backends import default_backend
from typing import Optional, Dict, Any, Tuple
import secrets
import base64
import json
import hashlib
from datetime import datetime, timedelta


class EncryptionError(Exception):
    """Base exception for encryption-related errors."""
    pass


class KeyRotationError(EncryptionError):
    """Exception raised when key rotation fails."""
    pass


class DecryptionError(EncryptionError):
    """Exception raised when decryption fails."""
    pass


class EncryptionService:
    """
    Enterprise-grade encryption service using AES-256-GCM.

    Features:
    - AES-256-GCM authenticated encryption
    - Per-field encryption for granular access control
    - Envelope encryption (DEK encrypted with KEK)
    - Key versioning and rotation support
    - Cryptographic integrity verification
    - Constant-time operations where possible

    Security Properties:
    - Confidentiality: AES-256-GCM encryption
    - Integrity: GCM authentication tag
    - Authenticity: AEAD properties
    - Forward secrecy: Key rotation support
    """

    def __init__(
        self,
        master_key: str,
        key_version: int = 1,
        rotation_period_days: int = 90,
        salt: Optional[bytes] = None
    ):
        """
        Initialize the encryption service.

        Args:
            master_key: Master encryption key (KEK). Should be 32+ characters.
                       In production, use a KMS (AWS KMS, Azure Key Vault, etc.)
            key_version: Current key version for rotation tracking
            rotation_period_days: Days before key rotation is recommended
            salt: Salt for key derivation (32 bytes). Auto-generated if not provided.

        Raises:
            ValueError: If master_key is too short or salt is invalid
        """
        if len(master_key) < 32:
            raise ValueError("Master key must be at least 32 characters")

        self.key_version = key_version
        self.rotation_period_days = rotation_period_days
        self.key_created_at = datetime.utcnow()

        # Use provided salt or generate a new one
        self.salt = salt if salt else secrets.token_bytes(32)
        if len(self.salt) != 32:
            raise ValueError("Salt must be exactly 32 bytes")

        # Derive KEK from master key using PBKDF2
        self.kek = self._derive_key(master_key.encode('utf-8'), self.salt)
        self.kek_cipher = AESGCM(self.kek)

    def _derive_key(self, password: bytes, salt: bytes, iterations: int = 600000) -> bytes:
        """
        Derive a 256-bit key using PBKDF2-HMAC-SHA256.

        Args:
            password: Password/master key to derive from
            salt: Salt for key derivation
            iterations: PBKDF2 iterations (600k recommended by OWASP 2023)

        Returns:
            32-byte derived key
        """
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=iterations,
            backend=default_backend()
        )
        return kdf.derive(password)

    def generate_dek(self) -> bytes:
        """
        Generate a random Data Encryption Key (DEK).

        Returns:
            32-byte random key for AES-256
        """
        return secrets.token_bytes(32)

    def encrypt_dek(self, dek: bytes) -> Dict[str, str]:
        """
        Encrypt a DEK with the KEK (envelope encryption).

        Args:
            dek: Data Encryption Key to encrypt

        Returns:
            Dict containing encrypted DEK, nonce, and metadata
        """
        nonce = secrets.token_bytes(12)  # 96-bit nonce for GCM
        encrypted_dek = self.kek_cipher.encrypt(nonce, dek, None)

        return {
            "encrypted_dek": base64.b64encode(encrypted_dek).decode('utf-8'),
            "nonce": base64.b64encode(nonce).decode('utf-8'),
            "key_version": self.key_version,
            "algorithm": "AES-256-GCM",
            "created_at": datetime.utcnow().isoformat()
        }

    def decrypt_dek(self, encrypted_dek_data: Dict[str, str]) -> bytes:
        """
        Decrypt a DEK using the KEK.

        Args:
            encrypted_dek_data: Dict containing encrypted DEK and metadata

        Returns:
            Decrypted DEK

        Raises:
            DecryptionError: If decryption fails
            KeyRotationError: If key version mismatch
        """
        # Check key version compatibility
        if encrypted_dek_data.get("key_version") != self.key_version:
            raise KeyRotationError(
                f"Key version mismatch: data encrypted with v{encrypted_dek_data.get('key_version')}, "
                f"but current version is v{self.key_version}"
            )

        try:
            encrypted_dek = base64.b64decode(encrypted_dek_data["encrypted_dek"])
            nonce = base64.b64decode(encrypted_dek_data["nonce"])
            return self.kek_cipher.decrypt(nonce, encrypted_dek, None)
        except Exception as e:
            raise DecryptionError(f"Failed to decrypt DEK: {str(e)}")

    def encrypt_field(
        self,
        plaintext: str,
        associated_data: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Encrypt a single field using envelope encryption.

        Args:
            plaintext: Data to encrypt
            associated_data: Additional authenticated data (AAD) for GCM

        Returns:
            Dict containing encrypted data, encrypted DEK, and metadata
        """
        # Generate a unique DEK for this field
        dek = self.generate_dek()
        dek_cipher = AESGCM(dek)

        # Encrypt the plaintext with DEK
        nonce = secrets.token_bytes(12)
        aad = associated_data.encode('utf-8') if associated_data else None
        ciphertext = dek_cipher.encrypt(nonce, plaintext.encode('utf-8'), aad)

        # Encrypt the DEK with KEK
        encrypted_dek_data = self.encrypt_dek(dek)

        return {
            "ciphertext": base64.b64encode(ciphertext).decode('utf-8'),
            "nonce": base64.b64encode(nonce).decode('utf-8'),
            "dek_metadata": encrypted_dek_data,
            "algorithm": "AES-256-GCM",
            "has_aad": associated_data is not None,
            "encrypted_at": datetime.utcnow().isoformat()
        }

    def decrypt_field(
        self,
        encrypted_data: Dict[str, Any],
        associated_data: Optional[str] = None
    ) -> str:
        """
        Decrypt a field encrypted with encrypt_field.

        Args:
            encrypted_data: Dict containing encrypted field and metadata
            associated_data: AAD used during encryption (must match)

        Returns:
            Decrypted plaintext

        Raises:
            DecryptionError: If decryption or integrity check fails
        """
        try:
            # Decrypt the DEK
            dek = self.decrypt_dek(encrypted_data["dek_metadata"])
            dek_cipher = AESGCM(dek)

            # Decrypt the ciphertext
            ciphertext = base64.b64decode(encrypted_data["ciphertext"])
            nonce = base64.b64decode(encrypted_data["nonce"])
            aad = associated_data.encode('utf-8') if associated_data else None

            plaintext_bytes = dek_cipher.decrypt(nonce, ciphertext, aad)
            return plaintext_bytes.decode('utf-8')
        except Exception as e:
            raise DecryptionError(f"Failed to decrypt field: {str(e)}")

    def encrypt_json(
        self,
        data: Dict[str, Any],
        fields_to_encrypt: list[str],
        record_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Encrypt specific fields in a JSON object.

        Args:
            data: JSON object to encrypt
            fields_to_encrypt: List of field names to encrypt
            record_id: Optional record ID to use as AAD for integrity

        Returns:
            JSON object with encrypted fields
        """
        encrypted_data = data.copy()

        for field in fields_to_encrypt:
            if field in encrypted_data and encrypted_data[field] is not None:
                # Convert to string if not already
                value = encrypted_data[field]
                if not isinstance(value, str):
                    value = json.dumps(value)

                # Use record_id + field_name as AAD for binding
                aad = f"{record_id}:{field}" if record_id else field

                # Encrypt and mark as encrypted
                encrypted_data[f"{field}_encrypted"] = self.encrypt_field(value, aad)
                encrypted_data[field] = None  # Clear plaintext

        return encrypted_data

    def decrypt_json(
        self,
        data: Dict[str, Any],
        fields_to_decrypt: list[str],
        record_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Decrypt specific fields in a JSON object.

        Args:
            data: JSON object with encrypted fields
            fields_to_decrypt: List of field names to decrypt
            record_id: Optional record ID used as AAD during encryption

        Returns:
            JSON object with decrypted fields
        """
        decrypted_data = data.copy()

        for field in fields_to_decrypt:
            encrypted_field = f"{field}_encrypted"
            if encrypted_field in decrypted_data and decrypted_data[encrypted_field]:
                # Use same AAD as during encryption
                aad = f"{record_id}:{field}" if record_id else field

                # Decrypt and restore
                plaintext = self.decrypt_field(decrypted_data[encrypted_field], aad)

                # Try to parse as JSON if it looks like JSON
                try:
                    if plaintext.startswith(('{', '[')):
                        decrypted_data[field] = json.loads(plaintext)
                    else:
                        decrypted_data[field] = plaintext
                except json.JSONDecodeError:
                    decrypted_data[field] = plaintext

                # Remove encrypted version
                del decrypted_data[encrypted_field]

        return decrypted_data

    def hash_for_search(self, value: str) -> str:
        """
        Create a deterministic hash for searching encrypted fields.

        This allows searching for encrypted values without decrypting them.
        Uses HMAC-SHA256 with the KEK for security.

        Args:
            value: Value to hash

        Returns:
            Hex-encoded hash suitable for database indexing
        """
        import hmac
        return hmac.new(
            self.kek,
            value.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def needs_rotation(self) -> bool:
        """
        Check if key rotation is needed based on age.

        Returns:
            True if key is older than rotation_period_days
        """
        age = datetime.utcnow() - self.key_created_at
        return age > timedelta(days=self.rotation_period_days)

    def get_key_info(self) -> Dict[str, Any]:
        """
        Get information about the current encryption key.

        Returns:
            Dict with key version, age, and rotation status
        """
        age_days = (datetime.utcnow() - self.key_created_at).days
        return {
            "key_version": self.key_version,
            "created_at": self.key_created_at.isoformat(),
            "age_days": age_days,
            "rotation_period_days": self.rotation_period_days,
            "needs_rotation": self.needs_rotation(),
            "algorithm": "AES-256-GCM",
            "kdf": "PBKDF2-HMAC-SHA256",
            "kdf_iterations": 600000,
            "salt": base64.b64encode(self.salt).decode('utf-8')
        }


def create_encryption_service(
    master_key: str,
    key_version: int = 1,
    salt: Optional[str] = None
) -> EncryptionService:
    """
    Factory function to create an encryption service.

    Args:
        master_key: Master encryption key
        key_version: Current key version
        salt: Base64-encoded salt (optional)

    Returns:
        Configured EncryptionService instance
    """
    salt_bytes = base64.b64decode(salt) if salt else None
    return EncryptionService(
        master_key=master_key,
        key_version=key_version,
        salt=salt_bytes
    )
