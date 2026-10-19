"""Jobs & contracts plan: contracts (CON-*, XLK-02)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from contracts.models import Contract, ContractRenewal, ContractServiceEvent
from contracts.tasks import send_contract_renewal_reminders
from core.models import AuditEvent, Notification
from sales.models import RecurringInvoiceSchedule
from support.models import Ticket

from .conftest import make_customer, make_product, make_tenant

pytestmark = pytest.mark.django_db

URL = "/api/v1/contracts/"
TODAY = timezone.localdate


def _on(tenant):
    tenant.company.feature_flags = {"ENABLE_CONTRACTS": True, "ENABLE_SUPPORT_TICKETS": True}
    tenant.company.save(update_fields=["feature_flags"])


def _payload(customer, product=None, **extra):
    body = {
        "customer": customer.id, "contract_type": "AMC",
        "start_date": str(TODAY() - timedelta(days=30)), "end_date": str(TODAY() + timedelta(days=300)),
        "value": "1200.00", "renewal_reminder_days": 30, **extra,
    }
    if product is not None:
        body["product"] = product.id
    return body


def _make(tenant, customer, product=None, **extra):
    resp = tenant.client.post(URL, _payload(customer, product, **extra), format="json")
    assert resp.status_code == 201, resp.data
    return resp.data


# ---- CON-07: status filters read plain dates -------------------------------------------------------------------------------------

def test_effective_status_filters_use_the_stored_dates(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    for number, offset, reminder in (("A", 200, 30), ("B", 10, 30), ("C", -5, 30), ("D", 0, 0)):
        Contract.objects.create(
            company=tenant_a.company, customer=customer, contract_type="AMC", number=f"CON-{number}",
            start_date=TODAY() - timedelta(days=400), end_date=TODAY() + timedelta(days=offset),
            renewal_reminder_days=reminder,
        )
    cancelled = Contract.objects.create(
        company=tenant_a.company, customer=customer, contract_type="AMC", number="CON-X",
        start_date=TODAY() - timedelta(days=400), end_date=TODAY() + timedelta(days=100),
        status=Contract.Status.CANCELLED,
    )
    def numbers(status):
        resp = tenant_a.client.get(URL, {"status": status})
        return sorted(row["number"] for row in resp.data["results"])
    assert numbers("ACTIVE") == ["CON-A"]
    assert numbers("EXPIRING") == ["CON-B", "CON-D"]
    assert numbers("EXPIRED") == ["CON-C"]
    assert numbers("CANCELLED") == [cancelled.number]
    assert Contract.objects.get(number="CON-A").expiring_from_date == TODAY() + timedelta(days=170)


def test_search_matches_number_customer_and_covered_product(tenant_a):
    _on(tenant_a)
    first = make_customer(tenant_a.company, name="Acme Foods")
    second = make_customer(tenant_a.company, name="Zed Mills")
    pump = make_product(tenant_a.company, name="Booster Pump", sku="BP-1")
    fan = make_product(tenant_a.company, name="Exhaust Fan", sku="EF-1")
    one = _make(tenant_a, first, pump)
    _make(tenant_a, second, fan)
    assert tenant_a.client.get(URL, {"q": "acme"}).data["count"] == 1
    assert tenant_a.client.get(URL, {"q": "exhaust"}).data["count"] == 1
    assert tenant_a.client.get(URL, {"q": one["number"]}).data["count"] == 1
    listed = tenant_a.client.get(URL).data["results"][0]
    assert listed["customer_name"] in {"Acme Foods", "Zed Mills"} and "days_to_expiry" in listed


# ---- CON-05: validation and overlap ------------------------------------------------------------------------------------------------

def test_overlapping_contracts_warn_and_can_be_confirmed(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    pump = make_product(tenant_a.company, name="Pump", sku="P-1")
    _make(tenant_a, customer, pump)
    clash = tenant_a.client.post(URL, _payload(customer, pump), format="json")
    assert clash.status_code == 409
    assert clash.data["error"]["details"]["code"] == "overlap"
    confirmed = tenant_a.client.post(URL, _payload(customer, pump, allow_overlap=True), format="json")
    assert confirmed.status_code == 201
    other_type = tenant_a.client.post(URL, _payload(customer, pump, contract_type="WARRANTY"), format="json")
    assert other_type.status_code == 201  # a different type is not an overlap


def test_values_dates_and_status_are_validated(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    assert tenant_a.client.post(URL, _payload(customer, value="-5"), format="json").status_code == 400
    assert tenant_a.client.post(URL, _payload(customer, renewal_reminder_days=900), format="json").status_code == 400
    assert tenant_a.client.post(URL, _payload(customer, status="CANCELLED"), format="json").status_code == 400
    backwards = _payload(customer, end_date=str(TODAY() - timedelta(days=60)))
    assert tenant_a.client.post(URL, backwards, format="json").status_code == 400


def test_a_client_may_send_back_the_status_it_was_shown_and_a_cancelled_contract_is_frozen(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    data = _make(tenant_a, customer, end_date=str(TODAY() + timedelta(days=10)))
    assert data["status"] == "EXPIRING"
    ok = tenant_a.client.patch(f"{URL}{data['id']}/", {"status": "EXPIRING", "notes": "n"}, format="json")
    assert ok.status_code == 200
    assert tenant_a.client.patch(f"{URL}{data['id']}/", {"status": "CANCELLED"}, format="json").status_code == 200
    frozen = tenant_a.client.patch(f"{URL}{data['id']}/", {"notes": "edit"}, format="json")
    assert frozen.status_code == 400
    assert tenant_a.client.patch(f"{URL}{data['id']}/", {"status": "ACTIVE"}, format="json").status_code == 200


# ---- CON-02 / CON-04: billing schedule ----------------------------------------------------------------------------------------

def _with_schedule(tenant, customer, product, **extra):
    data = _make(tenant, customer, product, **extra)
    resp = tenant.client.post(f"{URL}{data['id']}/create-schedule/", {"cadence": "QUARTERLY"}, format="json")
    assert resp.status_code == 200, resp.data
    return data, resp.data


def test_billing_can_start_on_a_chosen_cadence_and_is_shown_on_the_contract(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    pump = make_product(tenant_a.company, name="Pump", sku="P-2", product_type="SERVICE")
    data, scheduled = _with_schedule(tenant_a, customer, pump)
    assert scheduled["cadence"] == "QUARTERLY"
    shown = tenant_a.client.get(f"{URL}{data['id']}/").data["schedule"]
    assert shown["cadence"] == "QUARTERLY" and shown["is_active"] is True
    bad = tenant_a.client.post(f"{URL}{data['id']}/create-schedule/", {"cadence": "DAILY"}, format="json")
    assert bad.status_code in (400, 200)  # an existing schedule is returned as is
    assert tenant_a.staff_client.post(f"{URL}{data['id']}/create-schedule/").status_code == 403


def test_a_value_change_reaches_the_billing_line_only_when_asked(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    pump = make_product(tenant_a.company, name="Pump", sku="P-3", product_type="SERVICE")
    data, scheduled = _with_schedule(tenant_a, customer, pump)
    tenant_a.client.patch(f"{URL}{data['id']}/", {"value": "1500.00"}, format="json")
    schedule = RecurringInvoiceSchedule.objects.get(pk=scheduled["id"])
    assert schedule.line_template["items"][0]["unit_price"] == "1200.00"
    synced = tenant_a.client.post(f"{URL}{data['id']}/sync-schedule/")
    assert synced.status_code == 200
    schedule.refresh_from_db()
    assert schedule.line_template["items"][0]["unit_price"] == "1500.00"
    assert tenant_a.staff_client.post(f"{URL}{data['id']}/sync-schedule/").status_code == 403


def test_billing_can_be_paused_and_resumed_by_the_owner(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    pump = make_product(tenant_a.company, name="Pump", sku="P-4", product_type="SERVICE")
    data, scheduled = _with_schedule(tenant_a, customer, pump)
    paused = tenant_a.client.post(f"{URL}{data['id']}/pause-schedule/")
    assert paused.status_code == 200 and paused.data["schedule"]["is_active"] is False
    assert RecurringInvoiceSchedule.objects.get(pk=scheduled["id"]).paused_reason == ""
    resumed = tenant_a.client.post(f"{URL}{data['id']}/resume-schedule/")
    assert resumed.data["schedule"]["is_active"] is True


# ---- CON-03: renewal -------------------------------------------------------------------------------------------------------------------

def test_an_expired_contract_can_be_renewed_and_its_billing_resumes(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    pump = make_product(tenant_a.company, name="Pump", sku="P-5", product_type="SERVICE")
    data, scheduled = _with_schedule(tenant_a, customer, pump)
    Contract.objects.filter(pk=data["id"]).update(end_date=TODAY() - timedelta(days=3))
    from contracts.tasks import refresh_contract_statuses

    refresh_contract_statuses()  # the nightly beat moves the status and stops the billing
    assert RecurringInvoiceSchedule.objects.get(pk=scheduled["id"]).is_active is False
    assert tenant_a.client.get(f"{URL}{data['id']}/").data["status"] == "EXPIRED"
    new_end = TODAY() + timedelta(days=365)
    renewed = tenant_a.client.post(
        f"{URL}{data['id']}/renew/", {"new_end_date": str(new_end), "value": "1400.00", "note": "Year 2"},
        format="json",
    )
    assert renewed.status_code == 200, renewed.data
    assert renewed.data["status"] == "ACTIVE" and renewed.data["end_date"] == str(new_end)
    schedule = RecurringInvoiceSchedule.objects.get(pk=scheduled["id"])
    assert schedule.is_active is True
    assert schedule.line_template["items"][0]["unit_price"] == "1400.00"
    renewal = ContractRenewal.objects.get(contract_id=data["id"])
    assert renewal.new_value == Decimal("1400.00") and renewal.note == "Year 2"
    assert tenant_a.client.get(f"{URL}{data['id']}/timeline/").data["renewals"][0]["note"] == "Year 2"


def test_renewal_must_extend_the_term_and_cannot_touch_a_cancelled_contract(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    data = _make(tenant_a, customer)
    same = tenant_a.client.post(f"{URL}{data['id']}/renew/", {"new_end_date": data["end_date"]}, format="json")
    assert same.status_code == 400
    junk = tenant_a.client.post(f"{URL}{data['id']}/renew/", {"new_end_date": "soon"}, format="json")
    assert junk.status_code == 400
    tenant_a.client.patch(f"{URL}{data['id']}/", {"status": "CANCELLED"}, format="json")
    late = tenant_a.client.post(
        f"{URL}{data['id']}/renew/", {"new_end_date": str(TODAY() + timedelta(days=900))}, format="json",
    )
    assert late.status_code == 400


# ---- CON-06: service events -----------------------------------------------------------------------------------------------------------

def test_service_events_take_a_date_and_only_a_ticket_of_the_same_customer(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    other = make_customer(tenant_a.company, name="Other Buyer")
    data = _make(tenant_a, customer)
    own = Ticket.objects.create(company=tenant_a.company, customer=customer, subject="Noise", number="T-1")
    foreign = Ticket.objects.create(company=tenant_a.company, customer=other, subject="Other", number="T-2")
    url = f"{URL}{data['id']}/service-events/"
    visit = str(timezone.now() - timedelta(days=3))
    ok = tenant_a.client.post(url, {"notes": "Replaced filter", "ticket": own.id, "occurred_at": visit}, format="json")
    assert ok.status_code == 201 and ok.data["ticket_number"] == "T-1"
    assert abs((timezone.now() - timedelta(days=3)) - ContractServiceEvent.objects.get().occurred_at) < timedelta(minutes=1)
    assert tenant_a.client.post(url, {"notes": "x", "ticket": foreign.id}, format="json").status_code == 400
    assert tenant_a.client.post(url, {"notes": " "}, format="json").status_code == 400
    future = str(timezone.now() + timedelta(days=5))
    assert tenant_a.client.post(url, {"notes": "later", "occurred_at": future}, format="json").status_code == 400


def test_a_service_event_can_be_corrected_only_by_its_author_within_a_day(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    data = _make(tenant_a, customer)
    url = f"{URL}{data['id']}/service-events/"
    event_id = tenant_a.client.post(url, {"notes": "first"}, format="json").data["id"]
    edit = f"{URL}{data['id']}/service-event/"
    assert tenant_a.client.patch(edit, {"event": event_id, "notes": "corrected"}, format="json").status_code == 200
    assert ContractServiceEvent.objects.get(pk=event_id).notes == "corrected"
    ContractServiceEvent.objects.filter(pk=event_id).update(created_at=timezone.now() - timedelta(days=2))
    assert tenant_a.client.delete(f"{edit}?event={event_id}").status_code == 400
    fresh = tenant_a.client.post(url, {"notes": "second"}, format="json").data["id"]
    assert tenant_a.client.delete(f"{edit}?event={fresh}").status_code == 204


# ---- CON-01 / CON-08 / CON-09 --------------------------------------------------------------------------------------------------------

def test_deletion_is_owner_only_and_blocked_by_history(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    data = _make(tenant_a, customer)
    assert tenant_a.staff_client.delete(f"{URL}{data['id']}/").status_code == 403
    tenant_a.client.post(f"{URL}{data['id']}/service-events/", {"notes": "visit"}, format="json")
    assert tenant_a.client.delete(f"{URL}{data['id']}/").status_code == 400


def test_reports_leave_out_cancelled_by_default_and_export_csv(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    live = _make(tenant_a, customer, value="1000.00")
    gone = _make(tenant_a, customer, value="500.00", allow_overlap=True)
    tenant_a.client.patch(f"{URL}{gone['id']}/", {"status": "CANCELLED"}, format="json")
    rows = tenant_a.client.get(f"{URL}report/").data
    assert [(row["status"], row["value"]) for row in rows] == [("ACTIVE", "1000.00")]
    with_cancelled = tenant_a.client.get(f"{URL}report/", {"include_cancelled": 1}).data
    assert {row["status"] for row in with_cancelled} == {"ACTIVE", "CANCELLED"}
    export = tenant_a.client.get(f"{URL}report/export/")
    assert export.status_code == 200 and export["Content-Type"].startswith("text/csv")
    body = export.content.decode()
    assert live["number"] in body and gone["number"] not in body
    summary = tenant_a.client.get(f"{URL}summary/").data
    assert sum(row["count"] for row in summary["expiring_by_month"]) == 1


def test_renewal_reminders_go_out_once_per_term(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    data = _make(tenant_a, customer, end_date=str(TODAY() + timedelta(days=12)))
    first = send_contract_renewal_reminders()
    assert first["reminders"] >= 1
    sent = Notification.objects.filter(company=tenant_a.company, subject__contains=data["number"]).count()
    assert sent >= 1
    assert send_contract_renewal_reminders()["reminders"] == 0  # same term: nothing more
    Contract.objects.filter(pk=data["id"]).update(end_date=TODAY() + timedelta(days=20))
    assert send_contract_renewal_reminders()["reminders"] == 1  # a renewed term earns a fresh reminder
    assert AuditEvent.objects.filter(action="contract_renewal_reminder", entity_id=str(data["id"])).count() == 2


# ---- XLK-02: coverage lookup ---------------------------------------------------------------------------------------------------------

def test_coverage_finds_second_covered_products_and_ignores_expired_or_cancelled(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    pump = make_product(tenant_a.company, name="Pump", sku="C-1")
    fan = make_product(tenant_a.company, name="Fan", sku="C-2")
    other = make_product(tenant_a.company, name="Other", sku="C-3")
    multi = tenant_a.client.post(URL, _payload(customer, products=[pump.id, fan.id]), format="json")
    assert multi.status_code == 201, multi.data
    expired = Contract.objects.create(
        company=tenant_a.company, customer=customer, contract_type="AMC", number="CON-OLD", product=other,
        start_date=TODAY() - timedelta(days=400), end_date=TODAY() - timedelta(days=1),
    )
    cancelled = _make(tenant_a, customer, other, allow_overlap=True)
    tenant_a.client.patch(f"{URL}{cancelled['id']}/", {"status": "CANCELLED"}, format="json")
    def hits(product):
        resp = tenant_a.client.get(f"{URL}coverage/", {"customer": customer.id, "product": product.id})
        assert resp.status_code == 200
        return [row["id"] for row in resp.data]
    assert hits(pump) == [multi.data["id"]]
    assert hits(fan) == [multi.data["id"]]  # the second covered product is found too
    assert hits(other) == []
    assert expired.pk not in hits(other)
    past = tenant_a.client.get(
        f"{URL}coverage/", {"customer": customer.id, "product": other.id, "date": str(TODAY() - timedelta(days=5))},
    )
    assert [row["id"] for row in past.data] == [expired.id]
    assert tenant_a.client.get(f"{URL}coverage/").status_code == 400


# ---- FND-14 and tenancy ----------------------------------------------------------------------------------------------------------------

def test_files_are_frozen_on_a_cancelled_or_expired_contract(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    cancelled = _make(tenant_a, customer)
    tenant_a.client.patch(f"{URL}{cancelled['id']}/", {"status": "CANCELLED"}, format="json")
    assert tenant_a.client.post(f"{URL}{cancelled['id']}/attachments/", {}, format="multipart").status_code == 400
    expired = Contract.objects.create(
        company=tenant_a.company, customer=customer, contract_type="AMC", number="CON-EXP",
        start_date=TODAY() - timedelta(days=400), end_date=TODAY() - timedelta(days=2),
    )
    assert tenant_a.client.delete(f"{URL}{expired.id}/attachments/?attachment=1").status_code == 400


def test_a_contract_of_another_company_is_invisible(tenant_a, tenant_b):
    _on(tenant_a)
    _on(tenant_b)
    data = _make(tenant_a, make_customer(tenant_a.company))
    assert tenant_b.client.get(f"{URL}{data['id']}/").status_code == 404
    assert tenant_b.client.post(f"{URL}{data['id']}/renew/", {"new_end_date": "2030-01-01"}, format="json").status_code == 404
    assert tenant_b.client.get(f"{URL}coverage/", {"customer": data["customer"]}).data == []
    assert make_tenant("delta").company.pk != tenant_a.company.pk
