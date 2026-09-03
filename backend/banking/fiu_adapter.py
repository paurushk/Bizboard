"""FIU adapter for Account Aggregator ingest.

Mock path is allowlisted in views (dev/test/local only). Live HTTP is fail-closed
without FIU_BASE_URL and never invents rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from django.utils import timezone


@dataclass
class MockFiTransaction:
    txn_id: str
    amount: Decimal
    txn_date: date
    narration: str
    raw: dict[str, Any]


def fetch_transactions_for_consent(*, consent_id: str, fi_type: str) -> list[MockFiTransaction]:
    """Return deterministic mock transactions for local/dev AA ingest."""
    suffix = consent_id[-4:] if consent_id else "0000"
    return [
        MockFiTransaction(
            txn_id=f"aa-mock-{suffix}-001",
            amount=Decimal("1500.00"),
            txn_date=timezone.localdate(),
            narration="UPI/CR/MOCK CUSTOMER",
            raw={"mode": "UPI", "fi_type": fi_type, "consent_id": consent_id},
        ),
        MockFiTransaction(
            txn_id=f"aa-mock-{suffix}-002",
            amount=Decimal("2500.50"),
            txn_date=timezone.localdate(),
            narration="NEFT/CR/MOCK CUSTOMER",
            raw={"mode": "NEFT", "fi_type": fi_type, "consent_id": consent_id},
        ),
    ]


def fetch_live_transactions_for_consent(*, consent_id: str, fi_type: str) -> list[MockFiTransaction]:
    """HTTP FIU fetch. Raises BusinessRuleError when unset or the FIU fails."""
    import json
    import urllib.error
    import urllib.request

    from django.conf import settings

    from core.exceptions import BusinessRuleError

    base = (getattr(settings, "FIU_BASE_URL", "") or "").rstrip("/")
    api_key = (getattr(settings, "FIU_API_KEY", "") or "").strip()
    if not base:
        raise BusinessRuleError("Live AA ingest is fail-closed: FIU_BASE_URL is not configured.")
    if not api_key:
        raise BusinessRuleError("Live AA ingest is fail-closed: FIU_API_KEY is not configured.")
    try:
        req = urllib.request.Request(
            f"{base}/consents/{consent_id}/transactions?fi_type={fi_type}",
            method="GET",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode("utf-8") or "{}")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        raise BusinessRuleError("Live AA FIU fetch failed closed.") from exc

    rows = payload.get("transactions") or payload.get("data") or []
    out: list[MockFiTransaction] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        txn_id = str(row.get("txn_id") or row.get("id") or "").strip()
        if not txn_id:
            continue
        txn_date = timezone.localdate()
        raw_date = str(row.get("txn_date") or row.get("date") or "")
        if raw_date:
            try:
                txn_date = date.fromisoformat(raw_date[:10])
            except ValueError:
                pass
        out.append(
            MockFiTransaction(
                txn_id=txn_id,
                amount=Decimal(str(row.get("amount") or "0")),
                txn_date=txn_date,
                narration=str(row.get("narration") or ""),
                raw={"fi_type": fi_type, "consent_id": consent_id, **row},
            )
        )
    return out


def generate_key_material() -> dict[str, str]:
    """ReBIT step 3 — a fresh X25519 keypair + 32-byte nonce for one FI request.

    Returns base64 strings: ``private`` (keep — never send), ``public`` and
    ``nonce`` (send in the FI/request KeyMaterial). The FIP mirrors this and the
    two sides ECDH to the same AES key.
    """
    import base64

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

    priv = X25519PrivateKey.generate()
    priv_raw = priv.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    pub_raw = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    nonce = _os_urandom(32)
    b64 = lambda b: base64.b64encode(b).decode("ascii")  # noqa: E731
    return {"private": b64(priv_raw), "public": b64(pub_raw), "nonce": b64(nonce)}


def _os_urandom(n: int) -> bytes:
    import os

    return os.urandom(n)


def _rebit_session_key(*, our_private_b64: str, remote_public_b64: str,
                       our_nonce_b64: str, remote_nonce_b64: str) -> tuple[bytes, bytes]:
    """ECDH(X25519) -> HKDF-SHA256 -> (AES-256 key, 12-byte GCM nonce).

    Matches the Sahamati / ReBIT ``ecc-crypto`` scheme: HKDF salt is the XOR of
    the two 32-byte nonces, info is empty, and the AES-GCM IV is the trailing 12
    bytes of that XOR. If a specific aggregator diverges, only this function
    needs tuning.
    """
    import base64

    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric.x25519 import (
        X25519PrivateKey,
        X25519PublicKey,
    )
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    priv = X25519PrivateKey.from_private_bytes(base64.b64decode(our_private_b64))
    remote_pub = X25519PublicKey.from_public_bytes(base64.b64decode(remote_public_b64))
    shared = priv.exchange(remote_pub)

    our_nonce = base64.b64decode(our_nonce_b64)
    remote_nonce = base64.b64decode(remote_nonce_b64)
    width = min(len(our_nonce), len(remote_nonce)) or 32
    xor_nonce = bytes(a ^ b for a, b in zip(our_nonce[:width], remote_nonce[:width]))

    key = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=xor_nonce, info=b""
    ).derive(shared)
    iv = xor_nonce[-12:].rjust(12, b"\x00")
    return key, iv


def decrypt_fi_data(*, encrypted_b64: str, our_private_b64: str, remote_public_b64: str,
                    our_nonce_b64: str, remote_nonce_b64: str) -> str:
    """ReBIT step 5 — decrypt one base64 ``encryptedFI`` block to its plaintext
    FI (XML or JSON). The 16-byte GCM tag is appended to the ciphertext."""
    import base64

    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    from core.exceptions import BusinessRuleError

    key, iv = _rebit_session_key(
        our_private_b64=our_private_b64,
        remote_public_b64=remote_public_b64,
        our_nonce_b64=our_nonce_b64,
        remote_nonce_b64=remote_nonce_b64,
    )
    try:
        plaintext = AESGCM(key).decrypt(iv, base64.b64decode(encrypted_b64), None)
    except (InvalidTag, ValueError) as exc:
        raise BusinessRuleError("AA FI-data decryption failed (bad key / tag).") from exc
    return plaintext.decode("utf-8")


def encrypt_fi_data(*, plaintext: str, our_private_b64: str, remote_public_b64: str,
                    our_nonce_b64: str, remote_nonce_b64: str) -> str:
    """FIP-side counterpart of ``decrypt_fi_data`` — used to simulate a FIP push
    end-to-end in tests and local dev."""
    import base64

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key, iv = _rebit_session_key(
        our_private_b64=our_private_b64,
        remote_public_b64=remote_public_b64,
        our_nonce_b64=our_nonce_b64,
        remote_nonce_b64=remote_nonce_b64,
    )
    ct = AESGCM(key).encrypt(iv, plaintext.encode("utf-8"), None)
    return base64.b64encode(ct).decode("ascii")


class ReBITClient:
    """INTG-01: the real Account-Aggregator / ReBIT FI-data flow.

    ``fetch_live_transactions_for_consent`` above is a thin proxy call; this is
    the full ReBIT FI request/fetch handshake:

        1.  POST {base}/Consent            -> consent handle
        2.  GET  {base}/Consent/handle/{h} -> consent artefact (signed)
        3.  POST {base}/FI/request         -> {sessionId}  (KeyMaterial from
                                              ``generate_key_material()``)
        4.  GET  {base}/FI/fetch/{sessionId}
        5.  For each encryptedFI: ``decrypt_fi_data(...)`` (X25519 ECDH ->
            HKDF-SHA256 -> AES-256-GCM) -> parse the FI XML/JSON.

    Transport calls are fail-closed without FIU creds. The crypto
    (``_rebit_session_key`` / ``decrypt_fi_data``) follows the Sahamati
    ``ecc-crypto`` scheme; **still validate the exact HKDF salt / IV derivation
    against your live aggregator's sandbox** before enabling `ENABLE_AA_LIVE`.
    """

    def __init__(self):
        from django.conf import settings

        from core.exceptions import BusinessRuleError

        self._BusinessRuleError = BusinessRuleError
        self.base = (getattr(settings, "FIU_BASE_URL", "") or "").rstrip("/")
        self.api_key = (getattr(settings, "FIU_API_KEY", "") or "").strip()
        if not self.base or not self.api_key:
            raise BusinessRuleError(
                "AA/ReBIT is fail-closed: set FIU_BASE_URL and FIU_API_KEY."
            )

    def _post(self, path: str, body: dict) -> dict:
        import json
        import urllib.error
        import urllib.request

        req = urllib.request.Request(
            f"{self.base}{path}",
            method="POST",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8") or "{}")
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise self._BusinessRuleError("AA/ReBIT call failed closed.") from exc

    def request_fi_data(self, *, consent_id: str, from_ts: str, to_ts: str) -> dict:
        """Step 3 — returns ``{"session_id", "key_material"}``. Keep
        ``key_material["private"]`` for the decrypt step; never transmit it."""
        km = generate_key_material()
        resp = self._post(
            "/FI/request",
            {
                "ver": "2.0.0",
                "Consent": {"id": consent_id},
                "FIDataRange": {"from": from_ts, "to": to_ts},
                "KeyMaterial": {
                    "cryptoAlg": "ECDH",
                    "curve": "Curve25519",
                    "params": "",
                    "DHPublicKey": {
                        "expiry": to_ts,
                        "Parameters": "",
                        "KeyValue": km["public"],
                    },
                    "Nonce": km["nonce"],
                },
            },
        )
        session_id = str(resp.get("sessionId") or "")
        if not session_id:
            raise self._BusinessRuleError("AA/ReBIT FI/request returned no sessionId.")
        return {"session_id": session_id, "key_material": km}

    def fetch_fi_data(self, *, session_id: str) -> dict:
        """Step 4 — the encrypted FI payload envelope."""
        import json
        import urllib.error
        import urllib.request

        req = urllib.request.Request(
            f"{self.base}/FI/fetch/{session_id}",
            method="GET",
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8") or "{}")
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise self._BusinessRuleError("AA/ReBIT FI/fetch failed closed.") from exc

    def decrypt_fi_records(self, *, fi_fetch_response: dict, key_material: dict) -> list[str]:
        """Step 5 — decrypt every ``encryptedFI`` in a FI/fetch response to its
        plaintext FI document, using the KeyMaterial we sent in step 3 and the
        FIP's KeyMaterial echoed back per FI block."""
        out: list[str] = []
        for fi in fi_fetch_response.get("FI") or []:
            fip_km = (fi.get("KeyMaterial") or {})
            remote_public = ((fip_km.get("DHPublicKey") or {}).get("KeyValue")) or ""
            remote_nonce = fip_km.get("Nonce") or ""
            for rec in fi.get("data") or []:
                enc = rec.get("encryptedData") or rec.get("encryptedFI") or ""
                if not enc or not remote_public or not remote_nonce:
                    continue
                out.append(
                    decrypt_fi_data(
                        encrypted_b64=enc,
                        our_private_b64=key_material["private"],
                        remote_public_b64=remote_public,
                        our_nonce_b64=key_material["nonce"],
                        remote_nonce_b64=remote_nonce,
                    )
                )
        return out
