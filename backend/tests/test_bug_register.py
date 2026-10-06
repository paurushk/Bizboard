"""Regression tests for BUGS_REMEDIATION_PLAN.md waves 1 and 2."""

from __future__ import annotations

import inspect
from decimal import Decimal

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from accounts.erasure import assert_erasure_model_coverage
from accounts.models import CompanyUser
from config.settings import _assert_mfa_encryption_key, resolve_mfa_enforce
from core.models import AuditEvent
from payments.models import CustomerReceipt
from payments.services import PaymentService
from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db

PASSWORD = "StrongPass123!"


def test_bug_sec_014_production_refuses_empty_mfa_key():
    with pytest.raises(ImproperlyConfigured, match="MFA_ENCRYPTION_KEY"):
        _assert_mfa_encryption_key(django_env="production", key="")
    with pytest.raises(ImproperlyConfigured, match="MFA_ENCRYPTION_KEY"):
        _assert_mfa_encryption_key(django_env="staging", key="  ")
    _assert_mfa_encryption_key(django_env="test", key="")
    _assert_mfa_encryption_key(django_env="development", key="")
    _assert_mfa_encryption_key(django_env="production", key="fernet-key")


def test_bug_sec_004_unset_enforcement_is_on_outside_test():
    assert resolve_mfa_enforce(django_env="test", raw="") is False
    assert resolve_mfa_enforce(django_env="development", raw="") is True
    assert resolve_mfa_enforce(django_env="staging", raw="") is True
    assert resolve_mfa_enforce(django_env="production", raw="0") is False
    assert resolve_mfa_enforce(django_env="production", raw="1") is True


def test_bug_sec_004_waiver_login_writes_an_audit_row(tenant_a, settings):
    settings.MFA_ENFORCE_FOR_MONEY_ROLES = False
    settings.MFA_ENFORCE_WAIVER = True
    before = AuditEvent.objects.filter(action="MFA_ENFORCE_WAIVER").count()
    response = APIClient().post(
        "/api/v1/auth/login/",
        {"email": tenant_a.owner.email, "password": PASSWORD},
        format="json",
    )
    assert response.status_code == 200
    assert response.data.get("mfa_required") is not True
    assert AuditEvent.objects.filter(action="MFA_ENFORCE_WAIVER").count() == before + 1


def test_bug_sec_010_session_setup_requires_password(tenant_a):
    refused = tenant_a.client.post("/api/v1/auth/mfa/setup/", {}, format="json")
    assert refused.status_code == 400
    assert "password" in str(refused.data)
    accepted = tenant_a.client.post(
        "/api/v1/auth/mfa/setup/", {"password": PASSWORD}, format="json",
    )
    assert accepted.status_code == 200
    assert accepted.data.get("secret")


def test_bug_sec_011_mfa_login_blacklists_the_minted_refresh(tenant_a):
    from tests.test_mfa import _enrol

    _enrol(tenant_a)
    response = APIClient().post(
        "/api/v1/auth/login/",
        {"email": tenant_a.owner.email, "password": PASSWORD},
        format="json",
    )
    assert response.status_code == 200
    assert response.data.get("mfa_required") is True
    assert "refresh" not in response.data
    outstanding = OutstandingToken.objects.filter(user=tenant_a.owner)
    assert outstanding.exists()
    assert BlacklistedToken.objects.filter(token__in=outstanding).count() == outstanding.count()


def test_bug_sec_012_portal_phone_matches_formatted_numbers(tenant_a, tenant_b):
    flags = dict(tenant_a.company.feature_flags or {})
    flags["ENABLE_CUSTOMER_PORTAL"] = True
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    make_customer(tenant_a.company, name="Portal A", phone="+91 98450-11111")
    make_customer(tenant_b.company, name="Portal B", phone="9845022222")
    response = APIClient().post(
        "/api/v1/public/customer-portal/request-link/",
        {"phone": "919845011111"},
        format="json",
    )
    assert response.status_code == 200
    from payments.models import CustomerPortalToken

    assert CustomerPortalToken.objects.filter(company=tenant_a.company).count() == 1
    assert CustomerPortalToken.objects.filter(company=tenant_b.company).count() == 0


def test_bug_sec_006_erasure_coverage_includes_every_protect_fk():
    assert_erasure_model_coverage()


def test_bug_sec_013_erase_company_refuses_production_without_force(settings):
    settings.DJANGO_ENV = "production"
    with pytest.raises(CommandError, match="--force"):
        call_command("erase_company", company_id=1, confirm="nobody")


def test_bug_sec_020_reset_user_mfa_refuses_staging_without_force(settings):
    settings.DJANGO_ENV = "staging"
    with pytest.raises(CommandError, match="--force"):
        call_command("reset_user_mfa", email="owner@alpha.test")


def test_bug_sec_020_grant_flag_refuses_production_without_force(settings):
    settings.DJANGO_ENV = "production"
    with pytest.raises(CommandError, match="--force"):
        call_command("grant_company_flag", email="owner@alpha.test", flag="ENABLE_POS", on=True)


@override_settings(OPS_ALERT_TOKEN="ops-secret", DJANGO_ENV="production")
def test_bug_sec_021_production_rejects_query_string_token():
    client = APIClient()
    query = client.post("/api/v1/ops/alert/?token=ops-secret", {}, format="json")
    assert query.status_code == 401
    header = client.post(
        "/api/v1/ops/alert/",
        {},
        format="json",
        HTTP_X_OPS_ALERT_TOKEN="ops-secret",
    )
    assert header.status_code == 200


