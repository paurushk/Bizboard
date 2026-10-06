"""Edge cases for the audit append-only guard and hash chain (F-SEC-03). Complements
test_audit_append_only.py with the paths that legitimately mutate the log and the ones
that must keep working around it."""

from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from core.audit_guard import AuditImmutableError, audit_maintenance, maintenance_active
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


# --- sealing mechanics -----------------------------------------------------------------

def test_sealing_in_small_batches_continues_one_unbroken_chain(tenant_a):
    _log(tenant_a.company, tenant_a.owner, 7)
    assert audit_chain.seal(tenant_a.company.id, batch=2) == 7
    seqs = list(AuditEvent.objects.filter(company=tenant_a.company).order_by("chain_seq").values_list("chain_seq", flat=True))
    assert seqs == list(range(1, 8))
    assert audit_chain.verify(tenant_a.company.id).ok


def test_events_without_a_company_get_their_own_chain(tenant_a):
    AuditService.log(company=None, user=tenant_a.owner, action="LOGIN", entity_type="User", entity_id="1")
    AuditService.log(company=None, user=tenant_a.owner, action="LOGIN", entity_type="User", entity_id="2")
    _log(tenant_a.company, tenant_a.owner, 1)
    assert audit_chain.seal(None) == 2
    assert audit_chain.seal(tenant_a.company.id) == 1
    assert sorted(AuditEvent.objects.filter(company__isnull=True).values_list("chain_seq", flat=True)) == [1, 2]
    assert audit_chain.verify(all_companies=True).ok


def test_chain_seq_is_unique_per_company(tenant_a):
    a, b = _log(tenant_a.company, tenant_a.owner, 2)
    audit_chain.seal(tenant_a.company.id)
    with audit_maintenance("constraint test"):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                AuditEvent.objects.filter(pk=b.pk).update(chain_seq=1)


def test_swapping_two_sealed_events_is_detected(tenant_a):
    evs = _log(tenant_a.company, tenant_a.owner, 3)
    audit_chain.seal(tenant_a.company.id)
    with audit_maintenance("tamper test"):
        AuditEvent.objects.filter(pk=evs[0].pk).update(chain_seq=99)
        AuditEvent.objects.filter(pk=evs[1].pk).update(chain_seq=1)
        AuditEvent.objects.filter(pk=evs[0].pk).update(chain_seq=2)
    res = audit_chain.verify(tenant_a.company.id)
    assert not res.ok and any("content hash mismatch" in p or "reordered" in p for p in res.problems)


def test_verify_scopes_to_one_company_and_ignores_unsealed_rows(tenant_a, tenant_b):
    _log(tenant_a.company, tenant_a.owner, 2)
    _log(tenant_b.company, tenant_b.owner, 2)
    audit_chain.seal(tenant_a.company.id)
    # tamper with B only; A must still verify, B must not
    audit_chain.seal(tenant_b.company.id)
    victim = AuditEvent.objects.filter(company=tenant_b.company).first()
    with audit_maintenance("tamper test"):
        AuditEvent.objects.filter(pk=victim.pk).update(description="forged")
    assert audit_chain.verify(tenant_a.company.id).ok
    assert not audit_chain.verify(tenant_b.company.id).ok
    assert not audit_chain.verify(all_companies=True).ok


# --- re-parenting (sandbox teardown) keeps content verifiable ---------------------------

def test_events_detached_from_a_deleted_company_still_verify_by_content(tenant_a):
    _log(tenant_a.company, tenant_a.owner, 3)
    audit_chain.seal(tenant_a.company.id)
    with audit_maintenance("sandbox teardown"):
        AuditEvent.objects.filter(company=tenant_a.company).update(company=None)
    res = audit_chain.verify(all_companies=True)
    assert res.ok, res.problems
    assert res.checked >= 3  # other sealed rows may already exist in a reused test DB


