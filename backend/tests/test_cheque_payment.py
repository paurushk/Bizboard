from decimal import Decimal

import pytest
from django.core.files.base import ContentFile

from payments.models import ChequeStatus, PaymentMode
from payments.services import PaymentService
from tests.conftest import add_stock, make_customer, make_product


@pytest.mark.django_db
def test_cheque_receipt_requires_number_and_bank(tenant_a):
    customer = make_customer(tenant_a.company)
    with pytest.raises(Exception):
        PaymentService.create_receipt(
            company=tenant_a.company,
            customer=customer,
            amount=Decimal("100.00"),
            mode=PaymentMode.CHEQUE,
            user=tenant_a.owner,
        )


@pytest.mark.django_db
def test_cheque_receipt_starts_pending_and_bounce_voids(tenant_a):
    customer = make_customer(tenant_a.company)
    rec = PaymentService.create_receipt(
        company=tenant_a.company,
        customer=customer,
        amount=Decimal("100.00"),
        mode=PaymentMode.CHEQUE,
        user=tenant_a.owner,
        cheque_number="123456",
        cheque_bank_name="HDFC",
    )
    assert rec.cheque_status == ChequeStatus.PENDING_CLEARANCE
    cleared = PaymentService.set_cheque_status(
        receipt=rec, cheque_status=ChequeStatus.CLEARED,         user=tenant_a.owner
    )
    assert cleared.cheque_status == ChequeStatus.CLEARED
    bounced = PaymentService.set_cheque_status(
        receipt=cleared, cheque_status=ChequeStatus.BOUNCED, user=tenant_a.owner
    )
    assert bounced.cheque_status == ChequeStatus.BOUNCED
    assert bounced.status == "VOIDED"


@pytest.mark.django_db
def test_bounced_cheque_cannot_be_re_cleared(tenant_a):
    """A BOUNCED cheque is terminal — flipping it back to CLEARED must not be
    possible, since the receipt was already voided and its allocations
    reversed; re-clearing would make it look settled when the money never
    arrived."""
    customer = make_customer(tenant_a.company)
    rec = PaymentService.create_receipt(
        company=tenant_a.company,
        customer=customer,
        amount=Decimal("100.00"),
        mode=PaymentMode.CHEQUE,
        user=tenant_a.owner,
        cheque_number="123456",
        cheque_bank_name="HDFC",
    )
    bounced = PaymentService.set_cheque_status(
        receipt=rec, cheque_status=ChequeStatus.BOUNCED, user=tenant_a.owner
    )
    assert bounced.status == "VOIDED"
    with pytest.raises(Exception):
        PaymentService.set_cheque_status(
            receipt=bounced, cheque_status=ChequeStatus.CLEARED, user=tenant_a.owner
        )
    bounced.refresh_from_db()
    assert bounced.cheque_status == ChequeStatus.BOUNCED
    assert bounced.status == "VOIDED"


