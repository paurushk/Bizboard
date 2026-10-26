"""BB-100 F2 (D-14): a regular company's bills of supply, behind GST_BILL_OF_SUPPLY_RETURNS."""

from decimal import Decimal

import pytest

from accounts.models import Company
from reporting.gst_returns import build_gstr1, build_gstr3b
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.invariant_skip(
        "gl.ar_ties_to_documents",
        reason="report tests build completed invoices through the ORM, so the ledger cannot tie",
    ),
]

PERIOD = "2026-08"


def _flag(company, on=True):
    flags = dict(company.feature_flags or {})
    flags["GST_BILL_OF_SUPPLY_RETURNS"] = on
    company.feature_flags = flags
    company.save(update_fields=["feature_flags"])


def _bill(tenant, nature, *, amount="100", status=None, invoice_type="NON_GST"):
    from sales.models import SalesInvoice
    from sales.services import SalesService

    customer = make_customer(tenant.company, name=f"Buyer {nature}", state="Karnataka")
    inv = SalesInvoice.objects.create(
        company=tenant.company,
        customer=customer,
        invoice_date=f"{PERIOD}-10",
        invoice_type=invoice_type,
        number=f"BOS-{nature}",
        created_by=tenant.owner,
        updated_by=tenant.owner,
    )
    product = make_product(tenant.company, sku=f"BOS-{nature}", gst_rate="0")
    SalesService.set_items(
        inv,
        [
            {
                "product": product,
                "quantity": Decimal("1"),
                "unit_price": Decimal(amount),
                "gst_rate": Decimal("0"),
                "supply_nature": nature,
            }
        ],
        tenant.owner,
    )
    inv.status = status or SalesInvoice.Status.COMPLETED
    inv.save(update_fields=["status"])
    return inv


def test_flag_off_keeps_bills_of_supply_out_of_the_returns(tenant_a):
    assert tenant_a.company.registration_type == Company.RegistrationType.REGULAR
    _bill(tenant_a, "EXEMPT")
    g1 = build_gstr1(tenant_a.company, PERIOD)
    assert Decimal(g1["nil"]["exempt"]) == Decimal("0")
    assert g1["docs"]["invoices_issued"] == 0
    assert g1["register_tie"]["sales"] is False


def test_flag_on_reports_them_in_tables_8_and_13_and_3b(tenant_a):
    _flag(tenant_a.company)
    _bill(tenant_a, "EXEMPT", amount="100")
    _bill(tenant_a, "NON_GST", amount="40")
    g1 = build_gstr1(tenant_a.company, PERIOD)
    assert Decimal(g1["nil"]["exempt"]) == Decimal("100.00")
    assert Decimal(g1["nil"]["non_gst"]) == Decimal("40.00")
    assert g1["docs"]["invoices_issued"] == 2
    assert g1["b2b"] == [] and g1["b2cs"] == []
    assert g1["register_tie"]["sales"] is True, g1["register_tie"]
    g3 = build_gstr3b(tenant_a.company, PERIOD)
    assert Decimal(g3["outward_supplies"]["c_nil_rated_exempt"]["taxable_value"]) == Decimal("100.00")
    assert Decimal(g3["outward_supplies"]["d_non_gst"]["taxable_value"]) == Decimal("40.00")


def test_an_older_taxable_line_on_a_bill_of_supply_is_reported_as_exempt(tenant_a):
    _flag(tenant_a.company)
    _bill(tenant_a, "TAXABLE", amount="70")
    g1 = build_gstr1(tenant_a.company, PERIOD)
    assert Decimal(g1["nil"]["exempt"]) == Decimal("70.00")
    assert g1["b2cs"] == []


def test_a_composition_company_is_not_affected(tenant_a):
    _flag(tenant_a.company)
    Company.objects.filter(pk=tenant_a.company.pk).update(registration_type=Company.RegistrationType.COMPOSITION)
    tenant_a.company.refresh_from_db()
    from core.services.registration_gates import bill_of_supply_rules_on

    assert bill_of_supply_rules_on(tenant_a.company) is False


def _draft_bill(tenant, nature):
    product = make_product(tenant.company, sku=f"BOSC-{nature}", gst_rate="0")
    add_stock(tenant, product, "5")
    customer = make_customer(tenant.company, name=f"Walk {nature}", state="Karnataka")
    line = {"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0", "supply_nature": nature}
    return create_draft_invoice(tenant, customer, [line], invoice_type="NON_GST")


def test_completing_a_bill_of_supply_with_a_taxable_line_is_refused_when_on(tenant_a):
    _flag(tenant_a.company)
    taxable = _draft_bill(tenant_a, "TAXABLE")
    res = tenant_a.client.post(f"/api/v1/sales/invoices/{taxable['id']}/complete/")
    assert res.status_code == 400, res.data
    assert "bill of supply" in str(res.data).lower()
    exempt = _draft_bill(tenant_a, "EXEMPT")
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{exempt['id']}/complete/").status_code == 200


def test_completing_is_unchanged_while_the_flag_is_off(tenant_a):
    taxable = _draft_bill(tenant_a, "TAXABLE")
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{taxable['id']}/complete/").status_code == 200
