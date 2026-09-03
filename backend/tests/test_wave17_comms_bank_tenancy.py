"""Wave 17E/F/G — WhatsApp, AA banking, gateways, multi-company, feature flags."""

from decimal import Decimal

import pytest
from django.test import override_settings

from accounts.models import CompanyUser
from core.services.whatsapp import send_whatsapp_template
from payments.gateway import CashfreeGateway, PayUGateway, get_adapter

pytestmark = pytest.mark.django_db


def test_whatsapp_fallback_wa_me_link():
    result = send_whatsapp_template("919876543210", "invoice_ready", ["INV-001", "1500"])
    assert result.mode == "link"
    assert result.share_link.startswith("https://wa.me/919876543210")


@override_settings(WHATSAPP_TOKEN="", WHATSAPP_PHONE_NUMBER_ID="")
def test_whatsapp_unconfigured_always_link():
    result = send_whatsapp_template("+91 98765 43210", "payment_reminder", {"amount": "500"})
    assert result.mode == "link"
    assert "wa.me" in result.share_link


def test_cashfree_adapter_exists_and_fail_closed_without_credentials():
    adapter = CashfreeGateway({})
    assert adapter.name == "cashfree"
    with pytest.raises(Exception) as exc:
        adapter.create_payment_link(
            amount=Decimal("100"),
            description="Test",
            customer_name="A",
            customer_email="a@test.com",
            customer_phone="9999999999",
            reference="ref1",
            callback_url="https://example.com/cb",
        )
    assert "not configured" in str(exc.value).lower()


def test_payu_adapter_exists_and_fail_closed_without_credentials():
    adapter = PayUGateway({})
    assert adapter.name == "payu"
    with pytest.raises(Exception) as exc:
        adapter.create_payment_link(
            amount=Decimal("100"),
            description="Test",
            customer_name="A",
            customer_email="a@test.com",
            customer_phone="9999999999",
            reference="ref1",
            callback_url="https://example.com/cb",
        )
    assert "not configured" in str(exc.value).lower()


@override_settings(ENABLE_CASHFREE=True)
def test_get_adapter_registers_cashfree_class():
    adapter = get_adapter("cashfree", {"app_id": "", "secret_key": ""})
    assert adapter.name == "cashfree"
    with pytest.raises(Exception) as exc:
        adapter.create_payment_link(
            amount=Decimal("100"),
            description="Test",
            customer_name="A",
            customer_email="a@test.com",
            customer_phone="9999999999",
            reference="ref1",
            callback_url="https://example.com/cb",
        )
    assert "not configured" in str(exc.value).lower()