def test_detached_events_that_were_edited_are_still_caught(tenant_a):
    evs = _log(tenant_a.company, tenant_a.owner, 2)
    audit_chain.seal(tenant_a.company.id)
    with audit_maintenance("sandbox teardown"):
        AuditEvent.objects.filter(company=tenant_a.company).update(company=None)
        AuditEvent.objects.filter(pk=evs[0].pk).update(description="forged after detach")
    assert not audit_chain.verify(all_companies=True).ok


# --- the legitimate mutators keep working ------------------------------------------------

def test_tenant_erasure_can_still_delete_the_audit_trail(tenant_a):
    from accounts.erasure import _delete_protect_rows

    _log(tenant_a.company, tenant_a.owner, 3)
    audit_chain.seal(tenant_a.company.id)
    _delete_protect_rows(tenant_a.company)
    assert not AuditEvent.objects.filter(company=tenant_a.company).exists()
    assert not maintenance_active(), "the maintenance flag must be closed again afterwards"


def test_sandbox_teardown_detaches_audit_events_without_error(tenant_a):
    """delete_sandbox_company wipes a restored sandbox, re-parenting its audit events."""
    from accounts.tenant_backup import delete_sandbox_company

    company = tenant_a.company
    _log(company, tenant_a.owner, 2)
    delete_sandbox_company(company)
    assert AuditEvent.objects.filter(company__isnull=True, entity_type="Invoice").count() >= 2
    assert not maintenance_active()


# --- the guard itself ---------------------------------------------------------------------

def test_maintenance_flag_closes_even_when_the_body_raises(tenant_a):
    (ev,) = _log(tenant_a.company, tenant_a.owner)
    with pytest.raises(RuntimeError):
        with audit_maintenance("will fail"):
            assert maintenance_active()
            raise RuntimeError("boom")
    assert not maintenance_active()
    with pytest.raises(AuditImmutableError):
        AuditEvent.objects.filter(pk=ev.pk).update(description="x")


def test_nested_maintenance_blocks_do_not_close_the_outer_one(tenant_a):
    (ev,) = _log(tenant_a.company, tenant_a.owner)
    with audit_maintenance("outer"):
        with audit_maintenance("inner"):
            pass
        assert maintenance_active()
        AuditEvent.objects.filter(pk=ev.pk).update(description="still allowed")
    assert not maintenance_active()


def test_the_error_message_says_how_to_do_it_properly(tenant_a):
    (ev,) = _log(tenant_a.company, tenant_a.owner)
    with pytest.raises(AuditImmutableError, match="audit_maintenance"):
        ev.delete()


def test_nightly_task_is_scheduled_and_importable():
    from django.conf import settings

    entry = settings.CELERY_BEAT_SCHEDULE["core-seal-audit-chain"]
    assert entry["task"] == "core.tasks.seal_audit_chain_task"
    from core.tasks import seal_audit_chain_task

    assert seal_audit_chain_task.name == entry["task"]


def test_nightly_task_reports_a_tampered_chain_without_raising(tenant_a, monkeypatch):
    import core.tasks as tasks_mod
    from core.tasks import seal_audit_chain_task

    logged = []
    monkeypatch.setattr(tasks_mod.logger, "error", lambda msg, *a, **k: logged.append(msg % a if a else msg))

    evs = _log(tenant_a.company, tenant_a.owner, 2)
    seal_audit_chain_task()
    with audit_maintenance("tamper test"):
        AuditEvent.objects.filter(pk=evs[0].pk).update(description="forged")
    out = seal_audit_chain_task()
    assert out["problems"] >= 1
    assert any("audit_chain_verify FAILED" in m for m in logged)


def test_audit_service_write_path_is_unchanged(tenant_a):
    """Normal logging (the thing every endpoint does) must not need maintenance."""
    ev = AuditService.log(company=tenant_a.company, user=tenant_a.owner, action="UPDATE", entity_type="X", entity_id="1")
    assert ev.pk and ev.chain_hash == "" and ev.sealed_at is None


