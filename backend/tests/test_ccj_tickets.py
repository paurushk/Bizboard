"""Customer care plan: support tickets and the vendor inbox (TKT-*, SHR-*)."""

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from accounts.models import Company, CompanyUser, User
from core.rls import rls_bypass
from support.models import Ticket, TicketComment, VendorTicketShare
from support.tickets import SLA_OFFSETS, reprioritise, sla_state

from .conftest import make_customer, make_tenant

pytestmark = pytest.mark.django_db

URL = "/api/v1/support/tickets/"


def _on(tenant):
    tenant.company.feature_flags = {"ENABLE_SUPPORT_TICKETS": True, "ENABLE_COMPLAINTS": True}
    tenant.company.save(update_fields=["feature_flags"])


def _ticket(tenant, customer=None, **extra):
    customer = customer or make_customer(tenant.company)
    body = {"customer": customer.id, "subject": "Pump leaks", "priority": "MEDIUM", **extra}
    resp = tenant.client.post(URL, body, format="json")
    assert resp.status_code == 201, resp.data
    return resp.data


def _move(tenant, ticket_id, *statuses):
    for status in statuses:
        resp = tenant.client.post(f"{URL}{ticket_id}/transition/", {"status": status}, format="json")
        assert resp.status_code == 200, resp.data
    return resp.data


# ---- TKT-01: server-side SLA verdict ---------------------------------------------------------------------------------------------

def test_sla_state_is_decided_by_the_server_and_stops_at_resolve(tenant_a):
    _on(tenant_a)
    data = _ticket(tenant_a)
    assert data["sla_state"] == "running"
    ticket = Ticket.objects.get(pk=data["id"])
    ticket.status = Ticket.Status.RESOLVED
    ticket.resolved_at = ticket.sla_due_at - timedelta(minutes=5)
    assert sla_state(ticket)["state"] == "met"
    ticket.resolved_at = ticket.sla_due_at + timedelta(hours=2)
    assert sla_state(ticket)["state"] == "breached_resolved"
    # a month later it is still judged at resolve time, not against the wall clock
    later = timezone.now() + timedelta(days=30)
    assert sla_state(ticket, now=later)["state"] == "breached_resolved"


def test_an_open_ticket_past_its_due_time_is_breached_and_a_waiting_one_is_paused(tenant_a):
    _on(tenant_a)
    ticket = Ticket.objects.get(pk=_ticket(tenant_a)["id"])
    ticket.sla_due_at = timezone.now() - timedelta(hours=1)
    assert sla_state(ticket)["state"] == "breached"
    ticket.status = Ticket.Status.WAITING
    ticket.waiting_since = timezone.now()
    assert sla_state(ticket)["state"] == "paused"


# ---- TKT-02: a priority change cannot be used to reset the clock ---------------------------------------------------------------

def test_toggling_priority_returns_to_the_original_deadline(tenant_a):
    _on(tenant_a)
    data = _ticket(tenant_a, priority="HIGH")
    ticket = Ticket.objects.get(pk=data["id"])
    original = ticket.sla_due_at
    reprioritise(ticket, tenant_a.owner, "MEDIUM")
    ticket.refresh_from_db()
    assert ticket.sla_due_at == original + (SLA_OFFSETS["MEDIUM"] - SLA_OFFSETS["HIGH"])
    reprioritise(ticket, tenant_a.owner, "HIGH")
    ticket.refresh_from_db()
    assert ticket.sla_due_at == original


def test_raising_the_priority_of_an_old_ticket_shows_it_breached(tenant_a):
    _on(tenant_a)
    ticket = Ticket.objects.get(pk=_ticket(tenant_a, priority="LOW")["id"])
    ticket.sla_due_at = timezone.now() + timedelta(days=1)  # low: 7 days from a creation 6 days ago
    ticket.save(update_fields=["sla_due_at"])
    resp = tenant_a.client.patch(f"{URL}{ticket.id}/", {"priority": "URGENT"}, format="json")
    assert resp.status_code == 200, resp.data
    assert resp.data["priority"] == "URGENT"
    assert resp.data["sla_state"] == "breached"


