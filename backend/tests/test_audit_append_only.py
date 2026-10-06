"""AuditEvent is append-only and hash-chained (F-SEC-03)."""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection, transaction

from core.audit_guard import AuditImmutableError, audit_maintenance
from core.models import AuditEvent
from core.services import audit_chain
from core.services.audit import AuditService

pytestmark = pytest.mark.django_db


def _log(company, user, n=1, prefix="e"):
    return [
        AuditService.log(company=company, user=user, action="CREATE", entity_type="Invoice",
                         entity_id=f"{prefix}{i}", description=f"{prefix} {i}", metadata={"i": i})
        for i in range(n)
    ]


# --- layer 1: model / queryset guard ---------------------------------------------

def test_create_is_allowed(tenant_a):
    (ev,) = _log(tenant_a.company, tenant_a.owner)
    assert AuditEvent.objects.filter(pk=ev.pk).exists()


def test_bulk_create_is_allowed(tenant_a):
    AuditEvent.objects.bulk_create([AuditEvent(company=tenant_a.company, action="LOGIN") for _ in range(3)])
    assert AuditEvent.objects.filter(company=tenant_a.company).count() == 3


def test_saving_an_existing_event_is_refused(tenant_a):
    (ev,) = _log(tenant_a.company, tenant_a.owner)
    ev.description = "edited"
    with pytest.raises(AuditImmutableError):
        ev.save()
    assert AuditEvent.objects.get(pk=ev.pk).description != "edited"


def test_deleting_is_refused_on_instance_and_queryset(tenant_a):
    (ev,) = _log(tenant_a.company, tenant_a.owner)
    with pytest.raises(AuditImmutableError):
        ev.delete()
    with pytest.raises(AuditImmutableError):
        AuditEvent.objects.filter(pk=ev.pk).delete()
    with pytest.raises(AuditImmutableError):
        AuditEvent.objects.filter(pk=ev.pk).update(description="x")
    with pytest.raises(AuditImmutableError):
        AuditEvent.objects.bulk_update([ev], ["description"])
    assert AuditEvent.objects.filter(pk=ev.pk).exists()


def test_maintenance_context_allows_and_then_closes(tenant_a):
    (ev,) = _log(tenant_a.company, tenant_a.owner)
    with audit_maintenance("test"):
        AuditEvent.objects.filter(pk=ev.pk).update(description="allowed")
    assert AuditEvent.objects.get(pk=ev.pk).description == "allowed"
    with pytest.raises(AuditImmutableError):
        AuditEvent.objects.filter(pk=ev.pk).update(description="again")


def test_maintenance_requires_a_reason():
    with pytest.raises(ValueError):
        with audit_maintenance(""):
            pass


def _extra_user(tenant, email):
    from accounts.models import CompanyUser, User

    extra = User.objects.create_user(email=email, password="StrongPass123!", full_name="Gone")
    CompanyUser.objects.create(company=tenant.company, user=extra, role=CompanyUser.Role.SALES_STAFF)
    return extra


def test_user_deletion_still_works_and_keeps_the_event(tenant_a):
    """FK SET_NULL on user must not be blocked by the guard."""
    from accounts.models import CompanyUser

    extra = _extra_user(tenant_a, "gone@alpha.test")
    (ev,) = _log(tenant_a.company, extra)
    CompanyUser.objects.filter(user=extra).delete()
    extra.delete()
    ev.refresh_from_db()
    assert ev.user_id is None


# --- layer 3: hash chain ----------------------------------------------------------

def test_seal_assigns_a_contiguous_chain_and_verifies(tenant_a):
    _log(tenant_a.company, tenant_a.owner, 5)
    assert audit_chain.seal(tenant_a.company.id) == 5
    rows = list(AuditEvent.objects.filter(company=tenant_a.company).order_by("chain_seq"))
    assert [r.chain_seq for r in rows] == [1, 2, 3, 4, 5]
    assert rows[0].chain_prev == ""
    assert all(rows[i].chain_prev == rows[i - 1].chain_hash for i in range(1, 5))
    assert audit_chain.verify(tenant_a.company.id).ok


def test_seal_is_idempotent_and_continues_the_chain(tenant_a):
    _log(tenant_a.company, tenant_a.owner, 2, "a")
    audit_chain.seal(tenant_a.company.id)
    assert audit_chain.seal(tenant_a.company.id) == 0
    _log(tenant_a.company, tenant_a.owner, 2, "b")
    assert audit_chain.seal(tenant_a.company.id) == 2
    seqs = list(
        AuditEvent.objects.filter(company=tenant_a.company).order_by("chain_seq").values_list("chain_seq", flat=True)
    )
    assert seqs == [1, 2, 3, 4]
    assert audit_chain.verify(tenant_a.company.id).ok


def test_unsealed_events_do_not_break_verification(tenant_a):
    _log(tenant_a.company, tenant_a.owner, 2)
    audit_chain.seal(tenant_a.company.id)
    _log(tenant_a.company, tenant_a.owner, 3, "late")
    res = audit_chain.verify(tenant_a.company.id)
    assert res.ok and res.checked == 2


def test_editing_a_sealed_event_is_detected(tenant_a):
    evs = _log(tenant_a.company, tenant_a.owner, 4)
    audit_chain.seal(tenant_a.company.id)
    with audit_maintenance("tamper test"):
        AuditEvent.objects.filter(pk=evs[1].pk).update(description="I never approved that payment")
    res = audit_chain.verify(tenant_a.company.id)
    assert not res.ok
    assert any("content hash mismatch" in p and f"id={evs[1].pk}" in p for p in res.problems)


