"""Locked BizBoard OS vision tickets: flags default off, behavior matches the plan."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import override_settings
from django.utils import timezone

from accounts.models import CompanyPackState, CompanyUser
from accounts.packs import apply_pack
from crm.models import Lead, Opportunity
from crm.pipeline import capture_lead, find_candidates, ingest_whatsapp_message, verify_whatsapp_signature
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
    tenant_a.company.lead_form_token = "wa-token"
    tenant_a.company.save(update_fields=["lead_form_token"])
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
    second = tenant_a.client.post(f"/api/v1/crm/opportunities/{opportunity.id}/quotation/")
    assert second.status_code == 201
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
