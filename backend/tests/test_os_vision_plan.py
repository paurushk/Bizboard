"""Locked BizBoard OS vision tickets: flags default off, behavior matches the plan."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import override_settings
from django.utils import timezone

from accounts.models import CompanyPackState, CompanyUser
from accounts.packs import apply_pack
from crm.models import Lead, Opportunity
from crm.pipeline import (
    capture_lead,
    ensure_whatsapp_webhook_token,
    find_candidates,
    ingest_whatsapp_message,
    verify_whatsapp_signature,
)
from insights.attention import _attach_assignment, assign_attention_row
from insights.customer_actions import build_customer_action_rows
from insights.event_schema import APPROVAL, EVENT_SOURCES, event_for
from masters.models import Customer
from payments.predictive_dunning import median_days_late
from sales.models import Quotation, SalesOrder, SalesOrderItem
from sales.order_gates import apply_order_gates

pytestmark = pytest.mark.django_db


def _enable(company, *keys):
    flags = dict(company.feature_flags or {})
    for key in keys:
        flags[key] = True
    # Bare ENABLE_CRM JSON no longer grants CRM; the insurance pack is the grant.
    if "ENABLE_CRM" in keys:
        flags.setdefault("pack_grant", "insurance")
    company.feature_flags = flags
    company.save(update_fields=["feature_flags"])


def _body(resp):
    data = resp.data
    if isinstance(data, dict) and isinstance(data.get("data"), (dict, list)):
        return data["data"]
    return data


def _member(tenant):
    return CompanyUser.objects.get(company=tenant.company, user=tenant.owner)


def test_assignment_overdue_starts_the_day_after_due_date(tenant_a):
    _enable(tenant_a.company, "ENABLE_ACTION_ASSIGNMENT")
    member = _member(tenant_a)
    today = timezone.localdate()
    assign_attention_row(
        tenant_a.company,
        member,
        dedupe_key="ROW-1",
        assignee_id=member.id,
        due_date=today.isoformat(),
    )
    today_rows = _attach_assignment(tenant_a.company, [{"dedupe_key": "ROW-1"}])
    assert today_rows[0]["overdue"] is False
    assert today_rows[0]["assigned_to"] == member.id
    assign_attention_row(
        tenant_a.company,
        member,
        dedupe_key="ROW-1",
        assignee_id=member.id,
        due_date=(today - timedelta(days=1)).isoformat(),
    )
    late_rows = _attach_assignment(tenant_a.company, [{"dedupe_key": "ROW-1"}])
    assert late_rows[0]["overdue"] is True


def test_assignment_fields_hidden_when_flag_off(tenant_a):
    _enable(tenant_a.company, "ENABLE_ACTION_ASSIGNMENT")
    member = _member(tenant_a)
    assign_attention_row(
        tenant_a.company,
        member,
        dedupe_key="ROW-2",
        assignee_id=member.id,
        due_date=timezone.localdate().isoformat(),
    )
    tenant_a.company.feature_flags = {}
    tenant_a.company.save(update_fields=["feature_flags"])
    rows = _attach_assignment(tenant_a.company, [{"dedupe_key": "ROW-2"}])
    assert "assigned_to" not in rows[0]


def test_assignment_rejects_a_user_from_another_company(tenant_a, tenant_b):
    _enable(tenant_a.company, "ENABLE_ACTION_ASSIGNMENT")
    from core.exceptions import BusinessRuleError

    with pytest.raises(BusinessRuleError):
        assign_attention_row(
            tenant_a.company,
            _member(tenant_a),
            dedupe_key="ROW-3",
            assignee_id=_member(tenant_b).id,
            due_date=None,
        )


def test_median_days_late_needs_three_paid_invoices(tenant_a):
    from tests.conftest import make_customer

    customer = make_customer(tenant_a.company, name="Cold Start")
    assert median_days_late(tenant_a.company, customer) is None


def test_customer_360_and_collections_are_hidden_until_flagged(tenant_a):
    customer = Customer.objects.filter(company=tenant_a.company).first()
    if customer is None:
        from tests.conftest import make_customer

        customer = make_customer(tenant_a.company)
    assert tenant_a.client.get(f"/api/v1/insights/customers/{customer.id}/360/").status_code == 404
    assert tenant_a.client.get("/api/v1/insights/collections-worklist/").status_code == 404
    _enable(tenant_a.company, "ENABLE_CUSTOMER_360")
    seen = tenant_a.client.get(f"/api/v1/insights/customers/{customer.id}/360/")
    assert seen.status_code == 200, seen.data
    body = _body(seen)
    assert body["customer_id"] == customer.id
    assert "pattern" in body


def test_purchase_planning_requires_replenishment(tenant_a):
    _enable(tenant_a.company, "ENABLE_PURCHASE_PLANNING")
    resp = tenant_a.client.get("/api/v1/inventory/purchase-planning/")
    assert resp.status_code == 400
    assert "replenishment" in str(resp.data).lower()
    off = tenant_a.client.get("/api/v1/inventory/purchase-planning/")
    tenant_a.company.feature_flags = {}
    tenant_a.company.save(update_fields=["feature_flags"])
    assert tenant_a.client.get("/api/v1/inventory/purchase-planning/").status_code == 404
    assert off.status_code == 400


def test_customer_pincode_stays_blank_for_existing_rows(tenant_a):
    from tests.conftest import make_customer

    customer = make_customer(tenant_a.company)
    assert customer.pincode == ""
    customer.pincode = "560001"
    customer.save(update_fields=["pincode"])
    assert Customer.objects.get(pk=customer.id).pincode == "560001"


@override_settings(ENABLE_CRM=True)
def test_manual_lead_dedupe_prompts_instead_of_duplicating(tenant_a):
    from tests.conftest import make_customer

    make_customer(tenant_a.company, name="Existing", phone="9876543210")
    _enable(tenant_a.company, "ENABLE_CRM")
    resp = tenant_a.client.post(
        "/api/v1/crm/leads/",
        {"name": "New", "phone": "9876543210", "email": "new@example.com"},
        format="json",
    )
    assert resp.status_code == 409, resp.data
    assert Lead.objects.filter(company=tenant_a.company, name="New").count() == 0
    created = tenant_a.client.post(
        "/api/v1/crm/leads/",
        {
            "name": "New",
            "phone": "9876543210",
            "email": "other@example.com",
            "dedupe_decision": "review",
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    lead = Lead.objects.get(company=tenant_a.company, name="New")
    assert lead.dedupe_review == "PENDING_REVIEW"
    assert lead.source is None or lead.source in ("", None)


@override_settings(ENABLE_CRM=True)
def test_csv_import_and_public_form(tenant_a):
    _enable(tenant_a.company, "ENABLE_CRM")
    from django.core.files.uploadedfile import SimpleUploadedFile

    upload = SimpleUploadedFile(
        "leads.csv",
        b"name,phone,email,message\nImported,9123456780,imp@example.com,hello\n",
        content_type="text/csv",
    )
    resp = tenant_a.client.post("/api/v1/crm/leads/import-csv/", {"file": upload}, format="multipart")
    assert resp.status_code == 202, resp.data
    assert _body(resp)["status"] == "DONE"
    assert Lead.objects.filter(company=tenant_a.company, source="import").count() == 1
    token = tenant_a.client.post("/api/v1/crm/leads/form-token/")
    assert token.status_code == 200, token.data
    form_token = _body(token)["token"]
    public = tenant_a.client.post(
        f"/api/v1/crm/public/lead-form/{form_token}/",
        {"name": "Web", "phone": "9988776655", "message": "need a quote", "website": ""},
        format="json",
    )
    assert public.status_code == 202, public.data
    assert Lead.objects.filter(company=tenant_a.company, source="website").count() == 1
    honeypot = tenant_a.client.post(
        f"/api/v1/crm/public/lead-form/{form_token}/",
        {"name": "Bot", "phone": "9988776644", "website": "http://spam"},
        format="json",
    )
    assert honeypot.status_code == 200
    assert Lead.objects.filter(company=tenant_a.company, name="Bot").count() == 0


@override_settings(ENABLE_CRM=True, ENABLE_CRM_WHATSAPP_INBOUND=True, WHATSAPP_APP_SECRET="test-secret")
def test_whatsapp_inbound_requires_signature_and_is_idempotent(tenant_a):
    _enable(tenant_a.company, "ENABLE_CRM", "ENABLE_CRM_WHATSAPP_INBOUND")
    tenant_a.company.lead_form_token = "form-token"
    tenant_a.company.whatsapp_webhook_token = "wa-token"
    tenant_a.company.save(update_fields=["lead_form_token", "whatsapp_webhook_token"])
    assert tenant_a.company.lead_form_token != tenant_a.company.whatsapp_webhook_token
    wrong = tenant_a.client.post(
        "/api/v1/crm/public/whatsapp/form-token/",
        {"message_id": "m1", "from": "9876501234", "text": "hi", "timestamp": "1"},
        format="json",
    )
    assert wrong.status_code == 404
    denied = tenant_a.client.post(
        "/api/v1/crm/public/whatsapp/wa-token/",
        {"message_id": "m1", "from": "9876501234", "text": "hi", "timestamp": "1"},
        format="json",
    )
    assert denied.status_code == 403
    assert verify_whatsapp_signature(b"{}", "", "test-secret") is False
    lead = ingest_whatsapp_message(
        tenant_a.company, message_id="m1", sender="9876501234", text="hi", sent_at="1"
    )
    again = ingest_whatsapp_message(
        tenant_a.company, message_id="m1", sender="9876501234", text="hi", sent_at="1"
    )
    assert lead.id == again.id
    assert Lead.objects.filter(company=tenant_a.company, source="whatsapp").count() == 1


def test_whatsapp_webhook_token_is_minted_once_and_the_public_url_does_not(tenant_a):
    from accounts.models import Company

    tenant_a.company.lead_form_token = "form-token"
    tenant_a.company.whatsapp_webhook_token = None
    tenant_a.company.save(update_fields=["lead_form_token", "whatsapp_webhook_token"])
    flags_before = dict(tenant_a.company.feature_flags or {})
    first = ensure_whatsapp_webhook_token(tenant_a.company)
    tenant_a.company.refresh_from_db()
    assert first
    assert tenant_a.company.whatsapp_webhook_token == first
    assert first != tenant_a.company.lead_form_token
    assert ensure_whatsapp_webhook_token(tenant_a.company) == first
    replaced = ensure_whatsapp_webhook_token(tenant_a.company, rotate=True)
    tenant_a.company.refresh_from_db()
    assert replaced != first
    assert tenant_a.company.whatsapp_webhook_token == replaced
    assert dict(tenant_a.company.feature_flags or {}) == flags_before
    assert "ENABLE_CRM_WHATSAPP_INBOUND" not in (tenant_a.company.feature_flags or {})

    stored = set(
        Company.objects.exclude(whatsapp_webhook_token__isnull=True)
        .exclude(whatsapp_webhook_token="")
        .values_list("whatsapp_webhook_token", flat=True)
    )
    missing = tenant_a.client.post(
        "/api/v1/crm/public/whatsapp/not-a-real-token/",
        {"message_id": "m-unknown", "from": "9876501234", "text": "hi", "timestamp": "1"},
        format="json",
    )
    assert missing.status_code == 404
    handshake = tenant_a.client.get("/api/v1/crm/public/whatsapp/not-a-real-token/")
    assert handshake.status_code == 404
    assert stored == set(
        Company.objects.exclude(whatsapp_webhook_token__isnull=True)
        .exclude(whatsapp_webhook_token="")
        .values_list("whatsapp_webhook_token", flat=True)
    )


@override_settings(ENABLE_CRM=True)
def test_owner_issues_whatsapp_token_and_meta_can_verify_before_the_flag(tenant_a):
    _enable(tenant_a.company, "ENABLE_CRM")
    denied = tenant_a.staff_client.post("/api/v1/crm/leads/whatsapp-token/", {}, format="json")
    assert denied.status_code == 403
    issued = tenant_a.client.post("/api/v1/crm/leads/whatsapp-token/", {}, format="json")
    assert issued.status_code == 200, issued.data
    token = _body(issued)["token"]
    again = tenant_a.client.post("/api/v1/crm/leads/whatsapp-token/", {}, format="json")
    assert _body(again)["token"] == token
    challenge = tenant_a.client.get(
        f"/api/v1/crm/public/whatsapp/{token}/",
        {"hub.mode": "subscribe", "hub.verify_token": token, "hub.challenge": "chal-1"},
    )
    assert challenge.status_code == 200
    assert challenge.content == b"chal-1"
    wrong = tenant_a.client.get(
        f"/api/v1/crm/public/whatsapp/{token}/",
        {"hub.mode": "subscribe", "hub.verify_token": "other", "hub.challenge": "chal-1"},
    )
    assert wrong.status_code == 403
    inbound = tenant_a.client.post(
        f"/api/v1/crm/public/whatsapp/{token}/",
        {"message_id": "m1", "from": "9876501234", "text": "hi", "timestamp": "1"},
        format="json",
    )
    assert inbound.status_code == 404
    rotated = tenant_a.client.post("/api/v1/crm/leads/whatsapp-token/", {"rotate": True}, format="json")
    new_token = _body(rotated)["token"]
    assert new_token != token
    stale = tenant_a.client.get(
        f"/api/v1/crm/public/whatsapp/{token}/",
        {"hub.mode": "subscribe", "hub.verify_token": token, "hub.challenge": "chal-1"},
    )
    assert stale.status_code == 404
    fresh = tenant_a.client.get(
        f"/api/v1/crm/public/whatsapp/{new_token}/",
        {"hub.mode": "subscribe", "hub.verify_token": new_token, "hub.challenge": "chal-2"},
    )
    assert fresh.status_code == 200
    assert fresh.content == b"chal-2"
    from accounts.models import Company

    tenant_a.company.lead_form_token = "form-token"
    tenant_a.company.whatsapp_webhook_token = None
    tenant_a.company.save(update_fields=["lead_form_token", "whatsapp_webhook_token"])
    flags_before = dict(tenant_a.company.feature_flags or {})
    first = ensure_whatsapp_webhook_token(tenant_a.company)
    tenant_a.company.refresh_from_db()
    assert first
    assert tenant_a.company.whatsapp_webhook_token == first
    assert first != tenant_a.company.lead_form_token
    assert ensure_whatsapp_webhook_token(tenant_a.company) == first
    assert dict(tenant_a.company.feature_flags or {}) == flags_before
    assert "ENABLE_CRM_WHATSAPP_INBOUND" not in (tenant_a.company.feature_flags or {})

    tenant_a.company.whatsapp_webhook_token = "keep-me"
    tenant_a.company.save(update_fields=["whatsapp_webhook_token"])
    assert ensure_whatsapp_webhook_token(tenant_a.company) == "keep-me"

    stored = set(
        Company.objects.exclude(whatsapp_webhook_token__isnull=True)
        .exclude(whatsapp_webhook_token="")
        .values_list("whatsapp_webhook_token", flat=True)
    )
    missing = tenant_a.client.post(
        "/api/v1/crm/public/whatsapp/not-a-real-token/",
        {"message_id": "m-unknown", "from": "9876501234", "text": "hi", "timestamp": "1"},
        format="json",
    )
    assert missing.status_code == 404
    assert stored == set(
        Company.objects.exclude(whatsapp_webhook_token__isnull=True)
        .exclude(whatsapp_webhook_token="")
        .values_list("whatsapp_webhook_token", flat=True)
    )


@override_settings(ENABLE_CRM=True)
def test_won_opportunity_creates_a_blank_quotation(tenant_a):
    _enable(tenant_a.company, "ENABLE_CRM")
    from tests.conftest import make_customer

    customer = make_customer(tenant_a.company, name="Won Co", phone="9000001111")
    opportunity = Opportunity.objects.create(
        company=tenant_a.company,
        customer=customer,
        title="Deal",
        stage=Opportunity.Stage.OPEN,
        created_by=tenant_a.owner,
    )
    denied = tenant_a.client.post(f"/api/v1/crm/opportunities/{opportunity.id}/quotation/")
    assert denied.status_code == 400
    opportunity.stage = Opportunity.Stage.WON
    opportunity.save(update_fields=["stage"])
    created = tenant_a.client.post(f"/api/v1/crm/opportunities/{opportunity.id}/quotation/")
    assert created.status_code == 201, created.data
    quotation = Quotation.objects.get(pk=_body(created)["id"])
    assert quotation.customer_id == customer.id
    assert quotation.opportunity_id == opportunity.id
    assert quotation.items.count() == 0
    # An open quote for the same opportunity is returned, not duplicated.
    second = tenant_a.client.post(f"/api/v1/crm/opportunities/{opportunity.id}/quotation/")
    assert second.status_code == 200
    assert _body(second)["id"] == quotation.id
    assert _body(second)["already_exists"] is True
    assert Quotation.objects.filter(opportunity=opportunity).count() == 1
    # Once that quote is cancelled the deal can be quoted again.
    Quotation.objects.filter(pk=quotation.pk).update(status=Quotation.Status.CANCELLED)
    third = tenant_a.client.post(f"/api/v1/crm/opportunities/{opportunity.id}/quotation/")
    assert third.status_code == 201
    assert Quotation.objects.filter(opportunity=opportunity).count() == 2


@override_settings(ENABLE_ORDER_GATES=True)
def test_sales_order_credit_blocks_and_margin_warns(tenant_a):
    from tests.conftest import make_customer, make_product

    _enable(tenant_a.company, "ENABLE_ORDER_GATES")
    customer = make_customer(tenant_a.company, name="Credit Co", credit_limit=Decimal("100.00"))
    product = make_product(tenant_a.company, sku="GATE-1", purchase_price="96")
    order = SalesOrder.objects.create(
        company=tenant_a.company,
        customer=customer,
        grand_total=Decimal("150.00"),
        created_by=tenant_a.owner,
    )
    item = SalesOrderItem.objects.create(
        company=tenant_a.company,
        sales_order=order,
        product=product,
        quantity=Decimal("1"),
        unit_price=Decimal("100.00"),
    )
    from core.exceptions import BusinessRuleError

    with pytest.raises(BusinessRuleError):
        apply_order_gates(order, [item])
    customer.credit_limit = Decimal("0")
    customer.save(update_fields=["credit_limit"])
    warnings = apply_order_gates(order, [item])
    assert warnings
    assert warnings[0]["product_id"] == product.id
    from sales.notes_services import SalesNotesService

    with pytest.raises(BusinessRuleError, match="Confirm this sales order"):
        SalesNotesService.convert_sales_order(order, tenant_a.owner)
    with pytest.raises(BusinessRuleError, match="Confirm this sales order"):
        SalesNotesService.convert_sales_order_to_challan(order, tenant_a.owner)


def test_thin_history_does_not_emit_churn(tenant_a):
    _enable(tenant_a.company, "ENABLE_CUSTOMER_ACTIONS")
    assert build_customer_action_rows(tenant_a.company) == []


def test_route_combine_groups_only_matching_pincodes(tenant_a):
    from sales.route_combine import combine_suggestions

    assert combine_suggestions(tenant_a.company) is None
    _enable(tenant_a.company, "ENABLE_ROUTE_OPTIMIZATION")
    assert combine_suggestions(tenant_a.company) == []


def test_pack_confirm_does_not_overwrite_a_manual_deviation(tenant_a):
    _enable(tenant_a.company, "ENABLE_ARCHETYPE_PACKS", "ENABLE_POS")
    apply_pack(
        tenant_a.company,
        "retail",
        {"what_you_sell": "goods", "how_you_sell": "counter", "deliver": "no", "gst_registered": "yes"},
        tenant_a.owner,
    )
    flags = dict(tenant_a.company.feature_flags)
    flags["ENABLE_POS"] = False
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    apply_pack(
        tenant_a.company,
        "retail",
        {"what_you_sell": "goods", "how_you_sell": "counter", "deliver": "no", "gst_registered": "yes"},
        tenant_a.owner,
    )
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.feature_flags["ENABLE_POS"] is False
    assert "ENABLE_PAYROLL" not in (CompanyPackState.objects.get(company=tenant_a.company).applied_flags)


def test_event_schema_treats_only_assignment_as_approval():
    assert event_for("CHURN_RISK")["approval"] == APPROVAL
    assert "dismiss" in event_for("CHURN_RISK")["not_approval"]
    assert "PREDICTED_LATE_PAYMENT" in EVENT_SOURCES
    assert "AR_COLLECTION_RISK" in EVENT_SOURCES
    assert "score" not in str(EVENT_SOURCES)


def test_split_phone_and_email_is_not_a_single_match(tenant_a):
    from tests.conftest import make_customer

    first = make_customer(tenant_a.company, name="Phone", phone="9111222333")
    second = make_customer(tenant_a.company, name="Email", email="split@example.com", phone="9222333444")
    found = find_candidates(tenant_a.company, first.phone, second.email)
    assert len(found["customers"]) == 2


def test_capture_lead_without_phone_or_email_succeeds(tenant_a):
    """Not every manual capture has contact details on hand yet (e.g. a name
    jotted down mid-call) -- there's simply nothing to dedupe against."""
    lead = capture_lead(tenant_a.company, tenant_a.owner, name="Just A Name", manual=True)
    assert lead.id is not None
    assert lead.phone == ""
    assert lead.email == ""
    assert lead.dedupe_review == ""