@pytest.mark.django_db
def test_set_cheque_status_http_clears_pending(tenant_a):
    customer = make_customer(tenant_a.company)
    created = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {
            "customer": customer.id,
            "amount": "100.00",
            "mode": PaymentMode.CHEQUE,
            "cheque_number": "123456",
            "cheque_bank_name": "HDFC",
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    rid = created.data["id"]
    assert created.data.get("cheque_status") == ChequeStatus.PENDING_CLEARANCE
    cleared = tenant_a.client.post(
        f"/api/v1/payments/receipts/{rid}/set-cheque-status/",
        {"cheque_status": ChequeStatus.CLEARED},
        format="json",
    )
    assert cleared.status_code == 200, cleared.data
    assert cleared.data.get("cheque_status") == ChequeStatus.CLEARED


@pytest.mark.django_db
def test_cheque_receipt_http_stores_image(tenant_a):
    from core.models import FileAsset

    customer = make_customer(tenant_a.company)
    asset = FileAsset.objects.create(
        company=tenant_a.company,
        kind=FileAsset.Kind.ATTACHMENT,
        original_name="cheque.jpg",
        content_type="image/jpeg",
        size=4,
    )
    asset.file.save(f"{asset.pk}.jpg", ContentFile(b"\xff\xd8\xff\xd9"), save=True)
    created = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {
            "customer": customer.id,
            "amount": "50.00",
            "mode": PaymentMode.CHEQUE,
            "cheque_number": "654321",
            "cheque_bank_name": "ICICI",
            "cheque_image": asset.pk,
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    assert created.data.get("cheque_image") == asset.pk


@pytest.mark.django_db
def test_pos_checkout_cheque_requires_details_and_stays_pending(tenant_a):
    product = make_product(tenant_a.company, gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "10", unit_cost="40")
    customer = make_customer(tenant_a.company, state="Karnataka")
    payload = {
        "invoice": {
            "customer": customer.id,
            "invoice_type": "NON_GST",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "0"}],
        },
        "payment": {"mode": "CHEQUE", "amount": "100.00"},
    }
    blocked = tenant_a.client.post("/api/v1/sales/invoices/pos-checkout/", payload, format="json")
    assert blocked.status_code == 400, blocked.data
    payload["payment"].update({"cheque_number": "998877", "cheque_bank_name": "AXIS"})
    ok = tenant_a.client.post("/api/v1/sales/invoices/pos-checkout/", payload, format="json")
    assert ok.status_code == 201, ok.data
    from payments.models import CustomerReceipt

    receipt = CustomerReceipt.objects.get(pk=ok.data["receipt"]["id"])
    assert receipt.mode == PaymentMode.CHEQUE
    assert receipt.cheque_number == "998877"
    assert receipt.cheque_status == ChequeStatus.PENDING_CLEARANCE


