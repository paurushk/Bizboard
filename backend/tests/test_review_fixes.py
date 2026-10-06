"""Regression tests for defects found in the post-implementation code review (2026-10-05)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import RequestFactory
from django.utils import timezone

from planwave.models import ApprovalRequest
from planwave.services import (
    consume_action_approval,
    consume_stock_approval,
    decide_approval,
    submit_approval,
)


def _approved(tenant, action, payload):
    row = submit_approval(company=tenant.company, action=action, requester=tenant.owner, payload=payload)
    decide_approval(row, approver=tenant.staff, accept=True)
    return row


@pytest.mark.django_db
def test_approval_is_spent_once(tenant_a):
    row = _approved(tenant_a, "invoice_cancel", {"invoice": 7})
    first = consume_action_approval(tenant_a.company, row.pk, tenant_a.owner, "invoice_cancel", invoice=7)
    assert first is not None
    assert consume_action_approval(tenant_a.company, row.pk, tenant_a.owner, "invoice_cancel", invoice=7) is None


@pytest.mark.django_db
def test_approval_is_bound_to_its_subject(tenant_a):
    row = _approved(tenant_a, "invoice_cancel", {"invoice": 7})
    assert consume_action_approval(tenant_a.company, row.pk, tenant_a.owner, "invoice_cancel", invoice=8) is None
    # a wrong-subject attempt must not burn the approval
    assert consume_action_approval(tenant_a.company, row.pk, tenant_a.owner, "invoice_cancel", invoice=7) is not None


@pytest.mark.django_db
def test_expired_approval_is_refused(tenant_a):
    row = _approved(tenant_a, "invoice_cancel", {"invoice": 7})
    ApprovalRequest.objects.filter(pk=row.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
    assert consume_action_approval(tenant_a.company, row.pk, tenant_a.owner, "invoice_cancel", invoice=7) is None


@pytest.mark.django_db
def test_approval_cannot_be_spent_by_someone_else_or_by_the_approver(tenant_a):
    row = _approved(tenant_a, "invoice_cancel", {"invoice": 7})
    assert consume_action_approval(tenant_a.company, row.pk, tenant_a.staff, "invoice_cancel", invoice=7) is None
    assert consume_action_approval(tenant_a.company, "not-a-number", tenant_a.owner, "invoice_cancel", invoice=7) is None


@pytest.mark.django_db
def test_stock_approval_matches_product_and_quantity(tenant_a):
    row = _approved(tenant_a, "stock_adjustment", {"product": 3, "quantity": "-5"})
    assert consume_stock_approval(tenant_a.company, row.pk, tenant_a.owner, product=3, quantity=Decimal("-50")) is None
    assert consume_stock_approval(tenant_a.company, row.pk, tenant_a.owner, product=3, quantity=Decimal("-5.000")) is not None
    assert consume_stock_approval(tenant_a.company, row.pk, tenant_a.owner, product=3, quantity=Decimal("-5")) is None


def test_rate_limit_keys_use_the_trusted_client_ip_not_the_proxy(settings):
    from planwave import ratelimit

    settings.DJANGO_ENV = "production"
    settings.NUM_TRUSTED_PROXIES = 1
    req = RequestFactory().post(
        "/api/v1/auth/login/", data="{}", content_type="application/json",
        REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="203.0.113.9, 198.51.100.4",
    )
    keys = [key for key, _limit, _window in ratelimit.rules_for(req)]
    assert "login:ip:198.51.100.4" in keys
    assert not any("10.0.0.1" in key for key in keys)


def test_authenticated_api_calls_are_not_pooled_per_ip():
    from planwave import ratelimit

    def call(token):
        req = RequestFactory().get("/api/v1/sales/invoices/", HTTP_AUTHORIZATION=f"Bearer {token}", REMOTE_ADDR="10.0.0.1")
        return [key for key, _l, _w in ratelimit.rules_for(req) if key.startswith("api:")][0]

    assert call("token-a") != call("token-b")
    assert call("token-a") == call("token-a")


# ---- planwave endpoint authorization ---------------------------------------


@pytest.mark.django_db
def test_only_an_owner_can_decide_an_approval(tenant_a):
    row = submit_approval(company=tenant_a.company, action="invoice_cancel", requester=tenant_a.staff, payload={"invoice": 1})
    url = f"/api/v1/plan/approvals/{row.pk}/decide/"
    denied = tenant_a.staff_client.post(url, {"accept": True}, format="json")
    assert denied.status_code == 403
    row.refresh_from_db()
    assert row.status == "PENDING"
    ok = tenant_a.client.post(url, {"accept": True}, format="json")
    assert ok.status_code == 200, ok.data
    assert ok.data["status"] == "APPROVED"


@pytest.mark.django_db
def test_deciding_an_unknown_approval_is_a_404_not_a_500(tenant_a):
    assert tenant_a.client.post("/api/v1/plan/approvals/999999/decide/", {"accept": True}, format="json").status_code == 404


@pytest.mark.django_db
def test_only_an_owner_can_clear_the_books_quarantine(tenant_a):
    assert tenant_a.staff_client.delete("/api/v1/plan/quarantine/").status_code == 403
    assert tenant_a.client.delete("/api/v1/plan/quarantine/").status_code == 200


@pytest.mark.django_db
def test_a_viewer_cannot_write_through_the_plan_endpoints(tenant_a):
    from rest_framework.test import APIClient

    from accounts.models import CompanyUser, User

    viewer = User.objects.create_user(email="viewer-a@example.com", password="pw-12345-Ab!")
    CompanyUser.objects.create(company=tenant_a.company, user=viewer, role=CompanyUser.Role.VIEWER)
    client = APIClient()
    client.force_authenticate(user=viewer)
    for path, body in (
        ("/api/v1/plan/bulk-invoices/commit/", {"csv": ""}),
        ("/api/v1/plan/restore/", {"kind": "customer", "id": 1}),
        ("/api/v1/plan/approvals/", {"action": "invoice_cancel", "payload": {}}),
    ):
        assert client.post(path, body, format="json").status_code == 403, path


@pytest.mark.django_db
def test_restoring_a_missing_master_is_a_clean_error(tenant_a):
    resp = tenant_a.client.post("/api/v1/plan/restore/", {"kind": "customer", "id": 987654}, format="json")
    assert resp.status_code == 400
    assert tenant_a.client.post("/api/v1/plan/restore/", {"kind": "customer", "id": "abc"}, format="json").status_code == 400


# ---- delivery OTP -----------------------------------------------------------


@pytest.mark.django_db
def test_delivery_otp_locks_after_repeated_wrong_codes():
    from types import SimpleNamespace

    from django.core.cache import cache

    from accounts.otp_utils import hash_otp
    from core.exceptions import BusinessRuleError
    from sales.route_service import POD_OTP_MAX_ATTEMPTS, RouteService

    stop = SimpleNamespace(pk=990001, delivery_otp_hash=hash_otp("123456"))
    cache.delete(f"pod_otp_fail:{stop.pk}")
    for _ in range(POD_OTP_MAX_ATTEMPTS):
        with pytest.raises(BusinessRuleError, match="does not match"):
            RouteService._verify_delivery_otp(stop, "000000")
    # even the right code is refused once locked: a new code has to be issued
    with pytest.raises(BusinessRuleError, match="Too many wrong"):
        RouteService._verify_delivery_otp(stop, "123456")
    cache.delete(f"pod_otp_fail:{stop.pk}")
    RouteService._verify_delivery_otp(stop, "123456")  # correct code passes after reset
    assert stop.delivery_otp_hash == ""  # and it is spent: it cannot confirm a second delivery


def test_delivery_otp_blank_is_allowed_only_when_none_was_issued():
    from types import SimpleNamespace

    from core.exceptions import BusinessRuleError
    from sales.route_service import RouteService

    RouteService._verify_delivery_otp(SimpleNamespace(pk=990002, delivery_otp_hash=""), "")
    from accounts.otp_utils import hash_otp

    with pytest.raises(BusinessRuleError):
        RouteService._verify_delivery_otp(SimpleNamespace(pk=990003, delivery_otp_hash=hash_otp("654321")), "")


# ---- cheque dishonour ------------------------------------------------------


def _cheque_receipt(tenant, number="900100"):
    from payments.services import PaymentService
    from tests.conftest import make_customer

    customer = make_customer(tenant.company, name=f"Cheque Party {number}")
    return PaymentService.create_receipt(
        company=tenant.company, customer=customer, amount=Decimal("250.00"),
        mode="CHEQUE", cheque_number=number, cheque_bank_name="HDFC", user=tenant.owner,
    )


@pytest.mark.django_db
def test_a_bounce_with_no_configured_charge_bills_the_customer_nothing(tenant_a):
    from payments.models import ChequeStatus
    from payments.services import PaymentService

    receipt = _cheque_receipt(tenant_a)
    bounced = PaymentService.set_cheque_status(
        receipt=receipt, cheque_status=ChequeStatus.BOUNCED, user=tenant_a.owner,
    )
    bounced.refresh_from_db()
    assert bounced.cheque_status == ChequeStatus.BOUNCED
    assert bounced.dishonour_fee == Decimal("0.00")


@pytest.mark.django_db
def test_a_failed_notice_pdf_does_not_stop_the_bounce(tenant_a):
    from unittest.mock import patch

    from payments.models import ChequeStatus, ReceiptStatus
    from payments.services import PaymentService

    receipt = _cheque_receipt(tenant_a, "900200")
    with patch.object(PaymentService, "_store_section_138_notice", side_effect=RuntimeError("disk full")):
        bounced = PaymentService.set_cheque_status(
            receipt=receipt, cheque_status=ChequeStatus.BOUNCED, user=tenant_a.owner,
            bank_charge=Decimal("75.00"),
        )
    bounced.refresh_from_db()
    assert bounced.cheque_status == ChequeStatus.BOUNCED
    assert bounced.status == ReceiptStatus.VOIDED
    assert bounced.dishonour_fee == Decimal("75.00")
    assert bounced.section_138_notice_id is None


# ---- session version on password login --------------------------------------


@pytest.mark.django_db
def test_password_login_after_a_session_revoke_yields_a_working_session(tenant_a):
    """The password login mints its tokens in SimpleJWT. They must carry the user's
    current session version or the very first request is rejected as revoked."""
    from rest_framework.test import APIClient

    owner = tenant_a.owner
    owner.session_version = 3
    owner.save(update_fields=["session_version"])

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/", {"email": owner.email, "password": "StrongPass123!"}, format="json",
    )
    assert login.status_code == 200, login.data
    # the cookie session works straight away
    assert client.get("/api/v1/auth/me/").status_code == 200

    from rest_framework_simplejwt.tokens import AccessToken

    from django.conf import settings as dj_settings

    # The access token is always in the cookie; the body copy depends on the environment. Read
    # the cookie so these assertions run every time instead of only when the body carries a token.
    access = login.cookies[dj_settings.JWT_ACCESS_COOKIE_NAME].value
    assert AccessToken(access)["sv"] == 3
    bearer = APIClient()
    bearer.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    assert bearer.get("/api/v1/auth/me/").status_code == 200
    # A token with an older session version is refused on its first request.
    owner.session_version = 4
    owner.save(update_fields=["session_version"])
    assert bearer.get("/api/v1/auth/me/").status_code == 401


# ---- bulk invoice import ----------------------------------------------------


@pytest.mark.django_db
def test_bulk_committed_invoice_has_computed_totals_and_tax(tenant_a):
    from planwave.finish import commit_bulk_invoices
    from sales.models import SalesInvoice
    from tests.conftest import make_customer, make_product

    make_customer(tenant_a.company, name="Ravi Kumar")
    make_product(tenant_a.company, sku="BULK-1", gst_rate="18")
    text = "invoice_ref,customer,sku,quantity,rate\nA1,Ravi Kumar,BULK-1,2,100\n"
    result = commit_bulk_invoices(tenant_a.company, text, tenant_a.owner)
    assert len(result["created"]) == 1, result
    invoice = SalesInvoice.objects.get(pk=result["created"][0]["id"])
    assert invoice.taxable_total == Decimal("200.00")
    assert invoice.grand_total == Decimal("236.00")
    item = invoice.items.get()
    assert item.gst_rate == Decimal("18")
    assert item.line_total == Decimal("236.00")


# ---- offline POS batch sync -------------------------------------------------


@pytest.mark.django_db
def test_batch_sync_one_bad_bill_does_not_roll_back_the_good_ones(tenant_a):
    from unittest.mock import patch

    from rest_framework.response import Response

    from core.exceptions import BusinessRuleError
    from sales.views import SalesInvoiceViewSet

    def _checkout(self, request):
        if request.data.get("bad"):
            raise BusinessRuleError("Stock is short.")
        return Response({"n": request.data["n"], "key": request.headers.get("Idempotency-Key")}, status=201)

    body = {"checkouts": [
        {"n": 1, "idempotency_key": "k-1"},
        {"n": 2, "idempotency_key": "k-2", "bad": True},
        {"n": 3, "idempotency_key": "k-3"},
        {"n": 4},
    ]}
    with patch.object(SalesInvoiceViewSet, "pos_checkout", _checkout):
        resp = tenant_a.client.post("/api/v1/sales/pos/batch-sync/", body, format="json")
    assert resp.status_code == 207, resp.data
    assert [r["n"] for r in resp.data["results"]] == [1, 3]
    # each bill is sent under its own key, not the batch's
    assert [r["key"] for r in resp.data["results"]] == ["k-1", "k-3"]
    assert sorted(e["index"] for e in resp.data["errors"]) == [1, 3]


@pytest.mark.django_db
def test_batch_sync_cannot_check_out_against_another_tenants_customer(tenant_a, tenant_b):
    from sales.models import SalesInvoice
    from tests.conftest import make_customer, make_product

    foreign = make_customer(tenant_a.company, name="Alpha Only")
    product = make_product(tenant_b.company, sku="ISO-1")
    resp = tenant_b.client.post(
        "/api/v1/sales/pos/batch-sync/",
        {"checkouts": [{
            "idempotency_key": "iso-1",
            "invoice": {
                "customer": foreign.id, "invoice_type": "GST",
                "items": [{"product": product.id, "quantity": 1, "unit_price": 100}],
            },
            "payment": {"mode": "CASH", "amount": 118},
        }]},
        format="json",
    )
    assert resp.data["results"] == [], resp.data
    assert len(resp.data["errors"]) == 1
    assert not SalesInvoice.objects.filter(customer=foreign).exists()
    assert not SalesInvoice.objects.filter(company=tenant_b.company).exists()


# ---- 3-way match tolerance --------------------------------------------------


def test_three_way_rate_tolerance_is_half_a_percent_with_a_paisa_floor():
    from decimal import Decimal

    from purchases.services import _three_way_rate_tolerance

    assert _three_way_rate_tolerance(Decimal("100.00")) == Decimal("0.50")
    assert _three_way_rate_tolerance(Decimal("1000.00")) == Decimal("5.00")
    # tiny rates never get a tolerance below one paisa
    assert _three_way_rate_tolerance(Decimal("0.50")) == Decimal("0.01")
    assert _three_way_rate_tolerance(0) == Decimal("0.01")


# ---- sealed values -----------------------------------------------------------


def test_text_that_only_looks_sealed_is_still_encrypted():
    from planwave.crypto import open_secret, seal

    lookalike = "gcm1.k1.not-real-ciphertext"
    sealed = seal(lookalike)
    assert sealed != lookalike
    assert open_secret(sealed) == lookalike


def test_a_real_sealed_value_is_not_sealed_twice():
    from planwave.crypto import seal

    once = seal("123456789012")
    assert seal(once) == once


# ---- percent referral reward base -------------------------------------------


@pytest.mark.django_db
def test_percent_reward_ignores_invoices_from_before_the_deal_opened(tenant_a):
    from datetime import timedelta

    from crm.models import Opportunity
    from crm.referrals import invoiced_taxable_for_opportunity
    from sales.models import SalesInvoice
    from tests.conftest import make_customer

    buyer = make_customer(tenant_a.company, name="Existing Buyer")
    opportunity = Opportunity.objects.create(
        company=tenant_a.company, customer=buyer, title="Deal", amount=Decimal("1"),
        stage=Opportunity.Stage.OPEN, created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    today = timezone.localdate()
    for days_ago, taxable in ((400, "9000.00"), (0, "400.00")):
        SalesInvoice.objects.create(
            company=tenant_a.company, customer=buyer, status=SalesInvoice.Status.COMPLETED,
            invoice_date=today - timedelta(days=days_ago), taxable_total=Decimal(taxable),
            grand_total=Decimal(taxable), created_by=tenant_a.owner, updated_by=tenant_a.owner,
        )
    assert invoiced_taxable_for_opportunity(opportunity) == Decimal("400.00")


# ---- below-cost override ----------------------------------------------------


@pytest.mark.django_db
def test_an_owner_can_complete_a_below_cost_bill_with_a_reason_and_it_is_audited(tenant_a):
    from core.models import AuditEvent
    from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

    tenant_a.company.feature_flags = {**(tenant_a.company.feature_flags or {}), "allow_below_cost_sales": False}
    tenant_a.company.save(update_fields=["feature_flags"])
    customer = make_customer(tenant_a.company, name="Clearance")
    product = make_product(tenant_a.company, sku="CLR-1", purchase_price="80", selling_price="80", gst_rate="0")
    add_stock(tenant_a, product, "5", unit_cost="80")
    draft = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "50", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    url = f"/api/v1/sales/invoices/{draft['id']}/complete/"
    # no reason: refused
    assert tenant_a.client.post(url).status_code == 400
    # staff cannot override even with a reason
    assert tenant_a.staff_client.post(url, {"below_cost_override_reason": "clearance"}, format="json").status_code in (400, 403)
    # the owner can, and it leaves a trail
    ok = tenant_a.client.post(url, {"below_cost_override_reason": "Expired stock clearance"}, format="json")
    assert ok.status_code == 200, ok.data
    assert AuditEvent.objects.filter(
        company=tenant_a.company, entity_type="SalesInvoice", entity_id=str(draft["id"]),
        description__startswith="Below-cost sale allowed by owner",
    ).exists()


def test_login_account_limit_is_per_address_so_it_cannot_lock_a_victim_out():
    from planwave import ratelimit

    def keys(ip):
        req = RequestFactory().post(
            "/api/v1/auth/login/", data='{"email": "victim@example.com"}',
            content_type="application/json", REMOTE_ADDR=ip,
        )
        return {key for key, _l, _w in ratelimit.rules_for(req) if key.startswith("login:acct:")}

    attacker, victim = keys("203.0.113.9"), keys("198.51.100.4")
    assert attacker and victim and attacker.isdisjoint(victim)


# ---- reservation expiry is opt-in -------------------------------------------


@pytest.mark.django_db
def test_a_stock_hold_never_expires_unless_the_company_opted_in(tenant_a):
    from datetime import timedelta

    from inventory.models import StockBalance, StockReservation
    from inventory.services import InventoryService
    from tests.conftest import add_stock, make_product

    company = tenant_a.company
    product = make_product(company, sku="HOLD-1")
    add_stock(tenant_a, product, "10")
    warehouse = InventoryService.default_warehouse(company)
    later = timezone.now() + timedelta(days=2)

    # Default: no expiry is stamped, so a sweep two days later has nothing to release.
    InventoryService.reserve_stock(company, warehouse, product, Decimal("4"), user=tenant_a.owner)
    assert not StockReservation.objects.filter(company=company, product=product).exists()
    InventoryService.release_expired_reservations(company, now=later)
    balance = StockBalance.objects.get(company=company, product=product, warehouse=warehouse)
    assert balance.reserved == Decimal("4")

    # Opted in: the hold carries an expiry, and the sweep releases it once that passes.
    company.feature_flags = {"reservation_ttl_hours": 24}
    company.save(update_fields=["feature_flags"])
    InventoryService.reserve_stock(company, warehouse, product, Decimal("3"), user=tenant_a.owner)
    hold = StockReservation.objects.get(company=company, product=product)
    assert hold.expires_at is not None
    InventoryService.release_expired_reservations(company, now=hold.expires_at - timedelta(minutes=1))
    balance.refresh_from_db()
    assert balance.reserved == Decimal("7") and hold.released_at is None
    InventoryService.release_expired_reservations(company, now=later)
    balance.refresh_from_db()
    hold.refresh_from_db()
    assert balance.reserved == Decimal("4") and hold.released_at is not None


# ---- workshop zero-price lines ----------------------------------------------


@pytest.mark.django_db
def test_a_warranty_part_at_zero_price_is_accepted_but_a_negative_price_is_not(tenant_a):
    from core.exceptions import BusinessRuleError
    from tests.conftest import add_stock, make_customer, make_product
    from workshop.models import JobCardLine
    from workshop.services import add_line, create_job

    job = create_job(tenant_a.company, tenant_a.owner, customer=make_customer(tenant_a.company), complaint="Noise")
    part = make_product(tenant_a.company, sku="WARR-1")
    add_stock(tenant_a, part, "5")  # a part line holds its stock
    line = add_line(
        job, tenant_a.owner, kind=JobCardLine.Kind.PART, product=part, quantity="1", unit_price="0",
    )
    assert line.unit_price == 0
    with pytest.raises(BusinessRuleError):
        add_line(job, tenant_a.owner, kind=JobCardLine.Kind.PART, product=part, quantity="1", unit_price="-5")
    with pytest.raises(BusinessRuleError):
        add_line(job, tenant_a.owner, kind=JobCardLine.Kind.PART, product=part, quantity="0", unit_price="5")


# ---- a job card's own hold must not block its own invoice --------------------


@pytest.mark.django_db
def test_invoicing_a_job_whose_part_is_the_last_one_in_stock(tenant_a):
    from inventory.models import StockBalance
    from masters.models import Product
    from sales.models import SalesInvoice
    from sales.services import SalesService
    from tests.conftest import add_stock, make_customer, make_product
    from workshop.models import JobCardLine
    from workshop.services import add_line, convert_to_invoice, create_job

    part = make_product(tenant_a.company, name="Last spare", sku="LAST-1", product_type=Product.ProductType.GOODS)
    add_stock(tenant_a, part, "1")
    job = create_job(tenant_a.company, tenant_a.owner, customer=make_customer(tenant_a.company), complaint="Fault")
    add_line(job, tenant_a.owner, kind=JobCardLine.Kind.PART, product=part, quantity="1", unit_price="100")
    assert StockBalance.objects.get(company=tenant_a.company, product=part).reserved == Decimal("1")
    invoice = convert_to_invoice(job, tenant_a.owner)
    # the only unit is reserved for this very job; completing its invoice must still work
    SalesService.complete(SalesInvoice.objects.get(pk=invoice.pk if hasattr(invoice, "pk") else invoice), tenant_a.owner)
    balance = StockBalance.objects.get(company=tenant_a.company, product=part)
    assert balance.on_hand == Decimal("0")
    assert balance.reserved == Decimal("0")


# ---- quiet hours: midnight is a real hour -----------------------------------


def test_a_configured_midnight_is_not_replaced_by_the_default_quiet_window():
    from datetime import datetime
    from types import SimpleNamespace
    from zoneinfo import ZoneInfo

    from payments.dunning import in_quiet_hours

    three_am = datetime(2026, 10, 5, 3, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    # 0 to 0 means no quiet window at all, whatever the hour
    assert in_quiet_hours(SimpleNamespace(dunning_quiet_hours_start=0, dunning_quiet_hours_end=0), three_am) is False
    # a window that starts at midnight covers 03:00
    assert in_quiet_hours(SimpleNamespace(dunning_quiet_hours_start=0, dunning_quiet_hours_end=6), three_am) is True
    # unset fields still fall back to the 21:00-08:00 default
    assert in_quiet_hours(SimpleNamespace(), three_am) is True
