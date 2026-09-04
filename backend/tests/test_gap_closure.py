"""Gap-closure sprint tests (2026-08-21 roadmap §0.2)."""

from decimal import Decimal

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from accounting.reports import balance_sheet
from core.services.billing import extract_exclusive_from_inclusive_line
from core.services.uqc import normalize_uqc
from ledgers.services import LedgerService
from masters.models import Unit
from reporting.gst_returns import B2CL_THRESHOLD, build_gstr1
from reporting.services import ReportService
from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


@override_settings(ENABLE_ACCOUNT_AGGREGATOR=True)
def test_aa_empty_rows_do_not_inject_mocks(tenant_a):
    resp = tenant_a.client.post(
        "/api/v1/banking/aa/ingest/",
        {"consent_id": "consent-empty-001", "fi_type": "DEPOSIT", "transactions": []},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["transactions"] == []


@override_settings(ENABLE_ACCOUNT_AGGREGATOR=True, DJANGO_ENV="production")
def test_aa_mock_fail_closed_outside_allowlist(tenant_a):
    resp = tenant_a.client.post(
        "/api/v1/banking/aa/ingest/",
        {"consent_id": "consent-prod-001", "fi_type": "DEPOSIT", "use_mock_fiu": True},
        format="json",
    )
    assert resp.status_code == 400


@override_settings(ENABLE_ACCOUNT_AGGREGATOR=True)
def test_aa_ingest_cannot_resurrect_a_revoked_consent(tenant_a):
    """B4-009: `status` is client-supplied on this endpoint. A caller must
    not be able to reactivate (and pull fresh financial data for) a consent
    the customer already revoked just by re-POSTing status=ACTIVE for the
    same consent_id."""
    from banking.models import AaConsent, AaTransaction

    consent = AaConsent.objects.create(
        company=tenant_a.company, consent_id="consent-revoked-001",
        status=AaConsent.Status.REVOKED,
    )
    resp = tenant_a.client.post(
        "/api/v1/banking/aa/ingest/",
        {
            "consent_id": "consent-revoked-001", "fi_type": "DEPOSIT",
            "status": "ACTIVE", "use_mock_fiu": True,
        },
        format="json",
    )
    assert resp.status_code == 400, resp.data
    consent.refresh_from_db()
    assert consent.status == AaConsent.Status.REVOKED
    assert not AaTransaction.objects.filter(consent=consent).exists()


@override_settings(ENABLE_ACCOUNT_AGGREGATOR=True)
def test_aa_ingest_rejects_expired_consent(tenant_a):
    from banking.models import AaConsent

    AaConsent.objects.create(
        company=tenant_a.company, consent_id="consent-expired-001",
        status=AaConsent.Status.EXPIRED,
    )
    resp = tenant_a.client.post(
        "/api/v1/banking/aa/ingest/",
        {"consent_id": "consent-expired-001", "fi_type": "DEPOSIT", "use_mock_fiu": True},
        format="json",
    )
    assert resp.status_code == 400, resp.data


@override_settings(ENABLE_ACCOUNT_AGGREGATOR=True, FIU_BASE_URL="https://fiu.example", FIU_API_KEY="k")
def test_aa_ingest_fetch_failure_does_not_roll_back_consent_upsert(tenant_a):
    """B4-009: the FIU HTTP fetch must run outside any DB transaction — the
    consent upsert (and any status-gate decision made from it) is committed
    in its own short transaction *before* the fetch runs, so a slow/failing
    FIU no longer holds a write transaction open across the network call,
    and a fetch failure can't roll back work that already legitimately
    committed."""
    from unittest.mock import patch

    from banking.models import AaConsent
    from core.exceptions import BusinessRuleError

    with patch(
        "banking.views.fetch_live_transactions_for_consent",
        side_effect=BusinessRuleError("Live AA FIU fetch failed closed."),
    ):
        resp = tenant_a.client.post(
            "/api/v1/banking/aa/ingest/",
            {
                "consent_id": "consent-live-fail-001", "fi_type": "DEPOSIT",
                "status": "ACTIVE", "use_live_fiu": True,
            },
            format="json",
        )
    assert resp.status_code == 400, resp.data
    # The consent row itself was upserted and committed before the fetch ran
    # -- under the old whole-view @transaction.atomic it would have been
    # rolled back along with everything else when the fetch raised.
    assert AaConsent.objects.filter(
        company=tenant_a.company, consent_id="consent-live-fail-001", status=AaConsent.Status.ACTIVE,
    ).exists()


def test_dashboard_receivables_match_ledger_service(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "20")
    customer = make_customer(tenant_a.company, state="Karnataka")
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "2", "unit_price": "100", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    expected = LedgerService.company_receivables(tenant_a.company)
    assert ReportService._company_receivables(tenant_a.company) == expected
    dash = tenant_a.client.get("/api/v1/dashboard/")
    assert dash.status_code == 200
    assert Decimal(str(dash.data["receivables"])) == expected


def test_b2cl_threshold_is_one_lakh_from_aug_2024():
    assert B2CL_THRESHOLD == Decimal("100000")


def test_b2cl_classifies_above_new_threshold(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save(update_fields=["gstin", "state"])
    product = make_product(tenant_a.company, sku="B2CL-BIG", hsn_code="1001")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="Delhi URP", state="Delhi", gstin="")
    period = timezone.localdate().strftime("%Y-%m")
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "260000", "gst_rate": "18"}],
    )
    SalesInvoice.objects.filter(pk=inv["id"]).update(invoice_date=f"{period}-10")
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    payload = build_gstr1(tenant_a.company, period)
    assert payload["b2cl"]
    assert all(Decimal(str(r["invoice_value"])) > B2CL_THRESHOLD for r in payload["b2cl"])


