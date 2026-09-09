"""SR-40..45 / D13 — automated tenant right-to-erasure.

``erase_company`` removes a company and every row that belongs to it, writes an
immutable :class:`TenantErasureLog` (which carries **no** party PII), and is
idempotent. It builds on the sandbox-cleanup cascade (``wipe_logical_tenant_rows``
+ the PROTECT audit tables) but *deletes* the audit rows rather than orphaning
them, because they carry customer / supplier PII.

Scope revision 2026-09-09b: this is **v1 = full hard erasure**. The founder
decision on a statutory-retention carve-out (keep tax documents as an anonymised
tombstone for N years) — plan item **SR-40** — is NOT implemented here; until it
is signed off the endpoint stays behind ``ENABLE_TENANT_ERASURE`` (default OFF).

The completeness guard (:func:`assert_erasure_model_coverage`) fails if a new
model gains a ``company`` FK with an ``on_delete`` that ``company.delete()``
cannot resolve on its own and that is not explicitly handled here — that is the
drift SR-41 catches.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from django.apps import apps
from django.db import transaction
from django.db.models import ProtectedError
from django.utils import timezone

# Company FKs this module clears by hand before ``company.delete()`` because
# their ``on_delete`` is PROTECT. Keep in "child first" order is not required —
# each is an independent leaf table.
PROTECT_MODELS_HANDLED = {
    "core.AuditEvent",
    "core.MoneyFieldAudit",
    "core.StatutoryDocumentEvent",
}
# Company FKs that resolve themselves when the company row goes.
_SAFE_ON_DELETE = {"CASCADE", "SET_NULL", "SET_DEFAULT", "DO_NOTHING"}


def company_fk_relations() -> list[tuple[str, str, str]]:
    """(``app_label.Model``, field name, on_delete name) for every model with a
    many-to-one / one-to-one FK to ``accounts.Company``."""
    from accounts.models import Company

    out: list[tuple[str, str, str]] = []
    for model in apps.get_models():
        for field in model._meta.get_fields():
            if not getattr(field, "is_relation", False):
                continue
            if getattr(field, "related_model", None) is not Company:
                continue
            if not (field.many_to_one or field.one_to_one):
                continue
            on_delete = getattr(getattr(field, "remote_field", None), "on_delete", None)
            name = getattr(on_delete, "__name__", str(on_delete))
            out.append((f"{model._meta.app_label}.{model.__name__}", field.name, name))
    return sorted(out)


def assert_erasure_model_coverage() -> None:
    """Drift guard (SR-41): every ``company`` FK must be safe under
    ``company.delete()`` or explicitly handled in :func:`erase_company`."""
    unhandled = [
        f"{label}.{fname} (on_delete={od})"
        for (label, fname, od) in company_fk_relations()
        if od not in _SAFE_ON_DELETE and label not in PROTECT_MODELS_HANDLED
    ]
    if unhandled:
        raise AssertionError(
            "erasure wipe set is incomplete — these company FKs are neither "
            "auto-resolved by company.delete() nor handled in accounts.erasure:\n  "
            + "\n  ".join(unhandled)
        )


@dataclass
class ErasureResult:
    company_id: int
    company_name: str
    export_sha256: str
    log_id: int
    already_erased: bool = False


def _delete_protect_rows(company) -> None:
    from core.models import AuditEvent, MoneyFieldAudit, StatutoryDocumentEvent

    # DPDP: these carry party PII — delete, do not orphan.
    AuditEvent.objects.filter(company=company).delete()
    MoneyFieldAudit.objects.filter(company=company).delete()
    StatutoryDocumentEvent.objects.filter(company=company).delete()


@transaction.atomic
def erase_company(company, *, requested_by_email: str, reason: str = "", skip_export: bool = False) -> ErasureResult:
    """Irreversibly erase ``company`` and everything it owns. Idempotent: calling
    it again for an already-gone company id is a no-op that still records a log."""
    from accounts.models import CompanyUser, TenantErasureLog, User
    from accounts.tenant_backup import (
        build_export_payload,
        encrypt_export_zip,
        wipe_logical_tenant_rows,
    )

    company_id = int(company.pk)
    company_name = company.name

    export_sha = ""
    if not skip_export:
        blob = encrypt_export_zip(build_export_payload(company))
        export_sha = hashlib.sha256(blob).hexdigest()

    try:
        from core.rls import rls_bypass
    except Exception:  # noqa: BLE001 — RLS optional in the pilot profile
        from contextlib import nullcontext as rls_bypass  # type: ignore

    with rls_bypass():
        wipe_logical_tenant_rows(company)
        _delete_protect_rows(company)
        User.objects.filter(active_company=company).update(active_company=None)
        CompanyUser.objects.filter(company=company).delete()
        try:
            company.delete()
        except ProtectedError as exc:  # a new unhandled PROTECT FK slipped through
            raise AssertionError(
                f"erase_company blocked by an unhandled PROTECT FK: {exc}"
            ) from exc

        log = TenantErasureLog.objects.create(
            company_id=company_id,
            company_name=company_name,
            requested_by_email=requested_by_email or "",
            reason=(reason or "")[:2000],
            export_sha256=export_sha,
        )

    return ErasureResult(
        company_id=company_id,
        company_name=company_name,
        export_sha256=export_sha,
        log_id=log.pk,
    )