def test_priority_cannot_change_on_a_finished_ticket(tenant_a):
    _on(tenant_a)
    data = _ticket(tenant_a)
    _move(tenant_a, data["id"], "IN_PROGRESS", "RESOLVED")
    resp = tenant_a.client.patch(f"{URL}{data['id']}/", {"priority": "URGENT"}, format="json")
    assert resp.status_code == 400


# ---- TKT-03: create and edit -------------------------------------------------------------------------------------------------------

def test_a_ticket_can_name_an_invoice_and_a_contract_of_the_same_customer(tenant_a):
    from contracts.models import Contract
    from sales.models import SalesInvoice

    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    other = make_customer(tenant_a.company, name="Other Buyer")
    invoice = SalesInvoice.objects.create(company=tenant_a.company, customer=customer)
    foreign = SalesInvoice.objects.create(company=tenant_a.company, customer=other)
    contract = Contract.objects.create(
        company=tenant_a.company, customer=customer, contract_type="AMC", number="CON-1",
        start_date=timezone.localdate(), end_date=timezone.localdate() + timedelta(days=90),
    )
    data = _ticket(tenant_a, customer, source_invoice=invoice.id, contract=contract.id, description="Leaks")
    assert data["source_invoice"] == invoice.id
    assert data["contract_number"] == "CON-1"
    assert data["customer_name"] == customer.name
    bad = tenant_a.client.post(
        URL, {"customer": customer.id, "subject": "x", "source_invoice": foreign.id}, format="json",
    )
    assert bad.status_code == 400