def test_payment_link_cancels_when_invoice_cancelled(tenant_a):
    from payments.models import PaymentLinkStatus
    from payments.services import PaymentService
    from sales.services import SalesService
    from tests.test_phase3_payments import _complete_invoice

    inv, customer = _complete_invoice(tenant_a)
    link = PaymentService.create_payment_link(
        company=tenant_a.company,
        amount=Decimal("1000"),
        sales_invoice=inv,
        customer=customer,
        provider="sandbox",
    )
    SalesService.cancel(inv, tenant_a.owner)
    link.refresh_from_db()
    assert link.status == PaymentLinkStatus.CANCELLED


def test_webhook_capture_after_invoice_cancel_parks_and_alerts(tenant_a):
    """Owner decision 2026-09-01: a verified capture against a CANCELLED invoice is
    never dropped — the webhook 200s, the capture is parked as
    CAPTURED_PENDING_BOOKS (no receipt posted), and a health alert surfaces it
    for refund."""
    from payments.models import CustomerReceipt, GatewayPayment, GatewayPaymentStatus
    from payments.services import PaymentService
    from sales.services import SalesService
    from tests.test_phase3_payments import _complete_invoice, _post_sandbox_webhook

    inv, customer = _complete_invoice(tenant_a)
    link = PaymentService.create_payment_link(
        company=tenant_a.company,
        amount=Decimal("1000"),
        sales_invoice=inv,
        customer=customer,
        provider="sandbox",
    )
    SalesService.cancel(inv, tenant_a.owner)
    body = {
        "payment_id": "pay_cancelled_inv",
        "amount": "1000.00",
        "fee": "0",
        "status": "CAPTURED",
        "payment_link_id": link.provider_link_id,
    }
    wh = _post_sandbox_webhook(tenant_a.client, tenant_a.company.id, body)
    assert wh.status_code == 200, wh.data

    gp = GatewayPayment.objects.get(company=tenant_a.company, provider_payment_id="pay_cancelled_inv")
    assert gp.status == GatewayPaymentStatus.CAPTURED_PENDING_BOOKS
    # Cancelling the invoice also cancels its link, so the webhook trips the
    # LINK_CANCELLED guard first; INVOICE_CANCELLED covers a live-link edge case.
    assert gp.holding_reason in ("LINK_CANCELLED", "INVOICE_CANCELLED")
    # Nothing hit the books.
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 0
    # And it is surfaced for the owner to refund.
    health = PaymentService.payment_health(company=tenant_a.company)
    assert any(a["code"] == "GATEWAY_CAPTURE_HOLDING" for a in health["alerts"])


def test_pan_udyam_verify_soft_fail(tenant_a):
    ok = tenant_a.client.patch(
        "/api/v1/company/",
        {"pan": "ABCDE1234F", "udyam": "UDYAM-KR-03-0001234"},
        format="json",
    )
    assert ok.status_code == 200, ok.data
    pan = tenant_a.client.post("/api/v1/company/verify-pan/", format="json")
    assert pan.status_code == 200, pan.data
    assert pan.data["pan_verification_status"] == "UNVERIFIED"
    assert pan.data["pan_verified_at"] is None
    udyam = tenant_a.client.post("/api/v1/company/verify-udyam/", format="json")
    assert udyam.status_code == 200, udyam.data
    assert udyam.data["udyam_verification_status"] == "UNVERIFIED"
    bad = tenant_a.client.post("/api/v1/company/verify-pan/", {"pan": "NOTAPAN"}, format="json")
    assert bad.status_code == 200
    assert bad.data["pan_verification_status"] == "INVALID"


def test_backfill_uqc_maps_piece(tenant_a):
    unit = Unit.objects.create(company=tenant_a.company, name="Piece", short_name="pcs", uqc_code="")
    call_command("backfill_uqc")
    unit.refresh_from_db()
    assert unit.uqc_code == "PCS"
    assert normalize_uqc("kg") == "KGS"


def test_balance_sheet_includes_valuation_overlay(tenant_a):
    data = balance_sheet(tenant_a.company)
    assert "inventory_gl" in data
    assert "inventory_valuation" in data
    assert "inventory_source" in data
    assert "inventory_note" in data


def test_inclusive_cess_extract_and_irp_payload():
    exclusive, taxable = extract_exclusive_from_inclusive_line(
        quantity=Decimal("1"),
        unit_price_inclusive=Decimal("119"),
        discount_percent=Decimal("0"),
        gst_rate=Decimal("18"),
        cess_rate=Decimal("1"),
    )
    assert exclusive == Decimal("100.00")
    assert taxable == Decimal("100.00")
    # IRP CesRt/CesAmt are populated from line cess_rate/cess in
    # sales/einvoice_payload.py; GL 2270 is covered by test_sprint2_cess_reverse.
