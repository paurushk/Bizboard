"""API tests. Responses use the app envelope ({"success", "data"}) with camelCased keys."""

import json
import uuid

import pytest

from agents.enums import ProposalStatus
from agents.models import AgentProposal, AgentRun
from core.services.llm_providers import fake

from .conftest import enable_agents, make_proposal

pytestmark = pytest.mark.django_db

BASE = "/api/v1/agents"


def key():
    return {"HTTP_IDEMPOTENCY_KEY": f"k-{uuid.uuid4()}"}


def d(resp):
    return resp.json()["data"]


def text(resp):
    return json.dumps(resp.json())


def test_catalog_lists_enabled_agents_with_renderers_and_roles(tenant):
    [agent] = d(tenant.client.get(f"{BASE}/catalog/"))["agents"]
    assert agent["kind"] == "EXAMPLE" and agent["canPrepare"] is True
    assert agent["proposalKinds"][0] == {
        "kind": "EXAMPLE_NOTE", "renderer": "message", "bulkApprovable": True, "titleKey": "agents.example.note", "canApprove": True,
    }
    staff = d(tenant.staff_client.get(f"{BASE}/catalog/"))["agents"][0]
    assert staff["canPrepare"] is False and staff["proposalKinds"][0]["canApprove"] is False


def test_flag_off_means_403_and_an_empty_catalog(tenant):
    tenant.company.feature_flags = {}
    tenant.company.save()
    assert d(tenant.client.get(f"{BASE}/catalog/")) == {"agents": []}
    r = tenant.client.post(f"{BASE}/runs/", {"agent": "EXAMPLE"}, format="json", **key())
    assert r.status_code == 403 and "AGT_E_DISABLED" in text(r)


def test_an_unregistered_agent_flag_enables_nothing(tenant):
    enable_agents(tenant.company, "AGENT_FOO")
    r = tenant.client.post(f"{BASE}/runs/", {"agent": "FOO"}, format="json", **key())
    assert r.status_code in (400, 403) and AgentRun.objects.count() == 0


def test_global_kill_switch(tenant, settings):
    settings.AGENTS_GLOBAL_KILL = True
    assert d(tenant.client.get(f"{BASE}/catalog/")) == {"agents": []}
    r = tenant.client.post(f"{BASE}/runs/", {"agent": "EXAMPLE"}, format="json", **key())
    assert r.status_code == 403 and "AGT_E_GLOBAL_KILL" in text(r)


def test_start_run_creates_proposals_and_is_idempotent(tenant):
    k = key()
    body = {"agent": "EXAMPLE", "triggerRef": "AR_OVERDUE_CUSTOMER:customer:1"}
    r1 = tenant.client.post(f"{BASE}/runs/", body, format="json", **k)
    r2 = tenant.client.post(f"{BASE}/runs/", body, format="json", **k)
    assert r1.status_code == 202 and r2.status_code == 202 and d(r1)["id"] == d(r2)["id"]
    assert AgentRun.objects.filter(company=tenant.company).count() == 1
    run = d(tenant.client.get(f"{BASE}/runs/{d(r1)['id']}/"))
    assert run["status"] == "SUCCEEDED" and len(run["proposalIds"]) == 1  # Celery is eager in tests


def test_reusing_a_key_for_a_different_request_is_refused(tenant):
    k = key()
    assert tenant.client.post(f"{BASE}/runs/", {"agent": "EXAMPLE", "triggerRef": "a"}, format="json", **k).status_code == 202
    r = tenant.client.post(f"{BASE}/runs/", {"agent": "EXAMPLE", "triggerRef": "b"}, format="json", **k)
    assert r.status_code in (409, 422)
    assert AgentRun.objects.filter(company=tenant.company).count() == 1


def test_staff_cannot_start_a_run(tenant):
    r = tenant.staff_client.post(f"{BASE}/runs/", {"agent": "EXAMPLE"}, format="json", **key())
    assert r.status_code == 403 and "AGT_E_ROLE" in text(r)


