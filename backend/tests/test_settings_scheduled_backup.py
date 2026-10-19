"""SET-08: weekly automatic backup: opt in, kept copies, pruning, failures recorded, owner only."""

from unittest import mock

from accounts.scheduled_backup import KEEP, NAME_PREFIX, run_scheduled_backup, stored_backups
from accounts.tasks import run_scheduled_backups_task
from core.models import AuditEvent, FileAsset

URL = "/api/v1/company/export/schedule/"


def test_off_by_default_and_owner_only(tenant_a):
    data = tenant_a.client.get(URL).data
    assert data["enabled"] is False and data["backups"] == [] and data["last_run"] is None
    assert tenant_a.staff_client.get(URL).status_code == 403
    assert tenant_a.staff_client.patch(URL, {"enabled": True}, format="json").status_code == 403


def test_switching_on_is_saved_and_audited(tenant_a):
    r = tenant_a.client.patch(URL, {"enabled": True}, format="json")
    assert r.status_code == 200 and r.data["enabled"] is True
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.scheduled_backup_enabled is True
    assert AuditEvent.objects.filter(company=tenant_a.company, metadata__event="tenant.backup_schedule").exists()
    assert tenant_a.client.patch(URL, {"enabled": "yes"}, format="json").status_code == 400


def test_taking_a_backup_stores_an_encrypted_file_and_reports_it(tenant_a):
    r = tenant_a.client.post(URL, {}, format="json")
    assert r.status_code == 201, r.data
    assert len(r.data["backups"]) == 1 and r.data["last_run"]["ok"] is True
    asset = FileAsset.objects.get(pk=r.data["backups"][0]["id"])
    assert asset.kind == FileAsset.Kind.EXPORT and asset.size > 0 and asset.original_name.startswith(NAME_PREFIX)
    dl = tenant_a.client.get(f"/api/v1/files/{asset.pk}/download/")
    assert dl.status_code == 200


def test_only_the_last_few_are_kept(tenant_a):
    for _ in range(KEEP + 2):
        assert run_scheduled_backup(tenant_a.company) is not None
    assert stored_backups(tenant_a.company).count() == KEEP


def test_a_backup_does_not_contain_the_previous_one(tenant_a):
    from accounts.tenant_backup import build_export_payload

    run_scheduled_backup(tenant_a.company)
    names = [f["original_name"] for f in build_export_payload(tenant_a.company)["file_assets"]]
    assert not any(n.startswith(NAME_PREFIX) for n in names)


def test_a_failure_is_recorded_not_raised_and_other_companies_still_run(tenant_a, tenant_b):
    for t in (tenant_a, tenant_b):
        t.company.scheduled_backup_enabled = True
        t.company.save(update_fields=["scheduled_backup_enabled"])
    real = run_scheduled_backup.__globals__["build_export_payload"]

    def flaky(company):
        if company.pk == tenant_a.company.pk:
            raise RuntimeError("disk full")
        return real(company)

    with mock.patch("accounts.scheduled_backup.build_export_payload", side_effect=flaky):
        result = run_scheduled_backups_task()
    assert result == {"taken": 1, "failed": 1}
    last = tenant_a.client.get(URL).data["last_run"]
    assert last["ok"] is False and "disk full" in last["error"]
    assert tenant_b.client.get(URL).data["last_run"]["ok"] is True


def test_companies_that_did_not_opt_in_are_skipped(tenant_a):
    assert run_scheduled_backups_task() == {"taken": 0, "failed": 0}
    assert stored_backups(tenant_a.company).count() == 0