def test_async_capture_does_not_escalate_a_single_clean_match(tenant_a):
    """Only an explicit review decision, or genuine ambiguity, should send a
    lead to PENDING_REVIEW -- a single clean match on an async channel used
    to be escalated unconditionally, making every returning customer via
    WhatsApp/CSV/web-form indistinguishable from a real multi-party match."""
    from tests.conftest import make_customer

    existing = make_customer(tenant_a.company, name="Returning", phone="9812345670")
    lead = capture_lead(
        tenant_a.company, None, name="Returning", phone="9812345670",
        source="whatsapp", manual=False,
    )
    assert lead.dedupe_review == ""
    assert lead.dedupe_matched_customer_id == existing.id


def test_converted_lead_is_not_a_second_party_on_repeat_contact(tenant_a):
    """convert_lead() never deletes or excludes the source Lead -- it just
    stamps customer_id and QUALIFIED. Without excluding already-converted
    leads, that lead and its own resulting Customer both match on the next
    contact, permanently misreading one real party as two."""
    from tests.conftest import make_customer

    customer = make_customer(tenant_a.company, name="Once", phone="9812340001")
    lead = capture_lead(
        tenant_a.company, tenant_a.owner, name="Once Lead", phone="9812340001",
        manual=True, dedupe_decision="create",
    )
    lead.customer = customer
    lead.status = Lead.Status.QUALIFIED
    lead.save(update_fields=["customer", "status"])
    found = find_candidates(tenant_a.company, "9812340001", "")
    assert found["customers"] == [customer.id]
    assert found["leads"] == []