def test_run_detail_is_company_scoped(tenant, other_tenant):
    tenant.client.post(f"{BASE}/runs/", {"agent": "EXAMPLE", "triggerRef": "x"}, format="json", **key())
    run = AgentRun.objects.get(company=tenant.company)
    assert other_tenant.client.get(f"{BASE}/runs/{run.pk}/").status_code == 404


def test_proposals_list_detail_and_cross_tenant_404(tenant, other_tenant):
    p = make_proposal(tenant)
    rows = d(tenant.client.get(f"{BASE}/proposals/"))["results"]
    assert [r["id"] for r in rows] == [p.pk] and rows[0]["renderer"] == "message" and rows[0]["canApprove"] is True
    assert tenant.client.get(f"{BASE}/proposals/{p.pk}/").status_code == 200
    assert other_tenant.client.get(f"{BASE}/proposals/{p.pk}/").status_code == 404
    assert d(other_tenant.client.get(f"{BASE}/proposals/"))["results"] == []
    for action in ("approve", "reject", "cancel", "retry"):
        r = other_tenant.client.post(f"{BASE}/proposals/{p.pk}/{action}/", {"revision": 0}, format="json", **key())
        assert r.status_code == 404, action
    assert other_tenant.client.patch(f"{BASE}/proposals/{p.pk}/", {"editedPayload": {"text": "x"}, "revision": 0}, format="json").status_code == 404
    p.refresh_from_db()
    assert p.status == ProposalStatus.PENDING and p.revision == 0


def test_staff_sees_no_proposals_they_cannot_approve(tenant):
    p = make_proposal(tenant)
    assert d(tenant.staff_client.get(f"{BASE}/proposals/"))["results"] == []
    assert tenant.staff_client.get(f"{BASE}/proposals/{p.pk}/").status_code == 404


def test_approve_replays_for_the_same_key_and_executes_once(tenant):
    p = make_proposal(tenant)
    k = key()
    a = tenant.client.post(f"{BASE}/proposals/{p.pk}/approve/", {"revision": 0}, format="json", **k)
    b = tenant.client.post(f"{BASE}/proposals/{p.pk}/approve/", {"revision": 0}, format="json", **k)
    assert a.status_code == 200 and b.status_code == 200 and a.json() == b.json()
    assert d(a)["status"] == "EXECUTED"
    p.refresh_from_db()
    assert p.attempts == 1


def test_a_second_click_with_a_new_key_is_a_conflict_not_a_second_execution(tenant):
    p = make_proposal(tenant)
    assert tenant.client.post(f"{BASE}/proposals/{p.pk}/approve/", {"revision": 0}, format="json", **key()).status_code == 200
    r = tenant.client.post(f"{BASE}/proposals/{p.pk}/approve/", {"revision": 0}, format="json", **key())
    assert r.status_code == 409 and "AGT_E_BAD_TRANSITION" in text(r)
    p.refresh_from_db()
    assert p.attempts == 1


def test_wrong_revision_is_409(tenant):
    p = make_proposal(tenant)
    r = tenant.client.post(f"{BASE}/proposals/{p.pk}/approve/", {"revision": 3}, format="json", **key())
    assert r.status_code == 409 and "AGT_E_REVISION" in text(r)


def test_edit_after_a_stored_deterministic_failure_works_with_a_new_key(tenant):
    """The stored 4xx for key A must never be replayed against the corrected draft under key B."""
    p = make_proposal(tenant, fail="rule")
    a = tenant.client.post(f"{BASE}/proposals/{p.pk}/approve/", {"revision": 0}, format="json", **key())
    assert a.status_code == 400 and "example_rule" in text(a)
    edit = tenant.client.patch(
        f"{BASE}/proposals/{p.pk}/", {"editedPayload": {"text": "fixed 3", "fail": ""}, "revision": 0}, format="json",
    )
    assert edit.status_code == 200 and d(edit)["revision"] == 1 and d(edit)["status"] == "PENDING"
    b = tenant.client.post(f"{BASE}/proposals/{p.pk}/approve/", {"revision": 1}, format="json", **key())
    assert b.status_code == 200 and d(b)["status"] == "EXECUTED"


