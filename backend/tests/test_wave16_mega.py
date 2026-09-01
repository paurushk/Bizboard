"""Wave 16 smoke tests — GL-first outstanding, GSP factories, 2B claimable flag."""

from decimal import Decimal

import pytest

from accounting.services import seed_chart_of_accounts
from core.services.gsp_adapters import (
    SandboxIrpAdapter,
    get_gstr_filing_adapter,
    get_irp_adapter,
)
from inventory.models import InventoryCostLayer, MovementType
from inventory.services import InventoryService
from ledgers.services import LedgerService
from reporting.gstr2b import build_cmp08, claimable_itc_from_2b
from reporting.models import Gstr2bIngest
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def test_gl_first_customer_outstanding_uses_journals(tenant_a):
    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(company, tenant_a.owner)
    product = make_product(company)
    add_stock(tenant_a, product, "10")
    customer = make_customer(company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    outstanding = LedgerService.customer_outstanding(company, customer)
    assert outstanding == Decimal("100.00")


def test_fifo_creates_cost_layer_on_purchase_movement(tenant_a):
    company = tenant_a.company
    company.inventory_valuation_method = "FIFO"
    company.save(update_fields=["inventory_valuation_method"])
    product = make_product(company)
    wh = InventoryService.default_warehouse(company)
    move = InventoryService.post_movement(
        company=company,
        product=product,
        warehouse=wh,
        movement_type=MovementType.PURCHASE,
        quantity=Decimal("5"),
        unit_cost=Decimal("12.50"),
        user=tenant_a.owner,
    )
    layer = InventoryCostLayer.objects.filter(company=company, product=product).first()
    assert layer is not None
    assert layer.qty_remaining == Decimal("5")
    assert layer.unit_cost == Decimal("12.50")
    assert layer.source_movement_id == move.id


def test_gsp_factory_defaults_to_sandbox(tenant_a):
    adapter = get_irp_adapter(tenant_a.company)
    assert isinstance(adapter, SandboxIrpAdapter)
    result = adapter.submit({"DocDtls": {"No": "1"}})
    assert result.irn
    filing = get_gstr_filing_adapter(tenant_a.company)
    with pytest.raises(Exception):
        filing.fetch_gstr2b("2026-04")


def test_claimable_itc_from_matched_2b(tenant_a):
    company = tenant_a.company
    Gstr2bIngest.objects.create(
        company=company,
        period="2026-04",
        supplier_gstin="29AAAAA0000A1ZY",
        invoice_number="PI-1",
        taxable_value=Decimal("100"),
        cgst=Decimal("9"),
        sgst=Decimal("9"),
        match_status=Gstr2bIngest.MatchStatus.MATCHED,
        itc_eligibility=Gstr2bIngest.ItcEligibility.CLAIMABLE,
    )
    itc = claimable_itc_from_2b(company, "2026-04")
    assert itc["claimable"] is True
    assert itc["cgst"] == Decimal("9")
    cmp08 = build_cmp08(company, "2026-04")
    assert cmp08["aid_kind"] == "composition_cmp08"
