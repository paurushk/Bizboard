"""ACT-08 credit exposure and ACT-09 challan stock are posted once."""

from decimal import Decimal

from inventory.models import MovementType, StockMovement
from inventory.services import InventoryService
from ledgers.services import LedgerService
from masters.models import Customer
from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

import pytest

pytestmark = pytest.mark.django_db


def test_credit_limit_exposure_matches_ledger_service(tenant_a):
    """The complete() credit check already calls LedgerService. Keep that formula."""
    product = make_product(tenant_a.company, sku="ACT08", gst_rate="0")
    add_stock(tenant_a, product, "20")
    customer = make_customer(tenant_a.company, name="Limit Buyer")
    first = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    opened = tenant_a.client.post(f"/api/v1/sales/invoices/{first['id']}/complete/")
    assert opened.status_code == 200, opened.data

    exposure = LedgerService.customer_exposure_for_credit_limit(tenant_a.company, customer)
    outstanding = LedgerService.customer_outstanding(tenant_a.company, customer)
    assert exposure == outstanding
    assert exposure == Decimal("100.00")

    Customer.objects.filter(pk=customer.pk).update(credit_limit=Decimal("100.00"))
    second = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "50", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    blocked = tenant_a.client.post(f"/api/v1/sales/invoices/{second['id']}/complete/")
    assert blocked.status_code == 400, blocked.data
    details = blocked.data["error"]["details"]
    assert Decimal(str(details["current_exposure"])) == exposure
    assert SalesInvoice.objects.get(pk=second["id"]).status == "DRAFT"


def test_credit_exposure_on_the_customer_subtracts_an_unallocated_advance(tenant_a):
    """The invoice reads credit_exposure, which is outstanding minus advances."""
    from payments.services import PaymentService

    product = make_product(tenant_a.company, sku="ACT08B", gst_rate="0")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="Advance Buyer")
    opened = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{opened['id']}/complete/")
    assert done.status_code == 200, done.data
    PaymentService.create_receipt(
        company=tenant_a.company,
        customer=customer,
        amount=Decimal("40"),
        mode="CASH",
    )
    exposure = LedgerService.customer_exposure_for_credit_limit(tenant_a.company, customer)
    outstanding = LedgerService.customer_outstanding(tenant_a.company, customer)
    assert outstanding == Decimal("100.00")
    assert exposure == Decimal("60.00")
    detail = tenant_a.client.get(f"/api/v1/customers/{customer.id}/")
    assert detail.status_code == 200, detail.data
    body = detail.data
    raw = body.get("credit_exposure", body.get("creditExposure"))
    assert raw is not None, sorted(body.keys())
    assert Decimal(str(raw)) == exposure
    listed = tenant_a.client.get("/api/v1/customers/")
    assert listed.status_code == 200, listed.data
    rows = listed.data.get("results", listed.data)
    row = next(item for item in rows if item["id"] == customer.id)
    listed_raw = row.get("credit_exposure", row.get("creditExposure"))
    assert Decimal(str(listed_raw)) == exposure


def test_credit_exposure_list_keeps_two_receipts_of_the_same_amount(tenant_a):
    """Equal receipt amounts must not collapse into one row on the customer list."""
    from payments.services import PaymentService

    product = make_product(tenant_a.company, sku="ACT08C", gst_rate="0")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="Two Advances")
    opened = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{opened['id']}/complete/")
    assert done.status_code == 200, done.data
    invoice = SalesInvoice.objects.get(pk=opened["id"])
    paid = PaymentService.create_receipt(
        company=tenant_a.company, customer=customer, amount=Decimal("40"), mode="CASH",
    )
    PaymentService.allocate_receipt(receipt=paid, sales_invoice=invoice, amount=Decimal("40"))
    PaymentService.create_receipt(
        company=tenant_a.company, customer=customer, amount=Decimal("40"), mode="CASH",
    )
    exposure = LedgerService.customer_exposure_for_credit_limit(tenant_a.company, customer)
    assert exposure == Decimal("20.00")
    listed = tenant_a.client.get("/api/v1/customers/")
    rows = listed.data.get("results", listed.data)
    row = next(item for item in rows if item["id"] == customer.id)
    listed_raw = row.get("credit_exposure", row.get("creditExposure"))
    assert Decimal(str(listed_raw)) == exposure


def test_credit_exposure_list_matches_detail_when_books_are_on(tenant_a):
    """Books use the GL advance, not a second subtraction of the document receipt."""
    from payments.services import PaymentService

    product = make_product(tenant_a.company, sku="ACT08D", gst_rate="0")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="Books Buyer")
    opened = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{opened['id']}/complete/")
    assert done.status_code == 200, done.data
    PaymentService.create_receipt(
        company=tenant_a.company, customer=customer, amount=Decimal("40"), mode="CASH",
    )
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    exposure = LedgerService.customer_exposure_for_credit_limit(tenant_a.company, customer)
    listed = tenant_a.client.get("/api/v1/customers/")
    rows = listed.data.get("results", listed.data)
    row = next(item for item in rows if item["id"] == customer.id)
    listed_raw = row.get("credit_exposure", row.get("creditExposure"))
    assert Decimal(str(listed_raw)) == exposure