def _completed_sale(tenant):
    product = make_product(tenant.company, sku="BUG-W2")
    add_stock(tenant, product, "10")
    customer = make_customer(tenant.company, state="Karnataka")
    inv = create_draft_invoice(tenant, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100"},
    ])
    resp = tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 200, resp.data
    return resp.data, customer


def test_bug_sales_022_allocation_quantizes_sub_paisa(tenant_a):
    inv, customer = _completed_sale(tenant_a)
    receipt = PaymentService.create_receipt(
        company=tenant_a.company,
        customer=customer,
        amount=Decimal("100.00"),
        mode="CASH",
        user=tenant_a.owner,
    )
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    alloc = PaymentService.allocate_receipt(
        receipt=receipt,
        sales_invoice=invoice,
        amount=Decimal("100.004"),
        user=tenant_a.owner,
    )
    assert alloc.amount == Decimal("100.00")


def test_bug_sales_017_receipt_create_requires_idempotency_key(tenant_a):
    customer = make_customer(tenant_a.company, name="Key Customer")
    missing = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {"customer": customer.id, "amount": "10", "mode": "CASH"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="",
    )
    assert missing.status_code == 400
    assert "Idempotency-Key" in str(missing.data)


def test_bug_sales_012_record_payment_replays_the_same_key(tenant_a):
    inv, _customer = _completed_sale(tenant_a)
    url = f"/api/v1/sales/invoices/{inv['id']}/record-payment/"
    body = {"amount": "50", "mode": "CASH"}
    first = tenant_a.client.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY="pay-once")
    assert first.status_code == 200, first.data
    second = tenant_a.client.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY="pay-once")
    assert second.status_code == 200, second.data
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 1


def test_bug_sales_013_settlement_discount_is_posted_to_receivable(tenant_a):
    from accounting.models import JournalLine
    from accounting.services import seed_chart_of_accounts

    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(company, tenant_a.owner)
    inv, customer = _completed_sale(tenant_a)
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    receipt = PaymentService.create_receipt(
        company=company,
        customer=customer,
        amount=Decimal("100.00"),
        mode="CASH",
        user=tenant_a.owner,
        settlement_discount=Decimal("18.00"),
    )
    PaymentService.allocate_receipt(
        receipt=receipt, sales_invoice=invoice, amount=Decimal("100.00"), user=tenant_a.owner,
    )
    assert JournalLine.objects.filter(
        company=company, account__code="5150", debit=Decimal("18.00"),
    ).exists()
    from ledgers.services import LedgerService

    assert LedgerService.sales_invoice_outstanding(invoice) == Decimal("0.00")


def test_bug_sales_016_record_payment_requires_payment_permission(tenant_a):
    inv, _customer = _completed_sale(tenant_a)
    membership = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    membership.can_create_sales = True
    membership.can_create_payments = False
    membership.save(update_fields=["can_create_sales", "can_create_payments"])
    resp = tenant_a.staff_client.post(
        f"/api/v1/sales/invoices/{inv['id']}/record-payment/",
        {"amount": "10", "mode": "CASH"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="staff-pay",
    )
    assert resp.status_code == 403


def test_bug_sec_016_allocation_writes_an_audit_row(tenant_a):
    inv, customer = _completed_sale(tenant_a)
    receipt = PaymentService.create_receipt(
        company=tenant_a.company,
        customer=customer,
        amount=Decimal("10.00"),
        mode="CASH",
        user=tenant_a.owner,
    )
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    PaymentService.allocate_receipt(
        receipt=receipt, sales_invoice=invoice, amount=Decimal("10.00"), user=tenant_a.owner,
    )
    assert AuditEvent.objects.filter(
        company=tenant_a.company, description="payment_allocation.created",
    ).exists()


def test_bug_sales_005_set_items_is_atomic():
    from sales.services import SalesService

    assert getattr(SalesService.set_items, "__wrapped__", None) is not None


def test_bug_inv_005_transfer_complete_is_atomic():
    from inventory.services import StockTransferService

    source = inspect.getsource(StockTransferService.complete)
    assert "transaction.atomic" in source or getattr(StockTransferService.complete, "__wrapped__", None)


def test_bug_pay_004_refund_locks_the_gateway_payment():
    from payments.services import PaymentService as PS

    source = inspect.getsource(PS)
    assert "GatewayPayment.objects.select_for_update().get(pk=gp.pk)" in source


def test_bug_ins_004_renewal_lead_is_one_per_policy():
    from insurance.models import PolicyRenewalLead

    field = PolicyRenewalLead._meta.get_field("policy")
    assert field.one_to_one


def test_bug_pur_013_convert_locks_the_grn_row():
    from purchases.grn_service import GoodsReceiptService

    source = inspect.getsource(GoodsReceiptService.convert_to_bill)
    assert "select_for_update" in source


def test_bug_acc_013_bank_match_locks_both_rows():
    from accounting.views import BankReconSessionViewSet

    source = inspect.getsource(BankReconSessionViewSet.match)
    assert source.count("select_for_update") >= 2
    assert "transaction.atomic" in source or getattr(BankReconSessionViewSet.match, "__wrapped__", None)


def test_bug_bil_003_subscription_status_locks_the_row():
    from billing.services import apply_razorpay_subscription_status

    source = inspect.getsource(apply_razorpay_subscription_status)
    assert "select_for_update" in source
