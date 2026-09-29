"""NIC e-Invoice 1.04 crypto. No network."""

import base64
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from core.exceptions import BusinessRuleError
from core.services.gsp_adapters import wrap_irp_payload
from core.services.nic_irp_crypto import (
    aes_ecb_decrypt,
    aes_ecb_encrypt,
    nic_auth_fields,
    rsa_encrypt_pkcs1v15,
    sek_bytes,
    wrap_nic_invoice_data,
)


def _keypair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private, public_pem


def test_aes_round_trip_and_nic_data_envelope():
    key = b"0123456789abcdef0123456789abcdef"
    blob = aes_ecb_encrypt(b"invoice-json", key)
    assert aes_ecb_decrypt(blob, key) == b"invoice-json"
    wrapped = wrap_nic_invoice_data({"DocDtls": {"No": "1"}}, key)
    raw = aes_ecb_decrypt(base64.b64decode(wrapped["Data"]), key)
    assert json.loads(raw)["DocDtls"]["No"] == "1"
    assert wrapped["encryption"].startswith("nic-einvoice-1.04")


def test_rsa_auth_fields_decrypt_with_the_private_key():
    private, public_pem = _keypair()
    app_key = b"0123456789abcdef0123456789abcdef"
    fields = nic_auth_fields(username="user", password="secret", app_key=app_key, public_pem=public_pem)
    assert fields["UserName"] == "user"
    assert private.decrypt(base64.b64decode(fields["AppKey"]), padding.PKCS1v15()) == app_key
    assert sek_bytes(base64.b64encode(app_key).decode()) == app_key


def test_custom_wrap_refuses_without_sek_and_encrypts_with_one():
    try:
        wrap_irp_payload({"a": 1}, company=None, creds={})
    except BusinessRuleError as exc:
        assert "SEK" in str(exc)
    else:
        raise AssertionError("missing SEK must refuse")
    key = b"0123456789abcdef0123456789abcdef"
    wrapped = wrap_irp_payload({"a": 1}, company=None, creds={"sek": base64.b64encode(key).decode()})
    plain = aes_ecb_decrypt(base64.b64decode(wrapped["Data"]), key)
    assert json.loads(plain) == {"a": 1}


def test_rsa_encrypt_pkcs1v15_is_not_plaintext():
    _private, public_pem = _keypair()
    cipher = rsa_encrypt_pkcs1v15(b"password", public_pem)
    assert b"password" not in cipher