def test_subject_and_description_can_be_edited_but_not_the_customer(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    other = make_customer(tenant_a.company, name="Other Buyer")
    data = _ticket(tenant_a, customer)
    resp = tenant_a.client.patch(
        f"{URL}{data['id']}/", {"subject": "Pump leaks badly", "description": "Seal gone"}, format="json",
    )
    assert resp.status_code == 200 and resp.data["subject"] == "Pump leaks badly"
    blank = tenant_a.client.patch(f"{URL}{data['id']}/", {"subject": "  "}, format="json")
    assert blank.status_code == 400
    moved = tenant_a.client.patch(f"{URL}{data['id']}/", {"customer": other.id}, format="json")
    assert moved.status_code == 400


def test_a_stale_edit_is_refused_with_a_conflict(tenant_a):
    _on(tenant_a)
    data = _ticket(tenant_a)
    seen = data["updated_at"]
    assert tenant_a.client.patch(f"{URL}{data['id']}/", {"subject": "First"}, format="json").status_code == 200
    stale = tenant_a.client.patch(
        f"{URL}{data['id']}/", {"subject": "Second"}, format="json", HTTP_X_EXPECTED_UPDATED_AT=seen,
    )
    assert stale.status_code == 409
    assert Ticket.objects.get(pk=data["id"]).subject == "First"


# ---- TKT-04: list, filters, search, report ---------------------------------------------------------------------------------------

def test_search_filters_and_report_cover_the_whole_company_not_one_page(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company, name="Acme Foods")
    for index in range(25):
        _ticket(tenant_a, customer, subject=f"Fault {index}")
    odd = _ticket(tenant_a, make_customer(tenant_a.company, name="Zed Mills"), subject="Gearbox noise")
    _move(tenant_a, odd["id"], "IN_PROGRESS")
    found = tenant_a.client.get(URL, {"q": "gearbox"})
    assert [row["id"] for row in found.data["results"]] == [odd["id"]]
    by_customer = tenant_a.client.get(URL, {"q": "zed mills"})
    assert by_customer.data["count"] == 1
    by_number = tenant_a.client.get(URL, {"q": odd["number"]})
    assert by_number.data["count"] == 1
    assert tenant_a.client.get(URL, {"status": "IN_PROGRESS"}).data["count"] == 1
    report = tenant_a.client.get(f"{URL}report/").data
    totals = {row["status"]: row["count"] for row in report["by_status"]}
    assert totals == {"OPEN": 25, "IN_PROGRESS": 1}


def test_closed_tickets_can_be_hidden_after_some_days(tenant_a):
    _on(tenant_a)
    data = _ticket(tenant_a)
    _move(tenant_a, data["id"], "IN_PROGRESS", "RESOLVED", "CLOSED")
    Ticket.objects.filter(pk=data["id"]).update(updated_at=timezone.now() - timedelta(days=30))
    assert tenant_a.client.get(URL).data["count"] == 1
    assert tenant_a.client.get(URL, {"hide_closed_after_days": 7}).data["count"] == 0


# ---- TKT-05..07: comments, files, delete, concurrency ------------------------------------------------------------------------------

def test_comments_show_their_author_and_reject_empty_text(tenant_a):
    _on(tenant_a)
    data = _ticket(tenant_a)
    assert tenant_a.client.post(f"{URL}{data['id']}/comments/", {"body": "   "}, format="json").status_code == 400
    posted = tenant_a.client.post(f"{URL}{data['id']}/comments/", {"body": "Called the customer"}, format="json")
    assert posted.status_code == 201
    listed = tenant_a.client.get(f"{URL}{data['id']}/comments/").data
    assert listed[0]["author_name"] == tenant_a.owner.full_name
    assert listed[0]["body"] == "Called the customer"


def test_a_closed_ticket_takes_no_new_comment_or_file(tenant_a):
    _on(tenant_a)
    data = _ticket(tenant_a)
    _move(tenant_a, data["id"], "IN_PROGRESS", "RESOLVED", "CLOSED")
    assert tenant_a.client.post(f"{URL}{data['id']}/comments/", {"body": "late"}, format="json").status_code == 400
    assert tenant_a.client.post(f"{URL}{data['id']}/attachments/", {}, format="multipart").status_code == 400
    assert tenant_a.client.delete(f"{URL}{data['id']}/attachments/?attachment=1").status_code == 400
    _move(tenant_a, data["id"], "IN_PROGRESS")  # re-opening makes it editable again
    assert tenant_a.client.post(f"{URL}{data['id']}/comments/", {"body": "back"}, format="json").status_code == 201


def test_only_an_untouched_open_ticket_can_be_deleted_and_only_by_the_owner(tenant_a):
    _on(tenant_a)
    clean = _ticket(tenant_a)
    assert tenant_a.staff_client.delete(f"{URL}{clean['id']}/").status_code == 403
    commented = _ticket(tenant_a)
    tenant_a.client.post(f"{URL}{commented['id']}/comments/", {"body": "note"}, format="json")
    assert tenant_a.client.delete(f"{URL}{commented['id']}/").status_code == 400
    started = _ticket(tenant_a)
    _move(tenant_a, started["id"], "IN_PROGRESS")
    assert tenant_a.client.delete(f"{URL}{started['id']}/").status_code == 400
    assert tenant_a.client.delete(f"{URL}{clean['id']}/").status_code == 204


def test_every_ticket_action_leaves_an_audit_row(tenant_a):
    from core.models import AuditEvent

    _on(tenant_a)
    data = _ticket(tenant_a)
    tenant_a.client.post(f"{URL}{data['id']}/comments/", {"body": "note"}, format="json")
    _move(tenant_a, data["id"], "IN_PROGRESS")
    tenant_a.client.patch(f"{URL}{data['id']}/", {"priority": "URGENT"}, format="json")
    actions = set(
        AuditEvent.objects.filter(company=tenant_a.company, entity_type="Ticket", entity_id=str(data["id"]))
        .values_list("action", flat=True)
    )
    assert {"CREATE", "ticket_comment", "ticket_status", "ticket_priority"} <= actions
    timeline = tenant_a.client.get("/api/v1/audit-timeline/", {"entity": "Ticket", "id": data["id"]})
    assert timeline.status_code == 200 and len(timeline.data) >= 4
    assert all("ip" not in row["metadata"] for row in timeline.data)


# ---- TKT-08: sharing ---------------------------------------------------------------------------------------------------------------

def _vendor_setup(tenant_a, tenant_b):
    _on(tenant_a)
    _on(tenant_b)
    return override_settings(VENDOR_COMPANY_ID=str(tenant_b.company.id))


def test_share_state_is_visible_stop_is_repeatable_and_edits_reach_the_vendor(tenant_a, tenant_b):
    with _vendor_setup(tenant_a, tenant_b):
        data = _ticket(tenant_a, description="Seal gone")
        assert data["shared"] is False
        assert tenant_a.client.post(f"{URL}{data['id']}/stop-sharing/").status_code == 200  # nothing to stop
        assert tenant_a.client.post(
            f"{URL}{data['id']}/share/", {"include_description": True}, format="json",
        ).status_code == 200
        shown = tenant_a.client.get(f"{URL}{data['id']}/").data
        assert shown["shared"] is True and shown["share_includes_description"] is True
        tenant_a.client.patch(f"{URL}{data['id']}/", {"subject": "Pump leaks badly"}, format="json")
        with rls_bypass():
            share = VendorTicketShare.objects.get(source_ticket_id=data["id"])
        assert share.subject == "Pump leaks badly" and share.description == "Seal gone"
        assert tenant_a.client.post(f"{URL}{data['id']}/stop-sharing/").status_code == 200
        assert tenant_a.client.post(f"{URL}{data['id']}/stop-sharing/").status_code == 200
        assert tenant_a.client.get(f"{URL}{data['id']}/").data["shared"] is False
        assert tenant_a.staff_client.post(f"{URL}{data['id']}/share/").status_code == 403


def test_a_shared_ticket_without_the_description_never_leaks_it(tenant_a, tenant_b):
    with _vendor_setup(tenant_a, tenant_b):
        data = _ticket(tenant_a, description="Private detail")
        tenant_a.client.post(f"{URL}{data['id']}/share/", {}, format="json")
        listing = tenant_b.client.get("/api/v1/support/shared/").data["results"]
        assert len(listing) == 1 and "description" not in listing[0]
        tenant_a.client.patch(f"{URL}{data['id']}/", {"description": "Changed"}, format="json")
        with rls_bypass():
            assert VendorTicketShare.objects.get(source_ticket_id=data["id"]).description == ""


# ---- SHR-03: vendor replies --------------------------------------------------------------------------------------------------------

def test_a_vendor_reply_is_written_for_both_companies_and_nobody_else(tenant_a, tenant_b):
    tenant_c = make_tenant("gamma")
    _on(tenant_c)
    with _vendor_setup(tenant_a, tenant_b):
        data = _ticket(tenant_a)
        tenant_a.client.post(f"{URL}{data['id']}/share/", {}, format="json")
        share = tenant_b.client.get("/api/v1/support/shared/").data["results"][0]
        reply = tenant_b.client.post(
            f"/api/v1/support/shared/{share['id']}/replies/", {"body": "Send us the model number"}, format="json",
        )
        assert reply.status_code == 201, reply.data
        # the vendor sees its own reply
        mine = tenant_b.client.get(f"/api/v1/support/shared/{share['id']}/replies/").data
        assert [row["body"] for row in mine] == ["Send us the model number"]
        assert tenant_b.client.get("/api/v1/support/shared/").data["results"][0]["reply_count"] == 1
        # the source company sees it on its ticket, labelled as the vendor
        seen = tenant_a.client.get(f"{URL}{data['id']}/comments/").data
        assert seen[0]["from_vendor"] is True and seen[0]["is_internal"] is False
        assert seen[0]["author_name"] == tenant_b.company.name
        # a third company can neither read nor reply
        assert tenant_c.client.get(f"/api/v1/support/shared/{share['id']}/replies/").status_code == 404
        assert tenant_c.client.post(
            f"/api/v1/support/shared/{share['id']}/replies/", {"body": "hijack"}, format="json",
        ).status_code == 404
        # the source company has no access to the vendor's inbox rows
        assert tenant_a.client.get(f"/api/v1/support/shared/{share['id']}/").status_code == 404
        # empty text is refused and a revoked share takes no more replies
        assert tenant_b.client.post(
            f"/api/v1/support/shared/{share['id']}/replies/", {"body": " "}, format="json",
        ).status_code == 400
        tenant_a.client.post(f"{URL}{data['id']}/stop-sharing/")
        gone = tenant_b.client.post(
            f"/api/v1/support/shared/{share['id']}/replies/", {"body": "still there?"}, format="json",
        )
        assert gone.status_code in (400, 404)
        assert TicketComment.objects.filter(ticket_id=data["id"], from_vendor=True).count() == 1


def test_the_vendor_inbox_filters_by_live_status_and_search(tenant_a, tenant_b):
    with _vendor_setup(tenant_a, tenant_b):
        first = _ticket(tenant_a, subject="Gearbox noise")
        second = _ticket(tenant_a, subject="Display flicker")
        for ticket in (first, second):
            tenant_a.client.post(f"{URL}{ticket['id']}/share/", {}, format="json")
        _move(tenant_a, first["id"], "IN_PROGRESS")
        listing = tenant_b.client.get("/api/v1/support/shared/", {"status": "IN_PROGRESS"}).data
        assert listing["count"] == 1 and listing["results"][0]["subject"] == "Gearbox noise"
        assert tenant_b.client.get("/api/v1/support/shared/", {"q": "flicker"}).data["count"] == 1


def test_only_the_vendor_company_gets_the_inbox_flag(tenant_a, tenant_b):
    with _vendor_setup(tenant_a, tenant_b):
        flags_b = tenant_b.client.get("/api/v1/feature-flags/").data
        flags_a = tenant_a.client.get("/api/v1/feature-flags/").data
    payload_b = flags_b.get("flags", flags_b)
    payload_a = flags_a.get("flags", flags_a)
    assert payload_b["IS_VENDOR_COMPANY"] is True
    assert payload_a["IS_VENDOR_COMPANY"] is False


# ---- D1: a viewer can read but not change ------------------------------------------------------------------------------------------

def test_a_viewer_reads_tickets_but_cannot_change_them(tenant_a):
    _on(tenant_a)
    data = _ticket(tenant_a)
    viewer = User.objects.create_user(email="viewer@alpha.test", password="StrongPass123!", full_name="Viewer")
    CompanyUser.objects.create(company=tenant_a.company, user=viewer, role=CompanyUser.Role.VIEWER)
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=viewer)
    assert client.get(URL).status_code == 200
    assert client.get(f"{URL}{data['id']}/").status_code == 200
    assert client.post(URL, {"customer": 1, "subject": "x"}, format="json").status_code == 403
    assert client.post(f"{URL}{data['id']}/comments/", {"body": "x"}, format="json").status_code == 403
    assert client.post(f"{URL}{data['id']}/transition/", {"status": "IN_PROGRESS"}, format="json").status_code == 403


def test_other_companies_tickets_are_invisible(tenant_a, tenant_b):
    _on(tenant_a)
    _on(tenant_b)
    data = _ticket(tenant_a)
    assert tenant_b.client.get(f"{URL}{data['id']}/").status_code == 404
    assert tenant_b.client.get(URL, {"q": "pump"}).data["count"] == 0
    assert Company.objects.filter(pk=tenant_b.company.pk).exists()


def test_the_unassigned_queue_can_be_listed(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    mine = _ticket(tenant_a, customer, subject="Assigned one")
    waiting = Ticket.objects.get(pk=_ticket(tenant_a, customer, subject="Nobody has it")["id"])
    Ticket.objects.filter(pk=waiting.pk).update(assigned_to=None)
    Ticket.objects.filter(pk=mine["id"]).update(assigned_to=tenant_a.owner.company_memberships.first())
    queue = tenant_a.client.get(URL, {"unassigned": 1})
    assert [row["id"] for row in queue.data["results"]] == [waiting.pk]
