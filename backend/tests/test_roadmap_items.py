"""Roadmap items: role, packs, POD, job card, projects, vendor share, insurance, SaaS ops."""

from datetime import timedelta

import pytest
from django.core.files.base import ContentFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Company, CompanyUser, User
from accounts.packs import HELD_PACKS, PACKS, apply_pack, propose_pack
from billing.models import Plan, Subscription
from core.exceptions import BusinessRuleError
from core.models import AuditEvent, FileAsset
from core.services.feature_flags import flag_enabled
from inventory.models import StockMovement
from masters.models import Product
from sales.models import DeliveryRoute, DeliveryRouteStop, SalesInvoice, SalesOrder
from support.models import Ticket
from support.share import share_ticket
from tests.conftest import add_stock, make_customer, make_product

pytestmark = pytest.mark.django_db


def _plan(company):
    plan = Plan.objects.create(name="T", slug=f"t-{company.pk}", modules={"ENABLE_POS": True})
    Subscription.objects.create(company=company, plan=plan, status=Subscription.Status.TRIAL, trial_ends_at=timezone.now() + timedelta(days=14))
    return plan


def test_retail_and_trade_do_not_grant_dark_modules(tenant_a):
    _plan(tenant_a.company)
    for pack in ("retail", "trade"):
        apply_pack(tenant_a.company, pack, {}, tenant_a.owner)
        tenant_a.company.refresh_from_db()
        flags = tenant_a.company.feature_flags or {}
        assert "ENABLE_CRM" not in flags
        assert "ENABLE_MANUFACTURING" not in flags
        assert "ENABLE_PAYROLL" not in flags
        assert flag_enabled(tenant_a.company, "ENABLE_CRM") is False
    tenant_a.company.feature_flags = {"ENABLE_CRM": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    assert flag_enabled(tenant_a.company, "ENABLE_CRM") is False


def test_manufacturing_pack_grants_the_module(tenant_a):
    assert HELD_PACKS == ()
    assert "manufacturing" in PACKS
    assert "distribution" in PACKS
    assert propose_pack({"how_you_sell": "counter"}) == "retail"
    assert propose_pack({"how_you_sell": "field"}) == "trade"
    _plan(tenant_a.company)
    apply_pack(tenant_a.company, "manufacturing", {}, tenant_a.owner)
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.feature_flags.get("manufacturing_pack_grant") is True
    assert flag_enabled(tenant_a.company, "ENABLE_MANUFACTURING") is True
    assert flag_enabled(tenant_a.company, "ENABLE_CRM") is False
    assert flag_enabled(tenant_a.company, "ENABLE_PAYROLL") is False
    assert tenant_a.company.feature_flags.get("pack_grant") != "insurance"


def test_distribution_pack_skips_dark_modules(tenant_a):
    _plan(tenant_a.company)
    apply_pack(tenant_a.company, "distribution", {}, tenant_a.owner)
    tenant_a.company.refresh_from_db()
    flags = tenant_a.company.feature_flags or {}
    assert flags.get("ENABLE_CRM") is not True
    assert flags.get("ENABLE_MANUFACTURING") is not True
    assert flags.get("ENABLE_PAYROLL") is not True
    assert "manufacturing_pack_grant" not in flags
    assert flags.get("pack_grant") != "insurance"
    assert flags.get("ENABLE_ROUTE_PROFIT") is True
    assert flag_enabled(tenant_a.company, "ENABLE_CRM") is False
    assert flag_enabled(tenant_a.company, "ENABLE_MANUFACTURING") is False
    assert flag_enabled(tenant_a.company, "ENABLE_ROUTE_PROFIT") is True
    assert propose_pack({"how_you_sell": "counter"}) == "retail"
    assert propose_pack({"how_you_sell": "field"}) == "trade"


def test_insurance_pack_grants_the_sell_loop(tenant_a):
    _plan(tenant_a.company)
    apply_pack(tenant_a.company, "insurance", {}, tenant_a.owner)
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.feature_flags["pack_grant"] == "insurance"
    assert flag_enabled(tenant_a.company, "ENABLE_CRM") is True
    assert flag_enabled(tenant_a.company, "ENABLE_INSURANCE") is True
    assert flag_enabled(tenant_a.company, "ENABLE_REFERRALS") is True
    assert flag_enabled(tenant_a.company, "ENABLE_SUPPORT_TICKETS") is True
    assert flag_enabled(tenant_a.company, "ENABLE_COMPLAINTS") is True


def test_policy_desk_invite_cannot_post_money(tenant_a):
    resp = tenant_a.client.post(
        "/api/v1/company/users/",
        {"email": "desk@x.test", "full_name": "Desk", "password": "StrongPass123!", "role": "POLICY_DESK"},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    cu = CompanyUser.objects.get(user__email="desk@x.test")
    assert cu.can_manage_policies is True
    assert cu.can_create_sales is False
    user = cu.user
    client = APIClient()
    client.force_authenticate(user=user)
    denied = client.post("/api/v1/sales/invoices/", {"customer": 1}, format="json")
    assert denied.status_code == 403
    denied_journal = client.post("/api/v1/accounting/journals/", {}, format="json")
    assert denied_journal.status_code == 403
    denied_tb = client.get("/api/v1/accounting/trial-balance/")
    assert denied_tb.status_code == 403
    denied_import = client.post("/api/v1/imports/", {}, format="json")
    assert denied_import.status_code == 403
    sales = CompanyUser.objects.get(company=tenant_a.company, role="SALES_STAFF")
    patch = tenant_a.client.patch(
        f"/api/v1/company/users/{sales.id}/",
        {"can_manage_policies": True},
        format="json",
    )
    assert patch.status_code == 400


def _route(company, customer):
    order = SalesOrder.objects.create(company=company, customer=customer)
    route = DeliveryRoute.objects.create(company=company, route_date=timezone.localdate(), status=DeliveryRoute.Status.IN_TRANSIT)
    stop = DeliveryRouteStop.objects.create(company=company, route=route, sales_order=order)
    return route, stop


def test_delivered_stop_requires_receiver_and_does_not_post(tenant_a):
    from sales.route_service import RouteService

    customer = make_customer(tenant_a.company)
    route, stop = _route(tenant_a.company, customer)
    before = StockMovement.objects.filter(company=tenant_a.company).count()
    with pytest.raises(BusinessRuleError):
        RouteService.set_stop_status(route, stop, "DELIVERED", tenant_a.owner)
    RouteService.set_stop_status(route, stop, "DELIVERED", tenant_a.owner, received_by_name="Ravi")
    stop.refresh_from_db()
    assert stop.received_by_name == "Ravi"
    assert StockMovement.objects.filter(company=tenant_a.company).count() == before
    planned = DeliveryRoute.objects.create(company=tenant_a.company, route_date=timezone.localdate())
    pending = DeliveryRouteStop.objects.create(company=tenant_a.company, route=planned, sales_order=order_for(tenant_a.company, customer))
    with pytest.raises(BusinessRuleError):
        RouteService.set_stop_status(planned, pending, "DELIVERED", tenant_a.owner, received_by_name="Ravi")


def order_for(company, customer):
    return SalesOrder.objects.create(company=company, customer=customer)


def test_pod_rejects_other_customer_receipt(tenant_a, tenant_b):
    from payments.models import CustomerReceipt
    from sales.route_service import RouteService

    customer = make_customer(tenant_a.company)
    other = make_customer(tenant_a.company, name="Other")
    route, stop = _route(tenant_a.company, customer)
    foreign = CustomerReceipt.objects.create(company=tenant_b.company, customer=make_customer(tenant_b.company), amount=10)
    with pytest.raises(BusinessRuleError):
        RouteService.set_stop_status(route, stop, "DELIVERED", tenant_a.owner, received_by_name="Ravi", customer_receipt=foreign)
    mismatch = CustomerReceipt.objects.create(company=tenant_a.company, customer=other, amount=10)
    with pytest.raises(BusinessRuleError):
        RouteService.set_stop_status(route, stop, "DELIVERED", tenant_a.owner, received_by_name="Ravi", customer_receipt=mismatch)


def test_pod_slip_after_route_completed(tenant_a):
    from sales.pod_slip import render_pod_pdf
    from sales.route_service import RouteService

    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company)
    route, stop = _route(tenant_a.company, customer)
    from sales.models import SalesOrderItem

    SalesOrderItem.objects.create(
        company=tenant_a.company, sales_order=stop.sales_order, product=product, quantity=1, unit_price=10,
    )
    RouteService.set_stop_status(route, stop, "DELIVERED", tenant_a.owner, received_by_name="Ravi")
    route.status = DeliveryRoute.Status.COMPLETED
    route.save(update_fields=["status"])
    stop.refresh_from_db()
    body = render_pod_pdf(stop)
    assert body.startswith(b"%PDF")
    resp = tenant_a.client.get(f"/api/v1/sales/delivery-routes/{route.id}/stops/{stop.id}/pod.pdf")
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"


def test_job_card_converts_once_and_blocks_policy_desk(tenant_a):
    tenant_a.company.feature_flags = {"ENABLE_WORKSHOP": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    customer = make_customer(tenant_a.company)
    part = make_product(tenant_a.company, name="Spare", sku="SP", product_type=Product.ProductType.GOODS)
    labour = make_product(tenant_a.company, name="Labour", sku="LB", product_type=Product.ProductType.SERVICE, gst_rate="18")
    stock_as_labour = tenant_a.client.post(
        "/api/v1/workshop/job-cards/",
        {"customer": customer.id, "complaint": "No start"},
        format="json",
    )
    assert stock_as_labour.status_code == 201, stock_as_labour.data
    job_id = stock_as_labour.data["id"]
    bad = tenant_a.client.post(
        f"/api/v1/workshop/job-cards/{job_id}/lines/",
        {"kind": "LABOUR", "product": part.id, "quantity": "1", "unit_price": "100"},
        format="json",
    )
    assert bad.status_code == 400
    bad_part = tenant_a.client.post(
        f"/api/v1/workshop/job-cards/{job_id}/lines/",
        {"kind": "PART", "product": labour.id, "quantity": "1", "unit_price": "100"},
        format="json",
    )
    assert bad_part.status_code == 400
    ok = tenant_a.client.post(
        f"/api/v1/workshop/job-cards/{job_id}/lines/",
        {"kind": "PART", "product": part.id, "quantity": "1", "unit_price": "100"},
        format="json",
    )
    assert ok.status_code == 200, ok.data
    before = StockMovement.objects.filter(company=tenant_a.company).count()
    converted = tenant_a.client.post(f"/api/v1/workshop/job-cards/{job_id}/convert/")
    assert converted.status_code == 200, converted.data
    invoice_id = converted.data["sales_invoice"]
    again = tenant_a.client.post(f"/api/v1/workshop/job-cards/{job_id}/convert/")
    assert again.data["sales_invoice"] == invoice_id
    assert SalesInvoice.objects.filter(company=tenant_a.company).count() == 1
    assert StockMovement.objects.filter(company=tenant_a.company).count() == before
    add_stock(tenant_a, part, "5")
    from sales.services import SalesService

    SalesService.complete(SalesInvoice.objects.get(pk=invoice_id), tenant_a.owner)
    assert StockMovement.objects.filter(company=tenant_a.company, product=part, quantity__lt=0).exists()
    cancel = tenant_a.client.post(f"/api/v1/workshop/job-cards/{job_id}/cancel/")
    assert cancel.status_code == 400
    desk = User.objects.create_user(email="p12@x.test", password="StrongPass123!", full_name="P12")
    CompanyUser.objects.create(
        company=tenant_a.company, user=desk, role=CompanyUser.Role.POLICY_DESK, can_manage_policies=True,
    )
    client = APIClient()
    client.force_authenticate(user=desk)
    denied = client.post("/api/v1/workshop/job-cards/", {"customer": customer.id}, format="json")
    assert denied.status_code == 403


def test_project_milestones_invoice_once(tenant_a):
    tenant_a.company.feature_flags = {"ENABLE_PROJECTS": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    customer = make_customer(tenant_a.company)
    service = make_product(tenant_a.company, name="Civil", sku="CV", product_type=Product.ProductType.SERVICE)
    goods = make_product(tenant_a.company, name="Cement", sku="CM")
    created = tenant_a.client.post("/api/v1/projects/", {"customer": customer.id, "name": "Site"}, format="json")
    assert created.status_code == 201, created.data
    pid = created.data["id"]
    stock = tenant_a.client.post(
        f"/api/v1/projects/{pid}/milestones/",
        {"name": "Cement", "amount": "1000", "service_product": goods.id, "sequence": 1},
        format="json",
    )
    assert stock.status_code == 400
    for seq, name in ((1, "Foundation"), (2, "Handover")):
        row = tenant_a.client.post(
            f"/api/v1/projects/{pid}/milestones/",
            {"name": name, "amount": "1000", "service_product": service.id, "sequence": seq},
            format="json",
        )
        assert row.status_code == 200, row.data
    detail = tenant_a.client.get(f"/api/v1/projects/{pid}/")
    ids = [m["id"] for m in detail.data["milestones"]]
    tenant_a.client.post(f"/api/v1/projects/{pid}/milestones/{ids[0]}/ready/")
    tenant_a.client.post(f"/api/v1/projects/{pid}/milestones/{ids[1]}/ready/")
    first = tenant_a.client.post(f"/api/v1/projects/{pid}/milestones/{ids[0]}/invoice/")
    second = tenant_a.client.post(f"/api/v1/projects/{pid}/milestones/{ids[1]}/invoice/")
    again = tenant_a.client.post(f"/api/v1/projects/{pid}/milestones/{ids[0]}/invoice/")
    assert first.data["milestones"][0]["sales_invoice"] == again.data["milestones"][0]["sales_invoice"]
    assert first.data["milestones"][0]["sales_invoice"] != second.data["milestones"][1]["sales_invoice"]
    assert SalesInvoice.objects.filter(company=tenant_a.company).count() == 2
    off = tenant_a.company
    off.feature_flags = {}
    off.save(update_fields=["feature_flags"])
    hidden = tenant_a.client.get("/api/v1/projects/")
    assert hidden.status_code == 404


@override_settings(VENDOR_COMPANY_ID="")
def test_share_404_when_vendor_unset(tenant_a):
    tenant_a.company.feature_flags = {"ENABLE_SUPPORT_TICKETS": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    customer = make_customer(tenant_a.company)
    ticket = Ticket.objects.create(company=tenant_a.company, customer=customer, subject="Help", number="TKT-1")
    resp = tenant_a.client.post(f"/api/v1/support/tickets/{ticket.id}/share/", {}, format="json")
    assert resp.status_code == 404
    from support.models import VendorTicketShare

    assert VendorTicketShare.objects.count() == 0


@override_settings(VENDOR_COMPANY_ID="0")
def test_vendor_share_is_redacted_and_isolated(tenant_a, tenant_b):
    vendor = Company.objects.create(name="BizBoard", state="Karnataka")
    vendor_user = User.objects.create_user(email="p10@vendor.test", password="StrongPass123!", full_name="P10")
    CompanyUser.objects.create(
        company=vendor, user=vendor_user, role=CompanyUser.Role.SALES_STAFF, can_create_sales=True,
    )
    vendor.feature_flags = {"ENABLE_SUPPORT_TICKETS": True}
    vendor.save(update_fields=["feature_flags"])
    tenant_a.company.feature_flags = {"ENABLE_SUPPORT_TICKETS": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    with override_settings(VENDOR_COMPANY_ID=str(vendor.id)):
        customer = make_customer(tenant_a.company)
        other = make_customer(tenant_b.company)
        ticket_b = Ticket.objects.create(company=tenant_b.company, customer=other, subject="Secret", number="TKT-B")
        hidden = tenant_a.client.get(f"/api/v1/support/tickets/{ticket_b.id}/")
        assert hidden.status_code == 404
        ticket = Ticket.objects.create(
            company=tenant_a.company, customer=customer, subject="Cannot print", description="GSTIN 29", number="TKT-A",
        )
        seller = User.objects.create_user(email="seller-a@x.test", password="StrongPass123!", full_name="Seller")
        CompanyUser.objects.create(
            company=tenant_a.company, user=seller, role=CompanyUser.Role.SALES_STAFF, can_create_sales=True,
        )
        seller_client = APIClient()
        seller_client.force_authenticate(user=seller)
        staff = seller_client.post(f"/api/v1/support/tickets/{ticket.id}/share/", {}, format="json")
        assert staff.status_code == 403
        shared = tenant_a.client.post(f"/api/v1/support/tickets/{ticket.id}/share/", {}, format="json")
        assert shared.status_code == 200
        src = open(__file__.replace("test_roadmap_items.py", "../support/share.py"), encoding="utf-8").read()
        assert "rls_bypass" in src
        vendor_client = APIClient()
        vendor_client.force_authenticate(user=vendor_user)
        listing = vendor_client.get("/api/v1/support/shared/")
        assert listing.status_code == 200, listing.data
        row = listing.data["results"][0] if isinstance(listing.data, dict) else listing.data[0]
        assert "amount" not in row
        assert "file" not in row and "file_id" not in row
        assert "description" not in row
        with_body = tenant_a.client.post(
            f"/api/v1/support/tickets/{ticket.id}/share/",
            {"include_description": True},
            format="json",
        )
        assert with_body.status_code == 200
        listing = vendor_client.get("/api/v1/support/shared/")
        row = listing.data["results"][0] if isinstance(listing.data, dict) else listing.data[0]
        assert row["description"] == "GSTIN 29"
        stranger = tenant_b.client.get(f"/api/v1/support/shared/{row['id']}/")
        assert stranger.status_code == 404
        tenant_a.client.post(f"/api/v1/support/tickets/{ticket.id}/stop-sharing/")
        listing = vendor_client.get("/api/v1/support/shared/")
        payload = listing.data["results"] if isinstance(listing.data, dict) else listing.data
        assert payload == []
        assert AuditEvent.objects.filter(company=tenant_a.company, action="support.ticket_shared").exists()
        assert "rls_bypass" in share_ticket.__code__.co_names


def test_share_table_is_in_rls_list():
    import importlib

    mod = importlib.import_module("core.migrations.0020_rls_all_tenant_tables")
    for name in (
        "support_vendorticketshare",
        "workshop_jobcard",
        "workshop_jobcardline",
        "projects_project",
        "projects_projectmilestone",
    ):
        assert name in mod.RLS_TABLES


def test_insurance_issue_renew_commission_claim_kyc(tenant_a):
    from crm.models import Campaign, Lead
    from insurance.models import CommissionReceivable

    tenant_a.company.feature_flags = {"ENABLE_INSURANCE": True, "ENABLE_SUPPORT_TICKETS": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    desk = User.objects.create_user(email="desk2@x.test", password="StrongPass123!", full_name="Desk")
    CompanyUser.objects.create(company=tenant_a.company, user=desk, role="POLICY_DESK", can_manage_policies=True, is_active=True)
    client = APIClient()
    client.force_authenticate(user=desk)
    a = client.post("/api/v1/insurance/products/", {
        "name": "Motor A", "insurer_name": "Insurer", "line": "MOTOR",
        "tenure_months": 12, "sum_insured": "100000", "premium": "5000",
    }, format="json")
    b = client.post("/api/v1/insurance/products/", {
        "name": "Motor B", "insurer_name": "Insurer", "line": "MOTOR",
        "tenure_months": 12, "sum_insured": "200000", "premium": "7000",
    }, format="json")
    assert a.status_code == 201 and b.status_code == 201
    campaign = Campaign.objects.create(company=tenant_a.company, name="Renewals", campaign_type="DIGITAL")
    customer = make_customer(tenant_a.company)
    lead = Lead.objects.create(company=tenant_a.company, name=customer.name, campaign=campaign, customer=customer)
    options = client.post("/api/v1/insurance/option-sets/", {"lead": lead.id, "products": [a.data["id"], b.data["id"]]}, format="json")
    assert options.status_code == 201, options.data
    chosen = options.data["options"][0]["id"]
    client.post(f"/api/v1/insurance/option-sets/{options.data['id']}/choose/", {"option": chosen}, format="json")
    issued = client.post("/api/v1/insurance/policies/", {
        "option": chosen, "customer": customer.id, "nominee": "Anita", "start_date": timezone.localdate().isoformat(),
    }, format="json")
    assert issued.status_code == 201, issued.data
    assert issued.data["number"].startswith("POL-")
    again = client.post("/api/v1/insurance/policies/", {
        "option": chosen, "customer": customer.id, "nominee": "Anita", "start_date": timezone.localdate().isoformat(),
    }, format="json")
    assert again.data["id"] == issued.data["id"]
    policy_id = issued.data["id"]
    from insurance.models import Policy

    Policy.objects.filter(pk=policy_id).update(end_date=timezone.localdate() + timedelta(days=10))
    renewed = client.post("/api/v1/insurance/renewals/", {"within_days": 30}, format="json")
    assert renewed.data["created"] == 1
    commission = client.post(f"/api/v1/insurance/policies/{policy_id}/commission/", {"amount": "500"}, format="json")
    assert commission.status_code == 200
    assert CommissionReceivable.objects.get(pk=commission.data["id"]).policy_id == policy_id
    claim = client.post(f"/api/v1/insurance/policies/{policy_id}/claim/", {"summary": "Bumper"}, format="json")
    assert claim.status_code == 200
    asset = FileAsset.objects.create(
        company=tenant_a.company, kind=FileAsset.Kind.ATTACHMENT, original_name="pan.pdf",
        file=ContentFile(b"pdf", name="pan.pdf"),
    )
    kyc = client.post(f"/api/v1/insurance/policies/{policy_id}/kyc/", {"kind": "PAN", "file": asset.id}, format="json")
    assert kyc.status_code == 200
    endorse = client.post(f"/api/v1/insurance/policies/{policy_id}/endorse/", {"note": "Address change"}, format="json")
    assert endorse.status_code == 200
    assert AuditEvent.objects.filter(company=tenant_a.company, action="insurance.policy_endorsed").exists()
    book = client.get("/api/v1/insurance/book/")
    assert book.data["policies"]
    cancelled = client.post(f"/api/v1/insurance/policies/{policy_id}/cancel/", {"note": "Customer left"}, format="json")
    assert cancelled.data["status"] == "CANCELLED"
    from accounts.models import CompanyStatutoryLicence

    lic = tenant_a.client.post("/api/v1/company/statutory-licences/", {
        "licence_type": "POSP", "licence_number": "POSP-1",
    }, format="json")
    assert lic.status_code == 201, getattr(lic, "data", lic)
    assert CompanyStatutoryLicence.objects.filter(company=tenant_a.company, licence_type="POSP").exists()


def test_saas_activation_upgrade_trial_and_churn(tenant_a):
    from billing.ops import note_first_invoice, note_setup_completed, trial_ending_notice, upgrade_prompt

    vendor = Company.objects.create(name="Vendor", state="Karnataka")
    plan = Plan.objects.create(name="Small", slug=f"small-{tenant_a.company.pk}", seat_limit=1, monthly_complete_limit=1, modules={})
    Subscription.objects.create(
        company=tenant_a.company, plan=plan, status=Subscription.Status.TRIAL,
        trial_ends_at=timezone.now() + timedelta(days=3),
    )
    with override_settings(VENDOR_COMPANY_ID=str(vendor.id)):
        note_setup_completed(tenant_a.company)
        note_first_invoice(tenant_a.company.id)
        from billing.models import VendorTenantSnapshot

        snap = VendorTenantSnapshot.objects.get(company=vendor, source_company_id=tenant_a.company.id)
        assert snap.setup_completed_at is not None
        assert snap.first_invoice_at is not None
        prompt = upgrade_prompt(tenant_a.company)
        assert prompt["reason"] in {"seats", "documents"}
        notice = trial_ending_notice(tenant_a.company)
        assert notice["show"] is True
        past = Subscription.objects.get(company=tenant_a.company)
        past.status = Subscription.Status.PAST_DUE
        past.save(update_fields=["status"])
        assert trial_ending_notice(tenant_a.company)["show"] is False
        past.status = Subscription.Status.TRIAL
        past.save(update_fields=["status"])
        resp = tenant_a.client.post(
            "/api/v1/billing/subscription/",
            {"action": "suspend", "churn_reason": "Too expensive"},
            format="json",
        )
        assert resp.status_code == 200, resp.data
        assert resp.data["churn_reason"] == "Too expensive"
        from crm.models import Campaign

        assert Campaign.objects.filter(company=vendor, name__startswith="Win-back").exists()


def _list_rows(data):
    if isinstance(data, dict):
        return data.get("results", data.get("items", []))
    return data


def _assert_list_query_count_is_flat(client, url, make_row, flag_key, company):
    """Same shape as test_b5_008: count at 20 rows vs 40, tolerance + 2."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    company.feature_flags = {**(company.feature_flags or {}), flag_key: True}
    company.save(update_fields=["feature_flags"])
    for _ in range(20):
        make_row()
    with CaptureQueriesContext(connection) as small:
        first = client.get(url)
    assert first.status_code == 200, first.data
    assert len(_list_rows(first.data)) == 20
    for _ in range(20):
        make_row()
    with CaptureQueriesContext(connection) as large:
        second = client.get(url)
    assert second.status_code == 200, second.data
    assert len(_list_rows(second.data)) == 40
    assert len(large.captured_queries) <= len(small.captured_queries) + 2, (
        f"{url}: {len(small.captured_queries)} queries for 20 rows vs "
        f"{len(large.captured_queries)} for 40"
    )


def test_job_card_list_query_count_is_flat(tenant_a):
    from masters.models import Customer
    from workshop.models import JobCard

    customer = make_customer(tenant_a.company)
    n = {"n": 0}

    def make_row():
        n["n"] += 1
        JobCard.objects.create(company=tenant_a.company, customer=customer, complaint=f"c{n['n']}")

    _assert_list_query_count_is_flat(
        tenant_a.client, "/api/v1/workshop/job-cards/", make_row, "ENABLE_WORKSHOP", tenant_a.company,
    )
    assert Customer.objects.filter(pk=customer.pk).exists()


def test_project_list_query_count_is_flat(tenant_a):
    from projects.models import Project

    customer = make_customer(tenant_a.company)
    n = {"n": 0}

    def make_row():
        n["n"] += 1
        Project.objects.create(company=tenant_a.company, customer=customer, name=f"P{n['n']}")

    _assert_list_query_count_is_flat(
        tenant_a.client, "/api/v1/projects/", make_row, "ENABLE_PROJECTS", tenant_a.company,
    )


def test_policy_list_query_count_is_flat(tenant_a):
    from datetime import date

    from insurance.models import Policy, PolicyProduct

    user = User.objects.create_user(email="desk-q@alpha.test", password="StrongPass123!", full_name="Desk")
    CompanyUser.objects.create(
        company=tenant_a.company, user=user, role=CompanyUser.Role.POLICY_DESK, can_manage_policies=True,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    customer = make_customer(tenant_a.company)
    product = PolicyProduct.objects.create(
        company=tenant_a.company, name="Motor", insurer_name="Acme", line=PolicyProduct.Line.MOTOR,
        tenure_months=12, sum_insured="100000", premium="1000",
    )
    n = {"n": 0}

    def make_row():
        n["n"] += 1
        Policy.objects.create(
            company=tenant_a.company, customer=customer, product=product,
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), premium="1000",
        )

    _assert_list_query_count_is_flat(
        client, "/api/v1/insurance/policies/", make_row, "ENABLE_INSURANCE", tenant_a.company,
    )


def test_shared_ticket_list_query_count_is_flat(tenant_a):
    from support.models import VendorTicketShare

    source = Company.objects.create(name="Source Co", state="Maharashtra")
    n = {"n": 0}

    def make_row():
        n["n"] += 1
        VendorTicketShare.objects.create(
            company=tenant_a.company,
            vendor_company=tenant_a.company,
            source_company=source,
            source_ticket_id=n["n"],
            subject=f"T{n['n']}",
            status="OPEN",
            shared_at=timezone.now(),
        )

    _assert_list_query_count_is_flat(
        tenant_a.client, "/api/v1/support/shared/", make_row, "ENABLE_SUPPORT_TICKETS", tenant_a.company,
    )