@override_settings(ENABLE_ACCOUNT_AGGREGATOR=True)
def test_aa_ingest_and_list(tenant_a):
    resp = tenant_a.client.post(
        "/api/v1/banking/aa/ingest/",
        {"consent_id": "consent-test-001", "fi_type": "DEPOSIT", "use_mock_fiu": True},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["consent"]["consent_id"] == "consent-test-001"
    assert len(resp.data["transactions"]) >= 1

    listed = tenant_a.client.get("/api/v1/banking/aa/")
    assert listed.status_code == 200
    assert listed.data["consents"][0]["consent_id"] == "consent-test-001"


def test_aa_matcher_matches_on_narration_utr_and_unique_amount(tenant_a):
    """INTG-02: match on a UTR parsed from the narration, and on a lone
    amount+date candidate — not only reference == txn_id."""
    from datetime import date

    from banking.models import AaConsent, AaTransaction
    from banking.services import match_aa_to_receipts
    from masters.models import Customer
    from payments.models import CustomerReceipt, ReceiptStatus

    cust = Customer.objects.create(company=tenant_a.company, name="Imp Co")
    consent = AaConsent.objects.create(company=tenant_a.company, consent_id="c-utr-1")

    r_utr = CustomerReceipt.objects.create(
        company=tenant_a.company, customer=cust, amount=Decimal("1500.00"),
        receipt_date=date(2026, 6, 10), status=ReceiptStatus.POSTED,
        utr="AXISP002391847", number="RCPT-1",
    )
    AaTransaction.objects.create(
        company=tenant_a.company, consent=consent, txn_id="bankinternal-9001",
        amount=Decimal("1500.00"), txn_date=date(2026, 6, 11),
        raw={"narration": "UPI/CR/AXISP002391847/IMP CO"},
    )

    r_amt = CustomerReceipt.objects.create(
        company=tenant_a.company, customer=cust, amount=Decimal("7321.55"),
        receipt_date=date(2026, 6, 12), status=ReceiptStatus.POSTED, number="RCPT-2",
    )
    AaTransaction.objects.create(
        company=tenant_a.company, consent=consent, txn_id="bankinternal-9002",
        amount=Decimal("7321.55"), txn_date=date(2026, 6, 12),
        raw={"narration": "NEFT/CR/UNKNOWN"},
    )

    # Ambiguous: two receipts of the same amount → left for a human.
    for n in ("RCPT-3a", "RCPT-3b"):
        CustomerReceipt.objects.create(
            company=tenant_a.company, customer=cust, amount=Decimal("999.00"),
            receipt_date=date(2026, 6, 12), status=ReceiptStatus.POSTED, number=n,
        )
    AaTransaction.objects.create(
        company=tenant_a.company, consent=consent, txn_id="bankinternal-9003",
        amount=Decimal("999.00"), txn_date=date(2026, 6, 12), raw={"narration": "IMPS/CR"},
    )

    matched = match_aa_to_receipts(company=tenant_a.company)
    assert matched == 2
    assert AaTransaction.objects.get(txn_id="bankinternal-9001").matched_payment_id == r_utr.id
    assert AaTransaction.objects.get(txn_id="bankinternal-9002").matched_payment_id == r_amt.id
    assert AaTransaction.objects.get(txn_id="bankinternal-9003").matched_payment_id is None


def test_switch_company_multi_membership(tenant_a, tenant_b):
    user = tenant_a.owner
    # Same user active in two companies
    CompanyUser.objects.create(
        company=tenant_b.company,
        user=user,
        role=CompanyUser.Role.OWNER,
        can_manage_inventory=True,
        can_import=True,
        can_create_sales=True,
        can_create_purchases=True,
        can_create_payments=True,
        can_view_financial_reports=True,
        can_export=True,
    )
    user.active_company_id = tenant_a.company.id
    user.save(update_fields=["active_company_id"])

    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=user)

    me = client.get("/api/v1/auth/me/")
    assert me.status_code == 200
    assert me.data["company_id"] == tenant_a.company.id

    switched = client.post(
        "/api/v1/auth/switch-company/",
        {"company_id": tenant_b.company.id},
        format="json",
    )
    assert switched.status_code == 200, switched.data
    assert switched.data["user"]["company_id"] == tenant_b.company.id

    user.refresh_from_db()
    assert user.active_company_id == tenant_b.company.id


@override_settings(ENABLE_MANUFACTURING=True, ENABLE_PAYROLL=True, ENABLE_CRM=True)
def test_feature_flags_dark_modules_require_company_opt_in(tenant_a):
    tenant_a.company.feature_flags = {"ENABLE_CRM": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    resp = tenant_a.client.get("/api/v1/feature-flags/")
    assert resp.status_code == 200
    assert resp.data["ENABLE_MANUFACTURING"] is False
    assert resp.data["ENABLE_PAYROLL"] is False
    assert resp.data["ENABLE_CRM"] is True


@override_settings(ENABLE_MANUFACTURING=True, ENABLE_PAYROLL=False, ENABLE_CRM=True)
def test_feature_flags_endpoint(tenant_a):
    tenant_a.company.feature_flags = {"ENABLE_CRM": True, "ENABLE_MANUFACTURING": False}
    tenant_a.company.save(update_fields=["feature_flags"])

    resp = tenant_a.client.get("/api/v1/feature-flags/")
    assert resp.status_code == 200
    assert resp.data["ENABLE_MANUFACTURING"] is False
    assert resp.data["ENABLE_PAYROLL"] is False
    assert resp.data["ENABLE_CRM"] is True
    assert resp.data["item_custom_fields_v2"] is True


def test_feature_flags_anonymous_ok():
    from rest_framework.test import APIClient

    resp = APIClient().get("/api/v1/feature-flags/")
    assert resp.status_code == 200
    assert "ENABLE_SETUP_WIZARD" in resp.data
    assert "ENABLE_MANUFACTURING" not in resp.data
    assert "ENABLE_PAYROLL" not in resp.data