def test_challan_then_invoice_drops_stock_once(tenant_a):
    """Stock posted on the challan is not issued again when the invoice completes."""
    company = tenant_a.company
    company.stock_on_delivery_challan = True
    company.save(update_fields=["stock_on_delivery_challan"])
    product = make_product(company, sku="ACT09", gst_rate="0")
    add_stock(tenant_a, product, "20", unit_cost="40")
    customer = make_customer(company, name="Challan Buyer")
    assert InventoryService.available_quantity(company=company, product=product) == Decimal("20.000")

    challan = tenant_a.client.post(
        "/api/v1/sales/delivery-challans/",
        {
            "customer": customer.id,
            "items": [{
                "product": product.id,
                "quantity": "4",
                "unit_price": "100.00",
                "gst_rate": "0",
            }],
        },
        format="json",
    )
    assert challan.status_code == 201, challan.data
    done_challan = tenant_a.client.post(
        f"/api/v1/sales/delivery-challans/{challan.data['id']}/complete/",
    )
    assert done_challan.status_code == 200, done_challan.data
    assert InventoryService.available_quantity(company=company, product=product) == Decimal("16.000")

    converted = tenant_a.client.post(
        f"/api/v1/sales/delivery-challans/{challan.data['id']}/convert/",
    )
    assert converted.status_code == 200, converted.data
    invoice_id = converted.data["id"]
    completed = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice_id}/complete/")
    assert completed.status_code == 200, completed.data
    assert InventoryService.available_quantity(company=company, product=product) == Decimal("16.000")
    assert not StockMovement.objects.filter(
        company=company,
        movement_type=MovementType.SALE,
        reference_type="sales_invoice",
        reference_id=str(invoice_id),
    ).exists()


def _challan_ready(tenant, product, customer, qty):
    challan = tenant.client.post(
        "/api/v1/sales/delivery-challans/",
        {
            "customer": customer.id,
            "items": [{
                "product": product.id,
                "quantity": str(qty),
                "unit_price": "100.00",
                "gst_rate": "0",
            }],
        },
        format="json",
    )
    assert challan.status_code == 201, challan.data
    done = tenant.client.post(f"/api/v1/sales/delivery-challans/{challan.data['id']}/complete/")
    assert done.status_code == 200, done.data
    return challan.data["id"]


def test_partial_and_over_challan_invoice_does_not_drop_stock_again(tenant_a):
    company = tenant_a.company
    company.stock_on_delivery_challan = True
    company.save(update_fields=["stock_on_delivery_challan"])
    product = make_product(company, sku="ACT09P", gst_rate="0")
    add_stock(tenant_a, product, "20", unit_cost="40")
    customer = make_customer(company, name="Partial Challan")
    challan_id = _challan_ready(tenant_a, product, customer, "4")
    assert InventoryService.available_quantity(company=company, product=product) == Decimal("16.000")

    converted = tenant_a.client.post(f"/api/v1/sales/delivery-challans/{challan_id}/convert/")
    assert converted.status_code == 200, converted.data
    invoice_id = converted.data["id"]
    from sales.models import SalesItem

    SalesItem.objects.filter(invoice_id=invoice_id).update(quantity=Decimal("2"))
    completed = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice_id}/complete/")
    assert completed.status_code == 400, completed.data
    assert InventoryService.available_quantity(company=company, product=product) == Decimal("16.000")

    product_over = make_product(company, sku="ACT09O", gst_rate="0")
    add_stock(tenant_a, product_over, "20", unit_cost="40")
    challan_over = _challan_ready(tenant_a, product_over, customer, "4")
    converted_over = tenant_a.client.post(f"/api/v1/sales/delivery-challans/{challan_over}/convert/")
    assert converted_over.status_code == 200, converted_over.data
    over_id = converted_over.data["id"]
    SalesItem.objects.filter(invoice_id=over_id).update(quantity=Decimal("10"))
    over_done = tenant_a.client.post(f"/api/v1/sales/invoices/{over_id}/complete/")
    assert over_done.status_code == 400, over_done.data
    assert InventoryService.available_quantity(company=company, product=product_over) == Decimal("16.000")


def test_two_challans_on_one_invoice_drop_stock_once(tenant_a):
    from sales.models import DeliveryChallan

    company = tenant_a.company
    company.stock_on_delivery_challan = True
    company.save(update_fields=["stock_on_delivery_challan"])
    product = make_product(company, sku="ACT09M", gst_rate="0")
    add_stock(tenant_a, product, "20", unit_cost="40")
    customer = make_customer(company, name="Multi Challan")
    first = _challan_ready(tenant_a, product, customer, "3")
    second = _challan_ready(tenant_a, product, customer, "2")
    assert InventoryService.available_quantity(company=company, product=product) == Decimal("15.000")

    draft = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "5", "unit_price": "100", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    DeliveryChallan.objects.filter(pk__in=[first, second]).update(converted_invoice_id=draft["id"])
    completed = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert completed.status_code == 200, completed.data
    assert InventoryService.available_quantity(company=company, product=product) == Decimal("15.000")
    assert not StockMovement.objects.filter(
        company=company,
        movement_type=MovementType.SALE,
        reference_type="sales_invoice",
        reference_id=str(draft["id"]),
    ).exists()