@override_settings(ENABLE_CRM=True)
def test_resolve_dedupe_new_clears_pending_review(tenant_a):
    from tests.conftest import make_customer

    make_customer(tenant_a.company, name="Match", phone="9812340099")
    _enable(tenant_a.company, "ENABLE_CRM")
    created = tenant_a.client.post(
        "/api/v1/crm/leads/",
        {"name": "Ambi", "phone": "9812340099", "email": "ambi@example.com", "dedupe_decision": "review"},
        format="json",
    )
    assert created.status_code == 201, created.data
    lead_id = _body(created)["id"]
    lead = Lead.objects.get(pk=lead_id)
    assert lead.dedupe_review == "PENDING_REVIEW"
    still_stuck = tenant_a.client.post(
        f"/api/v1/crm/leads/{lead_id}/resolve-dedupe/", {"decision": ""}, format="json",
    )
    assert still_stuck.status_code == 400
    resolved = tenant_a.client.post(
        f"/api/v1/crm/leads/{lead_id}/resolve-dedupe/", {"decision": "new"}, format="json",
    )
    assert resolved.status_code == 200, resolved.data
    lead.refresh_from_db()
    assert lead.dedupe_review == ""
    assert lead.assigned_to_id is not None


@override_settings(ENABLE_CRM=True)
def test_resolve_dedupe_match_must_be_a_recorded_candidate(tenant_a):
    from tests.conftest import make_customer

    matched = make_customer(tenant_a.company, name="Recorded", phone="9812340098")
    unrelated = make_customer(tenant_a.company, name="Unrelated", phone="9812340097")
    _enable(tenant_a.company, "ENABLE_CRM")
    created = tenant_a.client.post(
        "/api/v1/crm/leads/",
        {"name": "Ambi2", "phone": "9812340098", "email": "ambi2@example.com", "dedupe_decision": "review"},
        format="json",
    )
    lead_id = _body(created)["id"]
    rejected = tenant_a.client.post(
        f"/api/v1/crm/leads/{lead_id}/resolve-dedupe/",
        {"decision": "match", "customer_id": unrelated.id},
        format="json",
    )
    assert rejected.status_code == 400
    accepted = tenant_a.client.post(
        f"/api/v1/crm/leads/{lead_id}/resolve-dedupe/",
        {"decision": "match", "customer_id": matched.id},
        format="json",
    )
    assert accepted.status_code == 200, accepted.data
    lead = Lead.objects.get(pk=lead_id)
    assert lead.dedupe_review == ""
    assert lead.customer_id == matched.id