def test_stale_returns_409_and_the_draft_is_failed_non_retryable(tenant):
    p = make_proposal(tenant, fail="stale")
    r = tenant.client.post(f"{BASE}/proposals/{p.pk}/approve/", {"revision": 0}, format="json", **key())
    assert r.status_code == 409 and "AGT_E_STALE" in text(r)
    retry = tenant.client.post(f"{BASE}/proposals/{p.pk}/retry/", {"revision": 0}, format="json", **key())
    assert retry.status_code == 409


def test_staff_cannot_approve_even_if_they_know_the_id(tenant):
    p = make_proposal(tenant)
    r = tenant.staff_client.post(f"{BASE}/proposals/{p.pk}/approve/", {"revision": 0}, format="json", **key())
    assert r.status_code == 404  # not visible to them at all


def test_reject_and_cancel(tenant):
    a, b = make_proposal(tenant, dedupe="a"), make_proposal(tenant, dedupe="b")
    r = tenant.client.post(f"{BASE}/proposals/{a.pk}/reject/", {"reason": "no"}, format="json")
    assert r.status_code == 200 and d(r)["status"] == "REJECTED"
    c = tenant.client.post(f"{BASE}/proposals/{b.pk}/cancel/", {"note": "later"}, format="json")
    assert c.status_code == 200 and d(c)["status"] == "CANCELLED"


def test_bulk_approve_reports_each_item_and_only_for_bulk_kinds(tenant):
    ps = [make_proposal(tenant, dedupe=f"b{i}") for i in range(3)]
    items = [{"id": ps[0].pk, "revision": 0}, {"id": ps[1].pk, "revision": 9}, {"id": 999999, "revision": 0}, {"id": ps[2].pk, "revision": 0}]
    r = tenant.client.post(f"{BASE}/proposals/bulk-approve/", {"items": items}, format="json", **key())
    assert r.status_code == 200
    results = {x["id"]: x for x in d(r)["results"]}
    assert results[ps[0].pk]["ok"] and results[ps[2].pk]["ok"]
    assert not results[ps[1].pk]["ok"] and results[ps[1].pk]["code"] == "AGT_E_REVISION"
    assert not results[999999]["ok"]
    assert AgentProposal.objects.filter(status="EXECUTED").count() == 2


def test_bulk_approve_is_capped_at_50(tenant):
    items = [{"id": i, "revision": 0} for i in range(1, 52)]
    r = tenant.client.post(f"{BASE}/proposals/bulk-approve/", {"items": items}, format="json", **key())
    assert r.status_code == 400


def test_unauthenticated_is_rejected(tenant):
    from rest_framework.test import APIClient

    assert APIClient().get(f"{BASE}/catalog/").status_code in (401, 403)


def test_llm_run_via_api_creates_a_draft_the_user_can_approve(tenant):
    fake.script("EXAMPLE", step=1, response={"text": json.dumps({"note": "Reviewed 3 items totalling 1500"}), "tokens_in": 10, "tokens_out": 5})
    run = d(tenant.client.post(f"{BASE}/runs/", {"agent": "EXAMPLE", "triggerRef": "EXAMPLE_ROW:1"}, format="json", **key()))
    detail = d(tenant.client.get(f"{BASE}/runs/{run['id']}/"))
    assert detail["status"] == "SUCCEEDED" and detail["rulesOnly"] is False
    pid = detail["proposalIds"][0]
    done = tenant.client.post(f"{BASE}/proposals/{pid}/approve/", {"revision": 0}, format="json", **key())
    assert done.status_code == 200 and d(done)["payload"]["text"].startswith("Reviewed")