@pytest.mark.django_db
def test_set_cheque_status_http_bounce_voids(tenant_a):
    customer = make_customer(tenant_a.company)
    created = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {
            "customer": customer.id,
            "amount": "80.00",
            "mode": PaymentMode.CHEQUE,
            "cheque_number": "777777",
            "cheque_bank_name": "PNB",
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    bounced = tenant_a.client.post(
        f"/api/v1/payments/receipts/{created.data['id']}/set-cheque-status/",
        {"chequeStatus": ChequeStatus.BOUNCED},
        format="json",
    )
    assert bounced.status_code == 200, bounced.data
    assert bounced.data.get("cheque_status") == ChequeStatus.BOUNCED
    assert bounced.data.get("status") == "VOIDED"


@pytest.mark.django_db
def test_set_cheque_status_staff_without_payments_cap_denied(tenant_a):
    customer = make_customer(tenant_a.company)
    rec = PaymentService.create_receipt(
        company=tenant_a.company,
        customer=customer,
        amount=Decimal("40.00"),
        mode=PaymentMode.CHEQUE,
        user=tenant_a.owner,
        cheque_number="555555",
        cheque_bank_name="BOI",
    )
    denied = tenant_a.staff_client.post(
        f"/api/v1/payments/receipts/{rec.id}/set-cheque-status/",
        {"cheque_status": ChequeStatus.CLEARED},
        format="json",
    )
    assert denied.status_code == 403
    rec.refresh_from_db()
    assert rec.cheque_status == ChequeStatus.PENDING_CLEARANCE


@pytest.mark.django_db
def test_supplier_payment_cheque_http_create(tenant_a):
    from tests.conftest import make_supplier

    supplier = make_supplier(tenant_a.company)
    created = tenant_a.client.post(
        "/api/v1/payments/supplier-payments/",
        {
            "supplier": supplier.id,
            "amount": "75.00",
            "mode": PaymentMode.CHEQUE,
            "cheque_number": "445566",
            "cheque_bank_name": "Yes Bank",
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    assert created.data.get("mode") == PaymentMode.CHEQUE
    assert created.data.get("cheque_number") == "445566"
    assert created.data.get("cheque_status") == ChequeStatus.PENDING_CLEARANCE


@pytest.mark.django_db
def test_record_invoice_payment_forwards_cheque_fields(tenant_a):
    from payments.models import CustomerReceipt

    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="CHQ-INV", gst_rate="0")
    add_stock(tenant_a, product, "5", unit_cost="40")
    from tests.conftest import create_draft_invoice

    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    paid = tenant_a.client.post(
        f"/api/v1/sales/invoices/{inv['id']}/record-payment/",
        {
            "amount": "100.00",
            "mode": PaymentMode.CHEQUE,
            "chequeNumber": "332211",
            "chequeBankName": "Kotak",
        },
        format="json",
    )
    assert paid.status_code == 200, paid.data
    rec = CustomerReceipt.objects.get(company=tenant_a.company, cheque_number="332211")
    assert rec.mode == PaymentMode.CHEQUE
    assert rec.cheque_bank_name == "Kotak"
    assert rec.cheque_status == ChequeStatus.PENDING_CLEARANCE


@pytest.mark.django_db
def test_pos_checkout_cheque_stores_image(tenant_a):
    from core.models import FileAsset
    from payments.models import CustomerReceipt

    product = make_product(tenant_a.company, gst_rate="0", selling_price="100", sku="POS-CHQ")
    add_stock(tenant_a, product, "10", unit_cost="40")
    customer = make_customer(tenant_a.company, state="Karnataka")
    asset = FileAsset.objects.create(
        company=tenant_a.company,
        kind=FileAsset.Kind.ATTACHMENT,
        original_name="pos-cheque.jpg",
        content_type="image/jpeg",
        size=4,
    )
    asset.file.save(f"{asset.pk}.jpg", ContentFile(b"\xff\xd8\xff\xd9"), save=True)
    ok = tenant_a.client.post(
        "/api/v1/sales/invoices/pos-checkout/",
        {
            "invoice": {
                "customer": customer.id,
                "invoice_type": "NON_GST",
                "items": [{"product": product.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "0"}],
            },
            "payment": {
                "mode": "CHEQUE",
                "amount": "100.00",
                "cheque_number": "110022",
                "cheque_bank_name": "Canara",
                "cheque_image": asset.pk,
            },
        },
        format="json",
    )
    assert ok.status_code == 201, ok.data
    receipt = CustomerReceipt.objects.get(pk=ok.data["receipt"]["id"])
    assert receipt.cheque_image_id == asset.pk


@pytest.mark.django_db
def test_cheque_fields_from_payload_normalizes_camel_case(tenant_a):
    from payments.services import cheque_fields_from_payload

    fields = cheque_fields_from_payload(
        {"chequeNumber": "1", "chequeBankName": "SBI", "chequeDate": "", "chequeImage": "not-an-id"},
        company=tenant_a.company,
    )
    assert fields["cheque_number"] == "1"
    assert fields["cheque_bank_name"] == "SBI"
    assert fields["cheque_date"] is None
    assert fields["cheque_image"] is None


@pytest.mark.django_db
def test_supplier_cheque_clear_and_bounce_http(tenant_a):
    from payments.models import SupplierPayment, SupplierPaymentStatus
    from tests.conftest import make_supplier

    supplier = make_supplier(tenant_a.company)
    created = tenant_a.client.post(
        "/api/v1/payments/supplier-payments/",
        {
            "supplier": supplier.id,
            "amount": "80.00",
            "mode": PaymentMode.CHEQUE,
            "cheque_number": "778899",
            "cheque_bank_name": "Canara",
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    pay_id = created.data["id"]
    cleared = tenant_a.client.post(
        f"/api/v1/payments/supplier-payments/{pay_id}/set-cheque-status/",
        {"chequeStatus": ChequeStatus.CLEARED},
        format="json",
    )
    assert cleared.status_code == 200, cleared.data
    assert cleared.data.get("cheque_status") == ChequeStatus.CLEARED
    bounced = tenant_a.client.post(
        f"/api/v1/payments/supplier-payments/{pay_id}/set-cheque-status/",
        {"cheque_status": ChequeStatus.BOUNCED},
        format="json",
    )
    assert bounced.status_code == 200, bounced.data
    pay = SupplierPayment.objects.get(pk=pay_id)
    assert pay.cheque_status == ChequeStatus.BOUNCED
    assert pay.status == SupplierPaymentStatus.VOIDED

    re_clear = tenant_a.client.post(
        f"/api/v1/payments/supplier-payments/{pay_id}/set-cheque-status/",
        {"cheque_status": ChequeStatus.CLEARED},
        format="json",
    )
    assert re_clear.status_code >= 400, re_clear.data
    pay.refresh_from_db()
    assert pay.cheque_status == ChequeStatus.BOUNCED
    assert pay.status == SupplierPaymentStatus.VOIDED
