"""Sprint 2: cess CoA + journal reverse copies party FKs."""

from decimal import Decimal

import pytest

from accounting.models import JournalEntry
from accounting.services import PostingService, seed_chart_of_accounts
from tests.conftest import add_stock, create_draft_invoice, create_draft_purchase, make_customer, make_product, make_supplier

pytestmark = pytest.mark.django_db


def test_bb_000600_sales_complete_posts_output_cess(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    product = make_product(tenant_a.company, sku="CESS-1")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, state="Karnataka")
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18", "cess_rate": "1"}],
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data
    entry = JournalEntry.objects.get(
        company=tenant_a.company, source_type="SALES_INVOICE", source_id=inv["id"], purpose="COMPLETE",
    )
    cess_line = entry.lines.filter(account__code="2270").first()
    assert cess_line is not None
    assert cess_line.credit == Decimal("1.00")


def test_bb_000600_purchase_complete_posts_input_cess(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    supplier = make_supplier(tenant_a.company, gstin="29AAAAA0000A1ZY", state="Karnataka")
    product = make_product(tenant_a.company, sku="PCESS-1")
    draft = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18", "cess_rate": "1"}],
    )
    done = tenant_a.client.post(f"/api/v1/purchases/invoices/{draft['id']}/complete/")
    assert done.status_code == 200, done.data
    entry = JournalEntry.objects.get(
        company=tenant_a.company, source_type="PURCHASE_INVOICE", source_id=draft["id"], purpose="COMPLETE",
    )
    cess_line = entry.lines.filter(account__code="1370").first()
    assert cess_line is not None
    assert cess_line.debit == Decimal("1.00")


def test_bb_000619_620_rcm_moves_cess_and_return_cn_copies_rate(tenant_a):
    from core.services.billing import apply_rcm_memo_after_tax, compute_document_totals
    from purchases.models import PurchaseInvoice, PurchaseItem

    inv = PurchaseInvoice(
        company=tenant_a.company,
        supplier=make_supplier(tenant_a.company, name="RCM Sup"),
        is_reverse_charge=True,
        taxable_total=Decimal("100"),
        cgst_total=Decimal("9"),
        sgst_total=Decimal("9"),
        igst_total=Decimal("0"),
        cess_total=Decimal("1"),
        grand_total=Decimal("119"),
    )
    item = PurchaseItem(
        product=make_product(tenant_a.company, sku="RCM-1"),
        quantity=Decimal("1"),
        unit_price=Decimal("100"),
        gst_rate=Decimal("18"),
        cess_rate=Decimal("1"),
        taxable_amount=Decimal("100"),
        cgst=Decimal("9"),
        sgst=Decimal("9"),
        igst=Decimal("0"),
        cess=Decimal("1"),
        line_total=Decimal("119"),
    )
    apply_rcm_memo_after_tax(inv, [item])
    assert inv.rcm_cess == Decimal("1.00")
    assert inv.cess_total == Decimal("0.00")
    assert item.cess == Decimal("0.00")

    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="RET-CESS")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, state="Karnataka")
    created = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18", "cess_rate": "1"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{created['id']}/complete/").status_code == 200
    ret = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id,
            "sales_invoice": created["id"],
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
        },
        format="json",
    )
    assert ret.status_code == 201, ret.data
    assert tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/").status_code == 200
    from sales.models import SalesCreditNote

    note = SalesCreditNote.objects.get(sales_return_id=ret.data["id"])
    assert note.items.first().cess_rate == Decimal("1.00")
    assert note.cess_total == Decimal("1.00")


def test_bb_000609_reverse_copies_customer_fk(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    product = make_product(tenant_a.company, sku="REV-1")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data
    entry = JournalEntry.objects.get(
        company=tenant_a.company, source_type="SALES_INVOICE", source_id=inv["id"], purpose="COMPLETE",
    )
    reversal = PostingService.reverse(entry, user=tenant_a.owner)
    assert reversal.lines.filter(customer=customer).exists()


def test_bb_000600_sales_cn_posts_output_cess(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    product = make_product(tenant_a.company, sku="CNCESS-1")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, state="Karnataka")
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18", "cess_rate": "1"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    cn = tenant_a.client.post(
        "/api/v1/sales/credit-notes/",
        {
            "customer": customer.id,
            "sales_invoice": inv["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18", "cess_rate": "1"}],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    assert tenant_a.client.post(f"/api/v1/sales/credit-notes/{cn.data['id']}/complete/").status_code == 200
    entry = JournalEntry.objects.get(
        company=tenant_a.company, source_type="SALES_CREDIT_NOTE", source_id=cn.data["id"], purpose="COMPLETE",
    )
    cess_line = entry.lines.filter(account__code="2270").first()
    assert cess_line is not None
    assert cess_line.debit == Decimal("1.00")