# --- Postgres: the trigger flag must nest like the Python flag --------------------------------

def _pg_only():
    from django.db import connection

    if connection.vendor != "postgresql":
        pytest.skip("Postgres trigger")


def test_inner_block_does_not_switch_the_database_flag_off_for_the_outer_block(tenant_a):
    """Regression: the inner block's exit used to write 'off', so the outer block's next raw
    UPDATE/DELETE hit the append-only trigger even though it was still inside audit_maintenance()."""
    from django.db import DatabaseError, connection

    _pg_only()
    evs = _log(tenant_a.company, tenant_a.owner, 2)
    with audit_maintenance("outer"):
        with audit_maintenance("inner"):
            pass
        with connection.cursor() as cur:
            cur.execute("DELETE FROM core_auditevent WHERE id = %s", [evs[0].pk])   # still allowed
    with pytest.raises(DatabaseError, match="append-only"):
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("DELETE FROM core_auditevent WHERE id = %s", [evs[1].pk])  # and closed again


def test_tip_still_matches_after_a_later_seal(tenant_a, tmp_path):
    from django.core.management import call_command

    _log(tenant_a.company, tenant_a.owner, 2)
    audit_chain.seal(tenant_a.company.id)
    out = tmp_path / "tip.json"
    call_command("export_audit_tip", out=str(out))
    _log(tenant_a.company, tenant_a.owner, 1, prefix="later")
    audit_chain.seal(tenant_a.company.id)
    call_command("verify_audit_chain", tip=str(out))


def test_deleting_the_exported_tail_fails_the_tip_check(tenant_a, tmp_path):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    _log(tenant_a.company, tenant_a.owner, 2)
    audit_chain.seal(tenant_a.company.id)
    out = tmp_path / "tip.json"
    call_command("export_audit_tip", out=str(out))
    later = AuditEvent.objects.filter(company=tenant_a.company, sealed_at__isnull=False).order_by("-chain_seq").first()
    with audit_maintenance("test tail"):
        AuditEvent.objects.filter(pk=later.pk).delete()
    assert audit_chain.verify(tenant_a.company.id).ok
    with pytest.raises(CommandError):
        call_command("verify_audit_chain", tip=str(out))


def test_tip_file_hash_mismatch_fails(tenant_a, tmp_path):
    import json

    from django.core.management import call_command
    from django.core.management.base import CommandError

    _log(tenant_a.company, tenant_a.owner, 2)
    audit_chain.seal(tenant_a.company.id)
    out = tmp_path / "tip.json"
    call_command("export_audit_tip", out=str(out))
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["companies"][0]["tip_hash"] = "0" * 64
    out.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CommandError):
        call_command("verify_audit_chain", tip=str(out))


def test_new_company_is_a_warning_unless_strict(tenant_a, tenant_b, tmp_path):
    from io import StringIO

    from django.core.management import call_command
    from django.core.management.base import CommandError

    _log(tenant_a.company, tenant_a.owner, 1)
    audit_chain.seal(tenant_a.company.id)
    out = tmp_path / "tip.json"
    call_command("export_audit_tip", out=str(out))
    _log(tenant_b.company, tenant_b.owner, 1, prefix="b")
    audit_chain.seal(tenant_b.company.id)
    stdout = StringIO()
    call_command("verify_audit_chain", tip=str(out), stdout=stdout)
    assert "WARNING" in stdout.getvalue()
    assert str(tenant_b.company.id) in stdout.getvalue()
    with pytest.raises(CommandError):
        call_command("verify_audit_chain", tip=str(out), strict=True)


def test_the_database_flag_is_restored_to_off_after_the_outermost_block(tenant_a):
    from django.db import connection

    _pg_only()
    with audit_maintenance("outer"):
        with audit_maintenance("inner"):
            pass
    with connection.cursor() as cur:
        cur.execute("SELECT current_setting('app.audit_maintenance', true)")
        assert cur.fetchone()[0] in (None, "", "off")