@override_settings(ENABLE_CRM=True)
def test_resolve_dedupe_new_clears_previously_recorded_match(tenant_a):
    """A single unambiguous match sent to review pre-populates
    dedupe_matched_customer/lead alongside PENDING_REVIEW -- rejecting it
    as "new" must clear those stale pointers too, not just the review flag."""
    from tests.conftest import make_customer

    matched = make_customer(tenant_a.company, name="Stale Match", phone="9812340096")
    _enable(tenant_a.company, "ENABLE_CRM")
    created = tenant_a.client.post(
        "/api/v1/crm/leads/",
        {"name": "Ambi3", "phone": "9812340096", "email": "ambi3@example.com", "dedupe_decision": "review"},
        format="json",
    )
    lead_id = _body(created)["id"]
    lead = Lead.objects.get(pk=lead_id)
    assert lead.dedupe_matched_customer_id == matched.id
    resolved = tenant_a.client.post(
        f"/api/v1/crm/leads/{lead_id}/resolve-dedupe/", {"decision": "new"}, format="json",
    )
    assert resolved.status_code == 200, resolved.data
    lead.refresh_from_db()
    assert lead.dedupe_review == ""
    assert lead.dedupe_matched_customer_id is None
    assert lead.dedupe_matched_lead_id is None


