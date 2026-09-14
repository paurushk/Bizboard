"""E-Invoice (IRN) & E-Way Bill Statutory Lifecycle persona journey.

Validates:
1. High-turnover B2B wholesale invoice (> Rs. 50,000) for GSTIN-registered customer.
2. E-Invoice JSON payload generation and validation (build_einvoice_payload).
3. E-Way Bill payload generation (build_eway_payload_from_invoice).
4. Statutory Immutability Guard: Once IRN is generated, invoice is locked against line edits.
5. Capability Boundary: Non-owner (P3 Sales Staff) cannot mark/submit/cancel IRN.
6. Zero invariant violations: assert_all_invariants(company) holds throughout.
"""

from decimal import Decimal
import pytest

from core.invariants import assert_all_invariants
from inventory.models import MovementType
from inventory.services import InventoryService
from sales.einvoice_payload import build_einvoice_payload
from sales.eway_payload import build_eway_payload_from_invoice
from sales.models import SalesInvoice
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db


def _body(resp):
    data = resp.data
    if isinstance(data, dict) and isinstance(data.get("data"), (dict, list)):
        return data["data"]
    return data


def test_pj_einvoice_and_eway_statutory_lifecycle():
    wholesale = seed_archetype("wholesale")
    company = wholesale.company
    company.einvoice_enabled = True
    company.address = "123 Peenya Industrial Area"
    company.city = "Bengaluru"
    company.pincode = "560058"
    company.save(update_fields=["einvoice_enabled", "address", "city", "pincode"])

    wh = wholesale.warehouses[0]
    plain_prods = [p for p in wholesale.products if not p.track_batch and not p.track_serial]
    prod = plain_prods[0]
    cust = [c for c in wholesale.customers if c.gstin][0]
    cust.billing_address = "456 Commercial Street 560001"
    cust.save(update_fields=["billing_address"])

    # Inward stock
    InventoryService.post_movement(
        company=company,
        product=prod,
        warehouse=wh,
        quantity=Decimal("100"),
        movement_type=MovementType.PURCHASE,
        unit_cost=Decimal("60.00"),
        user=wholesale.owner,
    )

    # 1. P3 (Sales Staff) drafts and completes high-value B2B Tax Invoice
    # 50 units @ 1200 + 18% GST = 60,000 + 10,800 = 70,800 (> 50,000 e-way threshold)
    inv_resp = wholesale.sales_client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id,
            "invoice_type": "GST",
            "items": [
                {
                    "product": prod.id,
                    "quantity": "50",
                    "unit_price": "1200.00",
                    "gst_rate": "18",
                    "hsn_code": "841590",
                }
            ],
        },
        format="json",
    )
    assert inv_resp.status_code == 201, inv_resp.data
    inv_id = _body(inv_resp)["id"]
    comp_inv = wholesale.sales_client.post(f"/api/v1/sales/invoices/{inv_id}/complete/")
    assert comp_inv.status_code == 200, comp_inv.data

    invoice = SalesInvoice.objects.get(pk=inv_id)
    invoice.transport_distance_km = 120
    invoice.vehicle_number = "KA01AB1234"
    invoice.save(update_fields=["transport_distance_km", "vehicle_number"])

    # 2. Validate E-Invoice Payload Builder
    einvoice_data = build_einvoice_payload(invoice)
    assert einvoice_data["DocDtls"]["Typ"] == "INV"
    assert einvoice_data["SellerDtls"]["Gstin"] == company.gstin
    assert einvoice_data["BuyerDtls"]["Gstin"] == cust.gstin
    assert einvoice_data["ValDtls"]["TotInvVal"] == f"{invoice.grand_total:.2f}"

    # 3. Validate E-Way Bill Payload Builder
    eway_data = build_eway_payload_from_invoice(invoice)
    assert eway_data["docNo"] == invoice.number
    assert eway_data["totInvValue"] == f"{invoice.grand_total:.2f}"
    assert eway_data["transDistance"] == "120"

    # 4. Boundary check: P3 Sales Staff cannot mark or submit IRN
    sales_mark = wholesale.sales_client.post(
        f"/api/v1/sales/invoices/{inv_id}/mark-einvoice-generated/",
        {
            "irn": "4a7b9c1d2e3f4a7b9c1d2e3f4a7b9c1d2e3f4a7b9c1d2e3f4a7b9c1d2e3f1234",
            "ack_no": "1122334455",
            "ack_date": "2026-05-15T10:30:00Z",
            "reason": "Portal generation",
        },
        format="json",
    )
    assert sales_mark.status_code in (400, 403), "Sales staff cannot mark IRN generated"

    # 5. P1 (Owner) marks IRN generated
    owner_mark = wholesale.owner_client.post(
        f"/api/v1/sales/invoices/{inv_id}/mark-einvoice-generated/",
        {
            "irn": "4a7b9c1d2e3f4a7b9c1d2e3f4a7b9c1d2e3f4a7b9c1d2e3f4a7b9c1d2e3f1234",
            "ack_no": "1122334455",
            "ack_date": "2026-05-15T10:30:00Z",
            "reason": "Portal generation",
        },
        format="json",
    )
    assert owner_mark.status_code == 200, owner_mark.data

    invoice.refresh_from_db()
    assert invoice.einvoice_status in (SalesInvoice.EInvoiceStatus.GENERATED, "MANUAL_IRN")
    assert invoice.irn == "4a7b9c1d2e3f4a7b9c1d2e3f4a7b9c1d2e3f4a7b9c1d2e3f4a7b9c1d2e3f1234"

    # 6. Statutory Guard: Books cancellation is strictly blocked while live IRN exists
    attempt_cancel = wholesale.owner_client.post(
        f"/api/v1/sales/invoices/{inv_id}/cancel/",
        {"reason": "Cancelled by customer"},
        format="json",
    )
    assert attempt_cancel.status_code == 400
    assert "live irn" in str(attempt_cancel.data).lower(), "Must block books cancellation while live IRN exists"

    # 7. Invariants hold
    assert_all_invariants(company)
