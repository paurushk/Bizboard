from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.exceptions import BusinessRuleError
from planwave.finish import (
    classify_purchase_bill,
    commit_bulk_invoices,
    godown_dashboard,
    hold_pos_cart,
    itc_summary,
    overdue_report,
    pharmacy_register_csv,
    release_expired_pos_holds,
    restore_master,
    score_2b_rows,
    section_50_csv,
)
from planwave.models import PharmacyDispense
from planwave.services import assert_gstin_override, assert_pharmacy_sale


def test_pharmacy_register_lists_the_dispense(tenant_a):
    from masters.models import Product

    product = Product.objects.create(
        company=tenant_a.company, name="Cough", sku="COUGH", drug_schedule="H",
        selling_price=Decimal("10"), purchase_price=Decimal("5"),
    )
    tenant_a.company.feature_flags = {"pharmacy_enabled": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    assert_pharmacy_sale(
        company=tenant_a.company, product=product, patient_name="Asha",
        prescriber_name="Dr Rao", prescriber_registration="KA1", quantity=1,
    )
    body = pharmacy_register_csv(tenant_a.company)
    assert "Asha" in body
    assert "Cough" in body
    assert PharmacyDispense.objects.filter(company=tenant_a.company).count() == 1


def test_section_50_csv_posts_no_journal():
    from datetime import date

    body = section_50_csv(tax="1000", excess_itc="0", days=365, on=date(2026, 4, 1))
    assert "journal_posted" in body
    assert "False" in body


def test_unconfirmed_bill_is_excluded_from_claimable_itc(tenant_a):
    from purchases.models import PurchaseInvoice
    from tests.conftest import make_supplier

    supplier = make_supplier(tenant_a.company, name="ITC Co")
    bill = PurchaseInvoice.objects.create(company=tenant_a.company, supplier=supplier)
    classify_purchase_bill(bill)
    summary = itc_summary(tenant_a.company)
    assert summary["claimable"] == 0
    assert summary["excluded"] == 1


def test_2b_blocked_invoice_is_not_eligible():
    rows = score_2b_rows([{
        "books_gstin": "29AAAAA0000A1Z5",
        "return_gstin": "29AAAAA0000A1Z5",
        "books_tax": "18",
        "return_tax": "18",
        "blocked_credit": True,
    }])
    assert rows[0]["eligible"] is False
    assert rows[0]["band"] == "BLOCKED"


def test_overdue_report_suggests_a_provision(tenant_a):
    from sales.models import SalesInvoice
    from tests.conftest import make_customer

    customer = make_customer(tenant_a.company, name="Late")
    SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, status=SalesInvoice.Status.COMPLETED,
        due_date=timezone.localdate() - timedelta(days=100), grand_total=Decimal("1000"),
    )
    rows = overdue_report(tenant_a.company)
    assert rows
    assert Decimal(rows[0]["provision"]) > 0


def test_godown_dashboard_lists_the_default_warehouse(tenant_a):
    from inventory.models import Warehouse

    Warehouse.objects.create(company=tenant_a.company, name="Main", code="MAIN")
    rows = godown_dashboard(tenant_a.company)
    assert rows
    assert rows[0]["name"] == "Main"
    assert "on_hand" in rows[0]


def test_bulk_commit_rejects_only_the_bad_invoice(tenant_a):
    from tests.conftest import make_customer, make_product

    make_customer(tenant_a.company, name="Ravi Kumar")
    make_product(tenant_a.company, sku="WID-9")
    text = (
        "invoice_ref,customer,sku,quantity,rate\n"
        "A1,Ravi Kumar,WID-9,1,100\n"
        "B1,Nobody,WID-9,1,100\n"
    )
    result = commit_bulk_invoices(tenant_a.company, text, tenant_a.owner)
    assert len(result["created"]) == 1
    assert result["rejected"]


def test_restore_brings_a_customer_back(tenant_a):
    from masters.models import Customer
    from tests.conftest import make_customer

    customer = make_customer(tenant_a.company, name="Gone")
    customer.is_deleted = True
    customer.save(update_fields=["is_deleted"])
    restore_master(tenant_a.company, "customer", customer.pk, tenant_a.owner)
    assert Customer.objects.filter(pk=customer.pk).exists()


def test_pos_hold_expires_and_the_row_remains(tenant_a):
    row = hold_pos_cart(tenant_a.company, label="Counter", payload={"lines": 1}, hours=0)
    row.expires_at = timezone.now() - timedelta(minutes=1)
    row.save(update_fields=["expires_at"])
    assert release_expired_pos_holds(tenant_a.company) == 1
    row.refresh_from_db()
    assert row.released_at is not None


def test_gstin_override_is_audited(tenant_a):
    from core.models import AuditEvent

    assert_gstin_override(tenant_a.company, tenant_a.owner, "CA confirmed the old bill.")
    assert AuditEvent.objects.filter(company=tenant_a.company, description__icontains="Cancelled-GSTIN").exists()


def test_sales_staff_cannot_release_a_gstin_hold(tenant_a):
    with pytest.raises(BusinessRuleError):
        assert_gstin_override(tenant_a.company, tenant_a.staff, "please")


def test_print_bridge_falls_back_without_a_printer(tenant_a):
    resp = tenant_a.client.post("/api/v1/plan/print/", {}, format="json")
    assert resp.status_code == 200
    assert resp.data["fallback"] == "pdf"
    assert resp.data["delivered"] is False
