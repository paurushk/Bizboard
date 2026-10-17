"""R1 (H-03, DEC-3): goods shipped on a completed challan count toward the credit limit.

Before the fix, completing a challan turned its order CONVERTED and the exposure check dropped
it, so goods that had left the godown on credit counted as nothing until they were invoiced.
"""

from decimal import Decimal

import pytest

from accounts.models import CompanyUser
from core.exceptions import BusinessRuleError
from sales.models import DeliveryChallan, SalesInvoice, SalesOrder, SalesOrderItem
from sales.notes_services import SalesNotesService
from sales.order_gates import apply_order_gates, sales_order_exposure
from tests.conftest import add_stock, make_customer, make_product

pytestmark = pytest.mark.django_db


def _gates_on(company, on=True):
    flags = dict(company.feature_flags or {})
    flags["ENABLE_ORDER_GATES"] = on
    company.feature_flags = flags
    company.save(update_fields=["feature_flags"])


def _invoice(tenant, customer, total, status=SalesInvoice.Status.COMPLETED):
    return SalesInvoice.objects.create(
        company=tenant.company, customer=customer, grand_total=Decimal(total),
        status=status, created_by=tenant.owner,
    )


def _challan(tenant, customer, total, *, order=None, status=DeliveryChallan.Status.COMPLETED, invoice=None):
    return DeliveryChallan.objects.create(
        company=tenant.company, customer=customer, grand_total=Decimal(total),
        status=status, sales_order=order, converted_invoice=invoice, created_by=tenant.owner,
    )


def _new_order(tenant, customer, total):
    order = SalesOrder.objects.create(
        company=tenant.company, customer=customer, grand_total=Decimal(total), created_by=tenant.owner,
    )
    product = make_product(tenant.company, sku=f"CR-{order.pk}", purchase_price="1", selling_price="100")
    item = SalesOrderItem.objects.create(
        company=tenant.company, sales_order=order, product=product,
        quantity=Decimal("1"), unit_price=Decimal(total),
    )
    return order, item


@pytest.fixture
def gated(tenant_a):
    _gates_on(tenant_a.company)
    return tenant_a


def test_tc_wp3_01_uninvoiced_completed_challan_counts(gated):
    customer = make_customer(gated.company, credit_limit=Decimal("1000"))
    _invoice(gated, customer, "400")
    _challan(gated, customer, "500")
    order, item = _new_order(gated, customer, "200")
    assert sales_order_exposure(gated.company, customer, order) == Decimal("1100")
    with pytest.raises(BusinessRuleError, match="Credit limit"):
        apply_order_gates(order, [item])


def test_tc_wp3_02_owner_can_override_with_a_reason(gated):
    customer = make_customer(gated.company, credit_limit=Decimal("1000"))
    _invoice(gated, customer, "400")
    _challan(gated, customer, "500")
    order, item = _new_order(gated, customer, "200")
    owner = CompanyUser.objects.get(company=gated.company, user=gated.owner)
    apply_order_gates(order, [item], override_reason="Valued customer", acting_user=owner)
    assert order.credit_override_reason == "Valued customer"


def test_tc_wp3_03_staff_cannot_override(gated):
    customer = make_customer(gated.company, credit_limit=Decimal("1000"))
    _challan(gated, customer, "900")
    order, item = _new_order(gated, customer, "200")
    staff = CompanyUser.objects.get(company=gated.company, user=gated.staff)
    with pytest.raises(BusinessRuleError):
        apply_order_gates(order, [item], override_reason="please", acting_user=staff)


def test_tc_wp3_04_challan_with_a_counted_invoice_is_not_counted_twice(gated):
    customer = make_customer(gated.company, credit_limit=Decimal("10000"))
    invoice = _invoice(gated, customer, "500")  # completed: the ledger already counts it
    _challan(gated, customer, "500", invoice=invoice)
    order, _item = _new_order(gated, customer, "200")
    assert sales_order_exposure(gated.company, customer, order) == Decimal("700")


def test_tc_wp3_04b_challan_whose_invoice_is_still_a_draft_counts_at_the_challan_total(gated):
    customer = make_customer(gated.company, credit_limit=Decimal("10000"))
    draft = _invoice(gated, customer, "500", status=SalesInvoice.Status.DRAFT)
    _challan(gated, customer, "500", invoice=draft)
    order, _item = _new_order(gated, customer, "200")
    assert sales_order_exposure(gated.company, customer, order) == Decimal("700")