def test_deleting_a_sealed_event_is_detected(tenant_a):
    evs = _log(tenant_a.company, tenant_a.owner, 4)
    audit_chain.seal(tenant_a.company.id)
    with audit_maintenance("tamper test"):
        AuditEvent.objects.filter(pk=evs[2].pk).delete()
    res = audit_chain.verify(tenant_a.company.id)
    assert not res.ok
    assert any("missing or reordered" in p for p in res.problems)
    assert any("chain_prev does not match" in p for p in res.problems)


def test_tail_truncation_needs_an_external_hash(tenant_a):
    """Documented limit: removing the LAST sealed event leaves a self-consistent shorter
    chain. Only an archived copy of the latest hash (ops) can reveal it."""
    evs = _log(tenant_a.company, tenant_a.owner, 3)
    audit_chain.seal(tenant_a.company.id)
    tail_hash = AuditEvent.objects.get(pk=evs[2].pk).chain_hash
    with audit_maintenance("tamper test"):
        AuditEvent.objects.filter(pk=evs[2].pk).delete()
    assert audit_chain.verify(tenant_a.company.id).ok
    latest = AuditEvent.objects.filter(company=tenant_a.company).order_by("-chain_seq").first()
    assert latest.chain_hash != tail_hash  # an offsite copy of the old tail hash would expose it


def test_new_events_are_sealed_after_earlier_ones_regardless_of_id(tenant_a):
    _log(tenant_a.company, tenant_a.owner, 2)
    audit_chain.seal(tenant_a.company.id)
    (third,) = _log(tenant_a.company, tenant_a.owner, 1, "third")
    audit_chain.seal(tenant_a.company.id)
    seqs = dict(AuditEvent.objects.filter(company=tenant_a.company).values_list("pk", "chain_seq"))
    assert seqs[third.pk] == max(seqs.values()) == 3
    assert audit_chain.verify(tenant_a.company.id).ok


def test_chain_survives_user_deletion(tenant_a):
    """user_id is not part of the hash, so erasing a user must not look like tampering."""
    from accounts.models import CompanyUser

    extra = _extra_user(tenant_a, "gone2@alpha.test")
    _log(tenant_a.company, extra, 2)
    audit_chain.seal(tenant_a.company.id)
    CompanyUser.objects.filter(user=extra).delete()
    extra.delete()
    assert audit_chain.verify(tenant_a.company.id).ok


def test_chains_are_per_company(tenant_a, tenant_b):
    _log(tenant_a.company, tenant_a.owner, 2)
    _log(tenant_b.company, tenant_b.owner, 3)
    audit_chain.seal(tenant_a.company.id)
    audit_chain.seal(tenant_b.company.id)
    a = AuditEvent.objects.filter(company=tenant_a.company).values_list("chain_seq", flat=True)
    b = AuditEvent.objects.filter(company=tenant_b.company).values_list("chain_seq", flat=True)
    assert sorted(a) == [1, 2] and sorted(b) == [1, 2, 3]
    assert audit_chain.verify(all_companies=True).ok


def test_management_commands(tenant_a):
    _log(tenant_a.company, tenant_a.owner, 3)
    call_command("seal_audit_chain")
    call_command("verify_audit_chain")
    ev = AuditEvent.objects.filter(company=tenant_a.company).first()
    with audit_maintenance("tamper test"):
        AuditEvent.objects.filter(pk=ev.pk).update(entity_id="forged")
    with pytest.raises(CommandError, match="FAILED"):
        call_command("verify_audit_chain")


def test_nightly_task_seals_and_reports(tenant_a):
    from core.tasks import seal_audit_chain_task

    _log(tenant_a.company, tenant_a.owner, 2)
    out = seal_audit_chain_task()
    assert out["sealed"] >= 2 and out["problems"] == 0


# --- layer 2: Postgres trigger (CI runs Postgres; skipped on SQLite) ---------------

pg = pytest.mark.skipif(connection.vendor != "postgresql", reason="Postgres trigger")


@pg
def test_trigger_blocks_raw_update_and_delete(tenant_a):
    (ev,) = _log(tenant_a.company, tenant_a.owner)
    with pytest.raises(DatabaseError, match="append-only"):
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("UPDATE core_auditevent SET description = 'x' WHERE id = %s", [ev.pk])
    with pytest.raises(DatabaseError, match="append-only"):
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("DELETE FROM core_auditevent WHERE id = %s", [ev.pk])
    assert AuditEvent.objects.filter(pk=ev.pk).exists()


@pg
def test_trigger_allows_user_null_and_first_seal_only(tenant_a):
    (ev,) = _log(tenant_a.company, tenant_a.owner)
    with connection.cursor() as cur:
        cur.execute("UPDATE core_auditevent SET user_id = NULL WHERE id = %s", [ev.pk])  # (a)
    audit_chain.seal(tenant_a.company.id)                                                 # (b)
    with pytest.raises(DatabaseError, match="append-only"):
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("UPDATE core_auditevent SET chain_hash = 'forged' WHERE id = %s", [ev.pk])


@pg
def test_trigger_allows_maintenance_and_resets_the_flag(tenant_a):
    (ev,) = _log(tenant_a.company, tenant_a.owner)
    with audit_maintenance("trigger test"):
        with connection.cursor() as cur:
            cur.execute("DELETE FROM core_auditevent WHERE id = %s", [ev.pk])
    (ev2,) = _log(tenant_a.company, tenant_a.owner, 1, "after")
    with pytest.raises(DatabaseError, match="append-only"):
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("DELETE FROM core_auditevent WHERE id = %s", [ev2.pk])
