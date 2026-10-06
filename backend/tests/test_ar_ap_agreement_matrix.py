"""AR/AP numbers must agree on every surface, with an independent oracle (QOS-0053 / D19).

The CR-101 test only compared the dashboard to the aging report for ONE unpaid purchase, and
the dashboard is *defined* as the aging total, so that comparison cannot fail. This matrix:

* computes the EXPECTED outstanding by hand in each scenario (the oracle), and
* checks that every surface a user can read agrees with it:
    dashboard KPI == aging total == per-document outstanding == oracle,
    and, with books on, the GL control accounts tie to the same figure,
* runs every scenario with books OFF and books ON.

Scenarios: unpaid, part-paid, fully paid, return/credit note on an unpaid invoice, return after
part payment, unallocated advance (must NOT reduce document outstanding), and two parties.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from accounting.services import BooksHealthService, seed_chart_of_accounts
from ledgers.services import LedgerService
from payments.services import PaymentService
from purchases.models import PurchaseInvoice
from reporting.services import ReportService
from sales.models import SalesInvoice
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db

D = Decimal


def _books(tenant, on: bool):
    if not on:
        return
    tenant.company.accounting_enabled = True
    tenant.company.gstin = "29ABCDE1234F1ZW"
    tenant.company.state = "Karnataka"
    tenant.company.save(update_fields=["accounting_enabled", "gstin", "state"])
    seed_chart_of_accounts(tenant.company, tenant.owner)


def _stock_once(t, product):
    from core.exceptions import BusinessRuleError

    try:
        add_stock(t, product, "20")
    except BusinessRuleError:
        pass  # opening stock already recorded for this product in this scenario


def _sale(t, customer, product, amount="1000"):
    _stock_once(t, product)
    inv = create_draft_invoice(
        t, customer,
        [{"product": product.id, "quantity": "1", "unit_price": amount, "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    assert t.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    return SalesInvoice.objects.get(pk=inv["id"])


def _purchase(t, supplier, product, amount="1000"):
    pur = create_draft_purchase(
        t, supplier,
        [{"product": product.id, "quantity": "1", "unit_price": amount, "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    assert t.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    return PurchaseInvoice.objects.get(pk=pur["id"])


def _receipt(t, customer, amount, invoice=None):
    r = PaymentService.create_receipt(company=t.company, customer=customer, amount=D(amount), mode="CASH", user=t.owner)
    if invoice is not None:
        PaymentService.allocate_receipt(receipt=r, sales_invoice=invoice, amount=D(amount), user=t.owner)
    return r


def _supplier_payment(t, supplier, amount, invoice=None):
    p = PaymentService.create_supplier_payment(
        company=t.company, supplier=supplier, amount=D(amount), mode="CASH", user=t.owner,
    )
    if invoice is not None:
        PaymentService.allocate_supplier_payment(payment=p, purchase_invoice=invoice, amount=D(amount), user=t.owner)
    return p


def _sales_cn(t, customer, inv, product, amount):
    cn = t.client.post(
        "/api/v1/sales/credit-notes/",
        {"customer": customer.id, "sales_invoice": inv.id, "reason": "CORRECTION_OF_INVOICE",
         "items": [{"product": product.id, "quantity": "1", "unit_price": amount, "gst_rate": "0"}]},
        format="json",
    )
    assert cn.status_code == 201, cn.data
    done = t.client.post(f"/api/v1/sales/credit-notes/{cn.data['id']}/complete/", {"confirm_price_override": True}, format="json")
    assert done.status_code == 200, done.data


def _purchase_cn(t, supplier, inv, product, amount):
    cn = t.client.post(
        "/api/v1/purchases/credit-notes/",
        {"supplier": supplier.id, "purchase_invoice": inv.id, "reason": "CORRECTION_OF_INVOICE",
         "items": [{"product": product.id, "quantity": "1", "unit_price": amount, "gst_rate": "0"}]},
        format="json",
    )
    assert cn.status_code == 201, cn.data
    done = t.client.post(
        f"/api/v1/purchases/credit-notes/{cn.data['id']}/complete/", {"confirm_price_override": True}, format="json",
    )
    assert done.status_code == 200, done.data


def _check_ar(t, expected: str, *, invoices=()):
    expected = D(expected)
    aging = ReportService._aging_total(ReportService.receivables_aging(t.company))
    dashboard = ReportService.dashboard(t.company)["receivables"]
    docs = sum((LedgerService.sales_invoice_outstanding(SalesInvoice.objects.get(pk=i.pk)) for i in invoices), D("0"))
    assert aging == expected, f"AR aging {aging} != oracle {expected}"
    assert dashboard == expected, f"AR dashboard {dashboard} != oracle {expected}"
    if invoices:
        assert docs == expected, f"sum of invoice outstanding {docs} != oracle {expected}"
    assert ReportService._company_receivables(t.company) == expected
    if t.company.accounting_enabled:
        ar = BooksHealthService.control_balances(t.company)["ar"]
        # 1200 control account, and the customer-tagged subledger, must both tie to the oracle.
        assert ar["gl"] == expected, f"GL 1200 {ar['gl']} != oracle {expected}"
        assert ar["ledger"] == expected, f"tagged customer ledger {ar['ledger']} != oracle {expected}"
        assert ar["healthy"]


def _check_ap(t, expected: str, *, invoices=()):
    expected = D(expected)
    aging = ReportService._aging_total(ReportService.payables_aging(t.company))
    dashboard = ReportService.dashboard(t.company)["payables"]
    docs = sum((LedgerService.purchase_invoice_outstanding(PurchaseInvoice.objects.get(pk=i.pk)) for i in invoices), D("0"))
    assert aging == expected, f"AP aging {aging} != oracle {expected}"
    assert dashboard == expected, f"AP dashboard {dashboard} != oracle {expected}"
    if invoices:
        assert docs == expected, f"sum of purchase outstanding {docs} != oracle {expected}"
    assert ReportService._company_payables(t.company) == expected
    if t.company.accounting_enabled:
        ap = BooksHealthService.control_balances(t.company)["ap"]
        assert ap["gl"] == expected, f"GL 2100 {ap['gl']} != oracle {expected}"
        assert ap["ledger"] == expected, f"tagged supplier ledger {ap['ledger']} != oracle {expected}"
        assert ap["healthy"]


@pytest.fixture(params=[False, True], ids=["books-off", "books-on"])
def t(request, tenant_a):
    _books(tenant_a, request.param)
    return tenant_a


# --- receivables --------------------------------------------------------------------

def test_ar_unpaid(t):
    c, p = make_customer(t.company), make_product(t.company, gst_rate="0")
    inv = _sale(t, c, p, "1000")
    _check_ar(t, "1000", invoices=[inv])


def test_ar_part_paid(t):
    c, p = make_customer(t.company), make_product(t.company, gst_rate="0")
    inv = _sale(t, c, p, "1000")
    _receipt(t, c, "400", invoice=inv)
    _check_ar(t, "600", invoices=[inv])


def test_ar_fully_paid(t):
    c, p = make_customer(t.company), make_product(t.company, gst_rate="0")
    inv = _sale(t, c, p, "1000")
    _receipt(t, c, "1000", invoice=inv)
    _check_ar(t, "0", invoices=[inv])


def test_ar_credit_note_on_unpaid_invoice(t):
    c, p = make_customer(t.company), make_product(t.company, gst_rate="0")
    inv = _sale(t, c, p, "1000")
    _sales_cn(t, c, inv, p, "400")
    _check_ar(t, "600", invoices=[inv])


def test_ar_credit_note_after_part_payment(t):
    c, p = make_customer(t.company), make_product(t.company, gst_rate="0")
    inv = _sale(t, c, p, "1000")
    _receipt(t, c, "300", invoice=inv)
    _sales_cn(t, c, inv, p, "200")
    _check_ar(t, "500", invoices=[inv])  # 1000 - 300 paid - 200 credited


def test_ar_unallocated_advance_does_not_reduce_document_outstanding(t):
    c, p = make_customer(t.company), make_product(t.company, gst_rate="0")
    inv = _sale(t, c, p, "1000")
    _receipt(t, c, "300", invoice=None)  # advance, not allocated to the invoice
    _check_ar(t, "1000", invoices=[inv])


def test_ar_two_customers_sum(t):
    c1, c2 = make_customer(t.company, name="One"), make_customer(t.company, name="Two")
    p = make_product(t.company, gst_rate="0")
    a, b = _sale(t, c1, p, "1000"), _sale(t, c2, p, "250")
    _receipt(t, c1, "100", invoice=a)
    _check_ar(t, "1150", invoices=[a, b])  # 900 + 250


# --- payables -----------------------------------------------------------------------

def test_ap_unpaid(t):
    s, p = make_supplier(t.company), make_product(t.company, gst_rate="0")
    inv = _purchase(t, s, p, "1000")
    _check_ap(t, "1000", invoices=[inv])


def test_ap_part_paid(t):
    s, p = make_supplier(t.company), make_product(t.company, gst_rate="0")
    inv = _purchase(t, s, p, "1000")
    _supplier_payment(t, s, "400", invoice=inv)
    _check_ap(t, "600", invoices=[inv])


def test_ap_fully_paid(t):
    s, p = make_supplier(t.company), make_product(t.company, gst_rate="0")
    inv = _purchase(t, s, p, "1000")
    _supplier_payment(t, s, "1000", invoice=inv)
    _check_ap(t, "0", invoices=[inv])


def test_ap_debit_note_on_unpaid_bill(t):
    s, p = make_supplier(t.company), make_product(t.company, gst_rate="0")
    inv = _purchase(t, s, p, "1000")
    _purchase_cn(t, s, inv, p, "400")
    _check_ap(t, "600", invoices=[inv])


def test_ap_debit_note_after_part_payment(t):
    s, p = make_supplier(t.company), make_product(t.company, gst_rate="0")
    inv = _purchase(t, s, p, "1000")
    _supplier_payment(t, s, "300", invoice=inv)
    _purchase_cn(t, s, inv, p, "200")
    _check_ap(t, "500", invoices=[inv])


def test_ap_unallocated_advance_does_not_reduce_document_outstanding(t):
    s, p = make_supplier(t.company), make_product(t.company, gst_rate="0")
    inv = _purchase(t, s, p, "1000")
    _supplier_payment(t, s, "300", invoice=None)
    _check_ap(t, "1000", invoices=[inv])


def test_ar_and_ap_are_independent(t):
    """A sale and a purchase in the same company must not leak into each other's figure."""
    c, s = make_customer(t.company), make_supplier(t.company)
    p = make_product(t.company, gst_rate="0")
    sale = _sale(t, c, p, "700")
    buy = _purchase(t, s, p, "300")
    _check_ar(t, "700", invoices=[sale])
    _check_ap(t, "300", invoices=[buy])
