"""WP-H5 (DPDP): record and check acceptance of the Terms, Privacy Policy and DPA.

Everyone accepts the current ``TOS`` and ``PRIVACY`` versions; a company owner also accepts the
``DPA`` for that company. Versions live in ``settings.LEGAL_DOCUMENT_VERSIONS``: bumping one makes
``pending`` return it again, and the web app asks the person to accept before going on.
"""

from __future__ import annotations

import hashlib

from django.conf import settings

PERSONAL = ("TOS", "PRIVACY")


def current_versions() -> dict[str, str]:
    return dict(getattr(settings, "LEGAL_DOCUMENT_VERSIONS", {}) or {})


def required_documents(user, company_user=None) -> list[tuple[str, int | None]]:
    """(document, company_id or None) pairs this person must have accepted."""
    docs: list[tuple[str, int | None]] = [(d, None) for d in PERSONAL]
    if company_user is not None and getattr(company_user, "role", "") == "OWNER":
        docs.append(("DPA", company_user.company_id))
    return docs


def pending(user, company_user=None) -> list[dict]:
    """Documents (with their current version) this person has not accepted yet."""
    from accounts.models import LegalAcceptance

    if not getattr(settings, "LEGAL_ACCEPTANCE_REQUIRED", True) or user is None or not user.is_authenticated:
        return []
    versions = current_versions()
    out = []
    for document, company_id in required_documents(user, company_user):
        version = versions.get(document)
        if not version:
            continue
        qs = LegalAcceptance.objects.filter(user=user, document=document, version=version)
        if company_id is not None:
            qs = qs.filter(company_id=company_id)
        if not qs.exists():
            out.append({"document": document, "version": version, "company_id": company_id})
    return out


def _ip_hash(request) -> str:
    from core.observability import current_client_ip

    ip = current_client_ip() if request is not None else ""
    return hashlib.sha256(f"legal|{ip}".encode()).hexdigest() if ip else ""


def record(user, documents, *, request=None, company_id=None) -> list:
    """Record acceptance of the current version of each document. Unknown documents are ignored."""
    from accounts.models import LegalAcceptance

    versions = current_versions()
    agent = ((request.META.get("HTTP_USER_AGENT") if request is not None else "") or "")[:255]
    rows = []
    for document in documents:
        version = versions.get(document)
        if not version:
            continue
        rows.append(LegalAcceptance.objects.create(
            user=user, document=document, version=version,
            company_id=company_id if document == "DPA" else None,
            ip_hash=_ip_hash(request), user_agent=agent,
        ))
    return rows
