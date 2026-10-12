"""P3 — tenant export → wipe → restore round-trip keeps the books consistent.

The unbacked-rows guard and the sandbox path are covered in
tests/test_remaining_gates.py; this adds the invariant check: after a
destroy-in-place restore the business rows are back and
`assert_all_invariants` is clean.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.invariants import assert_all_invariants
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def test_export_wipe_restore_preserves_state_and_invariants(tenant_a):
    from accounts.tenant_backup import build_export_payload, restore_destroy_in_place
    from sales.models import SalesInvoice

    company = tenant_a.company
    company.accounting_enabled = True
    company.gstin = "29AAAAA0000A1ZY"
    company.save(update_fields=["accounting_enabled", "gstin"])
    from accounting.services import seed_chart_of_accounts

    seed_chart_of_accounts(company)

    product = make_product(company, gst_rate="18", selling_price="100")
    add_stock(tenant_a, product, "20", unit_cost="60")
    customer = make_customer(company, state="Karnataka", gstin="29BBBBB1111B1Z5")
    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "3", "unit_price": "100.00", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    assert_all_invariants(company)

    invoices_before = SalesInvoice.objects.filter(company=company).count()
    number_before = SalesInvoice.objects.get(company=company).number

    payload = build_export_payload(company)

    # destroy-in-place restore from the payload we just took
    restore_destroy_in_place(
        company=company, payload=payload, owner=tenant_a.owner,
        confirm_destroy_unbacked=True,
    )

    assert SalesInvoice.objects.filter(company=company).count() == invoices_before
    assert SalesInvoice.objects.get(company=company).number == number_before

    # restore recreates rows with fresh pks — re-resolve the product by SKU
    from inventory.models import StockBalance, StockMovement
    from masters.models import Product

    restored_product = Product.objects.get(company=company, sku=product.sku)
    assert StockMovement.objects.filter(company=company, product=restored_product).exists()
    bal = StockBalance.objects.filter(company=company, product=restored_product).first()
    assert bal is not None and bal.on_hand == Decimal("17.000"), bal

    company.refresh_from_db()
    assert_all_invariants(company)


def test_restore_recreates_customers_as_exported_and_reports_ones_that_break_the_customer_rules(tenant_a, caplog):
    import logging

    from accounts.tenant_backup import build_export_payload, restore_destroy_in_place
    from masters.models import Customer

    make_customer(tenant_a.company, name="Old Mismatch", gstin="27AABCU9603R1ZN", state="Karnataka")
    make_customer(tenant_a.company, name="Clean", gstin="29ABCDE1234F1ZW", state="Karnataka")
    payload = build_export_payload(tenant_a.company)
    with caplog.at_level(logging.WARNING, logger="accounts.tenant_backup"):
        restore_destroy_in_place(
            company=tenant_a.company, payload=payload, owner=tenant_a.owner, confirm_destroy_unbacked=True,
        )
    # a restore is exact: it does not apply the form rules, it says what an older backup brought in
    assert Customer.objects.get(company=tenant_a.company, name="Old Mismatch").state == "Karnataka"
    assert "tenant_restore: customer audit" in caplog.text and "state_mismatch" in caplog.text


def test_restore_of_clean_customers_logs_no_customer_audit_warning(tenant_a, caplog):
    import logging

    from accounts.tenant_backup import build_export_payload, restore_destroy_in_place

    make_customer(tenant_a.company, name="Clean", gstin="29ABCDE1234F1ZW", state="Karnataka")
    payload = build_export_payload(tenant_a.company)
    with caplog.at_level(logging.WARNING, logger="accounts.tenant_backup"):
        restore_destroy_in_place(
            company=tenant_a.company, payload=payload, owner=tenant_a.owner, confirm_destroy_unbacked=True,
        )
    assert "tenant_restore: customer audit" not in caplog.text
