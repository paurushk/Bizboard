"""NIC e-Invoice API 1.04 payload crypto for the custom GSP provider.

Published envelope (e-Invoice API version 1.04):

- The AppKey and password are RSA-encrypted with the IRP public key
  (PKCS#1 v1.5) during auth.
- The auth response SEK is AES-encrypted under that AppKey.
- The invoice JSON sent as ``{"Data": "<base64>"}`` is AES-256-ECB with
  PKCS7 padding under the decrypted SEK.

ECB is the envelope NIC publishes for this API. It is not a general-purpose
cipher choice. The SEK lives in the company's existing encrypted GSP
credential blob under the key ``sek`` (base64 of the raw AES key). Replacing
that blob is how the key rotates. This module does not call NIC and does not
read ``GSP_LIVE_ENABLED`` or ``GSP_CERTIFIED``.
"""

from __future__ import annotations

import base64
import json

from cryptography.hazmat.primitives import padding, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

NIC_EINVOICE_API_VERSION = "1.04"
_AES_BLOCK = 128


def sek_bytes(value: str | bytes | None) -> bytes | None:
    """Accept a raw 32-byte key, a 32-character ASCII key, or base64 of a
    16/24/32-byte key.

    Base64 of a 16- or 24-byte key is itself exactly 24 or 32 characters
    long, which collides with a literal raw key of that same length --
    32 is the only length whose base64 form (44 chars) cannot collide with
    the literal form, so it's the only length treated as a literal key.
    Everything else is decoded as base64.
    """
    if value is None:
        return None
    if isinstance(value, bytes):
        raw = value
    else:
        text = str(value).strip()
        if not text:
            return None
        if len(text) == 32:
            raw = text.encode("utf-8")
        else:
            try:
                raw = base64.b64decode(text, validate=True)
            except Exception:
                return None
    if len(raw) not in (16, 24, 32):
        return None
    return raw


def aes_ecb_encrypt(plaintext: bytes, key: bytes) -> bytes:
    padder = padding.PKCS7(_AES_BLOCK).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()  # noqa: S305 — ECB is the envelope NIC's e-Invoice API 1.04 publishes
    return encryptor.update(padded) + encryptor.finalize()


def aes_ecb_decrypt(ciphertext: bytes, key: bytes) -> bytes:
    decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()  # noqa: S305 — ECB is the envelope NIC's e-Invoice API 1.04 publishes
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(_AES_BLOCK).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def rsa_encrypt_pkcs1v15(plaintext: bytes, public_pem: bytes) -> bytes:
    key = serialization.load_pem_public_key(public_pem)
    return key.encrypt(plaintext, asym_padding.PKCS1v15())


def wrap_nic_invoice_data(payload: dict, sek: bytes) -> dict:
    raw = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    token = base64.b64encode(aes_ecb_encrypt(raw, sek)).decode("ascii")
    return {"Data": token, "encryption": f"nic-einvoice-{NIC_EINVOICE_API_VERSION}-aes-256-ecb"}


def nic_auth_fields(*, username: str, password: str, app_key: bytes, public_pem: bytes) -> dict:
    """Auth request fields. Password and AppKey are RSA-wrapped, then base64."""
    return {
        "UserName": username,
        "Password": base64.b64encode(rsa_encrypt_pkcs1v15(password.encode("utf-8"), public_pem)).decode("ascii"),
        "AppKey": base64.b64encode(rsa_encrypt_pkcs1v15(app_key, public_pem)).decode("ascii"),
        "ForceRefreshAccessToken": False,
    }
