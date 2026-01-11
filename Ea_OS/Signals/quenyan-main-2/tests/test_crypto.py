import base64
from dataclasses import replace

import pytest
from hypothesis import given, strategies as st
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from qyn1.crypto import (
    CURRENT_ENCRYPTION_VERSION,
    EncryptionResult,
    decrypt,
    encrypt,
)


RFC_KEY = bytes.fromhex("1c9240a5eb55d38af333888604f6b5f0473917c1402b80099dca5cbc207075c0")
RFC_NONCE = bytes.fromhex("000000000102030405060708")
RFC_AAD = bytes.fromhex("f33388860000000000004e91")
RFC_PLAINTEXT = (
    b"Ladies and Gentlemen of the class of '99: If I could offer you only one tip for the future, "
    b"sunscreen would be it."
)
RFC_CIPHERTEXT = bytes.fromhex(
    "d31a8d34648e60db7b86afbc53ef7ec2a4aded51296e08fea9e2b5a736ee62d6"
    "3dbea45e8ca9671282fafb69da92728b1a71de0a9e0609f"
)
RFC_TAG = bytes.fromhex("1ae10b594f09e26a7e902ecbd0600691")


def test_rfc7539_vector_matches_chacha20_poly1305_reference() -> None:
    cipher = ChaCha20Poly1305(RFC_KEY)
    combined = cipher.encrypt(RFC_NONCE, RFC_PLAINTEXT, RFC_AAD)
    assert combined[:-16] == RFC_CIPHERTEXT
    assert combined[-16:] == RFC_TAG
    decrypted = cipher.decrypt(RFC_NONCE, RFC_CIPHERTEXT + RFC_TAG, RFC_AAD)
    assert decrypted == RFC_PLAINTEXT


@given(
    plaintext=st.binary(min_size=0, max_size=256),
    aad=st.binary(min_size=0, max_size=64),
)
@pytest.mark.property
def test_encrypt_decrypt_round_trip_with_associated_data(
    plaintext: bytes, aad: bytes
) -> None:
    result = encrypt(plaintext, "property-passphrase", aad)
    assert decrypt(result, "property-passphrase", aad) == plaintext
    with pytest.raises(ValueError):
        decrypt(result, "wrong-passphrase", aad)
    if aad:
        with pytest.raises(ValueError):
            decrypt(result, "property-passphrase", aad + b"!")  # tag must cover AAD


def test_corrupted_tag_and_nonce_are_rejected() -> None:
    aad = b"qyn1-associated-data"
    result = encrypt(b"payload", "nonce-guard", aad)
    with pytest.raises(ValueError):
        decrypt(replace(result, tag=b"\x00" * len(result.tag)), "nonce-guard", aad)
    with pytest.raises(ValueError):
        decrypt(
            replace(result, nonce=bytes(reversed(result.nonce))),
            "nonce-guard",
            aad,
        )


def test_encryption_result_metadata_serialises() -> None:
    """Guard against regressions when persisting encryption metadata."""

    result = encrypt(b"payload", "metadata-pass", b"meta")
    payload = base64.b64encode(result.ciphertext).decode("ascii")
    assert result.version == CURRENT_ENCRYPTION_VERSION
    assert result.kdf == "argon2id"
    assert result.aead == "chacha20poly1305"
    assert isinstance(result.kdf_parameters, dict)
    assert payload.startswith(tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"))