def test_tc_wp3_05_partly_processed_order_stays_in_the_picture(gated):
    customer = make_customer(gated.company, credit_limit=Decimal("10000"))
    partly = SalesOrder.objects.create(
        company=gated.company, customer=customer, grand_total=Decimal("1000"),
        status=SalesOrder.Status.PARTIALLY_CONVERTED, created_by=gated.owner,
    )
    # One completed challan of 400 belongs to that order: counted once, through the order.
    _challan(gated, customer, "400", order=partly)
    order, _item = _new_order(gated, customer, "200")
    assert sales_order_exposure(gated.company, customer, order) == Decimal("1200")


def test_tc_wp3_06_no_limit_never_blocks(gated):
    customer = make_customer(gated.company, credit_limit=Decimal("0"))
    _challan(gated, customer, "9000000")
    order, item = _new_order(gated, customer, "200")
    assert apply_order_gates(order, [item]) is not None


def test_tc_wp3_07_gates_off_changes_nothing(tenant_a):
    _gates_on(tenant_a.company, on=False)
    customer = make_customer(tenant_a.company, credit_limit=Decimal("100"))
    _challan(tenant_a, customer, "900")
    order, item = _new_order(tenant_a, customer, "200")
    assert apply_order_gates(order, [item]) == []


def test_tc_wp3_08_exactly_at_the_limit_is_allowed(gated):
    customer = make_customer(gated.company, credit_limit=Decimal("1000"))
    _challan(gated, customer, "800")
    order, item = _new_order(gated, customer, "200")
    assert sales_order_exposure(gated.company, customer, order) == Decimal("1000")
    apply_order_gates(order, [item])  # not "over"
    _challan(gated, customer, "1")
    with pytest.raises(BusinessRuleError, match="Credit limit"):
        apply_order_gates(order, [item])


def test_tc_wp3_09_cancelled_and_draft_challans_do_not_count(gated):
    customer = make_customer(gated.company, credit_limit=Decimal("1000"))
    _challan(gated, customer, "900", status=DeliveryChallan.Status.CANCELLED)
    _challan(gated, customer, "900", status=DeliveryChallan.Status.DRAFT)
    order, _item = _new_order(gated, customer, "200")
    assert sales_order_exposure(gated.company, customer, order) == Decimal("200")


def test_tc_wp3_10_another_customers_challan_never_counts(gated):
    customer = make_customer(gated.company, credit_limit=Decimal("1000"))
    other = make_customer(gated.company, name="Other Co")
    _challan(gated, other, "900")
    order, _item = _new_order(gated, customer, "200")
    assert sales_order_exposure(gated.company, customer, order) == Decimal("200")


def test_tc_wp3_11_another_companys_challan_never_counts(tenant_a, tenant_b):
    _gates_on(tenant_a.company)
    customer = make_customer(tenant_a.company, credit_limit=Decimal("1000"))
    foreign_customer = make_customer(tenant_b.company)
    _challan(tenant_b, foreign_customer, "900")
    order, _item = _new_order(tenant_a, customer, "200")
    assert sales_order_exposure(tenant_a.company, customer, order) == Decimal("200")


def test_tc_wp3_12_confirm_is_blocked_through_the_service(gated):
    """End to end through confirm: a draft order cannot be confirmed over the limit."""
    customer = make_customer(gated.company, credit_limit=Decimal("1000"))
    product = make_product(gated.company)
    add_stock(gated, product, "10")
    _challan(gated, customer, "950")
    resp = gated.client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id, "invoice_type": "NON_GST",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    order = SalesOrder.objects.get(pk=resp.data["id"])
    with pytest.raises(BusinessRuleError, match="Credit limit"):
        SalesNotesService.confirm_sales_order(order, gated.owner)


def test_tc_wp3_affected_customer_report_lists_only_uncovered_shipments(gated):
    """The pre-enable report names customers whose exposure rises, and skips covered challans."""
    from sales.management.commands.list_credit_exposure_changes import affected_customers

    shipped = make_customer(gated.company, name="Shipped Not Billed")
    billed = make_customer(gated.company, name="Billed Already")
    _challan(gated, shipped, "700")
    _challan(gated, billed, "300", invoice=_invoice(gated, billed, "300"))
    _challan(gated, shipped, "50", status=DeliveryChallan.Status.DRAFT)

    rows = affected_customers(gated.company.pk)

    assert [(r[1].name, r[2]) for r in rows] == [("Shipped Not Billed", Decimal("700"))]
