"""Authenticated encryption helpers for QYN-1 packages."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from hashlib import pbkdf2_hmac
from typing import Dict, Optional

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SALT_SIZE = 16
HKDF_SALT_SIZE = 16
NONCE_SIZE = 12
PBKDF2_ROUNDS = 200_000
CURRENT_ENCRYPTION_VERSION = 2
DEFAULT_KDF = "argon2id"
DEFAULT_AEAD = "chacha20poly1305"
ARGON2_PARAMETERS: Dict[str, int] = {
    "time_cost": 4,
    "memory_cost": 64 * 1024,
    "parallelism": 4,
    "hash_len": 32,
}
HKDF_INFO = b"qyn1-envelope:v2"


@dataclass
class EncryptionResult:
    nonce: bytes
    salt: bytes
    ciphertext: bytes
    tag: bytes
    hkdf_salt: Optional[bytes] = None
    version: int = CURRENT_ENCRYPTION_VERSION
    aead: str = DEFAULT_AEAD
    kdf: str = DEFAULT_KDF
    kdf_parameters: Dict[str, int] = field(
        default_factory=lambda: dict(ARGON2_PARAMETERS)
    )


def _zeroize(buffer: bytearray) -> None:
    for index in range(len(buffer)):
        buffer[index] = 0


def _derive_argon2id(passphrase: str, salt: bytes, params: Dict[str, int]) -> bytearray:
    if not passphrase:
        raise ValueError("passphrase must be non-empty")
    key = hash_secret_raw(
        secret=passphrase.encode("utf-8"),
        salt=salt,
        time_cost=params["time_cost"],
        memory_cost=params["memory_cost"],
        parallelism=params["parallelism"],
        hash_len=params["hash_len"],
        type=Type.ID,
    )
    return bytearray(key)


def _derive_pbkdf2(passphrase: str, salt: bytes) -> bytearray:
    if not passphrase:
        raise ValueError("passphrase must be non-empty")
    key = pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, PBKDF2_ROUNDS, 32)
    return bytearray(key)


def _derive_hkdf(key_material: bytearray, salt: bytes) -> bytearray:
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=HKDF_INFO)
    derived = hkdf.derive(bytes(key_material))
    return bytearray(derived)


def encrypt(
    plaintext: bytes,
    passphrase: str,
    associated_data: Optional[bytes] = None,
    *,
    version: int = CURRENT_ENCRYPTION_VERSION,
) -> EncryptionResult:
    associated = associated_data or b""
    if version not in {1, CURRENT_ENCRYPTION_VERSION}:
        raise ValueError(f"Unsupported encryption version {version}")
    if version == 1:
        return _encrypt_legacy(plaintext, passphrase, associated)

    salt = os.urandom(SALT_SIZE)
    hkdf_salt = os.urandom(HKDF_SALT_SIZE)
    nonce = os.urandom(NONCE_SIZE)
    kdf_parameters = dict(ARGON2_PARAMETERS)
    master_key = _derive_argon2id(passphrase, salt, kdf_parameters)
    encryption_key = _derive_hkdf(master_key, hkdf_salt)
    try:
        cipher = ChaCha20Poly1305(bytes(encryption_key))
        ciphertext_with_tag = cipher.encrypt(nonce, plaintext, associated)
    finally:
        _zeroize(master_key)
        _zeroize(encryption_key)
    return EncryptionResult(
        nonce=nonce,
        salt=salt,
        hkdf_salt=hkdf_salt,
        ciphertext=ciphertext_with_tag[:-16],
        tag=ciphertext_with_tag[-16:],
        version=CURRENT_ENCRYPTION_VERSION,
        aead=DEFAULT_AEAD,
        kdf=DEFAULT_KDF,
        kdf_parameters=kdf_parameters,
    )


def decrypt(
    result: EncryptionResult,
    passphrase: str,
    associated_data: Optional[bytes] = None,
) -> bytes:
    associated = associated_data or b""
    if result.version == 1:
        return _decrypt_legacy(result, passphrase, associated)
    if result.version != CURRENT_ENCRYPTION_VERSION:
        raise ValueError(f"Unsupported encryption version {result.version}")
    if result.aead != DEFAULT_AEAD:
        raise ValueError(f"Unsupported AEAD algorithm '{result.aead}'")
    if result.kdf != DEFAULT_KDF:
        raise ValueError(f"Unsupported KDF '{result.kdf}'")

    hkdf_salt = result.hkdf_salt or result.salt
    kdf_parameters = dict(ARGON2_PARAMETERS)
    kdf_parameters.update(result.kdf_parameters)
    master_key = _derive_argon2id(passphrase, result.salt, kdf_parameters)
    encryption_key = _derive_hkdf(master_key, hkdf_salt)
    try:
        cipher = ChaCha20Poly1305(bytes(encryption_key))
        return cipher.decrypt(
            result.nonce,
            result.ciphertext + result.tag,
            associated,
        )
    except InvalidTag as exc:  # pragma: no cover - exercised in tests
        raise ValueError("authentication tag mismatch") from exc
    finally:
        _zeroize(master_key)
        _zeroize(encryption_key)


def _encrypt_legacy(plaintext: bytes, passphrase: str, associated: bytes) -> EncryptionResult:
    salt = os.urandom(SALT_SIZE)
    nonce = os.urandom(NONCE_SIZE)
    key = _derive_pbkdf2(passphrase, salt)
    try:
        cipher = ChaCha20Poly1305(bytes(key))
        ciphertext_with_tag = cipher.encrypt(nonce, plaintext, associated)
    finally:
        _zeroize(key)
    return EncryptionResult(
        nonce=nonce,
        salt=salt,
        ciphertext=ciphertext_with_tag[:-16],
        tag=ciphertext_with_tag[-16:],
        version=1,
        aead=DEFAULT_AEAD,
        kdf="pbkdf2",
        kdf_parameters={"rounds": PBKDF2_ROUNDS},
    )


def _decrypt_legacy(result: EncryptionResult, passphrase: str, associated: bytes) -> bytes:
    key = _derive_pbkdf2(passphrase, result.salt)
    try:
        cipher = ChaCha20Poly1305(bytes(key))
        return cipher.decrypt(result.nonce, result.ciphertext + result.tag, associated)
    except InvalidTag as exc:  # pragma: no cover - exercised in tests
        raise ValueError("authentication tag mismatch") from exc
    finally:
        _zeroize(key)