@override_settings(ENABLE_CRM=True)
def test_resolve_dedupe_rejects_malformed_ids_with_400_not_500(tenant_a):
    from tests.conftest import make_customer

    make_customer(tenant_a.company, name="Malformed", phone="9812340095")
    _enable(tenant_a.company, "ENABLE_CRM")
    created = tenant_a.client.post(
        "/api/v1/crm/leads/",
        {"name": "Ambi4", "phone": "9812340095", "email": "ambi4@example.com", "dedupe_decision": "review"},
        format="json",
    )
    lead_id = _body(created)["id"]
    bad = tenant_a.client.post(
        f"/api/v1/crm/leads/{lead_id}/resolve-dedupe/",
        {"decision": "match", "customer_id": "not-an-int"},
        format="json",
    )
    assert bad.status_code == 400
    assert "integer" in bad.data.get("detail", "").lower()
    lead = Lead.objects.get(pk=lead_id)
    assert lead.dedupe_review == "PENDING_REVIEW"


def test_resolve_dedupe_wraps_the_reassignment_in_one_transaction():
    """next_assignee() takes its own row lock internally; resolve_dedupe must
    hold that lock open until its own save() persists assigned_to, or two
    concurrent resolves can both read the same least-loaded snapshot and
    double-assign -- the exact race the round-robin lock exists to prevent."""
    import inspect

    from crm.views import LeadViewSet

    source = inspect.getsource(LeadViewSet.resolve_dedupe)
    assert "transaction.atomic" in source
    atomic_at = source.index("transaction.atomic")
    assign_at = source.index("next_assignee(")
    save_at = source.index(".save(")
    assert atomic_at < assign_at < save_at


