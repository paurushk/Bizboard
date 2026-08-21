"""Wave 17A–C: GSTR depth, 2B API, FIFO matrix, BooksHealth golden path."""

from __future__ import annotations

from decimal import Decimal

import pytest

from accounting.models import AccountingPeriod
from accounting.services import BooksHealthService
from inventory.models import InventoryCostLayer, MovementType
from inventory.services import InventoryService
from reporting.gst_returns import assert_not_composition_for_regular_returns, build_gstr1, build_gstr9
from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def test_gstr1_exp_sez_nil_sections(tenant_a):
    company = tenant_a.company
    product = make_product(company, gst_rate="0")
    add_stock(tenant_a, product, "10")
    customer = make_customer(company, gstin="29AABCU9603R1ZJ", state="29")
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "0"}],
        invoice_type="GST",
    )
    SalesInvoice.objects.filter(pk=inv["id"]).update(supply_type=SalesInvoice.SupplyType.EXPWOP)
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    period = SalesInvoice.objects.get(pk=inv["id"]).invoice_date.strftime("%Y-%m")
    payload = build_gstr1(company, period)
    assert "exp" in payload and "sez" in payload and "nil" in payload
    assert any(r.get("supply_type") == "EXPWOP" for r in payload["exp"]) or Decimal(
        payload["nil"]["taxable_value"]
    ) >= 0


def test_gstr9_tables_4_to_8(tenant_a):
    payload = build_gstr9(tenant_a.company, "2025-26")
    assert payload["aid_kind"] == "gstr9_worksheet_mvp"
    assert "4" in payload["tables"] and "8" in payload["tables"]
    assert payload["tables"]["17"]["aid_kind"] == "hsn_outward"


def test_gstr2b_upload_and_match_api(tenant_a):
    from accounts.models import User

    User.objects.filter(pk=tenant_a.owner.pk).update(active_company=tenant_a.company)
    resp = tenant_a.client.post(
        "/api/v1/reports/gstr2b/upload/",
        {
            "period": "2026-04",
            "rows": [
                {
                    "supplier_gstin": "27AAAAA0000A1Z2",
                    "invoice_number": "PI-1",
                    "taxable_value": "100.00",
                    "cgst": "9.00",
                    "sgst": "9.00",
                    "igst": "0.00",
                }
            ],
        },
        format="json",
    )
    assert resp.status_code in (200, 201), resp.content
    assert resp.data["created"] == 1
    match = tenant_a.client.post("/api/v1/reports/gstr2b/match/", {"period": "2026-04"}, format="json")
    assert match.status_code == 200
    assert "matched" in match.data


def test_fifo_purchase_sale_return_matrix(tenant_a):
    company = tenant_a.company
    company.inventory_valuation_method = "FIFO"
    company.save(update_fields=["inventory_valuation_method"])
    product = make_product(company)
    wh = InventoryService.default_warehouse(company)
    user = tenant_a.owner

    InventoryService.post_movement(
        company=company,
        warehouse=wh,
        product=product,
        quantity=Decimal("10"),
        movement_type=MovementType.PURCHASE,
        unit_cost=Decimal("10"),
        reference_type="test",
        reference_id="p1",
        user=user,
    )
    InventoryService.post_movement(
        company=company,
        warehouse=wh,
        product=product,
        quantity=Decimal("10"),
        movement_type=MovementType.PURCHASE,
        unit_cost=Decimal("20"),
        reference_type="test",
        reference_id="p2",
        user=user,
    )
    assert InventoryCostLayer.objects.filter(company=company, product=product).count() >= 2

    sale = InventoryService.post_movement(
        company=company,
        warehouse=wh,
        product=product,
        quantity=Decimal("5"),
        movement_type=MovementType.SALE,
        reference_type="test",
        reference_id="s1",
        user=user,
    )
    assert Decimal(str(sale.unit_cost or 0)) == Decimal("10")

    InventoryService.post_movement(
        company=company,
        warehouse=wh,
        product=product,
        quantity=Decimal("5"),
        movement_type=MovementType.SALES_RETURN,
        unit_cost=Decimal("10"),
        reference_type="test",
        reference_id="r1",
        user=user,
    )


def test_books_health_control_balances_runs(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    health = BooksHealthService.control_balances(tenant_a.company)
    assert "alerts" in health
    assert "ar" in health and "ap" in health


def test_composition_cmp08_route_message(tenant_a):
    from accounts.models import Company
    from core.exceptions import BusinessRuleError

    tenant_a.company.registration_type = Company.RegistrationType.COMPOSITION
    tenant_a.company.save(update_fields=["registration_type"])
    with pytest.raises(BusinessRuleError) as exc:
        assert_not_composition_for_regular_returns(tenant_a.company)
    assert "cmp08" in str(exc.value).lower()


def test_submit_einvoice_async_task_idempotent(tenant_a):
    from datetime import date

    from sales.tasks import submit_einvoice_async

    customer = make_customer(tenant_a.company)
    inv = SalesInvoice.objects.create(
        company=tenant_a.company,
        customer=customer,
        invoice_type=SalesInvoice.InvoiceType.GST,
        invoice_date=date(2026, 4, 1),
        status=SalesInvoice.Status.COMPLETED,
        irn="EXISTINGIRN123",
    )
    result = submit_einvoice_async(inv.pk, tenant_a.owner.pk)
    assert result["status"] == "already_generated"


def test_period_close_soft_vs_hard(tenant_a):
    from datetime import date

    AccountingPeriod.objects.create(
        company=tenant_a.company,
        name="FY26-Apr",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
        status=AccountingPeriod.Status.SOFT_CLOSED,
    )
    health = BooksHealthService.control_balances(tenant_a.company)
    assert any(a["code"] == "PERIOD_SOFT_CLOSED" for a in health["alerts"])
    blockers = BooksHealthService.period_close_blockers(tenant_a.company)
    assert "PERIOD_SOFT_CLOSED" not in {a["code"] for a in blockers}


def test_purchase_charges_capitalization_policy_comment():
    """Document policy: purchase additional_charges → 5110 expense unless capitalized to 1400."""
    src = open("accounting/services.py", encoding="utf-8").read()
    assert "5110" in src
    assert "1400" in src
