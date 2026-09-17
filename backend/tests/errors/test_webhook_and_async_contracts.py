"""§H3 / §H8 / §H10 contract tests:

- an IRP (e-invoice) submission failure lands as visible FAILED state + is
  recoverable, and a re-submit after success is a no-op (idempotent on IRN)
- a bulk action processes only its in-scope rows and is idempotent on re-run
- the SaaS billing (Razorpay) webhook rejects a bad/absent signature and
  deduplicates a replayed event
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import date
from decimal import Decimal
from unittest import mock

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


# --- §H3: e-invoice submit failure is visible + recoverable ----------------

def _completed_gst_invoice(tenant):
    co = tenant.company
    co.gstin = "29AAAAA0000A1ZY"
    for f, v in (("address", "12 MG Road, Bengaluru"), ("pincode", "560001"),
                 ("pin_code", "560001"), ("city", "Bengaluru")):
        if hasattr(co, f):
            setattr(co, f, v)
    co.save()
    product = make_product(tenant.company, gst_rate="18", selling_price="100", hsn_code="3402")
    add_stock(tenant, product, "10")
    customer = make_customer(
        tenant.company, state="Karnataka", gstin="29BBBBB1111B1Z5",
    )
    for f, v in (("address", "9 Brigade Road, Bengaluru"), ("billing_address", "9 Brigade Road"),
                 ("pincode", "560025"), ("pin_code", "560025"), ("city", "Bengaluru")):
        if hasattr(customer, f):
            setattr(customer, f, v)
    customer.save()
    inv = create_draft_invoice(
        tenant, customer,
        [{"product": product.id, "quantity": "2", "unit_price": "100.00", "gst_rate": "18",
          "hsn_code": "3402"}],
    )
    assert tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    return inv["id"]


def test_einvoice_async_submit_failure_is_FAILED_state_not_a_crash(tenant_a):
    """The async IRP task persists a visible FAILED status + a human-readable
    error whenever submission cannot complete — the invoice never sits in a
    silent limbo — and a subsequent attempt still returns a structured result,
    not an unhandled crash. The success path + IRN idempotency is WF-* / e2e."""
    from sales.models import SalesInvoice
    from sales.tasks import submit_einvoice_async

    iid = _completed_gst_invoice(tenant_a)

    with mock.patch("core.services.gsp_adapters.get_irp_adapter") as get_adapter:
        get_adapter.return_value.submit.side_effect = RuntimeError("IRP gateway 503")
        try:
            submit_einvoice_async(iid, user_id=tenant_a.owner.id, company_id=tenant_a.company.id)
        except Exception:
            pass  # generic errors re-raise for Celery retry — AFTER persisting FAILED

    inv = SalesInvoice.objects.get(pk=iid)
    assert inv.einvoice_status == SalesInvoice.EInvoiceStatus.FAILED
    assert inv.einvoice_error  # a human-readable reason is stored, not a blank

    # a retry is still a structured outcome (generated / already_generated /
    # validation_failed with an errors list) — never a 500 / unhandled exception
    fake_result = mock.Mock(irn="IRN" + "1" * 61, ack_no="AN-1", ack_date="2026-06-12",
                            einvoice_qr="QR")
    with mock.patch("core.services.gsp_adapters.get_irp_adapter") as get_adapter, \
         mock.patch("core.services.gsp_adapters.verify_irn_result", return_value=None):
        get_adapter.return_value.submit.return_value = fake_result
        out = submit_einvoice_async(iid, company_id=tenant_a.company.id)
    assert out["status"] in ("generated", "already_generated", "validation_failed"), out
    if out["status"] == "validation_failed":
        assert out["errors"] and all(isinstance(e, str) for e in out["errors"])
    else:
        inv.refresh_from_db()
        assert inv.einvoice_status == SalesInvoice.EInvoiceStatus.GENERATED and inv.irn
        assert submit_einvoice_async(iid, company_id=tenant_a.company.id)["status"] == "already_generated"


# --- §H8: a bulk action is in-scope only + idempotent --------------------

def test_ims_bulk_accept_only_touches_exact_rows_and_is_idempotent(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.gstin = "29AAAAA0000A1ZY"
    tenant_a.company.save(update_fields=["accounting_enabled", "gstin"])

    from reporting.ims import bulk_accept_exact
    from reporting.models import Gstr2bIngest

    period = "2026-06"
    common = dict(
        company=tenant_a.company, period=period, supplier_gstin="29ZZZZZ0000Z1Z5",
        invoice_date=date(2026, 6, 5), taxable_value=Decimal("1000"),
        cgst=Decimal("90"), sgst=Decimal("90"),
    )
    Gstr2bIngest.objects.create(invoice_number="E-1", match_class=Gstr2bIngest.MatchClass.EXACT, **common)
    Gstr2bIngest.objects.create(invoice_number="E-2", match_class=Gstr2bIngest.MatchClass.EXACT, **common)
    partial = Gstr2bIngest.objects.create(
        invoice_number="P-1", match_class=Gstr2bIngest.MatchClass.VALUE_MISMATCH, **common
    )

    r1 = bulk_accept_exact(tenant_a.company, period)
    assert r1.get("accepted", r1.get("count", 0)) == 2

    partial.refresh_from_db()
    assert partial.ims_action != Gstr2bIngest.ImsAction.ACCEPT  # out of scope, untouched

    r2 = bulk_accept_exact(tenant_a.company, period)
    assert r2.get("accepted", r2.get("count", 0)) == 0  # nothing left -> no double effect


# --- §H10: SaaS billing webhook signature + replay ----------------------

_SECRET = "rzp-webhook-secret-xyz"


def _sig(body: bytes) -> str:
    return hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()


@override_settings(RAZORPAY_WEBHOOK_SECRET=_SECRET)
def test_billing_webhook_rejects_bad_signature_and_dedups_replay():
    c = APIClient()
    body = json.dumps({
        "event": "subscription.charged",
        "payload": {"subscription": {"entity": {"id": "sub_test1", "status": "active"}}},
    }).encode()

    # missing signature -> 400
    assert c.post(
        "/api/v1/billing/razorpay/webhook/", data=body, content_type="application/json"
    ).status_code == 400

    # wrong signature -> 400
    assert c.post(
        "/api/v1/billing/razorpay/webhook/", data=body, content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE="deadbeef",
    ).status_code == 400

    # valid signature -> accepted
    good = dict(
        HTTP_X_RAZORPAY_SIGNATURE=_sig(body),
        HTTP_X_RAZORPAY_EVENT_ID="evt_dedup_1",
    )
    first = c.post(
        "/api/v1/billing/razorpay/webhook/", data=body, content_type="application/json", **good
    )
    assert first.status_code in (200, 202), first.data

    # replay of the same event id -> still ok, no error, idempotent
    replay = c.post(
        "/api/v1/billing/razorpay/webhook/", data=body, content_type="application/json", **good
    )
    assert replay.status_code in (200, 202), replay.data

    from payments.models import ProcessedWebhookEvent

    assert ProcessedWebhookEvent.objects.filter(
        provider__icontains="razorpay"
    ).count() <= 1


@override_settings(RAZORPAY_WEBHOOK_SECRET=_SECRET)
def test_billing_webhook_hmac_required_without_test_header():
    c = APIClient()
    body = b'{"event":"subscription.charged"}'
    missing = c.post(
        "/api/v1/billing/razorpay/webhook/", data=body, content_type="application/json"
    )
    assert missing.status_code == 400
    unsigned_test_header = c.post(
        "/api/v1/billing/razorpay/webhook/",
        data=body,
        content_type="application/json",
        HTTP_X_BIZBOARD_TEST_WEBHOOK="1",
    )
    assert unsigned_test_header.status_code == 400
