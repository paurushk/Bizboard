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


class ReBITClient:
    """INTG-01: the real Account-Aggregator / ReBIT FI-data flow *shape*.

    The current `fetch_live_transactions_for_consent` above is a thin proxy call.
    A production AA integration is the ReBIT FI request/fetch handshake:

        1.  POST {base}/Consent            -> consent handle
        2.  GET  {base}/Consent/handle/{h} -> consent artefact (signed)
        3.  POST {base}/FI/request         -> {sessionId}  (with a fresh
                                              X25519 keypair + nonce in
                                              KeyMaterial for the FIP to
                                              ECDH-derive the data key)
        4.  GET  {base}/FI/fetch/{sessionId}
        5.  For each encryptedFI: ECDH(our_priv, remote_KeyMaterial.pub) ->
            HKDF -> AES-GCM decrypt -> parse the FI XML/JSON.

    The transport calls are implemented fail-closed; the crypto in
    `decrypt_fi_payload` is intentionally left unimplemented so nobody ships
    unreviewed key-exchange code. Wire an audited X25519/HKDF/AES-GCM
    implementation and validate against a live Sahamati sandbox before
    enabling this path.
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

    def request_fi_data(self, *, consent_id: str, from_ts: str, to_ts: str) -> str:
        """Step 3 — returns the FI sessionId. KeyMaterial generation belongs
        here once the crypto lib is wired."""
        resp = self._post(
            "/FI/request",
            {
                "ver": "2.0.0",
                "Consent": {"id": consent_id},
                "FIDataRange": {"from": from_ts, "to": to_ts},
            },
        )
        session_id = str(resp.get("sessionId") or "")
        if not session_id:
            raise self._BusinessRuleError("AA/ReBIT FI/request returned no sessionId.")
        return session_id

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

    def decrypt_fi_payload(self, *, encrypted_fi: dict, our_private_key: bytes) -> str:
        """Step 5 — X25519 ECDH -> HKDF -> AES-GCM. Deliberately not
        implemented: shipping unreviewed key-exchange code is worse than a
        clear failure. See the class docstring."""
        raise NotImplementedError(
            "AA FI-data decryption requires an audited X25519/HKDF/AES-GCM "
            "implementation validated against a live AA sandbox."
        )
