"""INTG-01: ReBIT FI-data crypto round-trip (X25519 ECDH -> HKDF -> AES-256-GCM)."""

from __future__ import annotations

import base64

import pytest

from banking.fiu_adapter import (
    decrypt_fi_data,
    encrypt_fi_data,
    generate_key_material,
)
from core.exceptions import BusinessRuleError


def test_key_material_shape():
    km = generate_key_material()
    assert set(km) == {"private", "public", "nonce"}
    assert len(base64.b64decode(km["private"])) == 32
    assert len(base64.b64decode(km["public"])) == 32
    assert len(base64.b64decode(km["nonce"])) == 32


def test_fip_encrypt_fiu_decrypt_round_trip():
    """The FIU and a simulated FIP each generate KeyMaterial, exchange public
    keys + nonces, and must derive the same AES key."""
    fiu = generate_key_material()
    fip = generate_key_material()
    plaintext = '{"Account":{"Transactions":[{"amount":"1500.00","type":"CREDIT"}]}}'

    # FIP encrypts toward the FIU (its private + FIU's public/nonce).
    cipher = encrypt_fi_data(
        plaintext=plaintext,
        our_private_b64=fip["private"],
        remote_public_b64=fiu["public"],
        our_nonce_b64=fip["nonce"],
        remote_nonce_b64=fiu["nonce"],
    )
    assert cipher != plaintext

    # FIU decrypts (its private + FIP's public/nonce) — symmetric ECDH.
    recovered = decrypt_fi_data(
        encrypted_b64=cipher,
        our_private_b64=fiu["private"],
        remote_public_b64=fip["public"],
        our_nonce_b64=fiu["nonce"],
        remote_nonce_b64=fip["nonce"],
    )
    assert recovered == plaintext


def test_wrong_key_fails_closed():
    fiu = generate_key_material()
    fip = generate_key_material()
    attacker = generate_key_material()
    cipher = encrypt_fi_data(
        plaintext="secret",
        our_private_b64=fip["private"],
        remote_public_b64=fiu["public"],
        our_nonce_b64=fip["nonce"],
        remote_nonce_b64=fiu["nonce"],
    )
    with pytest.raises(BusinessRuleError):
        decrypt_fi_data(
            encrypted_b64=cipher,
            our_private_b64=attacker["private"],
            remote_public_b64=fip["public"],
            our_nonce_b64=fiu["nonce"],
            remote_nonce_b64=fip["nonce"],
        )