def test_assign_attention_row_partial_update_preserves_the_other_field(tenant_a):
    """Omitting one field to update only the other must not silently clear
    the field left alone."""
    _enable(tenant_a.company, "ENABLE_ACTION_ASSIGNMENT")
    member = _member(tenant_a)
    today = timezone.localdate()
    assign_attention_row(
        tenant_a.company, member, dedupe_key="ROW-PARTIAL",
        assignee_id=member.id, due_date=today.isoformat(),
    )
    assign_attention_row(
        tenant_a.company, member, dedupe_key="ROW-PARTIAL",
        due_date=(today + timedelta(days=5)).isoformat(),
    )
    rows = _attach_assignment(tenant_a.company, [{"dedupe_key": "ROW-PARTIAL"}])
    assert rows[0]["assigned_to"] == member.id
    assert rows[0]["due_date"] == (today + timedelta(days=5)).isoformat()
    assign_attention_row(tenant_a.company, member, dedupe_key="ROW-PARTIAL", assignee_id=member.id)
    rows_after = _attach_assignment(tenant_a.company, [{"dedupe_key": "ROW-PARTIAL"}])
    assert rows_after[0]["due_date"] == (today + timedelta(days=5)).isoformat()


def test_assign_view_full_utc_timestamp_lands_on_the_correct_local_date(tenant_a):
    """A browser's Date.toISOString() is always UTC -- slicing the first 10
    characters used to assume it was already local time and could land a
    day early for anyone east of UTC (IST here, matching this repo's
    server timezone)."""
    _enable(tenant_a.company, "ENABLE_ACTION_ASSIGNMENT")
    member = _member(tenant_a)
    resp = tenant_a.client.post(
        "/api/v1/insights/attention/assign/",
        {"dedupe_key": "ROW-TZ", "assigned_to": member.id, "due_date": "2026-09-24T18:30:00.000Z"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    assert _body(resp)["due_date"] == "2026-09-25"


def test_predicted_and_customer_action_rows_are_not_blocked_by_the_raw_cache(tenant_a):
    """Attention's raw-row cache is keyed by (company, as_of) and lives for
    60s. Predicted-dunning and customer-action rows must be computed after
    that cached read, not inside it, so a same-as_of second call still
    reflects new order data instead of returning the stale cached list."""
    from datetime import date as date_cls

    from insights.attention import build_attention_rows
    from tests.conftest import make_customer

    _enable(tenant_a.company, "ENABLE_CUSTOMER_ACTIONS")
    customer = make_customer(tenant_a.company, name="Cache Co")
    as_of = date_cls(2026, 11, 15)
    warm = build_attention_rows(tenant_a.company, as_of=as_of)
    assert not any(row["code"] == "CHURN_RISK" for row in warm)
    for when in (date_cls(2026, 1, 1), date_cls(2026, 4, 1), date_cls(2026, 7, 1)):
        SalesOrder.objects.create(
            company=tenant_a.company, customer=customer, status=SalesOrder.Status.CONFIRMED,
            order_date=when, grand_total=Decimal("100"),
        )
    again = build_attention_rows(tenant_a.company, as_of=as_of)
    assert any(row["code"] == "CHURN_RISK" for row in again)


def test_customer_actions_ignore_orders_dated_after_as_of(tenant_a):
    """A post-dated/advance order (or a historical as_of replay) must not
    count as 'the last order' -- otherwise the computed gap goes negative
    and churn risk can silently never fire for a genuinely overdue customer."""
    from datetime import date as date_cls

    from tests.conftest import make_customer

    _enable(tenant_a.company, "ENABLE_CUSTOMER_ACTIONS")
    customer = make_customer(tenant_a.company, name="Postdated Co")
    for when in (date_cls(2026, 1, 1), date_cls(2026, 4, 1), date_cls(2026, 7, 1)):
        SalesOrder.objects.create(
            company=tenant_a.company, customer=customer, status=SalesOrder.Status.CONFIRMED,
            order_date=when, grand_total=Decimal("100"),
        )
    SalesOrder.objects.create(
        company=tenant_a.company, customer=customer, status=SalesOrder.Status.CONFIRMED,
        order_date=date_cls(2026, 12, 1), grand_total=Decimal("999"),
    )
    rows = build_customer_action_rows(tenant_a.company, as_of=date_cls(2026, 11, 15))
    assert any(row["code"] == "CHURN_RISK" for row in rows)


def test_lead_form_throttle_key_is_per_caller_not_shared():
    """Keying only on the company's form token made one shared 20/min bucket
    for every visitor -- a single abusive caller could throttle out
    everyone else submitting that company's real public form."""
    from django.test import RequestFactory

    from crm.views import LeadFormThrottle

    class FakeView:
        kwargs = {"token": "tok-1"}
        throttle_scope = "lead_form"

    factory = RequestFactory()
    request_a = factory.post("/x", REMOTE_ADDR="1.1.1.1")
    request_b = factory.post("/x", REMOTE_ADDR="2.2.2.2")
    throttle = LeadFormThrottle()
    key_a = throttle.get_cache_key(request_a, FakeView())
    key_b = throttle.get_cache_key(request_b, FakeView())
    assert key_a != key_b
